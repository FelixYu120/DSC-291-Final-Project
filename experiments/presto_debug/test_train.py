import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn

from train import YieldModel, choose_rows, logical_batches, fit_mode_mse, target_normalization, inverse_predictions, STAGES


class Encoder(nn.Module):
    embedding_size = 2
    def __init__(self):
        super().__init__()
        self.weight = nn.Parameter(torch.tensor([1.0, 2.0]))
    def forward(self, x, eval_task):
        return x * self.weight


class Arrays:
    def batches(self, index, size):
        # Simulate incompatible kept-token counts: each encoder call has one row.
        return [np.asarray([i]) for i in reversed(index)]
    def batch(self, block):
        return {"x": torch.tensor([[float(i + 1), float(i + 2)] for i in block])}


def test_bn_runs_after_concatenating_token_groups_and_backpropagates():
    model = YieldModel(Encoder())
    model.train()
    pred = model(Arrays(), np.array([0, 1]))
    assert pred.shape == (2,)
    pred.sum().backward()
    assert model.encoder.weight.grad is not None
    assert model.linear.weight.grad is not None


def test_singleton_bn_eval_still_learns_and_train_mode_is_rejected():
    model = YieldModel(Encoder())
    model.train()
    with pytest.raises(ValueError, match="at least two"):
        model(Arrays(), np.array([0]))
    model.bn.eval()
    model(Arrays(), np.array([0])).sum().backward()
    assert model.encoder.weight.grad is not None
    assert model.bn.weight.grad is not None


def test_fit_diagnostic_preserves_bn_running_statistics():
    model = YieldModel(Encoder())
    before = model.bn.running_mean.clone(), model.bn.running_var.clone(), model.bn.num_batches_tracked.clone()
    assert np.isfinite(fit_mode_mse(model, Arrays(), np.array([1., 2.]), np.array([0, 1])))
    assert all(torch.equal(a, b) for a, b in zip(before, (model.bn.running_mean, model.bn.running_var, model.bn.num_batches_tracked)))


def test_rows_exclude_holdout_and_validate_by_group():
    fields = pd.DataFrame({"fold": ["0", "1", "2", "3", "4"], "group_id": list("abcde")})
    train, val = choose_rows(fields, 3, False)
    assert set(train) == {2, 3, 4} and set(val) == {1}
    fields.loc[2, "group_id"] = "b"
    with pytest.raises(ValueError, match="overlap"):
        choose_rows(fields, 3, False)


def test_batch_planner_never_produces_singleton_tail():
    blocks = logical_batches(np.arange(33), 16, np.random.default_rng(1))
    assert all(len(block) >= 2 for block in blocks)
    assert sorted(np.concatenate(blocks).tolist()) == list(range(33))


def test_target_transform_uses_only_training_and_is_invertible():
    target = np.array([1., 3., 200.])
    train = np.array([0, 1])
    mean, sd = target_normalization(target, train)
    assert (mean, sd) == (2., 1.)
    target[2] = -10000.  # validation outcome cannot influence target scaling
    assert target_normalization(target, train) == (mean, sd)
    expected = np.array([1., 3.])
    assert np.allclose(inverse_predictions((expected - mean) / sd, mean, sd), expected)


def test_constant_target_rejected_and_regularization_control_is_zero():
    with pytest.raises(ValueError, match="zero variance"):
        target_normalization(np.array([4., 4.]), np.array([0, 1]))
    assert STAGES["none"] == (128, 0.0, 0.0)
