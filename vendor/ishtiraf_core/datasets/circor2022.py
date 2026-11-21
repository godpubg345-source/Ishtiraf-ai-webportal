"""CirCor DigiScope Phonocardiogram Dataset 2022 (PhysioNet, v1.0.3, ODC-BY 1.0).

942 patients (mostly children, Brazil), 3163 recordings at 4 kHz from AV/PV/TV/MV/Phc, with
murmur Present / Absent / Unknown (Unknown = too poor to judge) and a clinical Outcome.
Some children were screened in both campaigns under two ids ("Additional ID"): `person`
joins them, and every split must be by person.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

LOCATIONS = ('AV', 'PV', 'TV', 'MV', 'Phc')


@dataclass(frozen=True)
class Recording:
    name: str            # e.g. 13918_AV or 49748_MV_2
    patient_id: str
    person: str          # same value for ids that belong to one child
    location: str
    wav_path: Path
    murmur: str          # patient-level: Present / Absent / Unknown
    murmur_here: bool    # murmur reported at this location
    outcome: str         # patient-level clinical outcome: Normal / Abnormal
    age: str | None
    campaign: str


def _nan(v):
    return None if v in (None, '', 'nan') else v


def _persons(rows) -> dict:
    """Union-find over Patient ID <-> Additional ID."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in rows:
        a, b = r['Patient ID'], _nan(r['Additional ID'])
        find(a)
        if b:
            parent[find(a)] = find(b)
    return {pid: f'person-{find(pid)}' for pid in parent}


def list_recordings(root) -> list[Recording]:
    root = Path(root)
    rows = list(csv.DictReader(open(root / 'training_data.csv', newline='', encoding='utf-8')))
    meta = {r['Patient ID']: r for r in rows}
    person = _persons(rows)
    out = []
    for wav in sorted((root / 'training_data').glob('*.wav')):
        pid, loc = wav.stem.split('_')[:2]
        r = meta[pid]
        where = (_nan(r['Murmur locations']) or '').split('+')
        out.append(Recording(name=wav.stem, patient_id=pid, person=person[pid], location=loc, wav_path=wav,
                             murmur=r['Murmur'], murmur_here=loc in where, outcome=r['Outcome'],
                             age=_nan(r['Age']), campaign=r['Campaign']))
    return out


def person_folds(persons, labels, k: int = 5, seed: int = 42) -> list[int]:
    """Fold (1..k) per item. A person is never split; positive persons are spread evenly."""
    person_label = {}
    for p, y in zip(persons, labels):
        person_label[p] = person_label.get(p, False) or bool(y)
    rng = np.random.default_rng(seed)
    fold_of = {}
    for cls in (True, False):
        group = sorted(p for p, y in person_label.items() if y is cls)
        for i, j in enumerate(rng.permutation(len(group))):
            fold_of[group[j]] = i % k + 1
    return [fold_of[p] for p in persons]
