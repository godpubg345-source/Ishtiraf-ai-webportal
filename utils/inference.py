"""Portal AI: the same validated heart engine the Pi uses (ishtiraf_core.engine).

The model gets the raw recording exactly as in training and the result is NO RESULT
when the model or the audio is not usable. There is no validated lung model yet, and
no rule-based disease labels (murmur type, grade) are produced.
"""
import logging
import os
import sys
from pathlib import Path

_PORTAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PORTAL / 'vendor'))

from ishtiraf_core.engine import ABNORMAL, NO_RESULT, NORMAL, HeartEngine  # noqa: E402,F401

logger = logging.getLogger('IshtirafAI.Inference')
MODEL_PATH = Path(os.environ.get('HEART_MODEL_PATH', _PORTAL / 'ai_models' / 'heart_attention_v5.tflite'))
_engine = None


def load_models():
    """Load the heart engine once. Failure is logged and leaves the portal running without AI."""
    global _engine
    if _engine is None:
        _engine = HeartEngine(MODEL_PATH)
        if _engine.available:
            logger.info(f'Heart model loaded: {_engine.version}')
        else:
            logger.error(f'Heart model NOT loaded: {_engine.error}')
    return _engine


def get_engine():
    return _engine if _engine is not None else load_models()


def analyze_heart(audio, sr):
    """Returns a result dict; 'status' is NORMAL / ABNORMAL / UNSURE / NO RESULT."""
    engine = get_engine()
    res = engine.score(audio, sr)
    out = {'organ': 'Heart', 'status': res.status, 'probability': res.prob, 'score': res.score,
           'n_windows': res.n_windows, 'model': engine.version, 'decision': res.decision,
           'band': None if engine.decision is None else {'unsure_from': engine.decision.t_lo, 'refer_from': engine.decision.t_hi},
           'note': 'Screening aid only - not a diagnosis. Score is 0-100, not a confidence.'}
    if res.status == NO_RESULT:
        out['reason'] = res.reason
        out['model_available'] = engine.available
    return out


def analyze_lung(audio, sr):
    return {'organ': 'Lung', 'status': 'NOT ASSESSED', 'reason': 'No validated lung model yet'}
