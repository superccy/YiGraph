import unittest

import torch

from rgcn_error_trace.model import RelationalRootCauseModel


def make_edge_features(relation_ids, num_relations=5):
    features = torch.zeros(len(relation_ids), num_relations + 3)
    for index, relation_id in enumerate(relation_ids):
        features[index, relation_id] = 1.0
    return features


class RelationalRootCauseModelTest(unittest.TestCase):
    def test_forward_and_backward(self):
        torch.manual_seed(7)
        model = RelationalRootCauseModel(
            node_input_dim=12,
            edge_input_dim=8,
            hidden_dim=16,
            dropout=0.0,
            num_layers=2,
            num_bases=3,
            scorer_mode="pairwise",
        )
        logits = model(
            node_features=torch.randn(6, 12),
            edges=torch.tensor([[0, 1], [1, 2], [4, 2], [3, 5]]),
            edge_features=make_edge_features([0, 1, 3, 4]),
            edge_times=torch.arange(4, dtype=torch.float32),
            candidate_indices=torch.tensor([0, 2, 5]),
            error_index=5,
            pair_features=torch.randn(3, 4),
        )
        self.assertEqual(tuple(logits.shape), (3,))
        self.assertTrue(bool(torch.isfinite(logits).all()))
        logits.sum().backward()
        self.assertTrue(all(parameter.grad is not None for parameter in model.parameters()))

    def test_supports_graphs_without_edges(self):
        model = RelationalRootCauseModel(
            node_input_dim=6,
            edge_input_dim=8,
            hidden_dim=8,
            dropout=0.0,
            scorer_mode="candidate_only",
        )
        logits = model(
            node_features=torch.randn(3, 6),
            edges=torch.zeros((0, 2), dtype=torch.long),
            edge_features=torch.zeros((0, 8)),
            edge_times=torch.zeros((0,)),
            candidate_indices=torch.tensor([0, 2]),
            error_index=2,
            pair_features=torch.zeros((2, 4)),
        )
        self.assertEqual(tuple(logits.shape), (2,))
        self.assertTrue(bool(torch.isfinite(logits).all()))


if __name__ == "__main__":
    unittest.main()
