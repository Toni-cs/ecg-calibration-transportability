# -*- coding: utf-8

import torch
import torch.nn as nn
import torch.nn.functional as F


class TopKAccuracy(nn.Module):
    def __init__(self, k: int):
        super(TopKAccuracy, self).__init__()
        self.k = k
    @torch.no_grad()
    def forward(self, logits: torch.Tensor, labels: torch.Tensor):

        assert logits.ndim == 2, "(B, F)"
        assert labels.ndim == 1, "(B,  )"
        assert len(logits) == len(labels)

        preds = F.softmax(logits, dim=1)
        topk_probs, topk_indices = torch.topk(preds, self.k, dim=1)
        labels = labels.view(-1, 1).expand_as(topk_indices)  # (B, k)
        correct = labels.eq(topk_indices) * (topk_probs)  # (B, k)
        correct = correct.sum(dim=1).bool().float()  # (B, ) & {0, 1}

        return torch.mean(correct)


class TopKMixupAccuracy(nn.Module):
    def __init__(self, k: int):
        super(TopKMixupAccuracy, self).__init__()

        if k > 1:
            raise NotImplementedError

        self.k = k

    @torch.no_grad()
    def forward(
        self,
        logits: torch.Tensor,
        labels: torch.Tensor,
        index: torch.Tensor,
        lam: float,
    ):

        assert logits.ndim == 2, "(B, F)"
        assert labels.ndim == 1, "(B,  )"
        assert len(logits) == len(labels) == len(index)

        _, predicted = torch.max(logits.data, 1)
        correct = (
            lam * predicted.eq(labels.data).cpu().sum().float()
            + (1 - lam) * predicted.eq(labels[index].data).cpu().sum().float()
        )

        return correct * 1e-2
