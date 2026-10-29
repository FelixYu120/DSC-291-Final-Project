"""Pretrained Presto: pinned source, verified weights, and a frozen-encoder embedding call.

The model code is ``presto_single_file.py`` next to this module, a byte-identical copy of
``single_file_presto.py`` from github.com/nasaharvest/presto at the commit recorded in
``presto_weights.py`` (MIT licence, see PRESTO_LICENSE). The weights are ``data/default_model.pt``
from the same commit, fetched by ``scripts/models/get_presto.py`` and verified by SHA-256 before every
load.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from cropyield.features.presto_inputs import PrestoInputs
from cropyield.models.presto_single_file import Presto
from cropyield.models.presto_weights import PRESTO_WEIGHTS_PATH, weights_verified

EMBEDDING_SIZE = 128


def load_presto(path: Path = PRESTO_WEIGHTS_PATH, device: str | torch.device = "cpu") -> Presto:
    """Pretrained encoder-decoder in eval mode on ``device``; refuses a missing, partial or altered file.

    The upstream code builds its month table on the GPU whenever CUDA is available, so the
    whole model is moved to one device explicitly instead of trusting the constructor.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run: python scripts/models/get_presto.py")
    if not weights_verified(path):
        raise ValueError(f"{path} does not match the pinned Presto weights; rerun scripts/models/get_presto.py")
    model = Presto.construct().to(device)
    state = torch.load(path, map_location=device, weights_only=True)
    model.load_state_dict(state, strict=True)
    return model.eval()


def model_device(model: torch.nn.Module) -> torch.device:
    devices = {p.device for p in model.parameters()}
    if len(devices) != 1:
        raise RuntimeError(f"model parameters are spread over {sorted(map(str, devices))}")
    return devices.pop()


def to_tensors(inputs: PrestoInputs, device: str | torch.device = "cpu") -> dict:
    """Keyword arguments for ``Presto.encoder`` / ``PrestoFineTuningModel`` on ``device``."""
    return {"x": torch.from_numpy(inputs.x).to(device), "mask": torch.from_numpy(inputs.mask).to(device),
            "dynamic_world": torch.from_numpy(inputs.dynamic_world).to(device),
            "latlons": torch.from_numpy(inputs.latlons).to(device), "month": inputs.month}


def encode(model: Presto, inputs: PrestoInputs) -> np.ndarray:
    """Frozen-encoder embedding (EMBEDDING_SIZE,) for one record.

    Presto's encoder output with ``eval_task=True``: the final LayerNorm of the mean over the
    kept tokens (the unmasked band-group tokens of each month plus the latitude/longitude token).
    """
    with torch.no_grad():
        embedding = model.encoder(**to_tensors(inputs, model_device(model)), eval_task=True)
    return embedding[0].cpu().numpy()
