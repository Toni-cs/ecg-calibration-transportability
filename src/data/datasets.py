"""Dataset module: consumes the npy + metadata CSV output of preprocess_cinc2021.py.

Key facts (verified against scripts/preprocess_cinc2021.py source):
- outputs ``metadata_single_label.csv`` with fixed columns
  ``id, label, npy_path, fs, original_len``; npy_path is a filename (relative to the data dir)
- npy shape is ``(n_leads=12, seq_length)`` (channel-first), float32
- the preprocessing script only does resampling + fixed-length (zero-pad / truncate) filtering,
  with no normalization, so per-record z-score (per-lead) is applied inside this module's
  Dataset. The preregistered protocol §2 constraint "normalization statistics come only from the
  train split" is satisfied as follows: per-record mode uses only the single record itself (no
  cross-split leakage); global-statistics mode must use fit_train_stats() (train instances only) /
  apply_stats() (other instances).

Normalization protocol (corresponds to protocol §2):
- normalize="per_record" (default): per-record per-lead z-score, mu/sigma from the record itself;
  no information leakage for any split, no global statistics needed
- normalize="global": per-lead global mu/sigma; statistics may only come from train-split
  instances via fit_train_stats(), with val/cal/test instances reusing them through apply_stats();
  any usage that refits statistics on a non-train split violates the protocol and is rejected
  by this module (apply_stats only accepts explicitly passed statistics, no automatic fitting).

Augmentation (transform) should only be attached to train instances (protocol §2 "augmentation
applies to train only"); this module does not decide that; the caller guarantees it via
split_indices.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping as MappingType, Optional, Sequence

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

from src.data.splits import DEFAULT_RATIOS, patient_wise_split

__all__ = ["ECGNPZDataset", "SyntheticECGDatasetV2"]

_EPS = 1e-8  # guard against division by zero on constant leads (constant lead -> all-zero output)


class ECGNPZDataset(Dataset):
    """ECG npy dataset (consumes the preprocess_cinc2021.py output format).

    Parameters
    ----------
    metadata_csv : str|Path
        preprocess output metadata_single_label.csv (columns: id/label/npy_path/...)
    data_dir : str|Path, optional
        npy directory; defaults to ``data/`` next to metadata_csv (matches preprocess output)
    split_indices : sequence, optional
        retained metadata row-position indices (the row numbers of this split after patient-level
        splitting; order preserved)
    transform : callable, optional
        transform applied to the normalized signal (n_leads, seq); augmentation is for train only
        (protocol §2)
    normalize : str
        "per_record" (default) | "global" | None
    label_map : dict, optional
        {raw label string: class index}; defaults to auto-encoding from sorted unique labels.
        CINC2021 preprocess output labels are {"Normal","Rhythm","CD","ST","Other"}
        (ECGMatch-style 4 groups + Normal); to map to Wagner 5 superclasses provide it explicitly.
    expected_leads : int
        lead-count validation (default 12; lead drop in the L2-shift ladder is eval-time
        zeroing, not handled here)
    split_role : str
        split role of this instance ("train"/"cal"/"test", default "train"). Protocol §2 guard:
        fit_train_stats() may only be called by instances with split_role=="train"; the stats dict
        carries a ``source=split_role`` provenance field, and apply_stats() only accepts statistics
        with source=="train" (guards against fitting statistics on a non-train split).

    __getitem__ returns ``(signal: float32 tensor (n_leads, seq), label: int)``
    """

    _VALID_SPLIT_ROLES = ("train", "cal", "test")

    def __init__(
        self,
        metadata_csv,
        data_dir=None,
        split_indices: Optional[Sequence[int]] = None,
        transform: Optional[Callable] = None,
        normalize: str = "per_record",
        label_map: Optional[MappingType] = None,
        expected_leads: int = 12,
        split_role: str = "train",
    ):
        if normalize not in ("per_record", "global", None):
            raise ValueError(f"normalize must be 'per_record'/'global'/None, got: {normalize}")
        if split_role not in self._VALID_SPLIT_ROLES:
            raise ValueError(
                f"split_role must be one of {'/'.join(self._VALID_SPLIT_ROLES)}, got: {split_role!r}"
            )
        self.metadata_csv = Path(metadata_csv)
        if not self.metadata_csv.exists():
            raise FileNotFoundError(f"metadata CSV not found: {self.metadata_csv}")
        self.data_dir = Path(data_dir) if data_dir is not None else self.metadata_csv.parent / "data"

        meta = pd.read_csv(self.metadata_csv)
        missing_cols = {"id", "label", "npy_path"} - set(meta.columns)
        if missing_cols:
            raise KeyError(
                f"metadata CSV missing required columns {missing_cols} (preprocess_cinc2021.py "
                f"outputs columns id/label/npy_path/fs/original_len)"
            )
        if split_indices is not None:
            idx = np.asarray(split_indices, dtype=int)
            if idx.size and (idx.min() < 0 or idx.max() >= len(meta)):
                raise IndexError(
                    f"split_indices out of range: [{idx.min()}, {idx.max()}] "
                    f"vs {len(meta)} rows"
                )
            meta = meta.iloc[idx].reset_index(drop=True)
        self.metadata = meta

        self.record_ids = meta["id"].tolist()
        self.raw_labels = meta["label"].tolist()
        if label_map is not None:
            unknown = sorted(set(self.raw_labels) - set(label_map))
            if unknown:
                raise KeyError(f"labels not covered by label_map: {unknown}")
            self.classes = sorted(label_map, key=lambda k: label_map[k])
            self.class_to_idx = dict(label_map)
        else:
            self.classes = sorted(set(self.raw_labels))
            self.class_to_idx = {c: i for i, c in enumerate(self.classes)}
        self.y = np.array([self.class_to_idx[c] for c in self.raw_labels], dtype=np.int64)

        self.transform = transform
        self.normalize = normalize
        self.expected_leads = expected_leads
        self.split_role = split_role
        self.stats_: Optional[dict] = None  # global statistics (only allowed from train fit)

        paths = []
        for name in meta["npy_path"]:
            p = self.data_dir / str(name)
            if not p.exists():
                raise FileNotFoundError(f"npy file missing: {p}")
            paths.append(p)
        self.npy_paths = paths

    def __len__(self) -> int:
        return len(self.npy_paths)

    def _load_signal(self, path: Path) -> np.ndarray:
        try:
            x = np.load(path, allow_pickle=False)
        except Exception as e:
            # a corrupt/unreadable npy must be locatable via its path
            raise ValueError(f"corrupt or unreadable npy: {path}") from e
        if x.ndim != 2:
            raise ValueError(f"expected 2D signal (n_leads, seq), got shape {x.shape}: {path}")
        if x.shape[0] != self.expected_leads:
            raise ValueError(
                f"lead count mismatch: {x.shape[0]} != expected_leads={self.expected_leads}: {path}"
            )
        x = x.astype(np.float32, copy=False)
        if not np.isfinite(x).all():
            # NaN/Inf would silently propagate into normalization stats and training; fail fast
            raise ValueError(f"signal contains NaN/Inf: {path}")
        return x

    def _normalize(self, x: np.ndarray) -> np.ndarray:
        """Per-lead normalization: per_record uses its own statistics; global uses train-fit stats."""
        if self.normalize is None:
            return x
        if self.normalize == "per_record":
            mu = x.mean(axis=1, keepdims=True)
            sd = x.std(axis=1, keepdims=True)
            return (x - mu) / (sd + _EPS)  # constant lead: (x-mu)=0 -> all-zero output
        if self.stats_ is None:
            raise RuntimeError(
                "normalize='global' but statistics are not set: must call fit_train_stats() "
                "on the train instance first, then apply_stats() on the remaining instances "
                "(protocol §2: normalization statistics come only from the train split)"
            )
        mu = self.stats_["mean"][:, None]
        sd = self.stats_["std"][:, None]
        return (x - mu) / (sd + _EPS)

    def __getitem__(self, idx: int):
        x = self._load_signal(self.npy_paths[idx])
        x = self._normalize(x)
        if self.transform is not None:
            x = self.transform(x)
        return torch.as_tensor(np.ascontiguousarray(x), dtype=torch.float32), int(self.y[idx])

    # ---------------- global-statistics protocol (statistics come only from train) ----------------

    def fit_train_stats(self) -> dict:
        """Fit per-lead global mu/sigma on this instance (must be a train-split instance).

        Streaming sum/sumsq accumulation avoids loading all signals at once. Statistics are
        committed to stats_ and the normalization mode switches to global only after they are
        fully computed (compute-then-commit: a mid-iteration failure leaves no corrupted state
        of "normalize switched to global but statistics missing/contaminated").
        The result dict carries ``source`` (=split_role, always "train") for apply_stats
        provenance checks. Other split instances must reuse this result via apply_stats().

        Raises ValueError when the protocol is violated (split_role != "train", e.g. called on a
        test-split instance): normalization statistics may only be fit from the train split
        (protocol §2).
        """
        if self.split_role != "train":
            raise ValueError("normalization statistics may only be fit from the train split (protocol §2)")
        n_leads = None
        total, s, sq = 0, None, None
        for path in self.npy_paths:
            x = self._load_signal(path)
            if n_leads is None:
                n_leads = x.shape[0]
                s = np.zeros(n_leads, dtype=np.float64)
                sq = np.zeros(n_leads, dtype=np.float64)
            elif x.shape[0] != n_leads:
                raise ValueError(f"lead count inconsistent: {x.shape[0]} vs {n_leads}")
            s += x.sum(axis=1)
            sq += (x.astype(np.float64) ** 2).sum(axis=1)
            total += x.shape[1]
        if not total:
            raise RuntimeError("empty dataset, cannot fit statistics")
        mean = s / total
        var = np.maximum(sq / total - mean ** 2, 0.0)  # numerical guard: variance non-negative
        stats = {"mean": mean, "std": np.sqrt(var),
                 "n_records": len(self.npy_paths), "n_samples": total,
                 "source": self.split_role}
        self.stats_ = stats  # committed only after successful computation
        if self.normalize == "per_record":
            self.normalize = "global"  # activate global mode after successful fit
        return stats

    def apply_stats(self, stats: MappingType) -> None:
        """Apply global statistics from the train split (for val/cal/test instances only).

        Statistics must be produced by a train instance's fit_train_stats() and passed in
        explicitly; this method performs no fitting of its own, structurally preventing the
        leakage path of "recomputing statistics on val/cal/test". The statistics dict must
        carry a ``source=="train"`` provenance field (written automatically by fit_train_stats);
        a missing or non-"train" source is rejected (guards against statistics coming from a
        non-train instance).
        """
        source = stats.get("source")
        if source != "train":
            raise ValueError(
                f"statistics source check failed: expected source=='train', got source={source!r}"
                " (protocol §2: normalization statistics come only from the train split)"
            )
        mean = np.asarray(stats["mean"], dtype=np.float64)
        std = np.asarray(stats["std"], dtype=np.float64)
        probe = self._load_signal(self.npy_paths[0]) if self.npy_paths else None
        if probe is not None and mean.shape[0] != probe.shape[0]:
            raise ValueError(
                f"statistics lead count {mean.shape[0]} != data lead count {probe.shape[0]}"
            )
        self.stats_ = {"mean": mean, "std": std, "source": source}
        if self.normalize == "per_record":
            self.normalize = "global"


class SyntheticECGDatasetV2(Dataset):
    """Multi-patient structured synthetic ECG dataset (no external data; for leakage
    assertions / split testing / smoke training).

    Same idea as scripts/train.py's SyntheticECGDataset (generated and cached once in __init__,
    no re-randomization between epochs), but adds a patient hierarchy:
    - each patient has a latent class prior + patient-level signal offset -> records of the same
      patient are strongly correlated; record-level random splitting is artificially optimistic
      and patient-level splitting is fair, so it suits leakage-assertion testing
    - record labels follow the patient latent class with prob=0.85, otherwise uniformly resampled
    - signal = class base morphology + patient offset + record-level noise (float32, (n_leads, seq))

    Attributes: X (n_records, n_leads, seq), y, patient_ids, record_patient
    """

    def __init__(
        self,
        n_patients: int = 50,
        records_per_patient: int = 4,
        n_leads: int = 12,
        seq_length: int = 1000,
        n_classes: int = 5,
        seed: int = 42,
        label_loyalty: float = 0.85,
    ):
        if n_patients < 1 or records_per_patient < 1:
            raise ValueError("n_patients and records_per_patient must be >= 1")
        g = np.random.default_rng(seed)
        self.n_patients = n_patients
        self.records_per_patient = records_per_patient
        self.n_classes = n_classes
        self.patient_ids = np.arange(1, n_patients + 1)
        self.patient_class = g.integers(0, n_classes, size=n_patients)
        # patient-level offset makes same-patient records correlated (mimics real
        # "multiple records per patient" structure)
        patient_offset = g.normal(0.0, 0.05, size=(n_patients, n_leads, 1))
        class_wave = g.normal(0.0, 1.0, size=(n_classes, n_leads, seq_length))

        X = np.empty((n_patients * records_per_patient, n_leads, seq_length), dtype=np.float32)
        y = np.empty(n_patients * records_per_patient, dtype=np.int64)
        rec_patient = np.empty(n_patients * records_per_patient, dtype=np.int64)
        k = 0
        for p in range(n_patients):
            for _ in range(records_per_patient):
                c = int(self.patient_class[p])
                if g.random() >= label_loyalty:
                    c = int(g.integers(0, n_classes))
                X[k] = (class_wave[c] + patient_offset[p]
                        + g.normal(0.0, 0.1, size=(n_leads, seq_length))).astype(np.float32)
                y[k] = c
                rec_patient[k] = self.patient_ids[p]
                k += 1
        self.X = X
        self.y = y
        self.record_patient = rec_patient

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, idx: int):
        return torch.as_tensor(self.X[idx]), int(self.y[idx])

    def patient_label_map(self) -> dict:
        """Patient majority-label map (for patient_wise_split's label_for_patient argument)."""
        return {int(pid): int(c) for pid, c in zip(self.patient_ids, self.patient_class)}

    def split_by_patient(
        self,
        ratios: Sequence[float] = DEFAULT_RATIOS,
        seed: int = 42,
    ) -> dict[str, dict]:
        """Patient-level split -> record-index view
        ({"train": {"patients": [...], "record_indices": array}, ...}).

        Same seed and logic as src.data.splits.patient_wise_split, for leakage-assertion testing.
        """
        splits = patient_wise_split(
            self.patient_ids.tolist(),
            self.patient_label_map(),
            ratios=ratios,
            seed=seed,
        )
        out = {}
        for name, pids in splits.items():
            pid_set = set(pids)
            rec_idx = np.flatnonzero(np.isin(self.record_patient, list(pid_set)))
            out[name] = {"patients": list(pids), "record_indices": rec_idx}
        return out


if __name__ == "__main__":
    import tempfile

    # self-check: synthetic npy + CSV -> ECGNPZDataset normalization and global-stat protocol
    rng = np.random.default_rng(0)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        data_dir = root / "data"
        data_dir.mkdir()
        rows = []
        for i in range(6):
            x = rng.normal(5.0, 2.0, size=(12, 200)).astype(np.float32)  # non-zero mean/variance
            np.save(data_dir / f"R{i}.npy", x)
            rows.append({"id": f"R{i}", "label": "Normal" if i % 2 else "MI",
                         "npy_path": f"R{i}.npy", "fs": 500, "original_len": 200})
        pd.DataFrame(rows).to_csv(root / "metadata_single_label.csv", index=False)
        ds = ECGNPZDataset(root / "metadata_single_label.csv")
        x, y = ds[0]
        assert x.shape == (12, 200) and isinstance(y, int)
        assert abs(float(x.mean())) < 1e-5, "per-record z-score should make mean ~= 0"
        stats = ds.fit_train_stats()
        assert ds.normalize == "global" and stats["mean"].shape == (12,)
        ds2 = ECGNPZDataset(root / "metadata_single_label.csv")
        ds2.apply_stats(stats)
        x2, _ = ds2[0]
        assert x2.shape == (12, 200)
    # self-check: SyntheticECGDatasetV2 patient-level split has no leakage
    syn = SyntheticECGDatasetV2(n_patients=30, records_per_patient=4, seq_length=200, seed=7)
    assert len(syn) == 120
    sp = syn.split_by_patient(seed=7)
    from src.data.splits import assert_no_leakage
    assert assert_no_leakage({k: v["patients"] for k, v in sp.items()}) is True
    assert sum(len(v["record_indices"]) for v in sp.values()) == 120
    print("Self-check: dataset module passed")
