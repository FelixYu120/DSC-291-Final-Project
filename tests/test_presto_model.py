from datetime import date

import numpy as np
import pytest

torch = pytest.importorskip("torch")  # the "presto" extra

from cropyield.features.presto_inputs import presto_inputs
from cropyield.models import presto_weights as w
from cropyield.models.presto import EMBEDDING_SIZE, encode, load_presto, model_device, to_tensors
from cropyield.satellite.chips import read_chip
from cropyield.satellite.monthly import monthly_series

needs_weights = pytest.mark.skipif(not w.weights_verified(), reason="run scripts/models/get_presto.py first")


def test_vendored_presto_source_is_the_pinned_commit():
    assert w.sha256(w.PRESTO_SOURCE_PATH) == w.PRESTO_SOURCE_SHA256
    assert w.PRESTO_COMMIT in w.PRESTO_WEIGHTS_URL


@needs_weights
def test_checkpoint_loads_strictly_and_encoder_runs(chip_dir):
    model = load_presto()
    assert not model.training
    assert model_device(model) == torch.device("cpu")  # upstream builds the month table on the GPU if present
    inputs = presto_inputs(monthly_series(read_chip(chip_dir), date(2023, 3, 1), date(2023, 6, 30)),
                           latitude=-13.3171, longitude=33.3837)
    embedding = encode(model, inputs)
    assert embedding.shape == (EMBEDDING_SIZE,) and np.isfinite(embedding).all()
    head = model.construct_finetuning_model(num_outputs=1, regression=True)
    with torch.no_grad():
        prediction = head.eval()(**to_tensors(inputs, model_device(head)))
    assert prediction.shape == (1, 1) and torch.isfinite(prediction).all()


def test_altered_weights_are_refused(tmp_path):
    bad = tmp_path / "default_model.pt"
    bad.write_bytes(b"not a checkpoint")
    with pytest.raises(ValueError):
        load_presto(bad)
    with pytest.raises(FileNotFoundError):
        load_presto(tmp_path / "missing.pt")
