"""Official challenge metrics, so IshtirafAI numbers can be set next to published ones.

- CirCor / PhysioNet Challenge 2022 murmur task: weighted accuracy per patient over the classes
  Present / Unknown / Absent with weights 5 / 3 / 1 (correct predictions of each class, weighted,
  over the weighted class counts).
- PhysioNet / CinC Challenge 2016: MAcc = (sensitivity + specificity) / 2 per recording. The 2016
  scoring also weighted by signal quality labels, which only exist for the hidden test set; this
  is the plain version. An unsure answer counts as abnormal (refer) unless told otherwise.

These numbers are computed on our own cross-validation, not the hidden challenge test sets, so
they are a guide, not a leaderboard entry.
"""
from __future__ import annotations

import numpy as np

MURMUR_WEIGHTS = {'Present': 5.0, 'Unknown': 3.0, 'Absent': 1.0}


def circor_weighted_accuracy(true, pred) -> float:
    true, pred = list(true), list(pred)
    if len(true) != len(pred):
        raise ValueError('true and pred differ in length')
    bad = (set(true) | set(pred)) - set(MURMUR_WEIGHTS)
    if bad:
        raise ValueError(f'unknown murmur labels: {sorted(bad)}')
    num = sum(MURMUR_WEIGHTS[t] for t, p in zip(true, pred) if t == p)
    den = sum(MURMUR_WEIGHTS[t] for t in true)
    return float(num / den)


def physionet_macc(y_true, pred, unsure_as: int = 1) -> float:
    """pred: 1 abnormal, 0 normal, None unsure (counted as `unsure_as`)."""
    y = np.asarray(y_true, dtype=int)
    p = np.array([unsure_as if v is None else int(v) for v in pred])
    se = float(np.mean(p[y == 1] == 1))
    sp = float(np.mean(p[y == 0] == 0))
    return (se + sp) / 2
