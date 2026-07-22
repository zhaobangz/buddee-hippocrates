"""Device detection helpers for routing model computation to GPU when available.

Provides a small, safe API for deciding whether to use CUDA / MPS or CPU.
"""
import logging
from contextlib import suppress
from typing import Tuple

logger = logging.getLogger(__name__)

try:
    import torch  # type: ignore[import-not-found]
except ImportError:
    torch = None

try:
    # newer PyTorch exposes mps availability
    has_mps = torch is not None and getattr(torch.backends, 'mps', None) is not None and torch.backends.mps.is_available()
except Exception:
    logger.debug("PyTorch MPS backend check failed", exc_info=True)
    has_mps = False


def get_torch_device(preferred: str = 'auto', force_cpu: bool = False) -> Tuple[str, int]:
    """Return (device_str, device_index) for use with transformers/pipeline.

    device_str is one of 'cuda', 'mps', 'cpu'. device_index is the integer
    index used by transformers pipeline (0 for first CUDA device, -1 for CPU).
    """
    if force_cpu:
        return 'cpu', -1

    if preferred and preferred != 'auto':
        p = preferred.lower()
        if p == 'cuda':
            if torch is not None and torch.cuda.is_available():
                return 'cuda', 0
            return 'cpu', -1
        if p == 'mps':
            if has_mps:
                return 'mps', -1
            return 'cpu', -1
        if p == 'cpu':
            return 'cpu', -1

    # auto-detect
    if torch is not None:
        with suppress(Exception):
            if torch.cuda.is_available():
                return 'cuda', 0
    if has_mps:
        return 'mps', -1
    return 'cpu', -1
