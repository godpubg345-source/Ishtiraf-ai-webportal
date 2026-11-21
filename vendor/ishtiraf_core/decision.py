"""Operating point for screening (P1.5): two cut-offs on the model probability, loaded from a file.

    p <  t_lo           -> NO REFER   (t_lo keeps sensitivity >= target on training folds)
    t_lo <= p < t_hi    -> UNSURE     (refer or re-record; counts as "not cleared")
    p >= t_hi           -> REFER      (t_hi keeps specificity >= target on training folds)

The file `<model>.decision.json` is tied to one model by sha256, so a new model can never
silently reuse an old threshold. Fitting helpers are numpy only; the device only loads.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

REFER, UNSURE, NO_REFER = 'REFER', 'UNSURE', 'NO REFER'
_EPS = 1e-6


def threshold_for_sensitivity(p, y, target: float) -> float:
    """Highest cut-off t with mean(p[y==1] >= t) >= target."""
    pos = np.sort(np.asarray(p, float)[np.asarray(y) == 1])[::-1]
    if len(pos) == 0:
        raise ValueError('no positive examples')
    k = max(1, math.ceil(target * len(pos) - 1e-9))
    return float(pos[k - 1])


def threshold_for_specificity(p, y, target: float) -> float:
    """Lowest cut-off t with mean(p[y==0] < t) >= target."""
    neg = np.sort(np.asarray(p, float)[np.asarray(y) == 0])
    if len(neg) == 0:
        raise ValueError('no negative examples')
    k = max(1, math.ceil(target * len(neg) - 1e-9))
    return float(np.nextafter(neg[k - 1], np.inf))


def _band(p, y, target_sens, target_spec):
    t_lo = threshold_for_sensitivity(p, y, target_sens)
    t_hi = max(t_lo, threshold_for_specificity(p, y, target_spec))
    return t_lo, t_hi


def screen_metrics(p, y, t_lo: float, t_hi: float) -> dict:
    p, y = np.asarray(p, float), np.asarray(y)
    pos, neg = p[y == 1], p[y == 0]
    return {'sensitivity': float(np.mean(pos >= t_lo)),          # abnormal not cleared
            'specificity': float(np.mean(neg < t_lo)),           # normal cleared
            'unsure_rate': float(np.mean((p >= t_lo) & (p < t_hi))),
            'refer_sensitivity': float(np.mean(pos >= t_hi)),
            'refer_specificity': float(np.mean(neg < t_hi)),
            'n': int(len(p)), 'n_abnormal': int(len(pos))}


def nested_operating_point(p, y, folds, target_sens: float, target_spec: float) -> dict:
    """Choose the band on the other folds, measure it on the held-out fold."""
    p, y, folds = np.asarray(p, float), np.asarray(y), np.asarray(folds)
    out = []
    for f in sorted(set(folds.tolist())):
        tr, te = folds != f, folds == f
        t_lo, t_hi = _band(p[tr], y[tr], target_sens, target_spec)
        out.append({'fold': int(f), 't_lo': t_lo, 't_hi': t_hi, **screen_metrics(p[te], y[te], t_lo, t_hi)})
    keys = ('sensitivity', 'specificity', 'unsure_rate', 'refer_sensitivity', 'refer_specificity')
    summary = {k: [float(np.mean([o[k] for o in out])), float(np.std([o[k] for o in out]))] for k in keys}
    return {'target_sensitivity': target_sens, 'target_specificity': target_spec, 'folds': out, 'summary': summary}


def _logit(p):
    p = np.clip(np.asarray(p, float), _EPS, 1 - _EPS)
    return np.log(p / (1 - p))


def fit_platt(p, y, iters: int = 100) -> tuple[float, float]:
    """Logistic regression of y on logit(p) (Newton steps, small ridge for stability)."""
    x, y = _logit(p), np.asarray(y, float)

    def loss(a, b):
        z = a * x + b
        return float(np.sum(np.logaddexp(0, z) - y * z) + 0.5e-6 * a * a)

    a, b = 1.0, 0.0
    cur = loss(a, b)
    for _ in range(iters):
        q = 0.5 * (1 + np.tanh(0.5 * (a * x + b)))  # stable sigmoid
        w = q * (1 - q) + 1e-9
        g = np.array([np.sum((q - y) * x) + 1e-6 * a, np.sum(q - y)])
        h = np.array([[np.sum(w * x * x) + 1e-6, np.sum(w * x)], [np.sum(w * x), np.sum(w)]])
        step = np.linalg.solve(h, g)
        t = 1.0
        while t > 1e-8 and loss(a - t * step[0], b - t * step[1]) > cur:
            t *= 0.5  # backtracking: never accept a step that makes the fit worse
        a, b = a - t * step[0], b - t * step[1]
        new = loss(a, b)
        if cur - new < 1e-12:
            break
        cur = new
    return float(a), float(b)


def apply_platt(p, a: float, b: float):
    return 0.5 * (1 + np.tanh(0.5 * (a * _logit(p) + b)))


def ece(p, y, bins: int = 10) -> float:
    """Expected calibration error with equal-width bins."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(np.sum(idx == i) / len(p) * abs(p[idx == i].mean() - y[idx == i].mean())
                     for i in range(bins) if np.any(idx == i)))


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class Decision:
    model: str
    model_sha256: str
    t_lo: float
    t_hi: float
    platt_a: float
    platt_b: float
    metrics: dict = field(default_factory=dict, compare=False)
    version: int = 1

    def __post_init__(self):
        if not (0.0 < self.t_lo <= self.t_hi < 1.0):
            raise ValueError(f'need 0 < t_lo <= t_hi < 1, got {self.t_lo}, {self.t_hi}')

    def classify(self, prob: float) -> str:
        if prob >= self.t_hi:
            return REFER
        return UNSURE if prob >= self.t_lo else NO_REFER

    def calibrated(self, prob: float) -> float:
        return float(apply_platt(prob, self.platt_a, self.platt_b))

    def check_model(self, model_path) -> None:
        if sha256_file(model_path) != self.model_sha256:
            raise ValueError(f'{Path(model_path).name} is not the model this decision file was made for')

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path) -> 'Decision':
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('version') != 1:
            raise ValueError('unsupported decision file version')
        return cls(**data)
