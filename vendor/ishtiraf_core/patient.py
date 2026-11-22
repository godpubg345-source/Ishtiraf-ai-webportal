"""A6: one decision per child from several recordings (auscultation locations AV, PV, TV, MV, ...).

Per recording the engine gives a model probability and a quality result. For a child:

1. Only usable recordings count: quality ok and a finite probability. None usable -> NO RESULT
   (record again).
2. Repeats at the same location (AV, AV_1, AV_2) are re-measurements of one spot: their mean is
   the location score. A recording with no location is its own site (it cannot be assumed to be
   a repeat of another).
3. The location scores are combined by one rule: max, mean, top2 (mean of the two highest) or
   noisy_or (1 - prod(1 - p)).
4. Band as in `decision.py`: score < t_lo NO REFER, t_lo <= score < t_hi UNSURE, else REFER.
5. Missing locations: a child is only cleared (NO REFER) when at least `min_ok_locations` named
   locations have a usable recording; otherwise UNSURE with the locations to record. A missing
   location never blocks a REFER, since one abnormal site is enough to refer.

The file `<model>.patient_decision.json` is tied to one model by sha256, like `decision.py`.
Fitting helpers (numpy only) choose the rule and the band on training children; the device only
loads the file.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from . import decision as dc

REFER, UNSURE, NO_REFER, NO_RESULT = dc.REFER, dc.UNSURE, dc.NO_REFER, 'NO RESULT'
RULES = ('max', 'mean', 'top2', 'noisy_or')
STANDARD_LOCATIONS = ('AV', 'PV', 'TV', 'MV')
KIND = 'patient_decision'
NO_USABLE_REASON = 'no recording passed the quality check - record again'
_REPEAT = re.compile(r'_\d+$')


@dataclass(frozen=True)
class Recording:
    prob: float | None          # model probability of an abnormal recording; None = not scored
    quality_ok: bool
    location: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.quality_ok) and self.prob is not None and math.isfinite(self.prob)


@dataclass(frozen=True)
class Child:
    person: str
    label: int | None           # 1 abnormal / murmur present, 0 normal / absent, None unknown
    recordings: tuple
    fold: int | None = None
    murmur: str | None = None   # CirCor label Present / Absent / Unknown, for weighted accuracy


def normalise_location(loc) -> str | None:
    if loc is None:
        return None
    s = _REPEAT.sub('', str(loc).strip().upper())
    return s or None


def aggregate(scores, rule: str) -> float:
    s = np.asarray(scores, float)
    if rule not in RULES:
        raise ValueError(f'unknown rule {rule!r}, expected one of {RULES}')
    if len(s) == 0:
        raise ValueError('no scores to combine')
    if rule == 'max':
        return float(s.max())
    if rule == 'mean':
        return float(s.mean())
    if rule == 'top2':
        return float(np.sort(s)[-2:].mean())
    return float(1.0 - np.prod(1.0 - np.clip(s, 0.0, 1.0)))


def site_scores(recordings) -> dict:
    """{location or ('unlabelled', i): mean probability} over usable recordings."""
    sites: dict = {}
    for i, r in enumerate(recordings):
        if r.usable:
            loc = normalise_location(r.location)
            sites.setdefault(loc if loc else ('unlabelled', i), []).append(float(r.prob))
    return {k: float(np.mean(v)) for k, v in sites.items()}


def child_score(recordings, rule: str) -> float | None:
    sites = site_scores(recordings)
    return aggregate(list(sites.values()), rule) if sites else None


@dataclass(frozen=True)
class PatientResult:
    decision: str                   # REFER / UNSURE / NO REFER / NO RESULT
    score: float | None             # combined score (not calibrated), None for NO RESULT
    n_used: int                     # usable recordings
    locations_used: tuple = ()      # named locations with a usable recording
    missing_locations: tuple = ()   # expected locations without one
    reason: str = ''


@dataclass(frozen=True)
class PatientDecision:
    model: str
    model_sha256: str
    rule: str
    t_lo: float
    t_hi: float
    min_ok_locations: int = 1
    expected_locations: tuple = STANDARD_LOCATIONS
    metrics: dict = field(default_factory=dict, compare=False)
    kind: str = KIND
    version: int = 1

    def __post_init__(self):
        if self.rule not in RULES:
            raise ValueError(f'unknown rule {self.rule!r}')
        if not (0.0 < self.t_lo <= self.t_hi <= 1.0):
            raise ValueError(f'need 0 < t_lo <= t_hi <= 1, got {self.t_lo}, {self.t_hi}')
        if int(self.min_ok_locations) < 1:
            raise ValueError('min_ok_locations must be at least 1')
        if self.kind != KIND or self.version != 1:
            raise ValueError('unsupported patient decision file')
        object.__setattr__(self, 'expected_locations',
                           tuple(normalise_location(x) for x in self.expected_locations))

    def _order(self, locs):
        exp = list(self.expected_locations)
        return tuple(sorted(locs, key=lambda x: (exp.index(x) if x in exp else len(exp), x)))

    def decide(self, recordings) -> PatientResult:
        recordings = list(recordings)
        sites = site_scores(recordings)
        named = self._order({k for k in sites if isinstance(k, str)})
        missing = tuple(x for x in self.expected_locations if x not in named)
        n_used = sum(r.usable for r in recordings)
        if not sites:
            return PatientResult(NO_RESULT, None, 0, (), missing, NO_USABLE_REASON)
        s = aggregate(list(sites.values()), self.rule)
        if s >= self.t_hi:
            return PatientResult(REFER, s, n_used, named, missing)
        if s >= self.t_lo:
            return PatientResult(UNSURE, s, n_used, named, missing)
        covered = sum(x in self.expected_locations for x in named)  # unknown names never clear a child
        if covered < self.min_ok_locations:
            todo = ', '.join(missing) or 'more locations'
            return PatientResult(UNSURE, s, n_used, named, missing,
                                 f'only {covered} expected location(s) with a good recording; record {todo} before clearing')
        return PatientResult(NO_REFER, s, n_used, named, missing)

    def check_model(self, model_path) -> None:
        if dc.sha256_file(model_path) != self.model_sha256:
            raise ValueError(f'{Path(model_path).name} is not the model this patient decision file was made for')

    def save(self, path) -> None:
        d = asdict(self)
        d['expected_locations'] = list(self.expected_locations)
        Path(path).write_text(json.dumps(d, indent=2), encoding='utf-8')

    @classmethod
    def load(cls, path) -> 'PatientDecision':
        data = json.loads(Path(path).read_text(encoding='utf-8'))  # kind and version checked on init
        data['expected_locations'] = tuple(data.get('expected_locations', STANDARD_LOCATIONS))
        return cls(**data)


# ---- fitting (training machine only) ------------------------------------------------------------

def child_metrics(kids, pdec: PatientDecision) -> dict:
    """Screening metrics over labelled children. UNSURE and NO RESULT count as not cleared."""
    dec = np.array([pdec.decide(k.recordings).decision for k in kids if k.label is not None])
    y = np.array([k.label for k in kids if k.label is not None])
    pos, neg = dec[y == 1], dec[y == 0]
    return {'sensitivity': float(np.mean(pos != NO_REFER)) if len(pos) else float('nan'),
            'specificity': float(np.mean(neg == NO_REFER)) if len(neg) else float('nan'),
            'unsure_rate': float(np.mean(dec == UNSURE)) if len(dec) else float('nan'),
            'no_result_rate': float(np.mean(dec == NO_RESULT)) if len(dec) else float('nan'),
            'refer_sensitivity': float(np.mean(pos == REFER)) if len(pos) else float('nan'),
            'refer_specificity': float(np.mean(neg != REFER)) if len(neg) else float('nan'),
            'n': int(len(dec)), 'n_abnormal': int(len(pos))}


def _fit_band(kids, rule, target_sens, target_spec):
    pairs = [(child_score(k.recordings, rule), k.label) for k in kids if k.label is not None]
    pairs = [(s, y) for s, y in pairs if s is not None]
    s, y = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
    t_lo, t_hi = dc._band(s, y, target_sens, target_spec)
    t_lo = min(max(t_lo, 1e-6), 1.0)
    return t_lo, min(max(t_hi, t_lo), 1.0)


def _decision(rule, t_lo, t_hi, min_ok, expected):
    return PatientDecision('fit', '', rule, t_lo, t_hi, min_ok, expected)


def choose(kids, target_sens, target_spec, rules=RULES, min_ok=1, expected=STANDARD_LOCATIONS,
           sens_tolerance=0.02):
    """Pick the rule by inner CV over these children's folds (highest held-out specificity among
    rules whose held-out sensitivity is within `sens_tolerance` of the target), then fit its band on
    all of them. Returns (rule, t_lo, t_hi)."""
    kids = list(kids)
    folds = sorted({k.fold for k in kids if k.fold is not None})
    if len(rules) > 1 and len(folds) >= 2:
        scored = []
        for rule in rules:
            ms = []
            for g in folds:
                tr = [k for k in kids if k.fold != g]
                te = [k for k in kids if k.fold == g]
                lo, hi = _fit_band(tr, rule, target_sens, target_spec)
                ms.append(child_metrics(te, _decision(rule, lo, hi, min_ok, expected)))
            sens = float(np.nanmean([m['sensitivity'] for m in ms]))
            spec = float(np.nanmean([m['specificity'] for m in ms]))
            scored.append((sens >= target_sens - sens_tolerance, spec, sens, rule))
        rule = max(scored)[3]
    else:
        rule = rules[0]
    return (rule, *_fit_band(kids, rule, target_sens, target_spec))


def nested_patient_choice(kids, target_sens, target_spec, rules=RULES, min_ok=1, expected=STANDARD_LOCATIONS):
    """Outer CV over the children's folds: choose rule and band on the other folds (with inner CV),
    measure on the held-out fold. Also returns every held-out child's decision."""
    kids = list(kids)
    out, predictions = [], {}
    for f in sorted({k.fold for k in kids if k.fold is not None}):
        tr = [k for k in kids if k.fold != f]
        te = [k for k in kids if k.fold == f]
        rule, lo, hi = choose(tr, target_sens, target_spec, rules, min_ok, expected)
        pdec = _decision(rule, lo, hi, min_ok, expected)
        out.append({'fold': int(f), 'rule': rule, 't_lo': lo, 't_hi': hi, **child_metrics(te, pdec)})
        for k in te:
            predictions[k.person] = pdec.decide(k.recordings).decision
    keys = ('sensitivity', 'specificity', 'unsure_rate', 'no_result_rate', 'refer_sensitivity', 'refer_specificity')
    summary = {k: [float(np.nanmean([o[k] for o in out])), float(np.nanstd([o[k] for o in out]))] for k in keys}
    lab = [k for k in kids if k.label is not None and k.person in predictions]
    pos = [predictions[k.person] for k in lab if k.label == 1]
    neg = [predictions[k.person] for k in lab if k.label == 0]
    pooled = {'sensitivity': float(np.mean([d != NO_REFER for d in pos])),
              'specificity': float(np.mean([d == NO_REFER for d in neg])),
              'unsure_rate': float(np.mean([predictions[k.person] == UNSURE for k in lab])),
              'children': len(lab), 'abnormal': len(pos)}
    return {'target_sensitivity': target_sens, 'target_specificity': target_spec, 'rules': list(rules),
            'min_ok_locations': min_ok, 'folds': out, 'summary': summary, 'pooled': pooled,
            'predictions': predictions}
