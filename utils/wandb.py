try:
    import wandb
except ImportError:
    wandb = None


def configure_wandb(name: str, project: str, config: object):
    if wandb is None:
        raise ImportError(
            "wandb is not installed. Install it or disable --enable-wandb."
        )

    wandb.init(
        name=name,
        project=project,
        config=config.__dict__,
        sync_tensorboard=True,
    )
