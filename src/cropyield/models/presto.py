"""Pretrained Presto: pinned source, verified weights, and a frozen-encoder embedding call.

The model code is ``presto_single_file.py`` next to this module, a byte-identical copy of
``single_file_presto.py`` from github.com/nasaharvest/presto at PRESTO_COMMIT (MIT licence,
see PRESTO_LICENSE). The weights are ``data/default_model.pt`` from the same commit, fetched
by ``scripts/get_presto.py`` and verified by SHA-256 before every load.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from cropyield.features.presto_inputs import PrestoInputs
from cropyield.models.presto_single_file import Presto
from cropyield.models.presto_weights import (  # noqa: F401  (re-exported for callers)
    PRESTO_COMMIT,
    PRESTO_REPO,
    PRESTO_SOURCE_PATH,
    PRESTO_SOURCE_SHA256,
    PRESTO_WEIGHTS_BYTES,
    PRESTO_WEIGHTS_PATH,
    PRESTO_WEIGHTS_SHA256,
    PRESTO_WEIGHTS_URL,
    sha256,
    weights_verified,
)

EMBEDDING_SIZE = 128


def load_presto(path: Path = PRESTO_WEIGHTS_PATH) -> Presto:
    """Pretrained encoder-decoder in eval mode; refuses a missing, partial or altered file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run: python scripts/get_presto.py")
    if not weights_verified(path):
        raise ValueError(f"{path} does not match the pinned Presto weights; rerun scripts/get_presto.py")
    model = Presto.construct()
    state = torch.load(path, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    return model.eval()


def to_tensors(inputs: PrestoInputs) -> dict:
    """Keyword arguments for ``Presto.encoder`` / ``PrestoFineTuningModel``."""
    return {"x": torch.from_numpy(inputs.x), "mask": torch.from_numpy(inputs.mask),
            "dynamic_world": torch.from_numpy(inputs.dynamic_world),
            "latlons": torch.from_numpy(inputs.latlons), "month": inputs.month}


def encode(model: Presto, inputs: PrestoInputs) -> np.ndarray:
    """Frozen-encoder embedding (EMBEDDING_SIZE,) for one record: mean over kept tokens."""
    with torch.no_grad():
        embedding = model.encoder(**to_tensors(inputs), eval_task=True)
    return embedding[0].numpy()
