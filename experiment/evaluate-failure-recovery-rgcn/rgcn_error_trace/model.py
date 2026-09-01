from __future__ import annotations

import torch
from torch import nn


class RelationalGraphConv(nn.Module):
    """Directed R-GCN layer with basis-decomposed relation weights."""

    def __init__(
        self,
        hidden_dim: int,
        num_relations: int,
        num_bases: int,
        dropout: float,
    ) -> None:
        super().__init__()
        if num_relations < 1:
            raise ValueError("num_relations must be positive")
        if num_bases < 1:
            raise ValueError("num_bases must be positive")
        self.num_relations = num_relations
        self.num_bases = min(num_bases, num_relations * 2)
        self.bases = nn.Parameter(
            torch.empty(self.num_bases, hidden_dim, hidden_dim)
        )
        self.coefficients = nn.Parameter(
            torch.empty(num_relations * 2, self.num_bases)
        )
        self.self_loop = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.bias = nn.Parameter(torch.zeros(hidden_dim))
        self.normalization = nn.LayerNorm(hidden_dim)
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.xavier_uniform_(self.bases)
        nn.init.xavier_uniform_(self.coefficients)
        nn.init.xavier_uniform_(self.self_loop.weight)
        nn.init.zeros_(self.bias)

    def forward(
        self,
        node_states: torch.Tensor,
        edges: torch.Tensor,
        relation_ids: torch.Tensor,
    ) -> torch.Tensor:
        output = self.self_loop(node_states)
        if edges.numel() > 0:
            relation_weights = torch.einsum(
                "rb,bio->rio", self.coefficients, self.bases
            )
            source = edges[:, 0]
            target = edges[:, 1]

            forward_messages = torch.bmm(
                node_states[source].unsqueeze(1),
                relation_weights[relation_ids],
            ).squeeze(1)
            reverse_messages = torch.bmm(
                node_states[target].unsqueeze(1),
                relation_weights[relation_ids + self.num_relations],
            ).squeeze(1)

            aggregated = torch.zeros_like(node_states)
            degree = torch.zeros(
                node_states.shape[0],
                dtype=node_states.dtype,
                device=node_states.device,
            )
            aggregated.index_add_(0, target, forward_messages)
            aggregated.index_add_(0, source, reverse_messages)
            degree.index_add_(
                0, target, torch.ones_like(target, dtype=node_states.dtype)
            )
            degree.index_add_(
                0, source, torch.ones_like(source, dtype=node_states.dtype)
            )
            output = output + aggregated / degree.clamp_min(1.0).unsqueeze(1)

        output = self.normalization(output + self.bias)
        return self.dropout(self.activation(output))


class RelationalRootCauseModel(nn.Module):
    """R-GCN encoder and node scorer for recovery-start localization."""

    def __init__(
        self,
        node_input_dim: int,
        edge_input_dim: int,
        hidden_dim: int = 128,
        dropout: float = 0.1,
        scorer_mode: str = "candidate_only",
        num_layers: int = 2,
        num_bases: int = 4,
    ) -> None:
        super().__init__()
        if scorer_mode not in {"candidate_only", "pairwise"}:
            raise ValueError("scorer_mode must be one of: candidate_only, pairwise")
        if num_layers < 1:
            raise ValueError("num_layers must be positive")
        # Edge features contain a relation one-hot vector followed by three
        # structural values, as produced by data._append_edge.
        self.num_relations = edge_input_dim - 3
        if self.num_relations < 1:
            raise ValueError("edge_input_dim must include relation features")
        self.scorer_mode = scorer_mode
        self.node_projector = nn.Sequential(
            nn.Linear(node_input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.layers = nn.ModuleList(
            RelationalGraphConv(
                hidden_dim=hidden_dim,
                num_relations=self.num_relations,
                num_bases=num_bases,
                dropout=dropout,
            )
            for _ in range(num_layers)
        )
        scorer_input_dim = hidden_dim if scorer_mode == "candidate_only" else hidden_dim * 3 + 4
        self.scorer = nn.Sequential(
            nn.Linear(scorer_input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )

    def encode(
        self,
        node_features: torch.Tensor,
        edges: torch.Tensor,
        edge_features: torch.Tensor,
    ) -> torch.Tensor:
        node_states = self.node_projector(node_features)
        if edges.numel() == 0:
            return node_states
        relation_ids = edge_features[:, : self.num_relations].argmax(dim=1)
        for layer in self.layers:
            node_states = layer(node_states, edges, relation_ids)
        return node_states

    def forward(
        self,
        node_features: torch.Tensor,
        edges: torch.Tensor,
        edge_features: torch.Tensor,
        edge_times: torch.Tensor,
        candidate_indices: torch.Tensor,
        error_index: int,
        pair_features: torch.Tensor,
    ) -> torch.Tensor:
        del edge_times  # Kept for compatibility with the shared data pipeline.
        embeddings = self.encode(node_features, edges, edge_features)
        candidate_embeddings = embeddings[candidate_indices]
        if self.scorer_mode == "candidate_only":
            return self.scorer(candidate_embeddings).squeeze(1)

        error_embedding = embeddings[error_index].unsqueeze(0).expand_as(candidate_embeddings)
        score_input = torch.cat(
            [
                candidate_embeddings,
                error_embedding,
                candidate_embeddings * error_embedding,
                pair_features,
            ],
            dim=1,
        )
        return self.scorer(score_input).squeeze(1)
