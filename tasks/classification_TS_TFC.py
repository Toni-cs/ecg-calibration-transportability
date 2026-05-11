import collections
import os

import torch
import torch.nn as nn
import torch.nn.functional as F
from rich.progress import Progress
from torch.utils.data import DataLoader

from datasets.transforms.transforms_freq import to_frequency_domain
from tasks.classification import Classification as Task
from utils import RandomSampler, TopKAccuracy
from utils.graph_label_propagation import propagate_knn_labels
from utils.logging import make_epoch_description
from utils.optimization import get_multi_step_scheduler, get_optimizer


class Classification(Task):
    def __init__(self, backbone_tem, backbone_feq, projection_tem, projection_feq):
        super(Classification, self).__init__(backbone_tem)
        self.backbone_tem = backbone_tem
        self.backbone_feq = backbone_feq
        self.projection_tem = projection_tem
        self.projection_feq = projection_feq

    def prepare(self, *args, **kwargs):
        super().prepare(*args, **kwargs)
        self.backbone_tem.to(self.local_rank)
        self.backbone_feq.to(self.local_rank)
        self.projection_tem.to(self.local_rank)
        self.projection_feq.to(self.local_rank)
        self.optimizer = get_optimizer(
            params=[
                {"params": self.backbone_tem.parameters()},
                {"params": self.backbone_feq.parameters()},
                {"params": self.projection_tem.parameters()},
                {"params": self.projection_feq.parameters()},
            ],
            name=kwargs.get("optimizer", "adam"),
            lr=kwargs.get("learning_rate", self.learning_rate),
            weight_decay=kwargs.get("weight_decay", 0.0),
        )
        self.scheduler = get_multi_step_scheduler(
            optimizer=self.optimizer,
            milestones=self.milestones,
            gamma=self.gamma,
        )

    def run(
        self,
        train_set,
        eval_set,
        test_set,
        open_test_set,
        save_every,
        unlabeled_ratio,
        knn_num_time,
        knn_num_freq,
        pseudo_cutoff,
        lambda_cross_pseudo,
        lambda_supcon_time,
        lambda_supcon_freq,
        graph_alpha,
        graph_iters,
        recompute_every,
        use_confidence_weight,
        warm_up_end,
        n_bins,
        **kwargs,
    ):
        if not self.prepared:
            raise RuntimeError("Training not prepared.")

        batch_size = self.batch_size
        num_workers = self.num_workers
        labeled_batch_size = max(1, batch_size // (1 + unlabeled_ratio))
        unlabeled_batch_size = max(1, batch_size - labeled_batch_size)

        label_sampler = RandomSampler(
            len(train_set[0]), self.iterations * labeled_batch_size
        )
        train_l_loader = DataLoader(
            train_set[0],
            batch_size=labeled_batch_size,
            sampler=label_sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        train_l_iterator = iter(train_l_loader)

        unlabeled_sampler = RandomSampler(
            len(train_set[1]), self.iterations * unlabeled_batch_size
        )
        train_u_loader = DataLoader(
            train_set[1],
            batch_size=unlabeled_batch_size,
            sampler=unlabeled_sampler,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        train_u_iterator = iter(train_u_loader)

        pseudo_label_loader = DataLoader(
            train_set[0],
            batch_size=128,
            shuffle=False,
            num_workers=num_workers,
            drop_last=False,
            pin_memory=False,
        )
        pseudo_unlabel_loader = DataLoader(
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

        logger = kwargs.get("logger", None)
        best_eval_acc = -float("inf")
        best_epoch = 0
        epochs = self.iterations // save_every
        self.trained_iteration = 0

        pseudo_bank_time = None
        pseudo_bank_freq = None
        confidence_bank_time = None
        confidence_bank_freq = None

        for epoch in range(1, epochs + 1):
            if epoch > warm_up_end and (
                pseudo_bank_time is None or (epoch - warm_up_end - 1) % max(1, recompute_every) == 0
            ):
                pseudo_bank_time, confidence_bank_time = self._build_pseudo_bank(
                    labeled_loader=pseudo_label_loader,
                    unlabeled_loader=pseudo_unlabel_loader,
                    use_frequency=False,
                    topk=knn_num_time,
                    alpha=graph_alpha,
                    graph_iters=graph_iters,
                    pseudo_cutoff=pseudo_cutoff,
                )
                pseudo_bank_freq, confidence_bank_freq = self._build_pseudo_bank(
                    labeled_loader=pseudo_label_loader,
                    unlabeled_loader=pseudo_unlabel_loader,
                    use_frequency=True,
                    topk=knn_num_freq,
                    alpha=graph_alpha,
                    graph_iters=graph_iters,
                    pseudo_cutoff=pseudo_cutoff,
                )

            train_history, train_l_iterator, train_u_iterator = self.train(
                label_iterator=train_l_iterator,
                unlabel_iterator=train_u_iterator,
                iteration=save_every,
                warm_up_end=warm_up_end,
                current_epoch=epoch,
                lambda_cross_pseudo=lambda_cross_pseudo,
                lambda_supcon_time=lambda_supcon_time,
                lambda_supcon_freq=lambda_supcon_freq,
                use_confidence_weight=use_confidence_weight,
                n_bins=n_bins,
                pseudo_bank_time=pseudo_bank_time,
                pseudo_bank_freq=pseudo_bank_freq,
                confidence_bank_time=confidence_bank_time,
                confidence_bank_freq=confidence_bank_freq,
            )
            eval_history = self.evaluate(eval_loader, n_bins)

            epoch_history = collections.defaultdict(dict)
            for key, train_value in train_history.items():
                epoch_history[key]["train"] = train_value
                if key in eval_history:
                    epoch_history[key]["eval"] = eval_history[key]

            if self.writer is not None:
                for key, values in epoch_history.items():
                    for split, value in values.items():
                        self.writer.add_scalar(
                            f"{key}_{split}", value, global_step=epoch
                        )
                if self.scheduler is not None:
                    self.writer.add_scalar(
                        "lr", self.scheduler.get_last_lr()[0], global_step=epoch
                    )

            eval_acc = eval_history["top@1"]
            if eval_acc > best_eval_acc:
                best_eval_acc = eval_acc
                best_epoch = epoch
                if self.local_rank == 0:
                    self.save_checkpoint(f"{self.ckpt_dir}/ckpt.best.pth.tar", epoch=epoch)

                test_history = self.evaluate(test_loader, n_bins)
                for key, value in test_history.items():
                    epoch_history[key]["test"] = value

                open_history = self.evaluate_open_set(open_test_loader)
                for key, value in open_history.items():
                    epoch_history[key]["open"] = value

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
        warm_up_end,
        current_epoch,
        lambda_cross_pseudo,
        lambda_supcon_time,
        lambda_supcon_freq,
        use_confidence_weight,
        n_bins,
        pseudo_bank_time,
        pseudo_bank_freq,
        confidence_bank_time,
        confidence_bank_freq,
    ):
        self._set_learning_phase(train=True)
        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "sup_loss_time": torch.zeros(iteration, device=self.local_rank),
            "sup_loss_freq": torch.zeros(iteration, device=self.local_rank),
            "supcon_loss_time": torch.zeros(iteration, device=self.local_rank),
            "supcon_loss_freq": torch.zeros(iteration, device=self.local_rank),
            "cross_pseudo_loss": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
            "pseudo_conf_time": torch.zeros(iteration, device=self.local_rank),
            "pseudo_conf_freq": torch.zeros(iteration, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:
            if self.local_rank == 0:
                task = pg.add_task("[bold red] Training...", total=iteration)

            for i in range(iteration):
                with torch.autocast("cuda", enabled=self.mixed_precision):
                    l_batch = next(label_iterator)
                    u_batch = next(unlabel_iterator)

                    x_lb_0 = l_batch["x_lb_w_0"].to(self.local_rank)
                    x_lb_1 = l_batch["x_lb_w_1"].to(self.local_rank)
                    y_lb = l_batch["y_lb"].to(self.local_rank)

                    x_lb = torch.cat([x_lb_0, x_lb_1], dim=0)
                    y_lb_repeat = y_lb.repeat(2)

                    logits_time, feat_time = self.get_feature_tem(x_lb)
                    logits_freq, feat_freq = self.get_feature_feq(to_frequency_domain(x_lb))

                    sup_loss_time = self.loss_function(logits_time, y_lb_repeat.long())
                    sup_loss_freq = self.loss_function(logits_freq, y_lb_repeat.long())
                    supcon_loss_time = self._supervised_contrastive_loss(
                        F.normalize(self.projection_tem(feat_time), dim=1),
                        y_lb_repeat,
                    )
                    supcon_loss_freq = self._supervised_contrastive_loss(
                        F.normalize(self.projection_feq(feat_freq), dim=1),
                        y_lb_repeat,
                    )

                    cross_pseudo_loss = torch.tensor(0.0, device=self.local_rank)
                    pseudo_conf_time = torch.tensor(0.0, device=self.local_rank)
                    pseudo_conf_freq = torch.tensor(0.0, device=self.local_rank)

                    if current_epoch > warm_up_end and pseudo_bank_time is not None:
                        idx_ulb = u_batch["idx_ulb"].long().to(self.local_rank)
                        x_ulb_student = u_batch["x_ulb_w_1"].to(self.local_rank)

                        logits_ulb_time = self.backbone_tem(x_ulb_student)
                        logits_ulb_freq = self.backbone_feq(to_frequency_domain(x_ulb_student))

                        pseudo_from_time = pseudo_bank_time[idx_ulb]
                        pseudo_from_freq = pseudo_bank_freq[idx_ulb]
                        conf_from_time = confidence_bank_time[idx_ulb]
                        conf_from_freq = confidence_bank_freq[idx_ulb]

                        time_loss = self._soft_ce(
                            logits_ulb_time,
                            pseudo_from_freq,
                            conf_from_freq,
                            use_confidence_weight,
                        )
                        freq_loss = self._soft_ce(
                            logits_ulb_freq,
                            pseudo_from_time,
                            conf_from_time,
                            use_confidence_weight,
                        )
                        cross_pseudo_loss = time_loss + freq_loss
                        pseudo_conf_time = pseudo_from_time.max(dim=1).values.mean().detach()
                        pseudo_conf_freq = pseudo_from_freq.max(dim=1).values.mean().detach()

                    loss = (
                        sup_loss_time
                        + sup_loss_freq
                        + lambda_supcon_time * supcon_loss_time
                        + lambda_supcon_freq * supcon_loss_freq
                        + lambda_cross_pseudo * cross_pseudo_loss
                    )

                if self.scaler is not None:
                    self.scaler.scale(loss).backward()
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    loss.backward()
                    self.optimizer.step()
                self.optimizer.zero_grad()
                self.trained_iteration += 1

                avg_logits = 0.5 * (logits_time[: y_lb.shape[0]] + logits_freq[: y_lb.shape[0]])
                result["loss"][i] = loss.detach()
                result["sup_loss_time"][i] = sup_loss_time.detach()
                result["sup_loss_freq"][i] = sup_loss_freq.detach()
                result["supcon_loss_time"][i] = supcon_loss_time.detach()
                result["supcon_loss_freq"][i] = supcon_loss_freq.detach()
                result["cross_pseudo_loss"][i] = cross_pseudo_loss.detach()
                result["top@1"][i] = TopKAccuracy(k=1)(avg_logits, y_lb).detach()
                result["ece"][i] = self.get_ece(
                    preds=avg_logits.softmax(dim=1).detach().cpu().numpy(),
                    targets=y_lb.cpu().numpy(),
                    n_bins=n_bins,
                    plot=False,
                )[0]
                result["pseudo_conf_time"][i] = pseudo_conf_time
                result["pseudo_conf_freq"][i] = pseudo_conf_freq

                if self.local_rank == 0:
                    desc = f"[bold green] [{i+1}/{iteration}]: "
                    for key, value in result.items():
                        desc += f" {key} : {value[:i+1].mean():.4f} |"
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

                if self.scheduler is not None:
                    self.scheduler.step()

        return {key: value.mean().item() for key, value in result.items()}, label_iterator, unlabel_iterator

    @torch.no_grad()
    def _build_pseudo_bank(
        self,
        labeled_loader,
        unlabeled_loader,
        use_frequency,
        topk,
        alpha,
        graph_iters,
        pseudo_cutoff,
    ):
        labeled_embeddings = []
        labeled_labels = []
        unlabeled_embeddings = []
        unlabeled_indices = []

        self._set_learning_phase(train=False)
        for batch in labeled_loader:
            x = batch["x_lb_w_0"].to(self.local_rank)
            y = batch["y_lb"].to(self.local_rank)
            if use_frequency:
                x = to_frequency_domain(x)
                _, feat = self.get_feature_feq(x)
            else:
                _, feat = self.get_feature_tem(x)
            labeled_embeddings.append(feat)
            labeled_labels.append(y)

        for batch in unlabeled_loader:
            idx = batch["idx_ulb"].long().to(self.local_rank)
            x = batch["x_ulb_w_0"].to(self.local_rank)
            if use_frequency:
                x = to_frequency_domain(x)
                logits, feat = self.get_feature_feq(x)
            else:
                logits, feat = self.get_feature_tem(x)
            unlabeled_indices.append(idx)
            unlabeled_embeddings.append(feat)

        labeled_embeddings = torch.cat(labeled_embeddings, dim=0)
        labeled_labels = torch.cat(labeled_labels, dim=0)
        unlabeled_embeddings = torch.cat(unlabeled_embeddings, dim=0)
        unlabeled_indices = torch.cat(unlabeled_indices, dim=0)

        embeddings = torch.cat([labeled_embeddings, unlabeled_embeddings], dim=0)
        seed_mask = torch.zeros(embeddings.shape[0], dtype=torch.bool, device=self.local_rank)
        seed_mask[: labeled_embeddings.shape[0]] = True
        seed_labels = torch.full(
            (embeddings.shape[0],), -1, dtype=torch.long, device=self.local_rank
        )
        seed_labels[: labeled_embeddings.shape[0]] = labeled_labels.long()

        scores = propagate_knn_labels(
            embeddings=embeddings,
            seed_labels=seed_labels,
            seed_mask=seed_mask,
            num_classes=self.backbone_tem.class_num,
            topk=topk,
            alpha=alpha,
            iters=graph_iters,
        )
        unlabeled_scores = scores[labeled_embeddings.shape[0] :]
        confidence = unlabeled_scores.max(dim=1).values

        bank_size = int(unlabeled_indices.max().item()) + 1
        pseudo_bank = torch.full(
            (bank_size, self.backbone_tem.class_num),
            1.0 / self.backbone_tem.class_num,
            device=self.local_rank,
        )
        confidence_bank = torch.zeros(bank_size, device=self.local_rank)
        pseudo_bank[unlabeled_indices] = unlabeled_scores
        confidence_bank[unlabeled_indices] = confidence
        confidence_bank = confidence_bank.ge(pseudo_cutoff).float()
        return pseudo_bank, confidence_bank

    @staticmethod
    def _supervised_contrastive_loss(embeddings, labels, temperature=0.07):
        logits = (embeddings @ embeddings.T) / temperature
        logits = logits - logits.max(dim=1, keepdim=True).values.detach()
        labels = labels.view(-1, 1)
        mask = torch.eq(labels, labels.T).float().to(embeddings.device)
        logits_mask = torch.ones_like(mask) - torch.eye(mask.shape[0], device=embeddings.device)
        mask = mask * logits_mask
        exp_logits = torch.exp(logits) * logits_mask
        log_prob = logits - torch.log(exp_logits.sum(dim=1, keepdim=True).clamp_min(1e-12))
        mean_log_prob_pos = (mask * log_prob).sum(dim=1) / mask.sum(dim=1).clamp_min(1e-12)
        valid = mask.sum(dim=1) > 0
        if valid.any():
            return -mean_log_prob_pos[valid].mean()
        return torch.tensor(0.0, device=embeddings.device)

    @staticmethod
    def _soft_ce(logits, targets, confidence_mask, use_confidence_weight):
        if confidence_mask.sum().item() == 0:
            return torch.tensor(0.0, device=logits.device)
        log_probs = F.log_softmax(logits, dim=1)
        per_sample = -(targets * log_probs).sum(dim=1)
        if use_confidence_weight:
            weights = targets.max(dim=1).values * confidence_mask
            return (per_sample * weights).sum() / weights.sum().clamp_min(1e-12)
        return (per_sample * confidence_mask).sum() / confidence_mask.sum().clamp_min(1e-12)

    @torch.no_grad()
    def evaluate(self, data_loader, n_bins):
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
                task = pg.add_task("[bold red] Evaluating...", total=steps)

            pred, true = [], []
            for i, batch in enumerate(data_loader):
                x = batch["x"].to(self.local_rank)
                y = batch["y"].to(self.local_rank)
                logits = self.predict(x)
                loss = self.loss_function(logits, y.long())

                result["loss"][i] = loss
                true.append(y.cpu())
                pred.append(logits.cpu())

                if self.local_rank == 0:
                    desc = (
                        f"[bold green] [{i+1}/{steps}]: "
                        + f" loss : {result['loss'][:i+1].mean():.4f} |"
                        + f" top@1 : {TopKAccuracy(k=1)(logits, y).detach():.4f} |"
                    )
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

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
        return {key: value.mean().item() for key, value in result.items()}

    def get_feature_tem(self, x):
        return self.backbone_tem(x, return_feature=True)

    def get_feature_feq(self, x):
        return self.backbone_feq(x, return_feature=True)

    def predict(self, x):
        logits_tem = self.backbone_tem(x)
        logits_feq = self.backbone_feq(to_frequency_domain(x))
        return 0.5 * (logits_tem + logits_feq)

    def get_open_set_probs(self, x):
        probs_tem = self.backbone_tem(x).softmax(dim=1)
        probs_feq = self.backbone_feq(to_frequency_domain(x)).softmax(dim=1)
        return 0.5 * (probs_tem + probs_feq)

    def _set_learning_phase(self, train=False):
        if train:
            self.backbone_tem.train()
            self.backbone_feq.train()
            self.projection_tem.train()
            self.projection_feq.train()
        else:
            self.backbone_tem.eval()
            self.backbone_feq.eval()
            self.projection_tem.eval()
            self.projection_feq.eval()

    def save_checkpoint(self, path: str, **kwargs):
        ckpt = {
            "backbone_tem": self.backbone_tem.state_dict(),
            "backbone_feq": self.backbone_feq.state_dict(),
            "projection_tem": self.projection_tem.state_dict(),
            "projection_feq": self.projection_feq.state_dict(),
            "optimizer": self.optimizer.state_dict(),
        }
        if kwargs:
            ckpt.update(kwargs)
        torch.save(ckpt, path)

    def load_model_from_checkpoint(self, path: str):
        ckpt = torch.load(path)
        self.backbone_tem.load_state_dict(ckpt["backbone_tem"])
        self.backbone_feq.load_state_dict(ckpt["backbone_feq"])
        self.projection_tem.load_state_dict(ckpt["projection_tem"])
        self.projection_feq.load_state_dict(ckpt["projection_feq"])