import os
import sys
import time

import numpy as np
import rich
import torch

sys.path.append("./")
from configs import IOMATCHConfig
from datasets.transforms import SemiAugment, TestAugment
from datasets.ptbxl import get_ptbxl
from datasets.cinc2021 import get_cinc2021
from models.resnet1d import ResNet1D
from tasks.classification_IOMATCH import Classification
from utils.gpu import set_gpu
from utils.initialization import initialize_weights
from utils.logging import get_rich_logger
from utils.wandb import configure_wandb

NUM_CLASSES = {
    "ptbxl": 3,
    "chapman": 3,
    "georgia": 3,
    "ningbo": 3,
    "cinc2021": 3,
}

AUGMENTS = {"semi": SemiAugment, "test": TestAugment}


def main():
    """Main function for single/distributed linear classification."""

    config = IOMATCHConfig.parse_arguments()
    set_gpu(config)

    rich.print(config.__dict__)
    config.save()

    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.backends.cudnn.deterministic = False
    torch.backends.cudnn.benchmark = True

    rich.print("Single GPU training.")
    main_worker(0, config=config)  # single machine, single gpu


def main_worker(local_rank: int, config: object):
    """Single process."""

    torch.cuda.set_device(local_rank)
    num_classes = NUM_CLASSES[config.data]

    # Networks
    if config.backbone_type == "resnet1d":
        model = ResNet1D(num_classes=num_classes, normalize=config.normalize)
        if hasattr(model, "fc"):
            model.output = model.fc
        elif hasattr(model, "linear"):
            model.output = model.linear
        else:
            raise AttributeError(
                "ResNet1D model has no fc/linear output layer for IOMATCH."
            )
    else:
        raise NotImplementedError(
            f"Unsupported ECG backbone for release: {config.backbone_type}"
        )

    # create logger
    if local_rank == 0:
        logfile = os.path.join(config.checkpoint_dir, "main.log")
        logger = get_rich_logger(logfile=logfile)
        if config.enable_wandb:
            configure_wandb(
                name=f"{config.task} : {config.hash}",
                project=f"SafeSSL-Calibration-{config.data}-{config.task}",
                config=config,
            )
    else:
        logger = None

    # Sub-Network Plus
    import torch.nn as nn

    setattr(
        model,
        "mlp_proj",
        nn.Sequential(
            nn.Linear(model.output.in_features, model.output.in_features),
            nn.ReLU(),
            nn.Linear(model.output.in_features, model.output.in_features),
        ),
    )
    setattr(
        model,
        "mb_classifiers",
        nn.Linear(model.output.in_features, int(model.class_num * 2)),
    )
    setattr(
        model,
        "openset_classifier",
        nn.Linear(model.output.in_features, int(model.class_num + 1)),
    )

    initialize_weights(model)

    # Data (transforms & datasets)
    trans_kwargs = dict(
        size=config.input_size, data=config.data, impl=config.augmentation
    )
    train_trans = AUGMENTS[config.train_augment](**trans_kwargs)
    test_trans = AUGMENTS[config.test_augment](**trans_kwargs)

    if config.data in ["ptbxl", "chapman", "georgia", "ningbo"]:
        (
            train_labeled_dataset,
            train_unlabeled_dataset,
            val_dataset,
            test_dataset,
            open_test_dataset,
        ) = get_ptbxl(config, root=config.root)
    elif config.data == "cinc2021":
        (
            train_labeled_dataset,
            train_unlabeled_dataset,
            val_dataset,
            test_dataset,
            open_test_dataset,
        ) = get_cinc2021(config, root=config.root)
    else:
        raise NotImplementedError(
            f"Unsupported ECG dataset for release: {config.data}"
        )

    labeled_set = train_labeled_dataset
    unlabeled_set = train_unlabeled_dataset
    eval_set = val_dataset
    test_set = test_dataset
    open_test_set = open_test_dataset

    datasets = {
        "l_train": {"labels": train_labeled_dataset.labels},
        "u_train": {"labels": train_unlabeled_dataset.labels},
    }

    if local_rank == 0:
        logger.info(f"Data: {config.data}")
        logger.info(f"Labeled Data Observations: {len(labeled_set):,}")
        logger.info(f"Unlabeled Data Observations: {len(unlabeled_set):,}")
        logger.info(f"Backbone: {config.backbone_type}")
        logger.info(f"Checkpoint directory: {config.checkpoint_dir}")

    # Model (Task)
    model = Classification(backbone=model)
    model.prepare(
        ckpt_dir=config.checkpoint_dir,
        optimizer=config.optimizer,
        learning_rate=config.learning_rate,
        iterations=config.iterations,
        batch_size=config.batch_size,
        num_workers=config.num_workers,
        local_rank=local_rank,
        mixed_precision=config.mixed_precision,
        gamma=config.gamma,
        milestones=config.milestones,
        weight_decay=config.weight_decay,
    )

    # Train & evaluate
    start = time.time()
    model.run(
        train_set=[labeled_set, unlabeled_set],
        eval_set=eval_set,
        test_set=test_set,
        open_test_set=open_test_set,
        save_every=config.save_every,
        p_cutoff=config.p_cutoff,
        q_cutoff=config.q_cutoff,
        warm_up_end=config.warm_up,
        n_bins=config.n_bins,
        enable_plot=config.enable_plot,
        dist_da_len=config.dist_da_len,
        lambda_open=config.lambda_open,
        logger=logger,
    )
    elapsed_sec = time.time() - start

    if logger is not None:
        elapsed_mins = elapsed_sec / 60
        logger.info(f"Total training time: {elapsed_mins:,.2f} minutes.")
        logger.handlers.clear()


if __name__ == "__main__":

    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
