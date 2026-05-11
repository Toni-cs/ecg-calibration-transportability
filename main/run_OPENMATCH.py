import os
import sys
import time

import numpy as np
import rich
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import torch.nn as nn

sys.path.append("./")
from configs import OPENMATCHConfig
from datasets.transforms import SemiAugment, TestAugment
from datasets.ptbxl import get_ptbxl, PTBXLDataset
from datasets.cinc2021 import get_cinc2021, CINC2021Dataset
from models.resnet1d import ResNet1D
from tasks.classification_OPENMATCH import Classification
from utils.gpu import set_gpu
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

    config = OPENMATCHConfig.parse_arguments()
    set_gpu(config)
    num_gpus_per_node = len(config.gpus)
    world_size = config.num_nodes * num_gpus_per_node
    distributed = world_size > 1
    setattr(config, "num_gpus_per_node", num_gpus_per_node)
    setattr(config, "world_size", world_size)
    setattr(config, "distributed", distributed)

    rich.print(config.__dict__)
    config.save()

    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.backends.cudnn.deterministic = False
    torch.backends.cudnn.benchmark = True

    if config.distributed:
        rich.print(f"Distributed training on {world_size} GPUs.")
        mp.spawn(main_worker, nprocs=config.num_gpus_per_node, args=(config,))
    else:
        rich.print("Single GPU training.")
        main_worker(0, config=config)  # single machine, single gpu


def main_worker(local_rank: int, config: object):
    """Single process."""

    torch.cuda.set_device(local_rank)
    if config.distributed:
        dist_rank = config.node_rank * config.num_gpus_per_node + local_rank
        dist.init_process_group(
            backend=config.dist_backend,
            init_method=config.dist_url,
            world_size=config.world_size,
            rank=dist_rank,
        )

    config.batch_size = config.batch_size // config.world_size
    config.num_workers = config.num_workers // config.num_gpus_per_node

    num_classes = NUM_CLASSES[config.data]

    # Networks
    if config.backbone_type == "resnet1d":
        model = ResNet1D(num_classes=num_classes, normalize=config.normalize)
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
    setattr(
        model,
        "ova_classifiers",
        nn.Linear(model.in_features, int(model.class_num * 2), bias=False),
    )

    # Data (transforms & datasets)
    trans_kwargs = dict(
        size=config.input_size, data=config.data, impl=config.augmentation
    )
    train_trans = AUGMENTS[config.train_augment](**trans_kwargs)
    test_trans = AUGMENTS[config.test_augment](**trans_kwargs)

    if config.data in ["ptbxl", "chapman", "georgia", "ningbo"]:
        lb_dset, ulb_dset, val_dset, test_dset, open_test_dset = get_ptbxl(
            config, root=config.root
        )
        labeled_set = PTBXLDataset(
            lb_dset.data,
            lb_dset.labels,
            mode="train_lb",
            augment_impl=config.ptbxl_augment,
        )
        unlabeled_set = PTBXLDataset(
            ulb_dset.data,
            ulb_dset.labels,
            mode="train_ulb",
            augment_impl=config.ptbxl_augment,
        )
        selcted_unlabeled_set = PTBXLDataset(
            ulb_dset.data,
            ulb_dset.labels,
            mode="train_ulb_selected",
            augment_impl=config.ptbxl_augment,
        )
        eval_set = val_dset
        test_set = test_dset
        open_test_set = open_test_dset
    elif config.data == "cinc2021":
        lb_dset, ulb_dset, val_dset, test_dset, open_test_dset = get_cinc2021(
            config, root=config.root
        )
        labeled_set = CINC2021Dataset(
            lb_dset.data_paths,
            lb_dset.labels,
            mode="train_lb",
            augment_impl=config.ptbxl_augment,
        )
        unlabeled_set = CINC2021Dataset(
            ulb_dset.data_paths,
            ulb_dset.labels,
            mode="train_ulb",
            augment_impl=config.ptbxl_augment,
        )
        selcted_unlabeled_set = CINC2021Dataset(
            ulb_dset.data_paths,
            ulb_dset.labels,
            mode="train_ulb_selected",
            augment_impl=config.ptbxl_augment,
        )
        eval_set = val_dset
        test_set = test_dset
        open_test_set = open_test_dset
    else:
        raise NotImplementedError(
            f"Unsupported ECG dataset for release: {config.data}"
        )

    datasets = {
        "l_train": {"labels": labeled_set.labels},
        "u_train": {"labels": unlabeled_set.labels},
    }

    if local_rank == 0:
        logger.info(f"Data: {config.data}")
        logger.info(
            f"Labeled Data Observations: {len(datasets['l_train']['labels']):,}"
        )
        logger.info(
            f"Unlabeled Data Observations: {len(datasets['u_train']['labels']):,}"
        )
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
        train_set=[labeled_set, unlabeled_set, selcted_unlabeled_set],
        eval_set=eval_set,
        test_set=test_set,
        open_test_set=open_test_set,
        p_cutoff=config.p_cutoff,
        pi=config.pi,
        warm_up_end=config.warm_up,
        n_bins=config.n_bins,
        start_fix=config.start_fix,
        lambda_em=config.lambda_em,
        lambda_socr=config.lambda_socr,
        save_every=config.save_every,
        train_trans=train_trans,
        enable_plot=config.enable_plot,
        distributed=config.distributed,
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
