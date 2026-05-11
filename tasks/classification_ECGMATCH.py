import collections
import math
from copy import deepcopy

import torch
import torch.nn.functional as F
from rich.progress import Progress
from torch.utils.data import DataLoader

from tasks.classification import Classification as Task
from utils import RandomSampler, TopKAccuracy
from utils.logging import make_epoch_description


class Classification(Task):
    def __init__(self, backbone):
        super(Classification, self).__init__(backbone)
        self.teacher_backbone = None
        self.teacher_momentum = 0.999
        self.warm_up_end = 1

    def prepare(self, *args, teacher_momentum=0.999, **kwargs):
        super().prepare(*args, **kwargs)
        self.teacher_momentum = teacher_momentum
        self.teacher_backbone = deepcopy(self.backbone)
        self.teacher_backbone.to(self.local_rank)
        self.teacher_backbone.eval()
        for param in self.teacher_backbone.parameters():
            param.requires_grad_(False)

    def run(
        self,
        train_set,
        eval_set,
        test_set,
        open_test_set,
        save_every,
        neighbor_k,
        unlabeled_ratio,
        pseudo_temperature,
        unsup_coef,
        relationship_coef,
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

        label_loader = DataLoader(
            train_set[0],
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
        self.warm_up_end = max(1, warm_up_end)
        self.trained_iteration = 0

        relationship_target = self._build_labeled_relationship(label_loader)
        bank_size = len(train_set[1])
        feature_bank = F.normalize(
            torch.randn(bank_size, self.backbone.in_features, device=self.local_rank),
            dim=1,
        )
        score_bank = torch.full(
            (bank_size, self.backbone.class_num),
            1.0 / self.backbone.class_num,
            device=self.local_rank,
        )
        self._initialize_unlabeled_banks(train_set[1], feature_bank, score_bank)

        for epoch in range(1, epochs + 1):
            train_history, train_l_iterator, train_u_iterator = self.train(
                label_iterator=train_l_iterator,
                unlabel_iterator=train_u_iterator,
                iteration=save_every,
                neighbor_k=neighbor_k,
                pseudo_temperature=pseudo_temperature,
                unsup_coef=unsup_coef,
                relationship_coef=relationship_coef,
                use_confidence_weight=use_confidence_weight,
                n_bins=n_bins,
                feature_bank=feature_bank,
                score_bank=score_bank,
                relationship_target=relationship_target,
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

                if self.writer is not None:
                    self.writer.add_scalar(
                        "Best_Test_top@1", test_history["top@1"], global_step=epoch
                    )
                    self.writer.add_scalar(
                        "Best_Open_auroc", open_history["auroc"], global_step=epoch
                    )

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
        neighbor_k,
        pseudo_temperature,
        unsup_coef,
        relationship_coef,
        use_confidence_weight,
        n_bins,
        feature_bank,
        score_bank,
        relationship_target,
    ):
        self._set_learning_phase(train=True)
        self.teacher_backbone.eval()

        result = {
            "loss": torch.zeros(iteration, device=self.local_rank),
            "sup_loss": torch.zeros(iteration, device=self.local_rank),
            "unsup_loss": torch.zeros(iteration, device=self.local_rank),
            "relationship_loss": torch.zeros(iteration, device=self.local_rank),
            "warm_up_coef": torch.zeros(iteration, device=self.local_rank),
            "top@1": torch.zeros(iteration, device=self.local_rank),
            "ece": torch.zeros(iteration, device=self.local_rank),
            "pseudo_conf": torch.zeros(iteration, device=self.local_rank),
        }

        with Progress(transient=True, auto_refresh=False) as pg:
            if self.local_rank == 0:
                task = pg.add_task("[bold red] Training...", total=iteration)

            for i in range(iteration):
                with torch.autocast("cuda", enabled=self.mixed_precision):
                    l_batch = next(label_iterator)
                    u_batch = next(unlabel_iterator)

                    label_x = l_batch["x"].to(self.local_rank)
                    label_y = l_batch["y"].to(self.local_rank)

                    unlabel_weak_x = u_batch["weak_img"].to(self.local_rank)
                    unlabel_strong_x = u_batch["strong_img"].to(self.local_rank)
                    unlabel_idx = u_batch["idx"].long().to(self.local_rank)

                    label_logits = self.predict(label_x)
                    sup_loss = self.loss_function(label_logits, label_y.long())

                    with torch.no_grad():
                        teacher_logits, teacher_features = self.get_teacher_feature(
                            unlabel_weak_x
                        )
                        teacher_probs = F.softmax(
                            teacher_logits / pseudo_temperature, dim=1
                        )
                        teacher_features = F.normalize(teacher_features, dim=1)

                        feature_bank[unlabel_idx] = teacher_features.detach()
                        score_bank[unlabel_idx] = teacher_probs.detach()

                        similarity = teacher_features @ feature_bank.T
                        similarity.scatter_(1, unlabel_idx.unsqueeze(1), -1.0)
                        effective_k = max(1, min(neighbor_k, similarity.shape[1]))
                        _, neighbor_indices = torch.topk(
                            similarity,
                            k=effective_k,
                            dim=1,
                            largest=True,
                        )

                        pseudo_targets = score_bank[neighbor_indices].mean(dim=1)
                        pseudo_targets = pseudo_targets / pseudo_targets.sum(
                            dim=1, keepdim=True
                        ).clamp_min(1e-6)
                        confidence = pseudo_targets.max(dim=1).values
                        agreement = score_bank[neighbor_indices].std(dim=1).mean(dim=1)
                        if use_confidence_weight:
                            sample_weight = confidence * (1.0 - agreement)
                        else:
                            sample_weight = torch.ones_like(confidence)

                    strong_logits, _ = self.get_feature(unlabel_strong_x)
                    strong_log_probs = F.log_softmax(strong_logits, dim=1)
                    unsup_loss_per_sample = F.kl_div(
                        strong_log_probs,
                        pseudo_targets,
                        reduction="none",
                    ).sum(dim=1)
                    unsup_loss = (unsup_loss_per_sample * sample_weight).mean()

                    strong_probs = F.softmax(strong_logits, dim=1)
                    relationship_prediction = self.compute_similarity_matrix(strong_probs)
                    relationship_loss = torch.norm(
                        relationship_prediction - relationship_target, p="fro"
                    )

                    warm_up_coef = math.exp(
                        -5
                        * (
                            1.0
                            - min(self.trained_iteration / self.warm_up_end, 1.0)
                        )
                        ** 2
                    )
                    ssl_loss = (
                        unsup_coef * unsup_loss
                        + relationship_coef * relationship_loss
                    )
                    loss = sup_loss + warm_up_coef * ssl_loss

                if self.scaler is not None:
                    self.scaler.scale(loss).backward()
                    self.scaler.step(self.optimizer)
                    self.scaler.update()
                else:
                    loss.backward()
                    self.optimizer.step()
                self.optimizer.zero_grad()
                self.trained_iteration += 1
                self.update_teacher()

                result["loss"][i] = loss.detach()
                result["sup_loss"][i] = sup_loss.detach()
                result["unsup_loss"][i] = unsup_loss.detach()
                result["relationship_loss"][i] = relationship_loss.detach()
                result["warm_up_coef"][i] = warm_up_coef
                result["top@1"][i] = TopKAccuracy(k=1)(label_logits, label_y).detach()
                result["ece"][i] = self.get_ece(
                    preds=label_logits.softmax(dim=1).detach().cpu().numpy(),
                    targets=label_y.cpu().numpy(),
                    n_bins=n_bins,
                    plot=False,
                )[0]
                result["pseudo_conf"][i] = confidence.mean().detach()

                if self.local_rank == 0:
                    desc = f"[bold green] [{i+1}/{iteration}]: "
                    for key, value in result.items():
                        desc += f" {key} : {value[:i+1].mean():.4f} |"
                    pg.update(task, advance=1.0, description=desc)
                    pg.refresh()

                if self.scheduler is not None:
                    self.scheduler.step()

        return (
            {key: value.mean().item() for key, value in result.items()},
            label_iterator,
            unlabel_iterator,
        )

    @torch.no_grad()
    def _initialize_unlabeled_banks(self, dataset, feature_bank, score_bank):
        loader = DataLoader(
            dataset,
            batch_size=128,
            shuffle=False,
            num_workers=self.num_workers,
            drop_last=False,
            pin_memory=False,
        )
        for batch in loader:
            x = batch["weak_img"].to(self.local_rank)
            idx = batch["idx"].long().to(self.local_rank)
            logits, features = self.get_teacher_feature(x)
            feature_bank[idx] = F.normalize(features, dim=1)
            score_bank[idx] = F.softmax(logits, dim=1)

    @torch.no_grad()
    def _build_labeled_relationship(self, label_loader):
        labels = []
        for batch in label_loader:
            labels.append(batch["y"].long())
        labels = torch.cat(labels, dim=0).to(self.local_rank)
        one_hot = F.one_hot(labels, num_classes=self.backbone.class_num).float()
        return self.compute_similarity_matrix(one_hot)

    @staticmethod
    def compute_similarity_matrix(scores):
        scores = scores.float()
        scores = scores - scores.mean(dim=0, keepdim=True)
        scores = scores / scores.norm(dim=0, keepdim=True).clamp_min(1e-6)
        similarity = scores.transpose(0, 1) @ scores
        return similarity.clamp(0.0, 1.0)

    @torch.no_grad()
    def update_teacher(self):
        for teacher_param, student_param in zip(
            self.teacher_backbone.parameters(), self.backbone.parameters()
        ):
            teacher_param.data.mul_(self.teacher_momentum).add_(
                student_param.data, alpha=1.0 - self.teacher_momentum
            )

    @torch.no_grad()
    def get_teacher_feature(self, x):
        return self.teacher_backbone(x, return_feature=True)

    def save_checkpoint(self, path: str, **kwargs):
        ckpt = {
            "backbone": self.backbone.state_dict(),
            "teacher_backbone": self.teacher_backbone.state_dict(),
            "optimizer": self.optimizer.state_dict(),
        }
        if kwargs:
            ckpt.update(kwargs)
        torch.save(ckpt, path)

    def load_model_from_checkpoint(self, path: str):
        ckpt = torch.load(path)
        self.backbone.load_state_dict(ckpt["backbone"])
        self.teacher_backbone.load_state_dict(ckpt["teacher_backbone"])
        self.optimizer.load_state_dict(ckpt["optimizer"])