import torch.nn as nn


class ProjectionHead(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 64, output_dim: int = 32):
        super(ProjectionHead, self).__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x):
        return self.network(x)