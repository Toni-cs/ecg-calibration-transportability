import collections
import os

import numpy as np
import torch
import torch.nn as nn
from rich.progress import Progress
from sklearn.metrics import accuracy_score, precision_score, recall_score
from torch.utils.data import DataLoader

from tasks.classification import Classification as Task
from utils import RandomSampler, TopKAccuracy
from utils.logging import make_epoch_description


class Classification(Task):
    def __init__(self, backbone: nn.Module):
        super(Classification, self).__init__(backbone)

    def log_unlabeled_data(self, unlabel_loader, current_epoch):

        self._set_learning_phase(train=False)

        with torch.no_grad():
            with Progress(transient=True, auto_refresh=False) as pg:
                if self.local_rank == 0:
                    task = pg.add_task(
                        f"[bold red] Extracting...", total=len(unlabel_loader)
                    )
                for batch_idx, data in enumerate(unlabel_loader):

                    x = data["weak_img"].cuda(self.local_rank)
                    y = data["y"].cuda(self.local_rank)

                    logits = self.predict(x)
                    probs = nn.functional.softmax(logits, 1)
                    select_idx = logits.softmax(1).max(1)[0] > 0.95
                    gt_idx = y < self.backbone.class_num

                    if batch_idx == 0:
                        select_all = select_idx
                        gt_all = gt_idx
                        probs_all, logits_all = probs, logits
                        labels_all = y
                    else:
                        select_all = torch.cat([select_all, select_idx], 0)
                        gt_all = torch.cat([gt_all, gt_idx], 0)
                        probs_all, logits_all = torch.cat(
                            [probs_all, probs], 0
                        ), torch.cat([logits_all, logits], 0)
                        labels_all = torch.cat([labels_all, y], 0)

                    if self.local_rank == 0:
                        desc = f"[bold pink] Extracting .... [{batch_idx+1}/{len(unlabel_loader)}] "
                        pg.update(task, advance=1.0, description=desc)
                        pg.refresh()

        select_accuracy = accuracy_score(
            gt_all.cpu().numpy(), select_all.cpu().numpy()
        )  # positive : inlier, negative : out of distribution
        select_precision = precision_score(
            gt_all.cpu().numpy(), select_all.cpu().numpy()
        )
        select_recall = recall_score(gt_all.cpu().numpy(), select_all.cpu().numpy())

        selected_idx = torch.arange(0, len(select_all), device=self.local_rank)[
            select_all
        ]

        # Write TensorBoard summary
        if self.writer is not None:
            self.writer.add_scalar(
                "Selected ratio",
                len(selected_idx) / len(select_all),
                global_step=current_epoch,
            )
            self.writer.add_scalar(
                "Selected accuracy", select_accuracy, global_step=current_epoch
            )
            self.writer.add_scalar(
                "Selected precision", select_precision, global_step=current_epoch
            )
            self.writer.add_scalar(
                "Selected recall", select_recall, global_step=current_epoch
            )
            self.writer.add_scalar(
                "In distribution: ECE",
                self.get_ece(
                    probs_all[gt_all].cpu().numpy(), labels_all[gt_all].cpu().numpy()
                )[0].item(),
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
                    )[0].item(),
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
                    (((gt_all) & (probs_all.max(1)[0] >= 0.95)).sum() / gt_all.sum()).item(),
                    global_step=current_epoch,
                )

            if (probs_all.max(1)[0] >= 0.95).sum() > 0:
                self.writer.add_scalar(
                    "Seen-class ratio over conf 0.95",
                    ((labels_all[(probs_all.max(1)[0] >= 0.95)]< self.backbone.class_num).sum()/(probs_all.max(1)[0] >= 0.95).sum()).item()
                    ,
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class ratio over conf 0.95",
                    ((labels_all[(probs_all.max(1)[0] >= 0.95)]>= self.backbone.class_num).sum()/(probs_all.max(1)[0] >= 0.95).sum()).item(),
                    global_step=current_epoch,
                )

                self.writer.add_scalar(
                    "Seen-class over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= 0.95)]
                        < self.backbone.class_num
                    ).sum().item(),
                    global_step=current_epoch,
                )
                self.writer.add_scalar(
                    "Unseen-class over conf 0.95",
                    (
                        labels_all[(probs_all.max(1)[0] >= 0.95)]
                        >= self.backbone.class_num
                    ).sum().item(),
                    global_step=current_epoch,
                )

    def run(
        self,
        train_set,
        eval_set,
        test_set,
        open_test_set,
        save_every,
        p_cutoff,
        warm_up_end,
        n_bins,
        start_fix,
        **kwargs,
    ):  # pylint: disable=unused-argument

        batch_size = self.batch_size
        num_workers = self.num_workers

        if not self.prepared:
            raise RuntimeError("Training not prepared.")

        ## labeled
        sampler = RandomSampler(
            len(train_set[0]), self.iterations * self.batch_size // 2
        )
        train_l_loader = DataLoader(
            train_set[0],
            batch_size=batch_size // 2,
            sampler=sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        train_l_iterator = iter(train_l_loader)

        ## unlabeled
        sampler = RandomSampler(
            len(train_set[1]), self.iterations * self.batch_size // 2
        )
        train_u_loader = DataLoader(
            train_set[1],
            batch_size=batch_size // 2,
            sampler=sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        train_u_iterator = iter(train_u_loader)

        label_loader = DataLoader(
            train_set[0],
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        unlabel_loader = DataLoader(
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

        # Supervised training
        best_eval_acc = -float("inf")
        best_epoch = 0

        epochs = self.iterations // save_every
        self.warm_up_end = warm_up_end
        self.trained_iteration = 0

        self.alpha_min = 0.1
        self.k = 2.0
        self.ema_p = 0.999
        self.mode = "adello"
        self.alpha_from_epoch = False

        self.p_data, num_samples_lb = self.compute_labeled_prior(
            label_loader
        )
        self.gt_u_prior, num_samples_ulb = self.compute_unlabeled_prior(
            unlabel_loader
        )

        p_target = None  # ignored

        self.p_hat = torch.tensor(
            np.ones((self.backbone.class_num,)) / self.backbone.class_num
        ).to(self.local_rank)

        self.ce_loss = FlexDASupervisedLoss(
            alpha_min=self.alpha_min,
            k=self.k,
            use_epochs=self.alpha_from_epoch,
            p_data=self.p_data,
            p_target=p_target,
            target_mode=self.mode,
            num_samples_lb=num_samples_lb,
            num_samples_ulb=num_samples_ulb,
        )
        self.consistency_loss = FlexDAConsistencyLoss(
            alpha_min=self.alpha_min,
            k=self.k,
            use_epochs=self.alpha_from_epoch,
            p_data=self.p_data,
            p_target=p_target,
            target_mode=self.mode,
            num_samples_lb=num_samples_lb,
            num_samples_ulb=num_samples_ulb,
        )
        for epoch in range(1, epochs + 1):

            # training unlabeled data logging
            self.log_unlabeled_data(unlabel_loader=unlabel_loader, current_epoch=epoch)

            # Train & evaluate
            train_history, train_l_iterator, train_u_iterator = self.train(
                train_l_iterator,
                train_u_iterator,
                iteration=save_every,
                p_cutoff=p_cutoff,
                n_bins=n_bins,
                start_fix=start_fix,
                current_epoch=epoch,
            )
            eval_history = self.evaluate(eval_loader, n_bins)

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

    def train(
        self,
        label_iterator,
        unlabel_iterator,
        iteration,
        p_cutoff,
        n_bins,
        start_fix,
        current_epoch,
    ):
        """Training defined for a single epoch."""

        self._set_learning_phase(train=True)
        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Training...", total=iteration)

            for i in range(iteration):
                with torch.autocast("cuda", enabled=self.mixed_precision):

                    self.consistency_loss.set_params(
                        p_hat=self.p_hat,
                        cte_iter=self.trained_iteration,
                        max_iter=self.iterations,
                        num_iter_per_epoch=iteration,
                    )

                    self.ce_loss.set_params(
                        p_hat=self.p_hat,
                        cte_iter=self.trained_iteration,
                        max_iter=self.iterations,
                        num_iter_per_epoch=iteration,
                    )
                    self.smooth_factor = self.consistency_loss.get_alpha_factor()

                    l_batch = next(label_iterator)
                    u_batch = next(unlabel_iterator)

                    x_lb = l_batch["x"].to(self.local_rank)
                    y_lb = l_batch["y"].to(self.local_rank)

                    num_lb = y_lb.shape[0]

                    x_ulb_w, x_ulb_s = u_batch["weak_img"].to(self.local_rank), u_batch[
                        "strong_img"
                    ].to(self.local_rank)

                    inputs = torch.cat((x_lb, x_ulb_w, x_ulb_s))

                    outputs = self.adello_predict(inputs)

                    logits_x_lb = outputs["logits"][:num_lb]
                    logits_x_ulb_w, logits_x_ulb_s = outputs["logits"][num_lb:].chunk(2)
                    feats_x_lb = outputs["feat"][:num_lb]
                    feats_x_ulb_w, feats_x_ulb_s = outputs["feat"][num_lb:].chunk(2)

                    feat_dict = {
                        "x_lb": feats_x_lb,
                        "x_ulb_w": feats_x_ulb_w,
                        "x_ulb_s": feats_x_ulb_s,
                    }
                    sup_loss = self.ce_loss(logits_x_lb, y_lb, reduction="mean")
                    probs_x_ulb_w = self.compute_prob(
                        logits_x_ulb_w.detach(), lb_in_ulb_mask=None
                    )

                    # compute mask (just FixMatch masking)
                    mask = probs_x_ulb_w.max(-1)[0].ge(p_cutoff)

                    # generate unlabeled targets using pseudo label hook
                    pseudo_label = probs_x_ulb_w.argmax(-1)

                    unsup_loss = self.consistency_loss(
                        logits_x_ulb_s, pseudo_label, "ce", mask=mask
                    )

                    if current_epoch < start_fix:
                        unsup_loss = torch.zeros(1).to(self.local_rank).mean()

                    loss = sup_loss + unsup_loss

                if self.scaler is not None:
                    self.scaler.scale(loss).backward()
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    loss.backward()
                    self.optimizer.step()
                self.optimizer.zero_grad()
                self.trained_iteration += 1

                result["loss"][i] = loss.detach()
                result["top@1"][i] = TopKAccuracy(k=1)(logits_x_lb, y_lb).detach()
                result["ece"][i] = self.get_ece(
                    preds=logits_x_lb.softmax(dim=1).detach().cpu().numpy(),
                    targets=y_lb.cpu().numpy(),
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

        return (
            {k: v.mean().item() for k, v in result.items()},
            label_iterator,
            unlabel_iterator,
        )

    def adello_predict(self, x: torch.FloatTensor):

        logits, feat = self.get_feature(x)

        return {"logits": logits, "feat": feat}

    def compute_labeled_prior(self, label_loader):
        lb_class_dist = [0 for _ in range(self.backbone.class_num)]

        for c in label_loader.dataset.targets:
            lb_class_dist[c] += 1

        lb_class_dist = np.array(lb_class_dist)

        # normalize distribution
        p_data = torch.tensor(lb_class_dist / lb_class_dist.sum()).to(self.local_rank)
        return p_data, len(label_loader.dataset)

    def compute_unlabeled_prior(self, unlabel_loader):
        ulb_class_dist = None

        return ulb_class_dist, len(unlabel_loader.dataset)

    # TODO
    def compute_prob(self, u_logits, lb_in_ulb_mask=None, **kwargs):
        probs = u_logits.softmax(-1)

        if lb_in_ulb_mask is not None:
            mask_unl_data = lb_in_ulb_mask < 1
            if mask_unl_data.sum() > 0:  # there is true unlabeled data
                delta_p = probs[mask_unl_data].mean(dim=0)
            else:
                delta_p = None
        else:
            delta_p = probs.mean(dim=0)

        delta_p = (
            delta_p if (delta_p is not None) else self.p_hat
        )  # it doesn't update when delta_p is None
        self.p_hat = (
            self.ema_p * self.p_hat.to(delta_p.device) + (1 - self.ema_p) * delta_p
        )

        return probs


import torch
import torch.nn as nn
from torch.nn import functional as F


def ce_loss(logits, targets, reduction="none"):
    """
    cross entropy loss in pytorch.

    Args:
        logits: logit values, shape=[Batch size, # of classes]
        targets: integer or vector, shape=[Batch size] or [Batch size, # of classes]
        # use_hard_labels: If True, targets have [Batch size] shape with int values. If False, the target is vector (default True)
        reduction: the reduction argument
    """
    if logits.shape == targets.shape:
        # one-hot target
        log_pred = F.log_softmax(logits, dim=-1)
        nll_loss = torch.sum(-targets * log_pred, dim=1)
        if reduction == "none":
            return nll_loss
        else:
            return nll_loss.mean()
    else:
        log_pred = F.log_softmax(logits, dim=-1)
        return F.nll_loss(log_pred, targets, reduction=reduction)


class CELoss(nn.Module):
    """
    Wrapper for ce loss
    """

    def forward(self, logits, targets, reduction="none"):
        return ce_loss(logits, targets, reduction)


class FlexDASupervisedLoss(CELoss):
    def __init__(
        self,
        alpha_min=0.1,
        k=2.0,
        p_data=None,
        p_hat=None,
        p_target=None,
        target_mode="adello",
        use_epochs=True,
        num_samples_lb=None,
        num_samples_ulb=None,
    ):
        super().__init__()
        self.progressive_alpha_min = alpha_min
        self.progressive_k = k

        self.p_data = p_data
        self.p_hat = p_hat
        self.p_target = p_target
        self.target_mode = target_mode

        self.cte_iter = None
        self.max_iter = None
        self.num_iter_per_epoch = None
        self.use_epochs = use_epochs
        self.num_samples_lb = num_samples_lb
        self.num_samples_ulb = num_samples_ulb

    def set_params(
        self, p_hat=None, cte_iter=None, max_iter=None, num_iter_per_epoch=None
    ):
        self.p_hat = p_hat
        self.cte_iter = cte_iter
        self.max_iter = max_iter
        self.num_iter_per_epoch = num_iter_per_epoch

    def get_progress_values(self):
        if self.use_epochs:
            cte_epoch = int(self.cte_iter // self.num_iter_per_epoch)
            max_epoch = int(np.ceil(self.max_iter // self.num_iter_per_epoch))
            return cte_epoch, max_epoch
        else:
            return self.cte_iter, self.max_iter

    def get_alpha_factor(self):
        cte_val, max_val = self.get_progress_values()
        return compute_alpha_factor(
            cte_val, max_val, a_min=self.progressive_alpha_min, k=self.progressive_k
        )

    def forward(self, logits, targets, reduction="mean", T_src=None):
        assert self.target_mode in ["adello", "adello_gt"]

        p_target = self.get_target_dist()

        cte_val, max_val = self.get_progress_values()

        distr_ratio = compute_adello_adjustment_dist(
            self.p_data,
            p_target,
            cte_val,
            max_val,
            a_min=self.progressive_alpha_min,
            k=self.progressive_k,
        )

        adjusted_logits = logits + torch.log(distr_ratio).to(logits.device)

        if T_src is not None:
            adjusted_logits = adjusted_logits / T_src

        return super().forward(adjusted_logits, targets, reduction=reduction)

    def get_target_dist(self):
        assert self.target_mode in ["adello", "adello_gt"]

        if self.target_mode in ["adello"]:
            p_target = self.p_hat
        else:
            p_target = self.p_target

        return p_target


def compute_alpha_factor(current_epoch, max_epoch, a_min=0.0, k=1.0, a_max=1.0):
    return a_max - (a_max - a_min) * (current_epoch / max_epoch) ** k


def compute_adello_adjustment_dist(
    current_dist,
    p_target,
    current_epoch,
    max_epoch,
    a_min=0.1,
    k=2.0,
    a_max=1.0,
    eps=1e-9,
):
    a_factor = compute_alpha_factor(
        current_epoch, max_epoch, a_min=a_min, k=k, a_max=a_max
    )

    # normalization ensures the argument sums to 1
    target_dist = p_target**a_factor
    target_dist = target_dist / target_dist.sum(dim=-1)
    return (current_dist.to(target_dist.device) + eps) / (target_dist + eps)


def consistency_loss(logits, targets, name="ce", mask=None):
    """
    consistency regularization loss in semi-supervised learning.

    Args:
        logits: logit to calculate the loss on and back-propagation, usually being the strong-augmented unlabeled samples
        targets: pseudo-labels (either hard label or soft label)
        name: use cross-entropy ('ce') or mean-squared-error ('mse') to calculate loss
        mask: masks to mask-out samples when calculating the loss, usually being used as confidence-masking-out
    """

    assert name in ["ce", "mse"]

    if name == "mse":
        probs = torch.softmax(logits, dim=-1)
        loss = F.mse_loss(probs, targets, reduction="none").mean(dim=1)
    else:
        loss = ce_loss(logits, targets, reduction="none")

    if mask is not None:
        # mask must not be boolean type
        loss = loss * mask

    return loss.mean()


class ConsistencyLoss(nn.Module):
    """
    Wrapper for consistency loss
    """

    def forward(self, logits, targets, name="ce", mask=None):
        return consistency_loss(logits, targets, name, mask)


class FlexDAConsistencyLoss(ConsistencyLoss):
    def __init__(
        self,
        alpha_min=0.1,
        k=2.0,
        p_data=None,
        p_hat=None,
        p_target=None,
        target_mode="adello",
        use_epochs=True,
        num_samples_lb=None,
        num_samples_ulb=None,
    ):
        super().__init__()
        self.progressive_alpha_min = alpha_min
        self.progressive_k = k

        self.p_data = p_data
        self.p_hat = p_hat
        self.p_target = p_target
        self.target_mode = target_mode

        self.cte_iter = None
        self.max_iter = None
        self.num_iter_per_epoch = None
        self.use_epochs = use_epochs
        self.num_samples_lb = num_samples_lb
        self.num_samples_ulb = num_samples_ulb

    def set_params(
        self, p_hat=None, cte_iter=None, max_iter=None, num_iter_per_epoch=None
    ):
        self.p_hat = p_hat
        self.cte_iter = cte_iter
        self.max_iter = max_iter
        self.num_iter_per_epoch = num_iter_per_epoch

    def get_progress_values(self):
        if self.use_epochs:
            cte_epoch = int(self.cte_iter // self.num_iter_per_epoch)
            max_epoch = int(self.max_iter // self.num_iter_per_epoch)
            return cte_epoch, max_epoch
        else:
            return self.cte_iter, self.max_iter

    def get_alpha_factor(self):
        cte_val, max_val = self.get_progress_values()
        return compute_alpha_factor(
            cte_val, max_val, a_min=self.progressive_alpha_min, k=self.progressive_k
        )

    def forward(self, logits, targets, name="ce", mask=None, T_src=None, T_tgt=None):
        assert self.target_mode in ["adello", "adello_gt"]

        p_target = self.get_target_dist()

        cte_val, max_val = self.get_progress_values()

        distr_ratio = compute_adello_adjustment_dist(
            self.p_hat,
            p_target,
            cte_val,
            max_val,
            a_min=self.progressive_alpha_min,
            k=self.progressive_k,
        )

        adjusted_logits = logits + torch.log(distr_ratio).to(logits.device)
        adjusted_targets = targets

        if (T_src is not None) or (T_tgt is not None):
            assert adjusted_targets.dim() > 1

            T_src = T_src if (T_src is not None) else 1.0
            T_tgt = T_tgt if (T_tgt is not None) else 1.0

            adjusted_logits = adjusted_logits / T_src
            adjusted_targets = adjusted_targets ** (1.0 / T_tgt)
            adjusted_targets = adjusted_targets / adjusted_targets.sum(
                dim=-1, keepdim=True
            )

        return super().forward(adjusted_logits, adjusted_targets, name, mask)

    def get_target_dist(self):
        assert self.target_mode in ["adello", "adello_gt"]

        if self.target_mode in ["adello_gt"]:
            p_target = self.p_target
        elif self.target_mode in ["adello"]:
            p_target = self.p_hat
        else:
            p_target = None

        return p_target


class Hook:
    stages = (
        "before_run",
        "before_train_epoch",
        "before_train_step",
        "after_train_step",
        "after_train_epoch",
        "after_run",
    )

    def before_train_epoch(self, algorithm):
        pass

    def after_train_epoch(self, algorithm):
        pass

    def before_train_step(self, algorithm):
        pass

    def after_train_step(self, algorithm):
        pass

    def before_run(self, algorithm):
        pass

    def after_run(self, algorithm):
        pass

    def every_n_epochs(self, algorithm, n):
        return (algorithm.epoch + 1) % n == 0 if n > 0 else False

    def every_n_iters(self, algorithm, n):
        return (algorithm.it + 1) % n == 0 if n > 0 else False

    def end_of_epoch(self, algorithm):
        return algorithm.it + 1 % len(algorithm.data_loader["train_lb"]) == 0

    def is_last_epoch(self, algorithm):
        return algorithm.epoch + 1 == algorithm.epochs

    def is_last_iter(self, algorithm):
        return algorithm.it + 1 == algorithm.num_train_iter


def compute_divergences(p1, p2):
    fwd_kl_div = F.kl_div(p1.log(), p2.to(p1.device), reduction="sum")
    bwd_kl_div = F.kl_div(p2.log().to(p1.device), p1, reduction="sum")
    js_div = (fwd_kl_div + bwd_kl_div) / 2.0
    return fwd_kl_div, bwd_kl_div, js_div


class ADELLOHook(Hook):

    def before_train_step(self, algorithm):
        algorithm.consistency_loss.set_params(
            p_hat=algorithm.get_p_hat(),
            cte_iter=algorithm.it,
            max_iter=algorithm.num_train_iter,
            num_iter_per_epoch=algorithm.num_iter_per_epoch,
        )
        algorithm.ce_loss.set_params(
            p_hat=algorithm.get_p_hat(),
            cte_iter=algorithm.it,
            max_iter=algorithm.num_train_iter,
            num_iter_per_epoch=algorithm.num_iter_per_epoch,
        )
        algorithm.smooth_factor = algorithm.consistency_loss.get_alpha_factor()

    def after_train_step(self, algorithm):
        algorithm.log_dict["train/cte_alpha"] = (
            algorithm.consistency_loss.get_alpha_factor()
        )

        if self.every_n_iters(algorithm, algorithm.num_eval_iter) or self.is_last_iter(
            algorithm
        ):
            self._track_unl_prior_estimation(algorithm)

        if algorithm.args.eval_pl_accuracy and (
            self.every_n_iters(algorithm, algorithm.num_eval_iter)
            or self.is_last_iter(algorithm)
        ):
            algorithm.print_fn("evaluating unlabeled data...")
            eval_dict = algorithm.evaluate(
                "eval_ulb_privileged", return_logits=False, track_mean_acc=False
            )
            algorithm.log_dict.update(eval_dict)

    def _track_unl_prior_estimation(self, algorithm):
        p_hat = algorithm.get_p_hat()
        p_data = algorithm.p_data
        p_unif = torch.ones_like(p_hat) / algorithm.num_classes
        gt_prior = algorithm.gt_u_prior
        p_target = algorithm.get_p_target()

        if p_hat is not None:
            fwd_kl_div_p_data, _, js_div_p_data = compute_divergences(p_hat, p_data)
            algorithm.log_dict["train/kl_div_ulb_vs_lb_prior"] = fwd_kl_div_p_data
            fwd_kl_div_p_data_tgt, _, _ = compute_divergences(p_target, p_data)
            algorithm.log_dict["train/kl_div_tgt_vs_lb_prior"] = fwd_kl_div_p_data_tgt

            fwd_kl_div_p_unif, _, _ = compute_divergences(p_hat, p_unif)
            algorithm.log_dict["train/kl_div_ulb_vs_unif"] = fwd_kl_div_p_unif
            fwd_kl_div_p_unif_tgt, _, _ = compute_divergences(p_target, p_unif)
            algorithm.log_dict["train/kl_div_tgt_vs_unif"] = fwd_kl_div_p_unif_tgt

            fwd_kl_div_p_data_vs_unif, _, js_div_p_data_vs_unif = compute_divergences(
                p_data, p_unif
            )
            algorithm.log_dict["train/kl_div_p_data_vs_unif"] = (
                fwd_kl_div_p_data_vs_unif
            )
            algorithm.log_dict["train/abs_diff_kl_div"] = torch.abs(
                fwd_kl_div_p_data_vs_unif - fwd_kl_div_p_data
            )
            algorithm.log_dict["train/abs_diff_js_div"] = torch.abs(
                js_div_p_data_vs_unif - js_div_p_data
            )

            if gt_prior is not None:
                fwd_kl_div, _, _ = compute_divergences(p_hat, gt_prior)
                algorithm.log_dict["train/kl_div_ulb_prior"] = fwd_kl_div
                fwd_kl_div_tgt, _, _ = compute_divergences(p_target, gt_prior)
                algorithm.log_dict["train/kl_div_tgt_vs_gt"] = fwd_kl_div_tgt

            with np.printoptions(threshold=np.inf):
                algorithm.print_fn(
                    "ADELLO unlabeled prior:\n" + np.array_str(p_hat.cpu().numpy())
                )
