import os
import sys
import time

import numpy as np
import rich
import torch
import torch.distributed as dist
import torch.multiprocessing as mp

sys.path.append("./")
from configs import CompleMatchConfig
from datasets.cinc2021 import get_cinc2021
from datasets.ptbxl import get_ptbxl
from models.resnet1d import ResNet1D
from tasks.classification_COMPLEMATCH import Classification
from utils.gpu import set_gpu
from utils.logging import get_rich_logger
from utils.projection_head import ProjectionHead
from utils.wandb import configure_wandb


NUM_CLASSES = {
    "ptbxl": 3,
    "chapman": 3,
    "georgia": 3,
    "ningbo": 3,
    "cinc2021": 3,
}


def main():
    config = CompleMatchConfig.parse_arguments()
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
        main_worker(0, config=config)


def main_worker(local_rank: int, config: object):
    torch.cuda.set_device(local_rank)
    if config.distributed:
        dist_rank = config.node_rank * config.num_gpus_per_node + local_rank
        dist.init_process_group(
            backend=config.dist_backend,
            init_method=config.dist_url,
            world_size=config.world_size,
            rank=dist_rank,
        )

    config.batch_size = max(1, config.batch_size // config.world_size)
    config.num_workers = max(1, config.num_workers // config.num_gpus_per_node)

    if config.data not in NUM_CLASSES:
        raise NotImplementedError("CompleMatch currently supports ECG datasets only.")
    if config.backbone_type != "resnet1d":
        raise NotImplementedError("CompleMatch currently supports resnet1d only.")

    num_classes = NUM_CLASSES[config.data]
    backbone_tem = ResNet1D(num_classes=num_classes, normalize=config.normalize)
    backbone_feq = ResNet1D(num_classes=num_classes, normalize=config.normalize)
    projection_tem = ProjectionHead(
        input_dim=backbone_tem.in_features,
        hidden_dim=config.projection_hidden_dim,
        output_dim=config.projection_dim,
    )
    projection_feq = ProjectionHead(
        input_dim=backbone_feq.in_features,
        hidden_dim=config.projection_hidden_dim,
        output_dim=config.projection_dim,
    )

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

    if config.data in ["ptbxl", "chapman", "georgia", "ningbo"]:
        train_labeled_dataset, train_unlabeled_dataset, val_dataset, test_dataset, open_test_dataset = get_ptbxl(
            config, root=config.root
        )
    elif config.data == "cinc2021":
        train_labeled_dataset, train_unlabeled_dataset, val_dataset, test_dataset, open_test_dataset = get_cinc2021(
            config, root=config.root
        )
    else:
        raise NotImplementedError

    train_labeled_dataset.mode = "train_lb"
    train_unlabeled_dataset.mode = "train_ulb"

    datasets = {
        "l_train": {"labels": train_labeled_dataset.labels},
        "u_train": {"labels": train_unlabeled_dataset.labels},
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

    task = Classification(
        backbone_tem=backbone_tem,
        backbone_feq=backbone_feq,
        projection_tem=projection_tem,
        projection_feq=projection_feq,
    )
    task.prepare(
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

    start = time.time()
    task.run(
        train_set=[train_labeled_dataset, train_unlabeled_dataset],
        eval_set=val_dataset,
        test_set=test_dataset,
        open_test_set=open_test_dataset,
        save_every=config.save_every,
        unlabeled_ratio=config.unlabeled_ratio,
        knn_num_time=config.knn_num_time,
        knn_num_freq=config.knn_num_freq,
        pseudo_cutoff=config.pseudo_cutoff,
        lambda_cross_pseudo=config.lambda_cross_pseudo,
        lambda_supcon_time=config.lambda_supcon_time,
        lambda_supcon_freq=config.lambda_supcon_freq,
        graph_alpha=config.graph_alpha,
        graph_iters=config.graph_iters,
        recompute_every=config.recompute_every,
        use_confidence_weight=config.use_confidence_weight,
        warm_up_end=config.warm_up,
        n_bins=config.n_bins,
        logger=logger,
    )
    elapsed_sec = time.time() - start

    if logger is not None:
        logger.info(f"Total training time: {elapsed_sec / 60:,.2f} minutes.")
        logger.handlers.clear()

    if config.distributed and dist.is_initialized():
        try:
            dist.barrier()
        except Exception:
            pass
        if dist.is_initialized():
            dist.destroy_process_group()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)