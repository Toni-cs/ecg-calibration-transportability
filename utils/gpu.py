import os

STR2GPU = {
    "0": "GPU-7e5f8113-893b-23c8-cd67-101eea2f8eea",
    "1": "GPU-5fd619b1-1513-c518-8152-a8c4e6ea3ce5",
    "2": "GPU-1ed439f1-d754-f2fc-4f36-f4e1e25ead56",
    "3": "GPU-ff1babc7-5657-2e71-1a07-a9558d82a9e0",
    "4": "GPU-edefb71f-8316-c832-8331-94667e51a510",
}


def set_gpu(config):
    if getattr(config, 'gpus', None) is None:
        config.gpus = [0]

    if config.server == "workstation2":
        gpus = ",".join([STR2GPU[str(gpu)] for gpu in config.gpus])
    else:
        gpus = ",".join([str(gpu) for gpu in config.gpus])
    os.environ["CUDA_VISIBLE_DEVICES"] = gpus
