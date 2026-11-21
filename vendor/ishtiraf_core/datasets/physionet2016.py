"""PhysioNet/CinC 2016 records in the order used to build the training arrays."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Record:
    name: str
    wav_path: Path
    label: int  # 1 = abnormal, 0 = normal


def label_from_hea(hea_path: Path) -> int | None:
    """Same rule as the original preprocessor: first '#' line naming Abnormal/Normal."""
    for line in Path(hea_path).read_text(errors='ignore').splitlines():
        if line.startswith('#'):
            if 'Abnormal' in line:
                return 1
            if 'Normal' in line:
                return 0
    return None


def list_records(raw_dir) -> list[Record]:
    """Labeled records with a wav file, sorted by name (matches X_data/Y_data order)."""
    raw_dir = Path(raw_dir)
    out = []
    for hea in sorted(raw_dir.glob('*.hea')):
        label = label_from_hea(hea)
        wav = hea.with_suffix('.wav')
        if label is not None and wav.exists():
            out.append(Record(hea.stem, wav, label))
    return out
