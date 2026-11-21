"""Signal quality gate (P1.2): is this recording good enough for the heart model to score?

Uses the same features as the heart model (preprocessing.model_input: 2 kHz, 5 s windows,
STFT 128/64, raw dB). A small CNN gives each full 5 s window a quality score P(good); the
recording passes when enough full windows reach the cut-off. Every number that decides this
lives in a versioned `<model>.decision.json` next to the model, never in this file.
The zero-padded last window does not vote: padding looks like a dropout.
"""
from __future__ import annotations

import hashlib
import math
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from . import preprocessing as pp

OK, POOR_QUALITY, TOO_SHORT, INVALID_AUDIO = '', 'poor_quality', 'too_short', 'invalid_audio'
_REQUIRED = ('version', 'model_sha256', 'window_cutoff', 'min_good_fraction', 'min_full_windows')

Scorer = Callable[[np.ndarray], np.ndarray]  # (n, 65, 155, 1) -> (n,) P(good)


@dataclass(frozen=True)
class QualityResult:
    ok: bool
    score: float                       # mean P(good) over voting windows, 0..1
    reason: str                        # '' when ok, else POOR_QUALITY / TOO_SHORT / INVALID_AUDIO
    window_scores: tuple[float, ...]   # P(good) per full 5 s window


@dataclass(frozen=True)
class QualityDecision:
    version: str
    model_sha256: str
    window_cutoff: float
    min_good_fraction: float
    min_full_windows: int
    model_file: str = ''

    @classmethod
    def from_dict(cls, d: dict) -> 'QualityDecision':
        missing = [k for k in _REQUIRED if k not in d]
        if missing:
            raise ValueError(f'quality decision missing {missing}')
        dec = cls(version=str(d['version']), model_sha256=str(d['model_sha256']),
                  window_cutoff=float(d['window_cutoff']), min_good_fraction=float(d['min_good_fraction']),
                  min_full_windows=int(d['min_full_windows']), model_file=str(d.get('model_file', '')))
        if not dec.version.startswith('quality_'):
            raise ValueError(f'not a quality decision: version {dec.version!r}')
        if not 0.0 <= dec.window_cutoff <= 1.0:
            raise ValueError(f'window_cutoff out of [0, 1]: {dec.window_cutoff}')
        if not 0.0 < dec.min_good_fraction <= 1.0:
            raise ValueError(f'min_good_fraction out of (0, 1]: {dec.min_good_fraction}')
        if dec.min_full_windows < 1:
            raise ValueError(f'min_full_windows must be >= 1: {dec.min_full_windows}')
        return dec

    @classmethod
    def load(cls, path) -> 'QualityDecision':
        return cls.from_dict(json.loads(Path(path).read_text(encoding='utf-8')))


def features(audio, sr: int) -> tuple[np.ndarray, int]:
    """(model_input batch, number of full 5 s windows). Full windows come first in the batch."""
    batch = pp.model_input(audio, sr)
    n_full = len(pp.resample(audio, sr)) // pp.WINDOW_SAMPLES
    return batch, n_full


def decide(window_scores: Sequence[float], decision: QualityDecision) -> QualityResult:
    """The rule, as a pure function of the per-window scores and the decision file."""
    scores = tuple(float(s) for s in window_scores)
    if len(scores) < decision.min_full_windows:
        return QualityResult(False, 0.0, TOO_SHORT, ())
    good = sum(s >= decision.window_cutoff for s in scores)
    needed = math.ceil(decision.min_good_fraction * len(scores) - 1e-9)
    ok = good >= needed
    return QualityResult(ok, float(np.mean(scores)), OK if ok else POOR_QUALITY, scores)


def _interpreter_class():
    try:
        from ai_edge_litert.interpreter import Interpreter
        return Interpreter
    except ImportError:
        pass
    try:
        from tflite_runtime.interpreter import Interpreter
        return Interpreter
    except ImportError:
        pass
    import tensorflow as tf
    return tf.lite.Interpreter


def _tflite_scorer(model_path) -> Scorer:
    interp = _interpreter_class()(model_path=str(model_path))
    interp.allocate_tensors()
    inp, out = interp.get_input_details()[0], interp.get_output_details()[0]

    def score(batch: np.ndarray) -> np.ndarray:
        res = []
        for w in batch:  # the model has a fixed batch of 1
            interp.set_tensor(inp['index'], w[np.newaxis].astype(np.float32))
            interp.invoke()
            res.append(float(np.ravel(interp.get_tensor(out['index']))[0]))
        return 1.0 - np.asarray(res, dtype=np.float32)  # model outputs P(bad)
    return score


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class QualityChecker:
    def __init__(self, scorer: Scorer, decision: QualityDecision):
        self.scorer = scorer
        self.decision = decision

    @classmethod
    def from_files(cls, model_path, decision_path=None) -> 'QualityChecker':
        model_path = Path(model_path)
        decision_path = Path(decision_path) if decision_path else model_path.with_suffix('.decision.json')
        decision = QualityDecision.load(decision_path)
        actual = sha256_file(model_path)
        if actual != decision.model_sha256:
            raise ValueError(f'model sha256 {actual[:12]} does not match decision file {decision.model_sha256[:12]}')
        return cls(_tflite_scorer(model_path), decision)

    def assess(self, audio, sr: int) -> QualityResult:
        x = np.asarray(audio, dtype=np.float64)
        if x.size == 0 or not np.all(np.isfinite(x)):
            return QualityResult(False, 0.0, INVALID_AUDIO, ())
        batch, n_full = features(x, sr)
        scores = np.asarray(self.scorer(batch[:n_full]), dtype=np.float64) if n_full else ()
        return decide(scores, self.decision)


_default: QualityChecker | None = None


def default_model_path() -> Path:
    import os
    env = os.environ.get('ISHTIRAF_QUALITY_MODEL')
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / 'Model_Training' / '1_AI_Engine' / 'Saved_Models' / 'quality_v1.tflite'


def assess(audio, sr: int, checker: QualityChecker | None = None) -> QualityResult:
    """Assess with the given checker, or the default quality_v1 model (env ISHTIRAF_QUALITY_MODEL)."""
    global _default
    if checker is None:
        if _default is None:
            _default = QualityChecker.from_files(default_model_path())
        checker = _default
    return checker.assess(audio, sr)
