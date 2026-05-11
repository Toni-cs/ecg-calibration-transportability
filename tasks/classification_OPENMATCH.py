import collections
import math
import os

import numpy as np
import torch
import torch.distributed as dist
import torch.nn as nn
from rich.progress import Progress
from sklearn.metrics import accuracy_score, f1_score
from torch.utils.data import DataLoader
from torch.utils.data.sampler import Sampler

from tasks.classification import Classification as Task
from utils import TopKAccuracy
from utils.logging import make_epoch_description


class Classification(Task):
    def __init__(self, backbone: nn.Module):
        super(Classification, self).__init__(backbone)

    def run(
        self,
        train_set,
        eval_set,
        test_set,
        open_test_set,
        p_cutoff,
        pi,
        warm_up_end,
        save_every,
        n_bins,
        start_fix,
        lambda_em,
        lambda_socr,
        train_trans,
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

        for epoch in range(1, epochs + 1):

            # Selection related to unlabeled data
            self.exclude_dataset(
                unlabeled_dataset=train_set[1],
                selected_dataset=train_set[-1],
                start_fix=start_fix,
                current_epoch=epoch,
                pi=pi,
                p_cutoff=p_cutoff,
            )

            # Train & evaluate
            u_sel_sampler = DistributedSampler(
                dataset=train_set[-1],
                num_replicas=1,
                rank=self.local_rank,
                num_samples=num_samples,
            )
            selected_u_loader = DataLoader(
                train_set[-1],
                sampler=u_sel_sampler,
                batch_size=self.batch_size // 2,
                num_workers=num_workers,
                drop_last=False,
                pin_memory=False,
                shuffle=False,
            )

            train_history, cls_wise_results = self.train(
                l_loader,
                unlabel_loader,
                selected_u_loader,
                current_epoch=epoch,
                start_fix=start_fix,
                p_cutoff=p_cutoff,
                n_bins=n_bins,
                lambda_em=lambda_em,
                lambda_socr=lambda_socr,
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
                if cls_wise_results is not None:
                    self.writer.add_scalar(
                        "trained_unlabeled_data_in",
                        sum(
                            [
                                cls_wise_results[key].mean()
                                for key in cls_wise_results.keys()
                                if key < self.backbone.class_num
                            ]
                        ).item(),
                        global_step=epoch,
                    )
                    self.writer.add_scalar(
                        "trained_unlabeled_data_ood",
                        sum(
                            [
                                cls_wise_results[key].mean()
                                for key in cls_wise_results.keys()
                                if key >= self.backbone.class_num
                            ]
                        ).item(),
                        global_step=epoch,
                    )

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

    def exclude_dataset(
        self,
        unlabeled_dataset,
        selected_dataset,
        start_fix,
        current_epoch,
        pi,
        p_cutoff,
    ):

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

                    x = data["x_ulb_w_0"].cuda(self.local_rank)
                    y = data["y_ulb"].cuda(self.local_rank)

                    outputs = self.openmatch_predict(x)
                    logits, logits_open = outputs["logits"], outputs["logits_open"]
                    probs = nn.functional.softmax(logits, 1)
                    logits_open = nn.functional.softmax(
                        logits_open.view(logits_open.size(0), 2, -1), 1
                    )
                    tmp_range = (
                        torch.arange(0, logits_open.size(0))
                        .long()
                        .cuda(self.local_rank)
                    )
                    pred_close = probs.data.max(1)[1]
                    unk_score = logits_open[tmp_range, :, pred_close]
                    gt_idx = y < self.backbone.class_num
                    if batch_idx == 0:
                        unk_score_all = unk_score
                        gt_all = gt_idx
                        probs_all, logits_all = probs, logits
                        labels_all = y
                    else:
                        unk_score_all = torch.cat([unk_score_all, unk_score], 0)
                        gt_all = torch.cat([gt_all, gt_idx], 0)
                        probs_all, logits_all = torch.cat(
                            [probs_all, probs], 0
                        ), torch.cat([logits_all, logits], 0)
                        labels_all = torch.cat([labels_all, y], 0)

                    if self.local_rank == 0:
                        desc = f"[bold pink] Extracting .... [{batch_idx+1}/{len(loader)}] "
                        pg.update(task, advance=1.0, description=desc)
                        pg.refresh()

        s_us_confidence, s_us_result = unk_score_all.max(1)
        select_all = s_us_result == 1

        select_accuracy = accuracy_score(
            gt_all[s_us_confidence >= pi].cpu().numpy(),
            select_all[s_us_confidence >= pi].cpu().numpy(),
        )  # positive : inlier, negative : out of distribution
        select_f1 = f1_score(
            gt_all[s_us_confidence >= pi].cpu().numpy(),
            select_all[s_us_confidence >= pi].cpu().numpy(),
        )

        selected_idx = torch.arange(0, len(select_all), device=self.local_rank)[
            (select_all) & (s_us_confidence >= pi)
        ]

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

            if ((gt_all) & (probs_all.max(1)[0] >= p_cutoff)).sum() > 0:
                idx = (gt_all) & (probs_all.max(1)[0] >= p_cutoff)
                self.writer.add_scalar(
                    "In distribution over conf 0.95: ECE",
                    self.get_ece(
                        probs_all[idx].cpu().numpy(), labels_all[idx].cpu().numpy()
                    )[0],
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "In distribution over conf 0.95: ACC",
                    TopKAccuracy(k=1)(logits_all[idx], labels_all[idx]).item(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Selected ratio of i.d over conf 0.95",
                    (idx).sum() / gt_all.sum(),
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

            if (probs_all.max(1)[0] >= p_cutoff).sum() > 0:
                self.writer.add_scalar(
                    "Seen-class ratio over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= p_cutoff)]
                        < self.backbone.class_num
                    ).sum()
                    / (probs_all.max(1)[0] >= p_cutoff).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class ratio over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= p_cutoff)]
                        >= self.backbone.class_num
                    ).sum()
                    / (probs_all.max(1)[0] >= p_cutoff).sum(),
                    global_step=current_epoch,
                )

                self.writer.add_scalar(
                    "Seen-class over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= p_cutoff)]
                        < self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= p_cutoff)]
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

            if ((select_all) & (probs_all.max(1)[0] >= p_cutoff)).sum() > 0:
                self.writer.add_scalar(
                    "Seen-class ratio both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= p_cutoff))]
                        < self.backbone.class_num
                    ).sum()
                    / ((select_all) & (probs_all.max(1)[0] >= p_cutoff)).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class ratio both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= p_cutoff))]
                        >= self.backbone.class_num
                    ).sum()
                    / ((select_all) & (probs_all.max(1)[0] >= p_cutoff)).sum(),
                    global_step=current_epoch,
                )

                self.writer.add_scalar(
                    "Seen-class both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= p_cutoff))]
                        < self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class both under ood score 0.5 and over conf 0.95",
                    (
                        labels_all[((select_all) & (probs_all.max(1)[0] >= p_cutoff))]
                        >= self.backbone.class_num
                    ).sum(),
                    global_step=current_epoch,
                )

        self._set_learning_phase(train=True)
        if current_epoch >= start_fix:
            if len(selected_idx) > 0:
                selected_dataset.set_index(selected_idx)

    def train(
        self,
        label_loader,
        unlabel_loader,
        selected_unlabel_loader,
        current_epoch,
        start_fix,
        p_cutoff,
        n_bins,
        lambda_em,
        lambda_socr,
    ):
        """Training defined for a single epoch."""

        iteration = len(unlabel_loader)

        self._set_learning_phase(train=True)
        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
            "unlabeled_top@1": torch.zeros(iteration, device=self.local_rank),
            "unlabeled_ece": torch.zeros(iteration, device=self.local_rank),
            "N_used_unlabeled": torch.zeros(iteration, device=self.local_rank),
        }

        if self.backbone.class_num == 6:
            cls_wise_results = {i: torch.zeros(iteration) for i in range(10)}
        elif self.backbone.class_num == 50:
            cls_wise_results = {i: torch.zeros(iteration) for i in range(100)}
        else:
            cls_wise_results = {i: torch.zeros(iteration) for i in range(200)}

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Training...", total=iteration)

            for i, (data_lb, data_ulb, data_ulb_selected) in enumerate(
                zip(label_loader, unlabel_loader, selected_unlabel_loader)
            ):
                with torch.cuda.amp.autocast(self.mixed_precision):

                    x_lb_w_0 = data_lb["x_lb_w_0"].to(self.local_rank)
                    x_lb_w_1 = data_lb["x_lb_w_1"].to(self.local_rank)
                    y_lb = data_lb["y_lb"].to(self.local_rank)

                    x_ulb_w_0 = data_ulb["x_ulb_w_0"].to(self.local_rank)
                    x_ulb_w_1 = data_ulb["x_ulb_w_1"].to(self.local_rank)

                    x_ulb_w = data_ulb_selected["x_ulb_w"].to(self.local_rank)
                    x_ulb_s = data_ulb_selected["x_ulb_s"].to(self.local_rank)
                    unlabel_y = data_ulb_selected["unlabel_y"].to(self.local_rank)

                    num_lb = y_lb.shape[0]

                    inputs = torch.cat((x_lb_w_0, x_lb_w_1, x_ulb_w_0, x_ulb_w_1))
                    outputs = self.openmatch_predict(inputs)
                    logits_x_lb = outputs["logits"][: num_lb * 2]
                    logits_open_lb = outputs["logits_open"][: num_lb * 2]
                    logits_open_ulb_0, logits_open_ulb_1 = outputs["logits_open"][
                        num_lb * 2 :
                    ].chunk(2)

                    sup_loss = self.loss_function(logits_x_lb, y_lb.repeat(2))
                    ova_loss = ova_loss_func(logits_open_lb, y_lb.repeat(2))
                    em_loss = em_loss_func(logits_open_ulb_0, logits_open_ulb_1)
                    socr_loss = socr_loss_func(logits_open_ulb_0, logits_open_ulb_1)

                    fix_loss = torch.tensor(0).cuda(self.local_rank)
                    if current_epoch >= start_fix:
                        inputs_selected = torch.cat((x_ulb_w, x_ulb_s), 0)
                        outputs_selected = self.openmatch_predict(inputs_selected)
                        logits_x_ulb_w, logits_x_ulb_s = outputs_selected[
                            "logits"
                        ].chunk(2)

                        unlabel_confidence, unlabel_pseudo_y = logits_x_ulb_w.softmax(
                            1
                        ).max(1)
                        used_unlabeled_index = unlabel_confidence > p_cutoff

                        fix_loss = self.loss_function(
                            logits_x_ulb_s[used_unlabeled_index],
                            unlabel_pseudo_y[used_unlabeled_index].long().detach(),
                        )

                    loss = (
                        sup_loss
                        + ova_loss
                        + lambda_em * em_loss
                        + lambda_socr * socr_loss
                        + fix_loss
                    )

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
                    logits_x_lb.chunk(2)[0], y_lb
                ).detach()
                result["ece"][i] = self.get_ece(
                    preds=logits_x_lb.chunk(2)[0].softmax(dim=1).detach().cpu().numpy(),
                    targets=y_lb.cpu().numpy(),
                    n_bins=n_bins,
                    plot=False,
                )[0]
                if current_epoch >= start_fix:
                    if used_unlabeled_index.sum().item() != 0:
                        result["unlabeled_top@1"][i] = TopKAccuracy(k=1)(
                            logits_x_ulb_w[used_unlabeled_index],
                            unlabel_y[used_unlabeled_index],
                        ).detach()
                        result["unlabeled_ece"][i] = self.get_ece(
                            preds=logits_x_ulb_w[used_unlabeled_index]
                            .softmax(dim=1)
                            .detach()
                            .cpu()
                            .numpy(),
                            targets=unlabel_y[used_unlabeled_index].cpu().numpy(),
                            n_bins=n_bins,
                            plot=False,
                        )[0]
                    result["N_used_unlabeled"][i] = used_unlabeled_index.sum().item()

                    unique, counts = np.unique(
                        unlabel_y[used_unlabeled_index].cpu().numpy(),
                        return_counts=True,
                    )
                    uniq_cnt_dict = dict(zip(unique, counts))

                    for key, value in uniq_cnt_dict.items():
                        cls_wise_results[key][i] = value

                if self.local_rank == 0:
                    desc = f"[bold green] [{i+1}/{iteration}]: "
                    for k, v in result.items():
                        desc += f" {k} : {v[:i+1].mean():.4f} |"
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

                # Update learning rate
                if self.scheduler is not None:
                    self.scheduler.step()

        if current_epoch >= start_fix:
            return {k: v.mean().item() for k, v in result.items()}, cls_wise_results
        else:
            return {k: v.mean().item() for k, v in result.items()}, None

    def openmatch_predict(self, x: torch.FloatTensor):

        logits, feat = self.get_feature(x)
        logits_open = self.backbone.ova_classifiers(feat)

        return {"logits": logits, "logits_open": logits_open}

    def get_feature(self, x: torch.FloatTensor):
        """Make a prediction provided a batch of samples."""
        return self.backbone(x, return_feature=True)

    # Reference: https://github.com/VisionLearningGroup/OP_Match/blob/main/utils/misc.py
    @staticmethod
    def mb_sup_loss(logits_ova, label):
        batch_size = logits_ova.size(0)
        logits_ova = logits_ova.view(batch_size, 2, -1)
        num_classes = logits_ova.size(2)
        probs_ova = nn.functional.softmax(logits_ova, 1)
        label_s_sp = torch.zeros((batch_size, num_classes)).long().to(label.device)
        label_range = torch.arange(0, batch_size).long().to(label.device)
        label_s_sp[label_range[label < num_classes], label[label < num_classes]] = 1
        label_sp_neg = 1 - label_s_sp
        open_loss = torch.mean(
            torch.sum(-torch.log(probs_ova[:, 1, :] + 1e-8) * label_s_sp, 1)
        )
        open_loss_neg = torch.mean(
            torch.max(-torch.log(probs_ova[:, 0, :] + 1e-8) * label_sp_neg, 1)[0]
        )
        l_ova_sup = open_loss_neg + open_loss
        return l_ova_sup


def ova_loss_func(logits_open, label):
    # Eq.(1) in the paper
    logits_open = logits_open.view(logits_open.size(0), 2, -1)
    logits_open = nn.functional.softmax(logits_open, 1)
    label_s_sp = (
        torch.zeros((logits_open.size(0), logits_open.size(2))).long().to(label.device)
    )
    label_range = torch.arange(0, logits_open.size(0)).long()
    label_s_sp[label_range, label] = (
        1  # one-hot labels, in the shape of (bsz, num_classes)
    )
    label_sp_neg = 1 - label_s_sp
    open_loss = torch.mean(
        torch.sum(-torch.log(logits_open[:, 1, :] + 1e-8) * label_s_sp, 1)
    )
    open_loss_neg = torch.mean(
        torch.max(-torch.log(logits_open[:, 0, :] + 1e-8) * label_sp_neg, 1)[0]
    )
    l_ova = open_loss_neg + open_loss
    return l_ova


def em_loss_func(logits_open_u1, logits_open_u2):
    # Eq.(2) in the paper
    def em(logits_open):
        logits_open = logits_open.view(logits_open.size(0), 2, -1)
        logits_open = nn.functional.softmax(logits_open, 1)
        _l_em = torch.mean(
            torch.mean(torch.sum(-logits_open * torch.log(logits_open + 1e-8), 1), 1)
        )
        return _l_em

    l_em = (em(logits_open_u1) + em(logits_open_u2)) / 2

    return l_em


def socr_loss_func(logits_open_u1, logits_open_u2):
    # Eq.(3) in the paper
    logits_open_u1 = logits_open_u1.view(logits_open_u1.size(0), 2, -1)
    logits_open_u2 = logits_open_u2.view(logits_open_u2.size(0), 2, -1)
    logits_open_u1 = nn.functional.softmax(logits_open_u1, 1)
    logits_open_u2 = nn.functional.softmax(logits_open_u2, 1)
    l_socr = torch.mean(
        torch.sum(torch.sum(torch.abs(logits_open_u1 - logits_open_u2) ** 2, 1), 1)
    )
    return l_socr


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


