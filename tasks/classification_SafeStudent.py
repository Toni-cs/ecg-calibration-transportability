import collections
import os

import torch
import torch.distributed as dist
import torch.nn as nn
from rich.progress import Progress
from sklearn.metrics import (accuracy_score, f1_score, precision_score,
                             recall_score)
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
        save_every,
        tau,
        T,
        lambda_one,
        lambda_two,
        ema_factor,
        pretrain_train_split,
        n_bins,
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

        # Supervised training
        best_eval_acc = -float("inf")
        best_epoch = 0

        """Teacher Pretraining"""
        for epoch in range(1, epochs // pretrain_train_split + 1):

            # training unlabeled data logging
            self.log_unlabeled_data(
                unlabel_dataset=train_set[1], current_epoch=epoch, T=T, tau=tau
            )

            train_history = self.pretrain(l_loader, n_bins=n_bins)
            eval_history = self.evaluate(eval_loader, n_bins)

            epoch_history = collections.defaultdict(dict)
            for k, v1 in train_history.items():
                epoch_history[k]["pretrain"] = v1
                try:
                    v2 = eval_history[k]
                    epoch_history[k]["pretrain_eval"] = v2
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

            # Write logs
            log = make_epoch_description(
                history=epoch_history,
                current=epoch,
                total=epochs,
                best=best_epoch,
            )
            if logger is not None:
                logger.info(log)

        # 사전학습 된 teacher 불러오기
        self.load_model_from_checkpoint(ckpt)

        def create_model(model, no_grad=False):
            from copy import deepcopy

            s_model = deepcopy(model)
            if no_grad:
                for param in s_model.parameters():
                    param.detach_()
            return s_model

        self.teacher = create_model(self.backbone, no_grad=True)
        self.teacher.eval()

        """Student Training: Iterative Optimization"""
        for epoch in range(epochs // pretrain_train_split + 1, epochs + 1):

            # training unlabeled data logging
            self.log_unlabeled_data(
                unlabel_dataset=train_set[1], current_epoch=epoch, T=T, tau=tau
            )

            train_history = self.sst_train(
                l_loader,
                unlabel_loader,
                n_bins=n_bins,
                tau=tau,
                T=T,
                lambda_one=lambda_one,
                lambda_two=lambda_two,
            )
            eval_history = self.evaluate(eval_loader, n_bins)

            """EMA update teacher model"""
            if epoch % 10 == 0:
                for emp_p, p in zip(
                    self.teacher.parameters(), self.backbone.parameters()
                ):
                    emp_p.data = ema_factor * emp_p.data + (1 - ema_factor) * p.data

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
    def log_unlabeled_data(self, unlabel_dataset, current_epoch, T, tau):

        loader = DataLoader(
            dataset=unlabel_dataset,
            batch_size=128,
            drop_last=False,
            shuffle=False,
            num_workers=4,
        )

        self._set_learning_phase(train=False)

        with Progress(transient=True, auto_refresh=False) as pg:
            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Extracting...", total=len(loader))
            for batch_idx, data in enumerate(loader):

                x = data["x_ulb_w"].cuda(self.local_rank)
                y = data["y_ulb"].cuda(self.local_rank)

                unlabel_weak_logit = self.predict(x)

                """Seen and Unseen Classes Identiifcation"""
                ed_value = self.ed(
                    unlabel_weak_logit, t=T
                )  # Collect ED for unlabeled samples by teacher and Eq. (4)

                gt_idx = y < self.backbone.class_num

                if batch_idx == 0:
                    gt_all = gt_idx
                    logits_all = unlabel_weak_logit
                    labels_all = y
                    ed_values = ed_value
                else:
                    gt_all = torch.cat([gt_all, gt_idx], 0)
                    logits_all = torch.cat([logits_all, unlabel_weak_logit], 0)
                    labels_all = torch.cat([labels_all, y], 0)
                    ed_values = torch.cat([ed_values, ed_value], 0)

                if self.local_rank == 0:
                    desc = f"[bold pink] Extracting .... [{batch_idx+1}/{len(loader)}] "
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

        select_all = ed_values > tau

        select_accuracy = accuracy_score(
            gt_all.cpu().numpy(), select_all.cpu().numpy()
        )  # positive : inlier, negative : out of distribution
        select_precision = precision_score(
            gt_all.cpu().numpy(), select_all.cpu().numpy()
        )
        select_recall = recall_score(gt_all.cpu().numpy(), select_all.cpu().numpy())
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
            self.writer.add_scalar(
                "Selected precision", select_precision, global_step=current_epoch
            )
            self.writer.add_scalar(
                "Selected recall", select_recall, global_step=current_epoch
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

    def pretrain(self, label_loader, n_bins):
        """Training defined for a single epoch."""

        iteration = len(label_loader)

        self._set_learning_phase(train=True)
        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Training...", total=iteration)

            for i, (data_lb) in enumerate(label_loader):
                with torch.cuda.amp.autocast(self.mixed_precision):

                    x_lb_w = data_lb["x_lb"].to(self.local_rank)
                    y_lb = data_lb["y_lb"].to(self.local_rank)

                    logits = self.predict(x_lb_w)
                    loss = self.loss_function(logits, y_lb)

                if self.scaler is not None:
                    self.scaler.scale(loss).backward()
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    loss.backward()
                    self.optimizer.step()

                self.optimizer.zero_grad()

                result["loss"][i] = loss.detach()
                result["top@1"][i] = TopKAccuracy(k=1)(logits, y_lb).detach()
                result["ece"][i] = self.get_ece(
                    preds=logits.softmax(dim=1).detach().cpu().numpy(),
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

            return {k: v.mean().item() for k, v in result.items()}

    def sst_train(
        self, label_loader, unlabel_loader, n_bins, tau, T, lambda_one, lambda_two
    ):
        """Training defined for a single epoch."""

        iteration = len(unlabel_loader)

        self._set_learning_phase(train=True)
        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "loss_cbe": torch.zeros(iteration, device=self.local_rank),
            "loss_ucd": torch.zeros(iteration, device=self.local_rank),
            "loss_ce": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Training...", total=iteration)

            for i, (data_lb, data_ulb) in enumerate(zip(label_loader, unlabel_loader)):
                with torch.cuda.amp.autocast(self.mixed_precision):

                    x_lb_w = data_lb["x_lb"].to(self.local_rank)
                    y_lb = data_lb["y_lb"].to(self.local_rank)

                    x_ulb_w = data_ulb["x_ulb_w"].to(self.local_rank)
                    x_ulb_s = data_ulb["x_ulb_s"].to(self.local_rank)

                    with torch.no_grad():
                        unlabel_weak_logit = self.teacher(x_ulb_w)

                    full_logits = self.predict(torch.cat([x_lb_w, x_ulb_s]))
                    label_weak_logit, unlabel_strong_logit = full_logits.chunk(2)

                    """Seen and Unseen Classes Identiifcation"""
                    ed_values = self.ed(
                        unlabel_weak_logit, t=T
                    )  # Collect ED for unlabeled samples by teacher and Eq. (4)
                    seen, unseen = ed_values > tau, ed_values < max(
                        tau - 0.1, 0
                    )  # Obtain seen-class and unseen-class by Eq. (2)

                    """Seen-Class Learning"""
                    pseudo_label, teacher_seen_probs = unlabel_weak_logit[seen].argmax(
                        1
                    ), unlabel_weak_logit[seen].softmax(1)

                    l_cbe = torch.tensor(0).cuda(self.local_rank)
                    if seen.sum().item() != 0:
                        l_cbe_1 = torch.nn.functional.cross_entropy(
                            unlabel_strong_logit[seen], pseudo_label
                        )
                        l_cbe_2 = torch.nn.functional.kl_div(
                            unlabel_strong_logit[seen].log_softmax(1),
                            teacher_seen_probs,
                            reduction="batchmean",
                        )

                        l_cbe = l_cbe_1 + l_cbe_2

                    """Unseen-Class Label Distribution Learning"""
                    l_ucd_weighted = torch.tensor(0).cuda(self.local_rank)
                    if unseen.sum().item() != 0:
                        student_unseen_probs = unlabel_strong_logit[unseen].softmax(1)
                        uniform = (
                            torch.ones_like(student_unseen_probs)
                            / self.backbone.class_num
                        )
                        l_ucd = torch.nn.functional.kl_div(
                            student_unseen_probs.log(), uniform, reduction="none"
                        ).sum(1)

                        weight = (
                            (
                                (ed_values[unseen].max() - ed_values[unseen])
                                / (ed_values[unseen].max() + 1e-10)
                            ).exp()
                            if unseen.sum() != 0
                            else 0.0
                        )
                        l_ucd_weighted = (weight * l_ucd).mean()

                    l_ce = torch.nn.functional.cross_entropy(label_weak_logit, y_lb)

                    """Obtain Final Loss"""
                    loss = (
                        l_ce + lambda_one * l_cbe + lambda_two * l_ucd_weighted
                    )  # Eq. (11)

                if self.scaler is not None:
                    self.scaler.scale(loss).backward()
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    loss.backward()
                    self.optimizer.step()

                self.optimizer.zero_grad()

                result["loss"][i] = loss.detach()
                result["top@1"][i] = TopKAccuracy(k=1)(label_weak_logit, y_lb).detach()
                result["loss_cbe"][i] = l_cbe.detach()
                result["loss_ucd"][i] = l_ucd_weighted.detach()
                result["loss_ce"][i] = l_ce.detach()
                result["ece"][i] = self.get_ece(
                    preds=label_weak_logit.softmax(dim=1).detach().cpu().numpy(),
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

        return {k: v.mean().item() for k, v in result.items()}

    @staticmethod
    def ed(logits, t):

        assert logits.dim() == 2, "logits = [Batch size, Number of seen classes]"

        ed = logits.div(t).exp().sum(1).log().mul(t) - (
            logits.div(t).exp().sum(1) - logits.div(t).exp().max(1)[0] + 1e-5
        ).log().mul(t)

        return ed


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
