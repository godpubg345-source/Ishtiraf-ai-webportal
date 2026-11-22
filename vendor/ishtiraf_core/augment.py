"""Device augmentation for training (v5): random gain and a smooth EQ, applied to dB features.

The features are power in dB, so multiplying the audio by g adds exactly 20*log10(g) to every
bin, and a (slowly varying) linear filter adds its dB response per frequency row. Training on
these makes the model less tied to one stethoscope's level and frequency response, without
changing the preprocessing contract used on the Pi and the portal.
"""
from __future__ import annotations

import numpy as np

from . import preprocessing as pp

N_FREQ = pp.SPEC_SHAPE[0]
FLOOR_DB = float(10 * np.log10(pp._EPS))  # -100 dB: bins at the eps floor (e.g. DC after detrend) do not move


def device_curves(n: int, rng: np.random.Generator, max_gain_db: float = 10.0, max_eq_db: float = 6.0) -> np.ndarray:
    """(n, 65) dB curves: gain in [-max_gain_db, max_gain_db] plus an EQ (tilt + bump) within +-max_eq_db."""
    f = np.linspace(0.0, 1.0, N_FREQ)
    gain = rng.uniform(-max_gain_db, max_gain_db, (n, 1))
    tilt = rng.uniform(-max_eq_db / 2, max_eq_db / 2, (n, 1)) * (2 * f - 1)
    mu, width = rng.uniform(0, 1, (n, 1)), rng.uniform(0.1, 0.4, (n, 1))
    bump = rng.uniform(-max_eq_db / 2, max_eq_db / 2, (n, 1)) * np.exp(-((f - mu) / width) ** 2)
    return gain + tilt + bump


def apply_curves(x: np.ndarray, curves: np.ndarray) -> np.ndarray:
    """x: (n, 65, 155, 1) dB features; adds curves[i, freq] to every time frame, never below the floor."""
    return np.maximum(x + curves[:, :, None, None], FLOOR_DB).astype(np.float32)
