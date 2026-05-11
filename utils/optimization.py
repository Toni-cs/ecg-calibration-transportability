# -*- coding: utf-8 -*-

import torch.optim as optim
from torch.optim import SGD, Adam
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts, MultiStepLR


def get_optimizer(params, name: str, lr: float, weight_decay: float = 0.00, **kwargs):
    """Returns an `Optimizer` object given proper arguments."""

    if name == "adam":
        return Adam(params=params, lr=lr, weight_decay=weight_decay)
    elif name == "sgd":
        return SGD(
            params=params, lr=lr, momentum=0.9, weight_decay=weight_decay, nesterov=True
        )
    elif name == "lookahead":
        raise NotImplementedError
    else:
        raise NotImplementedError


def get_multi_step_scheduler(
    optimizer: optim.Optimizer, milestones: list, gamma: float = 0.1
):
    return MultiStepLR(optimizer, milestones=milestones, gamma=gamma)


def get_cosine_anneal_scheduler(
    optimizer: optim.Optimizer, milestones: int, gamma: float = 0.1
):
    return CosineAnnealingWarmRestarts(
        optimizer, T_0=milestones, eta_min=optimizer.param_groups[0]["lr"] * gamma
    )


class WeightSWA(object):
    """
    SWA or fastSWA
    """

    def __init__(self, swa_model):
        self.num_params = 0
        self.swa_model = swa_model  # assume that the parameters are to be discarded at the first update

    def update(self, student_model):
        self.num_params += 1
        if self.num_params == 1:
            self.swa_model.load_state_dict(student_model.state_dict())
        else:
            inv = 1.0 / float(self.num_params)
            for swa_p, src_p in zip(
                self.swa_model.parameters(), student_model.parameters()
            ):
                swa_p.data.add_(-inv * swa_p.data)
                swa_p.data.add_(inv * src_p.data)

    def reset(self):
        self.num_params = 0
