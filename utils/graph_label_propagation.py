import torch
import torch.nn.functional as F


@torch.no_grad()
def propagate_knn_labels(
    embeddings: torch.Tensor,
    seed_labels: torch.Tensor,
    seed_mask: torch.Tensor,
    num_classes: int,
    topk: int = 20,
    alpha: float = 0.9,
    iters: int = 20,
    chunk_size: int = 1024,
):
    if embeddings.ndim != 2:
        raise ValueError("embeddings must be 2D")

    num_nodes = embeddings.shape[0]
    device = embeddings.device
    topk = max(1, min(topk, max(1, num_nodes - 1)))

    normalized = F.normalize(embeddings, dim=1)
    seed_scores = torch.zeros(num_nodes, num_classes, device=device)
    seed_scores[seed_mask] = F.one_hot(
        seed_labels[seed_mask].long(), num_classes=num_classes
    ).float()

    if seed_mask.any():
        class_prior = seed_scores[seed_mask].mean(dim=0, keepdim=True)
    else:
        class_prior = torch.full(
            (1, num_classes), 1.0 / num_classes, device=device
        )

    scores = seed_scores.clone()
    scores[~seed_mask] = class_prior

    knn_indices = []
    knn_weights = []
    for start in range(0, num_nodes, chunk_size):
        end = min(start + chunk_size, num_nodes)
        sims = normalized[start:end] @ normalized.T
        row_indices = torch.arange(start, end, device=device)
        sims[torch.arange(end - start, device=device), row_indices] = -1e9

        weights, indices = torch.topk(sims, k=topk, dim=1)
        weights = torch.softmax(weights, dim=1)
        knn_indices.append(indices)
        knn_weights.append(weights)

    knn_indices = torch.cat(knn_indices, dim=0)
    knn_weights = torch.cat(knn_weights, dim=0)

    for _ in range(iters):
        propagated = torch.zeros_like(scores)
        for start in range(0, num_nodes, chunk_size):
            end = min(start + chunk_size, num_nodes)
            idx = knn_indices[start:end]
            weight = knn_weights[start:end].unsqueeze(-1)
            propagated[start:end] = (scores[idx] * weight).sum(dim=1)

        scores = alpha * propagated + (1.0 - alpha) * seed_scores
        scores[seed_mask] = seed_scores[seed_mask]
        scores = scores / scores.sum(dim=1, keepdim=True).clamp_min(1e-12)

    return scores