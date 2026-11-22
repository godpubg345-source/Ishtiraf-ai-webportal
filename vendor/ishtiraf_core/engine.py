"""Heart screening engine: validated TFLite model + ishtiraf_core preprocessing.

Shared by the Pi dashboard and the web portal so both give identical results. It feeds the model raw
audio exactly as in training (no bandpass, no normalization, no gain change), scores every
5 s window and averages them (decision D6), and returns NO RESULT instead of guessing
when the model or the recording is not usable.

Cut-offs come from `<model>.decision.json` (P1.5), which is tied to the model by sha256:
REFER (ABNORMAL) / UNSURE / NO REFER (NORMAL). A fixed `threshold=` gives the old two-way
output and is meant for evaluation only.

Before the heart model runs, the signal quality gate (P1.2, `quality_v2.tflite` + its decision
file, next to the heart model) checks the recording; a poor one gives NO RESULT: record again.

A6: `score_session` gives one result per child from several recordings (locations AV, PV, TV,
MV, ...), using `<model>.patient_decision.json` (`ishtiraf_core.patient`). That file is optional:
without it `score` works as before and only `score_session` returns NO RESULT.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import decision as dc
from . import patient as pt
from . import preprocessing as pp
from . import quality as qa

MODEL_VERSION = 'heart_attention_v5'  # default shipped model; an engine reports the file it loaded
NORMAL, ABNORMAL, UNSURE, NO_RESULT = 'NORMAL', 'ABNORMAL', 'UNSURE', 'NO RESULT'
_STATUS = {dc.REFER: ABNORMAL, dc.UNSURE: UNSURE, dc.NO_REFER: NORMAL}
MIN_SECONDS = 2  # below this the recording holds too little of a cardiac cycle
QUALITY_MODEL = 'quality_v2.tflite'
POOR_QUALITY_REASON = 'poor recording quality - record again'


def _interpreter_class():
    """LiteRT on the Pi (ai-edge-litert or tflite-runtime); full TensorFlow on a dev machine."""
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


@dataclass(frozen=True)
class HeartResult:
    status: str               # NORMAL / ABNORMAL / UNSURE / NO RESULT
    prob: float | None        # model probability of an abnormal recording (not calibrated)
    n_windows: int
    reason: str = ''
    decision: str | None = None  # REFER / UNSURE / NO REFER from the decision file
    quality: float | None = None   # mean P(good) from the quality gate, 0..1

    @property
    def score(self) -> int | None:
        """0-100 AI score for display. It is NOT a confidence percentage."""
        return None if self.prob is None else round(self.prob * 100)


@dataclass(frozen=True)
class SessionResult:
    status: str                    # NORMAL / ABNORMAL / UNSURE / NO RESULT for the child
    decision: str | None           # REFER / UNSURE / NO REFER / NO RESULT from the patient decision file
    score: float | None            # combined score of the usable recordings (not calibrated)
    recordings: tuple = ()         # (location, HeartResult) per recording, in the order given
    locations_used: tuple = ()
    missing_locations: tuple = ()  # expected locations with no usable recording: record these
    reason: str = ''
    rule: str | None = None


_SESSION_STATUS = {pt.REFER: ABNORMAL, pt.UNSURE: UNSURE, pt.NO_REFER: NORMAL, pt.NO_RESULT: NO_RESULT}


class HeartEngine:
    def __init__(self, model_path, threshold: float | None = None, decision_path=None, quality_model=None,
                 patient_decision_path=None):
        self.model_path = Path(model_path)
        self.threshold = threshold
        self.decision: dc.Decision | None = None
        self.quality: qa.QualityChecker | None = None
        self.version = self.model_path.stem
        self.error = None
        self._interp = None
        try:
            if not self.model_path.exists():
                raise FileNotFoundError(f'model file not found: {self.model_path}')
            if threshold is None:
                dpath = Path(decision_path) if decision_path else self.model_path.with_name(
                    f'{self.model_path.stem}.decision.json')
                if not dpath.exists():
                    raise FileNotFoundError(f'decision file not found: {dpath.name}')
                self.decision = dc.Decision.load(dpath)
                self.decision.check_model(self.model_path)
                qpath = Path(quality_model) if quality_model else self.model_path.with_name(QUALITY_MODEL)
                if not qpath.exists():
                    raise FileNotFoundError(f'quality model not found: {qpath.name}')
                self.quality = qa.QualityChecker.from_files(qpath)
            self._interp = _interpreter_class()(model_path=str(self.model_path))
            self._interp.allocate_tensors()
            self._in = self._interp.get_input_details()[0]
            self._out = self._interp.get_output_details()[0]
            if tuple(self._in['shape'][1:3]) != pp.SPEC_SHAPE:
                raise ValueError(f"model input {tuple(self._in['shape'])} does not match {pp.SPEC_SHAPE}")
        except Exception as e:  # keep the device usable, but never fake a result
            self._interp, self.error = None, f'{type(e).__name__}: {e}'
        self.patient: pt.PatientDecision | None = None
        self.patient_error = None
        try:  # optional: a missing or wrong file only disables score_session
            ppath = Path(patient_decision_path) if patient_decision_path else self.model_path.with_name(
                f'{self.model_path.stem}.patient_decision.json')
            if not ppath.exists():
                raise FileNotFoundError(f'patient decision file not found: {ppath.name}')
            patient = pt.PatientDecision.load(ppath)
            patient.check_model(self.model_path)
            self.patient = patient
        except Exception as e:
            self.patient_error = f'{type(e).__name__}: {e}'

    @property
    def available(self) -> bool:
        return self._interp is not None

    def score(self, audio, sr: int) -> HeartResult:
        if not self.available:
            return HeartResult(NO_RESULT, None, 0, f'AI model not loaded ({self.error})')
        audio = pp.to_mono(audio)
        if len(audio) < MIN_SECONDS * sr:
            return HeartResult(NO_RESULT, None, 0, f'recording shorter than {MIN_SECONDS} s')
        if not np.isfinite(audio).all():
            return HeartResult(NO_RESULT, None, 0, 'recording contains invalid samples')
        q = None
        if self.quality is not None:
            qr = self.quality.assess(audio, sr)
            q = qr.score
            if not qr.ok:
                detail = 'too short for the quality check' if qr.reason == qa.TOO_SHORT else f'quality {q:.2f}'
                return HeartResult(NO_RESULT, None, 0, f'{POOR_QUALITY_REASON} ({detail})', quality=q)
        x = pp.model_input(audio, sr)
        probs = []
        for window in x:
            self._interp.set_tensor(self._in['index'], window[None].astype(self._in['dtype']))
            self._interp.invoke()
            probs.append(float(np.ravel(self._interp.get_tensor(self._out['index']))[-1]))
        prob = float(np.mean(probs))
        if self.decision is None:
            return HeartResult(ABNORMAL if prob > self.threshold else NORMAL, prob, len(probs))
        d = self.decision.classify(prob)
        return HeartResult(_STATUS[d], prob, len(probs), decision=d, quality=q)

    def score_session(self, recordings) -> SessionResult:
        """One result for a child. `recordings`: iterable of (audio, sr, location); location may be
        None. Each recording goes through `score` (quality gate included); recordings that give NO
        RESULT are left out of the child decision but returned in `recordings`."""
        if not self.available:
            return SessionResult(NO_RESULT, None, None, reason=f'AI model not loaded ({self.error})')
        if self.patient is None:
            return SessionResult(NO_RESULT, None, None, reason=f'patient decision not loaded ({self.patient_error})')
        scored = tuple((location, self.score(audio, sr)) for audio, sr, location in recordings)
        res = self.patient.decide([pt.Recording(r.prob, r.status != NO_RESULT, location) for location, r in scored])
        return SessionResult(_SESSION_STATUS[res.decision], res.decision, res.score, scored, res.locations_used,
                             res.missing_locations, res.reason, self.patient.rule)
