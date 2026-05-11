import collections
import math
import os

import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from rich.progress import Progress
from sklearn.manifold import TSNE
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter

plt.style.use("bmh")

from tasks.base import Task
from utils import RandomSampler, TopKAccuracy
from utils.logging import make_epoch_description
from utils.optimization import (WeightSWA, get_multi_step_scheduler,
                                get_optimizer)


class Classification(Task):
    def __init__(self, backbone: nn.Module):
        super(Classification, self).__init__()

        self.backbone = backbone

        self.scaler = None
        self.optimizer = None
        self.scheduler = None
        self.loss_function = None
        self.writer = None

        self.prepared = False

    def prepare(
        self,
        ckpt_dir: str,
        optimizer: str,
        learning_rate: float,
        iterations: int,
        batch_size: int,
        num_workers: int,
        local_rank: int,
        mixed_precision: bool,
        gamma: float,
        milestones: list,
        weight_decay: float,
        **kwargs,
    ):  # pylint: disable=unused-argument
        """Add function docstring."""

        # Set attributes
        self.ckpt_dir = ckpt_dir  # pylint: disable=attribute-defined-outside-init
        self.iterations = iterations  # pylint: disable=attribute-defined-outside-init
        self.batch_size = batch_size  # pylint: disable=attribute-defined-outside-init
        self.milestones = milestones  # pylint: disable=attribute-defined-outside-init
        self.gamma = gamma  # pylint: disable=attribute-defined-outside-init
        self.num_workers = num_workers  # pylint: disable=attribute-defined-outside-init
        self.local_rank = local_rank  # pylint: disable=attribute-defined-outside-init
        self.mixed_precision = (
            mixed_precision  # pylint: disable=attribute-defined-outside-init
        )
        self.learning_rate = learning_rate

        self.backbone.to(local_rank)

        # Mixed precision training (optional)
        self.scaler = torch.cuda.amp.GradScaler() if mixed_precision else None

        # Optimization (TODO: freeze)
        self.optimizer = get_optimizer(
            params=[
                {"params": self.backbone.parameters()},
            ],
            name=optimizer,
            lr=learning_rate,
            weight_decay=weight_decay,
        )

        # Stochastic weight average On
        swa_on = kwargs.get("swa_on", False)
        if swa_on:

            def create_model(model, no_grad=False):
                from copy import deepcopy

                s_model = deepcopy(model)
                if no_grad:
                    for param in s_model.parameters():
                        param.detach_()
                return s_model

            self.swa_model = create_model(self.backbone, no_grad=True)
            self.swa_model.eval()

            self.swa_opt = WeightSWA(self.swa_model)

        self.scheduler = get_multi_step_scheduler(
            optimizer=self.optimizer, milestones=self.milestones, gamma=self.gamma
        )

        # Loss function
        self.loss_function = nn.CrossEntropyLoss()

        # TensorBoard
        self.writer = SummaryWriter(ckpt_dir) if local_rank == 0 else None

        # Ready to train!
        self.prepared = True

    def run(
        self, train_set, eval_set, test_set, open_test_set, save_every, n_bins, **kwargs
    ):  # pylint: disable=unused-argument

        batch_size = self.batch_size
        num_workers = self.num_workers

        if not self.prepared:
            raise RuntimeError("Training not prepared.")

        # DataLoader (train, val, test)

        ## labeled
        sampler = RandomSampler(len(train_set[0]), self.iterations * self.batch_size)
        train_l_loader = DataLoader(
            train_set[0],
            batch_size=batch_size,
            sampler=sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=True,
        )
        train_l_iterator = iter(train_l_loader)

        ## unlabeled
        unlabel_loader = DataLoader(
            train_set[1],
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=True,
        )

        eval_loader = DataLoader(
            eval_set,
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=True,
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

        epochs = self.iterations // save_every
        self.trained_iteration = 0

        for epoch in range(1, epochs + 1):

            # Train & evaluate
            train_history, train_l_iterator = self.train(
                train_l_iterator, iteration=save_every, n_bins=n_bins
            )
            eval_history = self.evaluate(eval_loader, n_bins)
            if enable_plot:
                self.log_plot_history(
                    data_loader=unlabel_loader,
                    time=self.trained_iteration,
                    name="unlabel",
                )
                self.log_plot_history(
                    data_loader=open_test_loader,
                    time=self.trained_iteration,
                    name="open+test",
                )

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
                import os
                os.makedirs(self.ckpt_dir, exist_ok=True)
                for k, v in epoch_history.items():
                    for k_, v_ in v.items():
                        self.writer.add_scalar(f"{k}_{k_}", v_, global_step=epoch)
                if self.scheduler is not None:
                    lr = self.scheduler.get_last_lr()[0]
                    self.writer.add_scalar("lr", lr, global_step=epoch)

            # Save best model checkpoint and Logging
            eval_acc = eval_history["top@1"]
            if eval_acc > best_eval_acc:
                best_eval_acc = eval_acc
                best_epoch = epoch
                if self.local_rank == 0:
                    ckpt = os.path.join(self.ckpt_dir, "ckpt.best.pth.tar")
                    self.save_checkpoint(ckpt, epoch=epoch)

                test_history = self.evaluate(test_loader, n_bins=n_bins)
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

    def train(self, label_iterator, iteration, n_bins):
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
                with torch.cuda.amp.autocast(self.mixed_precision):
                    l_batch = next(label_iterator)

                    x = l_batch["x"].to(self.local_rank)
                    y = l_batch["y"].to(self.local_rank)
                    logits = self.predict(x)
                    loss = self.loss_function(logits, y.long())

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
                result["top@1"][i] = TopKAccuracy(k=1)(logits, y).detach()
                result["ece"][i] = self.get_ece(
                    preds=logits.softmax(dim=1).detach().cpu().numpy(),
                    targets=y.cpu().numpy(),
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

        return {k: v.mean().item() for k, v in result.items()}, label_iterator

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

                logits = self.predict(x)
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

        ece_results = self.get_ece(
            preds=preds.softmax(dim=1).numpy(),
            targets=trues.numpy(),
            n_bins=n_bins,
            plot=False,
        )
        result["ece"][0] = ece_results[0]
        result["ace"][0] = self.get_ace(
            preds=preds.softmax(dim=1).numpy(),
            targets=trues.numpy(),
            n_bins=n_bins,
        )
        result["sce"][0] = self.get_sce(
            preds=preds.softmax(dim=1).numpy(),
            targets=trues.numpy(),
            n_bins=n_bins,
        )

        return {k: v.mean().item() for k, v in result.items()}

    @torch.no_grad()
    def evaluate_open_set(self, data_loader):
        self._set_learning_phase(train=False)

        ood_scores, ood_targets = [], []
        for batch in data_loader:
            x = batch["x"].to(self.local_rank)
            y = batch["y"].to(self.local_rank)

            probs = self.get_open_set_probs(x)
            ood_scores.append((1.0 - probs.max(dim=1)[0]).cpu())
            ood_targets.append((y >= self.backbone.class_num).long().cpu())

        ood_scores = torch.cat(ood_scores).numpy()
        ood_targets = torch.cat(ood_targets).numpy()
        if len(np.unique(ood_targets)) < 2:
            auroc = float("nan")
        else:
            auroc = roc_auc_score(ood_targets, ood_scores)
        return {"auroc": float(auroc)}

    def get_open_set_probs(self, x: torch.FloatTensor):
        return self.predict(x).softmax(dim=1)

    def predict(self, x: torch.FloatTensor):
        """Make a prediction provided a batch of samples."""
        return self.backbone(x)

    def get_feature(self, x: torch.FloatTensor):
        """Make a prediction provided a batch of samples."""
        return self.backbone(x, return_feature=True)

    def _set_learning_phase(self, train=False):
        if train:
            self.backbone.train()
        else:
            self.backbone.eval()

    def save_checkpoint(self, path: str, **kwargs):
        ckpt = {
            "backbone": self.backbone.state_dict(),
            "optimizer": self.optimizer.state_dict(),
        }
        if kwargs:
            ckpt.update(kwargs)
        torch.save(ckpt, path)

    def load_model_from_checkpoint(self, path: str):
        ckpt = torch.load(path)
        self.backbone.load_state_dict(ckpt["backbone"])
        self.optimizer.load_state_dict(ckpt["optimizer"])

    def load_history_from_checkpoint(self, path: str):
        ckpt = torch.load(path)
        del ckpt["backbone"]
        del ckpt["optimizer"]
        return ckpt

    @staticmethod
    def get_ece(preds: np.array, targets: np.array, n_bins: int = 15, **kwargs):

        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]

        confidences, predictions = np.max(preds, 1), np.argmax(preds, 1)
        accuracies = predictions == targets

        ece = 0.0
        avg_confs_in_bins, x_ticks = [], []
        acc_ticks, confs_ticks = [], []
        y_ticks_second_ticks = []
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            in_bin = np.logical_and(confidences > bin_lower, confidences <= bin_upper)
            prop_in_bin = np.mean(in_bin)
            if prop_in_bin > 0:
                accuracy_in_bin = np.mean(accuracies[in_bin])
                avg_confidence_in_bin = np.mean(confidences[in_bin])
                delta = avg_confidence_in_bin - accuracy_in_bin

                avg_confs_in_bins.append(delta)
                acc_ticks.append(accuracy_in_bin)
                confs_ticks.append(avg_confidence_in_bin)
                x_ticks.append((bin_lower + bin_upper) / 2)
                y_ticks_second_ticks.append(prop_in_bin)

                ece += np.abs(delta) * prop_in_bin
            else:
                avg_confs_in_bins.append(None)
                acc_ticks.append(None)
                confs_ticks.append(None)
                x_ticks.append(None)
                y_ticks_second_ticks.append(None)

        return ece, {
            tick: accuracy
            for tick, accuracy in zip(bin_boundaries.round(2)[:-1], acc_ticks)
        }

    @staticmethod
    def get_sce(preds: np.array, targets: np.array, n_bins: int = 15):
        preds = np.asarray(preds)
        targets = np.asarray(targets)
        num_classes = preds.shape[1]
        bin_boundaries = np.linspace(0, 1, n_bins + 1)

        sce = 0.0
        num_samples = max(len(targets), 1)
        for class_idx in range(num_classes):
            class_confidences = preds[:, class_idx]
            class_targets = (targets == class_idx).astype(np.float32)
            for bin_lower, bin_upper in zip(bin_boundaries[:-1], bin_boundaries[1:]):
                in_bin = np.logical_and(
                    class_confidences > bin_lower, class_confidences <= bin_upper
                )
                if not np.any(in_bin):
                    continue
                accuracy_in_bin = np.mean(class_targets[in_bin])
                avg_confidence_in_bin = np.mean(class_confidences[in_bin])
                sce += (
                    np.abs(avg_confidence_in_bin - accuracy_in_bin)
                    * np.sum(in_bin)
                    / num_samples
                )
        return float(sce / num_classes)

    @staticmethod
    def get_ace(preds: np.array, targets: np.array, n_bins: int = 15):
        preds = np.asarray(preds)
        targets = np.asarray(targets)
        num_classes = preds.shape[1]

        ace = 0.0
        valid_bins = 0
        for class_idx in range(num_classes):
            class_confidences = preds[:, class_idx]
            class_targets = (targets == class_idx).astype(np.float32)

            sorted_idx = np.argsort(class_confidences)
            sorted_confidences = class_confidences[sorted_idx]
            sorted_targets = class_targets[sorted_idx]

            for bin_indices in np.array_split(np.arange(len(sorted_confidences)), n_bins):
                if len(bin_indices) == 0:
                    continue
                ace += np.abs(
                    np.mean(sorted_confidences[bin_indices])
                    - np.mean(sorted_targets[bin_indices])
                )
                valid_bins += 1

        return float(ace / max(valid_bins, 1))

    @torch.no_grad()
    def log_plot_history(self, data_loader, time, name, **kwargs):
        """Evaluation defined for a single epoch."""

        steps = len(data_loader)
        self._set_learning_phase(train=False)

        return_results = kwargs.get("return_results", False)
        get_results = kwargs.get("get_results", None)

        with Progress(transient=True, auto_refresh=False) as pg:

            if self.local_rank == 0:
                task = pg.add_task(f"[bold red] Plotting...", total=steps)

            pred, true, IDX, FEATURE = [], [], [], []
            for i, batch in enumerate(data_loader):

                try:
                    x = batch["x"].to(self.local_rank)
                except:
                    x = batch["weak_img"].to(self.local_rank)
                y = batch["y"].to(self.local_rank)
                idx = batch["idx"].to(self.local_rank)

                logits, feature = self.get_feature(x)
                true.append(y.cpu())
                pred.append(logits.cpu())
                FEATURE.append(feature.squeeze().cpu())
                IDX += [idx]

                if self.local_rank == 0:
                    desc = f"[bold green] [{i+1}/{steps}]: Having feature vector..."
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

        # preds, pred are logit vectors
        preds, trues = torch.cat(pred, axis=0), torch.cat(true, axis=0)
        FEATURE = torch.cat(FEATURE)
        if get_results is not None:

            # get_results=[label_preds, label_trues, label_FEATURE]

            labels_unlabels = torch.cat(
                [torch.ones_like(get_results[1]), torch.zeros_like(trues)]
            )
            preds = torch.cat([get_results[0], preds], axis=0)
            trues = torch.cat([get_results[1], trues], axis=0)
            FEATURE = torch.cat([get_results[2], FEATURE], axis=0)
        snd_feature = TSNE(learning_rate=20).fit_transform(FEATURE)
        colors = ["b", "g", "r", "c", "m", "y", "k", "w", "orange", "purple"]

        if len(trues.unique()) != preds.shape[1]:
            plt.figure(figsize=(24, 24))
            plt.subplot(2, 2, 1)
            if get_results is not None:
                for c in trues.unique()[: preds.shape[1]]:
                    plt.scatter(
                        snd_feature[(labels_unlabels == 1) & (trues == c), 0],
                        snd_feature[(labels_unlabels == 1) & (trues == c), 1],
                        label=f"{c.item()}-label",
                        c=colors[c],
                        marker="o",
                    )
                    plt.scatter(
                        snd_feature[(labels_unlabels == 0) & (trues == c), 0],
                        snd_feature[(labels_unlabels == 0) & (trues == c), 1],
                        label=f"{c.item()}-unlabel",
                        c=colors[c],
                        marker="*",
                    )
            else:
                for c in trues.unique()[: preds.shape[1]]:
                    plt.scatter(
                        snd_feature[trues == c, 0],
                        snd_feature[trues == c, 1],
                        label=c.item(),
                        c=colors[c],
                    )
            plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=4)
            plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
            plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
            plt.title("Via true labels - IN")

            plt.subplot(2, 2, 2)
            for c in trues.unique()[preds.shape[1] :]:
                plt.scatter(
                    snd_feature[trues == c, 0],
                    snd_feature[trues == c, 1],
                    label=c.item(),
                    c=colors[c],
                )
            plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=4)
            plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
            plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
            plt.title("Via true labels - OOD")

            plt.subplot(2, 2, 3)
            if get_results is not None:
                for idx, c in enumerate(range(preds.shape[1])):
                    plt.scatter(
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 1),
                            0,
                        ],
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 1),
                            1,
                        ],
                        label=f"{c}-label",
                        c=colors[idx],
                        marker="o",
                    )

                    plt.scatter(
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 0),
                            0,
                        ],
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 0),
                            1,
                        ],
                        label=f"{c}-unlabel",
                        c=colors[idx],
                        marker="*",
                    )
            else:
                for idx, c in enumerate(range(preds.shape[1])):
                    plt.scatter(
                        snd_feature[
                            (trues < preds.shape[1]) & (preds.argmax(1) == c), 0
                        ],
                        snd_feature[
                            (trues < preds.shape[1]) & (preds.argmax(1) == c), 1
                        ],
                        label=c,
                        c=colors[idx],
                    )

            plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=4)
            plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
            plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
            plt.title("Via predicted label - IN(but, this is true)")

            plt.subplot(2, 2, 4)
            for idx, c in enumerate(range(preds.shape[1])):
                plt.scatter(
                    snd_feature[(trues >= preds.shape[1]) & (preds.argmax(1) == c), 0],
                    snd_feature[(trues >= preds.shape[1]) & (preds.argmax(1) == c), 1],
                    label=c,
                    c=colors[idx],
                )

            plt.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05), ncol=4)
            plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
            plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
            plt.title("Via predicted label - OOD(but, this is true)")

            plt.savefig(
                os.path.join(self.ckpt_dir, f"timestamp={time}+type={name}.png")
            )
            plt.close("all")

            if get_results is not None:
                plt.scatter(
                    snd_feature[(labels_unlabels == 0) & (trues >= preds.shape[1]), 0],
                    snd_feature[(labels_unlabels == 0) & (trues >= preds.shape[1]), 1],
                    label="unlabel-ood",
                    c="black",
                    marker="*",
                    s=5,
                    alpha=0.5,
                )
                plt.scatter(
                    snd_feature[(labels_unlabels == 0) & (trues < preds.shape[1]), 0],
                    snd_feature[(labels_unlabels == 0) & (trues < preds.shape[1]), 1],
                    label="unlabel-In",
                    c="blue",
                    marker="*",
                    s=5,
                    alpha=0.5,
                )
                plt.scatter(
                    snd_feature[(labels_unlabels == 1), 0],
                    snd_feature[(labels_unlabels == 1), 1],
                    label="label",
                    c="red",
                    marker="o",
                    s=5,
                    alpha=0.5,
                )
                plt.legend()
                plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
                plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
                plt.title("Label or Unlabel")
                plt.savefig(
                    os.path.join(
                        self.ckpt_dir, f"timestamp={time}+type=label-or-unlabel.png"
                    )
                )
                plt.close("all")
        else:
            plt.figure(figsize=(12, 6))
            plt.subplot(1, 2, 1)
            if get_results is not None:
                for c in trues.unique()[: preds.shape[1]]:
                    plt.scatter(
                        snd_feature[(labels_unlabels == 1) & (trues == c), 0],
                        snd_feature[(labels_unlabels == 1) & (trues == c), 1],
                        label=c.item(),
                        c=colors[c],
                        marker="o",
                    )
                    plt.scatter(
                        snd_feature[(labels_unlabels == 0) & (trues == c), 0],
                        snd_feature[(labels_unlabels == 0) & (trues == c), 1],
                        label=c.item(),
                        c=colors[c],
                        marker="*",
                    )
            else:
                for c in trues.unique()[: preds.shape[1]]:
                    plt.scatter(
                        snd_feature[trues == c, 0],
                        snd_feature[trues == c, 1],
                        label=c.item(),
                        c=colors[c],
                    )

            plt.legend()
            plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
            plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
            plt.title("Via true labels - IN")

            plt.subplot(1, 2, 2)
            if get_results is not None:
                for idx, c in enumerate(range(preds.shape[1])):
                    plt.scatter(
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 1),
                            0,
                        ],
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 1),
                            1,
                        ],
                        label=c,
                        c=colors[idx],
                        marker="o",
                    )

                    plt.scatter(
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 0),
                            0,
                        ],
                        snd_feature[
                            (trues < preds.shape[1])
                            & (preds.argmax(1) == c)
                            & (labels_unlabels == 0),
                            1,
                        ],
                        label=c,
                        c=colors[idx],
                        marker="*",
                    )
            else:
                for idx, c in enumerate(range(preds.shape[1])):
                    plt.scatter(
                        snd_feature[
                            (trues < preds.shape[1]) & (preds.argmax(1) == c), 0
                        ],
                        snd_feature[
                            (trues < preds.shape[1]) & (preds.argmax(1) == c), 1
                        ],
                        label=c,
                        c=colors[idx],
                    )

            plt.legend()
            plt.xlim(snd_feature[:, 0].min() * 1.05, snd_feature[:, 0].max() * 1.05)
            plt.ylim(snd_feature[:, 1].min() * 1.05, snd_feature[:, 1].max() * 1.05)
            plt.title("Via prediction - IN")

            plt.savefig(
                os.path.join(self.ckpt_dir, f"timestamp={time}+type={name}.png")
            )
            plt.close("all")

        if return_results:
            return preds, trues, FEATURE


