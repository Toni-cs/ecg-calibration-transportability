import collections
import math
import os

import numpy as np
import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F
from rich.progress import Progress
from torch.utils.data import DataLoader
from torch.utils.data.sampler import Sampler
from sklearn.metrics import accuracy_score, f1_score

from tasks.classification import Classification as Task
from utils import TopKAccuracy
from utils.logging import make_epoch_description


class Classification(Task):
    def __init__(self, backbone: nn.Module):
        super(Classification, self).__init__(backbone)

    def logging_unlabeled_dataset(self, unlabeled_dataset, current_epoch):

        loader = DataLoader(
            dataset=unlabeled_dataset,
            batch_size=128,
            drop_last=False,
            shuffle=False,
            num_workers=4,
        )

        self._set_learning_phase(train=False)

        with torch.no_grad():
            with Progress(transient=True, auto_refresh=False) as pg:
                if self.local_rank == 0:
                    task = pg.add_task(f"[bold red] Extracting...", total=len(loader))
                for batch_idx, data in enumerate(loader):

                    x = data["inputs_u_w"].cuda(self.local_rank)
                    y = data["targets_u_eval"].cuda(self.local_rank)

                    full_logit = self.scomatch_predict(x)[1]
                    logits = full_logit[:, : self.backbone.class_num]
                    probs = nn.functional.softmax(logits, 1)

                    pseudo_label_open = torch.softmax(full_logit / self.T, dim=-1)
                    score = torch.max(pseudo_label_open[:, : self.backbone.class_num], dim=-1)[0] # low --> OOD / high --> ID

                    gt_idx = y < self.backbone.class_num

                    if batch_idx == 0:
                        gt_all = gt_idx
                        probs_all, logits_all = probs, logits
                        labels_all = y
                        score_all = score
                    else:
                        gt_all = torch.cat([gt_all, gt_idx], 0)
                        probs_all, logits_all = torch.cat(
                            [probs_all, probs], 0
                        ), torch.cat([logits_all, logits], 0)
                        labels_all = torch.cat([labels_all, y], 0)
                        score_all = torch.cat(
                            [score_all, score], 0
                        )

                    if self.local_rank == 0:
                        desc = f"[bold pink] Extracting .... [{batch_idx+1}/{len(loader)}] "
                        pg.update(task, advance=1.0, description=desc)
                        pg.refresh()

        select_all = score_all > 0.5 # low --> OOD / high --> ID

        select_accuracy = accuracy_score(
            gt_all.cpu().numpy(), select_all.cpu().numpy()
        )  # positive : inlier, negative : out of distribution
        select_f1 = f1_score(gt_all.cpu().numpy(), select_all.cpu().numpy())

        selected_idx = torch.arange(0, len(select_all), device=self.local_rank)[
            select_all
        ]

        probs_all = logits_all.softmax(-1)

        # Write TensorBoard summary
        if self.writer is not None:
            self.writer.add_scalar(
                "Selected accuracy", select_accuracy, global_step=current_epoch
            )
            self.writer.add_scalar("Selected f1", select_f1, global_step=current_epoch)
            self.writer.add_scalar(
                "Selected ratio",
                len(selected_idx) / len(select_all),
                global_step=current_epoch,
            )
            self.writer.add_scalar(
                "In distribution: ECE",
                self.get_ece(
                    probs_all[gt_all].cpu().numpy(), labels_all[gt_all].cpu().numpy()
                )[0],
                global_step=current_epoch,
            )
            self.writer.add_scalar(
                "In distribution: ACC",
                TopKAccuracy(k=1)(logits_all[gt_all], labels_all[gt_all]).item(),
                global_step=current_epoch,
            )
            if ((gt_all) & (probs_all.max(1)[0] >= 0.95)).sum() > 0:
                self.writer.add_scalar(
                    "In distribution over conf 0.95: ECE",
                    self.get_ece(
                        probs_all[(gt_all) & (probs_all.max(1)[0] >= 0.95)]
                        .cpu()
                        .numpy(),
                        labels_all[(gt_all) & (probs_all.max(1)[0] >= 0.95)]
                        .cpu()
                        .numpy(),
                    )[0],
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "In distribution over conf 0.95: ACC",
                    TopKAccuracy(k=1)(
                        logits_all[(gt_all) & (probs_all.max(1)[0] >= 0.95)],
                        labels_all[(gt_all) & (probs_all.max(1)[0] >= 0.95)],
                    ).item(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Selected ratio of i.d over conf 0.95",
                    ((gt_all) & (probs_all.max(1)[0] >= 0.95)).sum() / gt_all.sum(),
                    global_step=current_epoch,
                )

            if ((gt_all) & (select_all)).sum() > 0:
                self.writer.add_scalar(
                    "In distribution under ood score 0.5: ECE",
                    self.get_ece(
                        probs_all[(gt_all) & (select_all)].cpu().numpy(),
                        labels_all[(gt_all) & (select_all)].cpu().numpy(),
                    )[0],
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "In distribution under ood score 0.5: ACC",
                    TopKAccuracy(k=1)(
                        logits_all[(gt_all) & (select_all)],
                        labels_all[(gt_all) & (select_all)],
                    ).item(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Selected ratio of i.d under ood score 0.5",
                    ((gt_all) & (select_all)).sum() / gt_all.sum(),
                    global_step=current_epoch,
                )

            if (probs_all.max(1)[0] >= 0.95).sum() > 0:
                self.writer.add_scalar(
                    "Seen-class ratio over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= 0.95)]
                        < self.backbone.class_num
                    ).sum()
                    / (probs_all.max(1)[0] >= 0.95).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class ratio over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= 0.95)]
                        >= self.backbone.class_num
                    ).sum()
                    / (probs_all.max(1)[0] >= 0.95).sum(),
                    global_step=current_epoch,
                )

                self.writer.add_scalar(
                    "Seen-class over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= 0.95)]
                        < self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= 0.95)]
                        >= self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )

            if select_all.sum() > 0:
                self.writer.add_scalar(
                    "Seen-class ratio under ood score 0.5",
                    (labels_all[select_all] < self.backbone.class_num).sum()
                    / select_all.sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class ratio under ood score 0.5",
                    (labels_all[select_all] >= self.backbone.class_num).sum()
                    / select_all.sum(),
                    global_step=current_epoch,
                )

                self.writer.add_scalar(
                    "Seen-class under ood score 0.5",
                    (labels_all[select_all] < self.backbone.class_num).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class under ood score 0.5",
                    (labels_all[select_all] >= self.backbone.class_num).sum(),
                    global_step=current_epoch,
                )

            if ((select_all) & (probs_all.max(1)[0] >= 0.95)).sum() > 0:
                self.writer.add_scalar(
                    "Seen-class ratio both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= 0.95))]
                        < self.backbone.class_num
                    ).sum()
                    / ((select_all) & (probs_all.max(1)[0] >= 0.95)).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class ratio both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= 0.95))]
                        >= self.backbone.class_num
                    ).sum()
                    / ((select_all) & (probs_all.max(1)[0] >= 0.95)).sum(),
                    global_step=current_epoch,
                )

                self.writer.add_scalar(
                    "Seen-class both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= 0.95))]
                        < self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= 0.95))]
                        >= self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )

    def run(
        self,
        train_set,
        eval_set,
        test_set,
        open_test_set,
        n_bins,
        save_every,
        start_fix,
        Km,
        threshold,
        ood_threshold,
        T,
        **kwargs,
    ):  # pylint: disable=unused-argument

        num_workers = self.num_workers

        if not self.prepared:
            raise RuntimeError("Training not prepared.")

        # DataLoader
        epochs = self.iterations // save_every
        per_epoch_steps = self.iterations // epochs
        num_samples = per_epoch_steps * self.batch_size // 2

        l_sampler = DistributedSampler(
            dataset=train_set[0],
            num_replicas=1,
            rank=self.local_rank,
            num_samples=num_samples,
        )
        l_loader = DataLoader(
            train_set[0],
            batch_size=self.batch_size // 2,
            sampler=l_sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )

        u_sampler = DistributedSampler(
            dataset=train_set[1],
            num_replicas=1,
            rank=self.local_rank,
            num_samples=num_samples,
        )
        unlabel_loader = DataLoader(
            train_set[1],
            batch_size=self.batch_size // 2,
            sampler=u_sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        unlabel_loader_for_log = DataLoader(
            train_set[1],
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        eval_loader = DataLoader(
            eval_set,
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        test_loader = DataLoader(
            test_set,
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        open_test_loader = DataLoader(
            open_test_set,
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )

        # Logging
        logger = kwargs.get("logger", None)
        enable_plot = kwargs.get("enable_plot", False)

        # Supervised training
        best_eval_acc = -float("inf")
        best_epoch = 0

        from collections import deque

        self.selected_ood_maxlength = max(8 * self.backbone.class_num, 256)
        self.selected_ood_update_length = Km
        self.selected_ood_count = 0
        self.selected_ood_scores = deque(maxlen=self.selected_ood_maxlength)
        self.selected_ood_labels = deque(maxlen=self.selected_ood_maxlength)
        self.selected_ood_images = deque(maxlen=self.selected_ood_maxlength)

        self.all_sample_scores = [[] for i in range(self.backbone.class_num + 1)]
        self.threshold_update_freq = (len(train_set[1])) // int(self.batch_size)

        self.init_ood_threshold = ood_threshold
        self.threshold = threshold
        self.T = T

        for epoch in range(1, epochs + 1):

            self.logging_unlabeled_dataset(unlabeled_dataset=train_set[1], current_epoch=epoch)
            
            train_history = self.train(
                label_loader=l_loader,
                unlabel_loader=unlabel_loader,
                current_epoch=epoch,
                start_fix=start_fix,
                n_bins=n_bins,
                ood_threshold=ood_threshold,
            )
            eval_history = self.evaluate(eval_loader, n_bins)
            if enable_plot:
                raise NotImplementedError

            epoch_history = collections.defaultdict(dict)
            for k, v1 in train_history.items():
                epoch_history[k]["train"] = v1
                try:
                    v2 = eval_history[k]
                    epoch_history[k]["eval"] = v2
                except KeyError:
                    continue

            # Write TensorBoard summary
            if self.writer is not None:
                for k, v in epoch_history.items():
                    for k_, v_ in v.items():
                        self.writer.add_scalar(f"{k}_{k_}", v_, global_step=epoch)
                if self.scheduler is not None:
                    lr = self.scheduler.get_last_lr()[0]
                    self.writer.add_scalar("lr", lr, global_step=epoch)

            # Save best model checkpoint and Logging
            eval_acc = eval_history["top@1"]

            if logger is not None and eval_acc == 1:
                logger.info("Eval acc == 1 --> Stop training")
                break

            if eval_acc > best_eval_acc:
                best_eval_acc = eval_acc
                best_epoch = epoch
                if self.local_rank == 0:
                    ckpt = os.path.join(self.ckpt_dir, "ckpt.best.pth.tar")
                    self.save_checkpoint(ckpt, epoch=epoch)

                test_history = self.evaluate(test_loader, n_bins)
                for k, v1 in test_history.items():
                    epoch_history[k]["test"] = v1

                open_history = self.evaluate_open_set(open_test_loader)
                for k, v1 in open_history.items():
                    epoch_history[k]["open"] = v1

                if self.writer is not None:
                    self.writer.add_scalar(
                        "Best_Test_top@1", test_history["top@1"], global_step=epoch
                    )
                    self.writer.add_scalar(
                        "Best_Open_auroc", open_history["auroc"], global_step=epoch
                    )

            # Write logs
            log = make_epoch_description(
                history=epoch_history,
                current=epoch,
                total=epochs,
                best=best_epoch,
            )
            if logger is not None:
                logger.info(log)

    @torch.no_grad()
    def evaluate(self, data_loader, n_bins):
        """Evaluation defined for a single epoch."""

        steps = len(data_loader)
        self._set_learning_phase(train=False)
        result = {
            "loss": torch.zeros(steps, device=self.local_rank),
            "top@1": torch.zeros(1, device=self.local_rank),
            "ece": torch.zeros(1, device=self.local_rank),
            "ace": torch.zeros(1, device=self.local_rank),
            "sce": torch.zeros(1, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Evaluating...", total=steps)

            pred, true, IDX = [], [], []
            for i, batch in enumerate(data_loader):

                x = batch["x"].to(self.local_rank)
                y = batch["y"].to(self.local_rank)
                idx = batch["idx"].to(self.local_rank)

                logits = self.scomatch_predict(x)[1][:, : self.backbone.class_num]
                loss = self.loss_function(logits, y.long())

                result["loss"][i] = loss
                true.append(y.cpu())
                pred.append(logits.cpu())
                IDX += [idx]

                if self.local_rank == 0:
                    desc = (
                        f"[bold green] [{i+1}/{steps}]: "
                        + f" loss : {result['loss'][:i+1].mean():.4f} |"
                        + f" top@1 : {TopKAccuracy(k=1)(logits, y).detach():.4f} |"
                    )
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

        # preds, pred are logit vectors
        preds, trues = torch.cat(pred, axis=0), torch.cat(true, axis=0)
        result["top@1"][0] = TopKAccuracy(k=1)(preds, trues)

        probs = preds.softmax(dim=1).numpy()

        ece_results = self.get_ece(
            preds=probs,
            targets=trues.numpy(),
            n_bins=n_bins,
            plot=False,
        )
        result["ece"][0] = ece_results[0]
        result["ace"][0] = self.get_ace(probs, trues.numpy(), n_bins=n_bins)
        result["sce"][0] = self.get_sce(probs, trues.numpy(), n_bins=n_bins)

        return {k: v.mean().item() for k, v in result.items()}

    def get_open_set_probs(self, x: torch.FloatTensor):
        logits = self.scomatch_predict(x)[1][:, : self.backbone.class_num]
        return logits.softmax(dim=1)

    def train(
        self,
        label_loader,
        unlabel_loader,
        current_epoch,
        start_fix,
        n_bins,
        ood_threshold,
    ):
        """Training defined for a single epoch."""

        iteration = len(unlabel_loader)

        self._set_learning_phase(train=True)
        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Training...", total=iteration)

            for i, (data_lb, data_ulb) in enumerate(zip(label_loader, unlabel_loader)):

                if (
                    i % self.threshold_update_freq == 0
                    and i > 0
                    and current_epoch >= start_fix
                ):
                    max_len = sum(
                        [
                            len(self.all_sample_scores[i])
                            for i in range(self.backbone.class_num)
                        ]
                    )
                    ood_len = len(self.all_sample_scores[-1])
                    if max_len > 0:
                        ratio = ood_len / (max_len)
                        ood_threshold = self.threshold * (ratio)
                        ood_threshold = min(0.95, max(0.75, ood_threshold))
                    else:
                        ood_threshold = self.init_ood_threshold
                    self.all_sample_scores = [
                        [] for i in range(self.backbone.class_num + 1)
                    ]

                with torch.cuda.amp.autocast(self.mixed_precision):

                    inputs_x = data_lb["inputs_x"]
                    targets_x = data_lb["targets_x"]

                    inputs_u_w = data_ulb["inputs_u_w"]
                    inputs_u_s = data_ulb["inputs_u_s"]
                    inputs_all_w = data_ulb["inputs_all_w"]
                    inputs_all_s = data_ulb["inputs_all_s"]
                    targets_u_eval = data_ulb["targets_u_eval"]

                    b_size = inputs_x.shape[0]

                    if self.selected_ood_count < b_size:
                        inputs = torch.cat(
                            [
                                inputs_x,
                                inputs_all_w,
                                inputs_all_s,
                                inputs_u_w,
                                inputs_u_s,
                            ],
                            0,
                        ).to(self.local_rank)
                        _, logits_p, _, _ = self.scomatch_predict(inputs)
                        logits_id_lb = logits_p[:b_size]
                        logits_open_w, logits_open_s, logits_close_w, logits_close_s = (
                            logits_p[b_size:].chunk(4)
                        )
                        L_sup_open = torch.zeros(1).to(self.local_rank).mean()
                    else:
                        indices = torch.randperm(len(self.selected_ood_images))[:b_size]
                        ood_samples = torch.stack(list(self.selected_ood_images))[
                            indices
                        ]
                        ood_scores = torch.tensor(list(self.selected_ood_scores))[
                            indices
                        ].to(self.local_rank)
                        ood_label = (
                            (torch.ones(b_size) * self.backbone.class_num)
                            .to(self.local_rank)
                            .long()
                        )

                        inputs = torch.cat(
                            [
                                inputs_x,
                                ood_samples,
                                inputs_all_w,
                                inputs_all_s,
                                inputs_u_w,
                                inputs_u_s,
                            ],
                            0,
                        ).to(self.local_rank)

                        _, logits_p, _, _ = self.scomatch_predict(inputs)
                        logits_id_lb = logits_p[:b_size]
                        logits_ood_lb = logits_p[b_size : b_size + b_size]
                        logits_open_w, logits_open_s, logits_close_w, logits_close_s = (
                            logits_p[b_size + b_size :].chunk(4)
                        )

                        ood_mask = ood_scores < self.threshold
                        L_sup_open = (
                            F.cross_entropy(logits_ood_lb, ood_label, reduction="none")
                            * ood_mask
                        ).mean()

                    targets_x = targets_x.to(self.local_rank)
                    L_sup_close = F.cross_entropy(
                        logits_id_lb, targets_x, reduction="mean"
                    )

                    pseudo_label_open = torch.softmax(
                        logits_open_w.detach() / self.T, dim=-1
                    )
                    max_probs, targets_u_all = torch.max(pseudo_label_open, dim=-1)
                    for prob, target in zip(max_probs, targets_u_all):
                        if prob > self.threshold:
                            self.all_sample_scores[target.item()].append(prob.item())

                    max_probs_open, _ = torch.max(
                        pseudo_label_open[:, : self.backbone.class_num], dim=-1
                    )
                    _, indices = torch.sort(max_probs_open)
                    indices = indices[: self.selected_ood_update_length]
                    if self.selected_ood_count < self.selected_ood_maxlength:
                        self.selected_ood_count += self.selected_ood_update_length
                    for prob, img, ulab in zip(
                        max_probs_open[indices],
                        inputs_all_w[indices.cpu()],
                        targets_u_eval[indices.cpu()],
                    ):
                        self.selected_ood_scores.append(prob.item())
                        self.selected_ood_images.append(img)
                        self.selected_ood_labels.append(ulab.item())

                    max_probs_open, targets_u_all_open = torch.max(
                        pseudo_label_open, dim=-1
                    )
                    mask_pos = max_probs_open.ge(self.threshold) & (
                        targets_u_all_open < self.backbone.class_num
                    )
                    mask_pos = mask_pos | (
                        (max_probs_open.ge(ood_threshold))
                        & (targets_u_all_open == self.backbone.class_num)
                    )
                    L_unsup_open = (
                        F.cross_entropy(
                            torch.cat([logits_open_s], dim=0),
                            targets_u_all_open,
                            reduction="none",
                        )
                        * mask_pos
                    ).mean()

                    logits_p_u_close_w = logits_close_w[:, : self.backbone.class_num]
                    logits_p_u_close_s = logits_close_s[:, : self.backbone.class_num]

                    pseudo_close = torch.softmax(
                        logits_p_u_close_w.detach() / self.T, dim=-1
                    )
                    pseudo_open = torch.softmax(
                        logits_close_w.detach() / self.T, dim=-1
                    )

                    max_probs_close, targets_close = torch.max(pseudo_close, dim=-1)
                    max_probs_open, targets_open = torch.max(pseudo_open, dim=-1)

                    mask = max_probs.ge(self.threshold).float()
                    id_mask = targets_open < self.backbone.class_num
                    L_unsup_close = (
                        F.cross_entropy(
                            logits_p_u_close_s, targets_close, reduction="none"
                        )
                        * (mask * id_mask)
                    ).mean()

                    if current_epoch < start_fix:

                        L_unsup_open = torch.zeros(1).to(self.local_rank).mean()
                        L_sup_open = torch.zeros(1).to(self.local_rank).mean()

                    loss = L_sup_close + L_sup_open + L_unsup_close + L_unsup_open

                if self.scaler is not None:
                    self.scaler.scale(loss).backward()
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    loss.backward()
                    self.optimizer.step()
                self.optimizer.zero_grad()

                result["loss"][i] = loss.detach()
                result["top@1"][i] = TopKAccuracy(k=1)(
                    logits_id_lb[:, : self.backbone.class_num], targets_x
                ).detach()
                result["ece"][i] = self.get_ece(
                    preds=logits_id_lb[:, : self.backbone.class_num]
                    .softmax(dim=1)
                    .detach()
                    .cpu()
                    .numpy(),
                    targets=targets_x.cpu().numpy(),
                    n_bins=n_bins,
                    plot=False,
                )[0]

                if self.local_rank == 0:
                    desc = f"[bold green] [{i+1}/{iteration}]: "
                    for k, v in result.items():
                        desc += f" {k} : {v[:i+1].mean():.4f} |"
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

                # Update learning rate
                if self.scheduler is not None:
                    self.scheduler.step()

        return {k: v.mean().item() for k, v in result.items()}

    def scomatch_predict(self, x: torch.FloatTensor):

        logits, feat = self.get_feature(x)

        return logits, self.backbone.pos_head(feat), self.backbone.neg_head(feat), feat

    def get_feature(self, x: torch.FloatTensor):
        """Make a prediction provided a batch of samples."""
        return self.backbone(x, return_feature=True)


class DistributedSampler(Sampler):
    """Sampler that restricts data loading to a subset of the dataset.

    It is especially useful in conjunction with
    :class:`torch.nn.parallel.DistributedDataParallel`. In such case, each
    process can pass a DistributedSampler instance as a DataLoader sampler,
    and load a subset of the original dataset that is exclusive to it.

    .. note::
        Dataset is assumed to be of constant size.

    Arguments:
        dataset: Dataset used for sampling.
        num_replicas (optional): Number of processes participating in
            distributed training.
        rank (optional): Rank of the current process within num_replicas.
    """

    def __init__(self, dataset, num_replicas=None, rank=None, num_samples=None):

        if not isinstance(num_samples, int) or num_samples <= 0:
            raise ValueError(
                "num_samples should be a positive integeral "
                "value, but got num_samples={}".format(num_samples)
            )

        if num_replicas is None:
            if not dist.is_available():
                raise RuntimeError("Requires distributed package to be available")
            else:
                num_replicas = dist.get_world_size()
        if rank is None:
            if not dist.is_available():
                raise RuntimeError("Requires distributed package to be available")
            else:
                rank = dist.get_rank()
        self.dataset = dataset
        self.num_replicas = num_replicas
        self.rank = rank
        self.epoch = 0

        self.total_size = num_samples
        assert num_samples % self.num_replicas == 0, (
            f"{num_samples} samples cant"
            f"be evenly distributed among {num_replicas} devices."
        )
        self.num_samples = int(num_samples // self.num_replicas)

    def __iter__(self):
        # deterministically shuffle based on epoch
        g = torch.Generator()
        g.manual_seed(self.epoch)

        n = len(self.dataset)
        n_repeats = self.total_size // n
        n_remain = self.total_size % n
        indices = [torch.randperm(n, generator=g) for _ in range(n_repeats)]
        indices.append(torch.randperm(n, generator=g)[:n_remain])
        indices = torch.cat(indices, dim=0).tolist()

        assert len(indices) == self.total_size

        # subsample
        indices = indices[self.rank : self.total_size : self.num_replicas]
        assert len(indices) == self.num_samples

        return iter(indices)

    def __len__(self):
        return self.num_samples

    def set_epoch(self, epoch):
        self.epoch = epoch


