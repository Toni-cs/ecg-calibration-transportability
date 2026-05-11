import torch


class RandomSampler(torch.utils.data.Sampler):
    """sampling without replacement"""

    def __init__(self, num_data, num_sample):
        epochs = num_sample // num_data + 1
        self.indices = torch.cat(
            [torch.randperm(num_data) for _ in range(epochs)]
        ).tolist()[:num_sample]

    def __iter__(self):
        return iter(self.indices)

    def __len__(self):
        return len(self.indices)
