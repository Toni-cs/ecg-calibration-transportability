# ⚠️ 污染通知 — `checkpoints/e2_probs_cache/*.npz`

> **生成日期**：2026-09-16
> **状态**：**标签数组已被污染**；概率数组（probs）干净
> **依据**：`docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md` §A3.6；
> `reports/CPSC_OFFICIAL_DEFINITION_VERDICT_2026-09-16.md`

## 一句话

本目录 62 个 `.npz` 的 **`cal_labels` / `test_labels` 用的是"新"编码
（idx1=MI, idx3=CD）**，而 60 格主分析模型是按 **"旧"编码
（idx1=CD, idx3=MI）** 训练的。**40 个含 CPSC 的 cell 的 MI 与 CD 两类标签被互换。**

`cal_probs` / `test_probs` **未受影响**，可直接使用。

## 根因

2026-09-09 提交 `452b3bf` 把 `src/data/mapping.py` 的 `SUBSPACE_CPSC`
由 `("NORM","CD","STTC","MI")` 改为 `("NORM","MI","STTC","CD")`，
**但未重训任何模型**。由于该元组**顺序即整数标签编码**
（`label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}`），
09-10 之后重新生成的 npz 标签与 09-08 训练的 checkpoint 语义失配。

2026-09-16 已把 `SUBSPACE_CPSC` **回退**至训练顺序
（并加回归测试 `tests/test_data.py::TestMapping::test_subspace_cpsc_order_is_pinned` 钉死），
但**本目录的 npz 未重新生成**——它们是 09-10 的产物。

## 如何正确使用

```python
import numpy as np

def swap13(y):
    out = y.copy()
    out[y == 1] = 3
    out[y == 3] = 1
    return out

d = np.load("checkpoints/e2_probs_cache/chapman_cpsc_inceptiontime_seed42.npz")
test_probs  = d["test_probs"]           # ✅ 直接用
cal_probs   = d["cal_probs"]            # ✅ 直接用
test_labels = d["test_labels"]          # ⚠️ 新编码
cal_labels  = d["cal_labels"]           # ⚠️ 新编码

# 含 CPSC 的 pair（4/6 个 pair）必须换回旧编码：
test_labels_old = swap13(test_labels)
cal_labels_old  = swap13(cal_labels)

# 不含 CPSC 的 pair（chapman<->ptbxl）两套编码相同，无需换。
```

**判据**：`"cpsc" in (source, target)`。

## 已核验（可复现）

| 检验 | 结果 |
|---|---|
| 用旧编码重算 ΔECE vs `checkpoints/transfer/**/transfer_result.json` | **60/60 逐位一致，max\|Δ\| = 1.11e-16** |
| 用旧编码重算的 60 格均值 | **+0.015863**（= 论文头条数 +0.0159） |
| 用新编码重算的 60 格均值 | +0.106562（= 被污染的 `delta_obs` 口径） |
| 20 个非 CPSC cell 两套编码 | 完全一致（对照通过） |
| 旧编码 T 中位数（62 条） | 1.0745（全部 < 1.5） |
| 新编码 T 中位数（62 条） | 1.5741 |

复现脚本：

```
python scripts/reproduce_main_endpoint_both_encodings.py
python scripts/emit_contamination_provenance.py
```

## 下游消费者须知

- **论文主终点未受影响**。论文用的是
  `results/strengthening_battle_corrected.json` 的 **`delta_obs_orig`** 字段，
  该字段口径正确（见 `results/strengthening_battle_corrected.PROVENANCE.json`）。
- **不要使用** `strengthening_battle_corrected.json` 的 `T` 与 `delta_obs` 字段。
- **不要**在未换回旧编码的情况下，把本目录 npz 的 labels 直接喂给 09-08 训练的 checkpoint。
- 若要彻底消除此问题：**重训全部含 CPSC 的模型**，然后重新生成 npz。
  当前选择是保留 09-08 checkpoint（论文数字来源）并显式记录编码。
