"""Training data for the signal quality model (P1.2): synthetic corruptions and the record split.

All functions work on mono float audio at preprocessing.SAMPLE_RATE (2 kHz), which is the
native rate of PhysioNet 2016. Outputs of corrupt_bad/augment_good are re-quantized to 16 bit,
like a real ADC (very low gain therefore ends up as a few LSBs, not a clean scaled copy).
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import numpy as np
from scipy import signal

from .preprocessing import SAMPLE_RATE

BAD_KINDS = ('white_noise', 'pink_noise', 'clipping', 'dropouts', 'friction', 'speech', 'low_gain')
GOOD_KINDS = ('none', 'noise_white', 'noise_pink', 'gain')
GOOD_MIN_SNR_DB = 20.0
BAD_SNR_DB = (-15.0, -5.0)  # noise, friction and speech: "bad" means at most -5 dB SNR
_EPS = 1e-12


def quantize16(x: np.ndarray) -> np.ndarray:
    return np.round(np.clip(np.asarray(x, dtype=np.float64), -1.0, 32767 / 32768) * 32768) / 32768


def colored_noise(n: int, color: str, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n)
    if color == 'white':
        return white
    if color != 'pink':
        raise ValueError(f'unknown noise color {color!r}')
    spec = np.fft.rfft(white)
    f = np.fft.rfftfreq(n)
    f[0] = f[1] if n > 1 else 1.0
    return np.fft.irfft(spec / np.sqrt(f), n)


def mix_at_snr(x: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """x + noise scaled so that 10*log10(P(x)/P(noise)) == snr_db. Silent x gets noise at rms 0.1."""
    x = np.asarray(x, dtype=np.float64)
    px, pn = np.mean(x ** 2), np.mean(noise ** 2)
    if pn < _EPS:
        return x.copy()
    target = 0.01 if px < _EPS else px / 10 ** (snr_db / 10)
    return x + noise * np.sqrt(target / pn)


def add_noise(x, snr_db: float, color: str, rng: np.random.Generator) -> np.ndarray:
    return mix_at_snr(x, colored_noise(len(x), color, rng), snr_db)


def clip(x, ratio: float) -> np.ndarray:
    """Hard saturation: the loudest `ratio` of samples sit at the rail (peak kept as before)."""
    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x)
    thr = np.quantile(a, 1 - ratio)
    if thr <= 0:
        return x.copy()
    return np.clip(x, -thr, thr) * (a.max() / thr)


def _blocks(n: int, rng: np.random.Generator, lo=0.3, hi=0.8):
    """Consecutive blocks of random length (seconds) covering 0..n."""
    start = 0
    while start < n:
        length = int(rng.uniform(lo, hi) * SAMPLE_RATE)
        yield start, min(n, start + max(1, length))
        start += max(1, length)


def dropouts(x, fraction: float, rng: np.random.Generator) -> np.ndarray:
    """Zero a run of `fraction` of every short block, so the loss is spread over the recording."""
    y = np.asarray(x, dtype=np.float64).copy()
    for a, b in _blocks(len(y), rng):
        run = int(round(fraction * (b - a)))
        if run:
            off = a + rng.integers(0, b - a - run + 1)
            y[off:off + run] = 0.0
    return y


def friction(x, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Rub/friction: crackly band-limited noise bursts in most blocks of the recording."""
    n = len(x)
    sos = signal.butter(4, [100, 900], btype='bandpass', fs=SAMPLE_RATE, output='sos')
    carrier = signal.sosfilt(sos, rng.standard_normal(n))
    crackle = 1 + 4 * (rng.random(n) < 0.01)
    env = np.zeros(n)
    for a, b in _blocks(n, rng):
        if rng.random() < 0.9:
            ln = int((b - a) * rng.uniform(0.4, 0.9))
            off = a + rng.integers(0, b - a - ln + 1)
            env[off:off + ln] = np.hanning(ln) * rng.uniform(0.5, 1.0)
    noise = carrier * crackle * env
    if np.mean(noise ** 2) < _EPS:  # extremely short input: fall back to plain bursts
        noise = carrier
    return mix_at_snr(x, noise, snr_db)


def speech_like(x, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Talking in the room: voiced harmonics with moving formants and syllable rhythm."""
    n = len(x)
    t = np.arange(n) / SAMPLE_RATE
    f0 = rng.uniform(90, 250) * (1 + 0.08 * np.sin(2 * np.pi * rng.uniform(0.5, 2) * t))
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    env = np.zeros(n)
    formant = np.zeros(n)
    for a, b in _blocks(n, rng, 0.12, 0.35):  # syllables
        if rng.random() < 0.8:
            env[a:b] = np.hanning(b - a)
        formant[a:b] = rng.uniform(300, 800)
    voice = np.zeros(n)
    for k in range(1, 12):
        fk = k * f0
        amp = np.exp(-((fk - formant) / 200) ** 2) + 0.3 / k
        voice += np.where(fk < SAMPLE_RATE / 2 - 50, amp, 0) * np.sin(k * phase)
    noise = voice * env
    if np.mean(noise ** 2) < _EPS:
        noise = voice
    return mix_at_snr(x, noise, snr_db)


EQ_MAX_DB = 15.0
_EQ_FREQS = np.array([20.0, 50.0, 100.0, 200.0, 400.0, 700.0, 1000.0])


def device_eq(x, rng: np.random.Generator) -> np.ndarray:
    """A different stethoscope/mic: random smooth frequency response (tilt + ripple), within
    +-EQ_MAX_DB, zero phase. PhysioNet sources differ by 10-15 dB between 100 and 700 Hz."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 2:
        return x.copy()
    pos = np.log(_EQ_FREQS / _EQ_FREQS[0]) / np.log(_EQ_FREQS[-1] / _EQ_FREQS[0])  # 0..1
    gains = rng.uniform(-1, 1) * EQ_MAX_DB * (2 * pos - 1) + rng.uniform(-6, 6, len(pos))
    gains = np.clip(gains, -EQ_MAX_DB, EQ_MAX_DB)
    f = np.fft.rfftfreq(len(x), 1 / SAMPLE_RATE)
    g_db = np.interp(np.log(np.maximum(f, _EQ_FREQS[0])), np.log(_EQ_FREQS), gains)
    return np.fft.irfft(np.fft.rfft(x) * 10 ** (g_db / 20), len(x))


def cap_peak(x, peak: float = 0.95) -> np.ndarray:
    m = np.max(np.abs(x)) if len(x) else 0.0
    return x * (peak / m) if m > peak else x


def low_gain(x, gain: float) -> np.ndarray:
    return quantize16(np.asarray(x, dtype=np.float64) * gain)


def _apply(x, kind: str, rng: np.random.Generator, severity: float) -> np.ndarray:
    """severity in [0, 1]: 0 = mildest "bad" level, 1 = heaviest."""
    snr = BAD_SNR_DB[1] + severity * (BAD_SNR_DB[0] - BAD_SNR_DB[1])
    if kind == 'white_noise':
        return add_noise(x, snr, 'white', rng)
    if kind == 'pink_noise':
        return add_noise(x, snr, 'pink', rng)
    if kind == 'clipping':
        return clip(x, 0.25 + 0.35 * severity)
    if kind == 'dropouts':
        return dropouts(x, 0.3 + 0.4 * severity, rng)
    if kind == 'friction':
        return friction(x, snr, rng)
    if kind == 'speech':
        return speech_like(x, snr, rng)
    if kind == 'low_gain':
        return low_gain(x, 10 ** (np.log10(2e-3) + severity * (np.log10(1e-4) - np.log10(2e-3))))
    raise ValueError(f'unknown corruption kind {kind!r}')


def corrupt_bad(x, rng: np.random.Generator, kind: str | None = None):
    """A recording too poor to score. Returns (audio, kind)."""
    if kind is None:
        kind = BAD_KINDS[rng.integers(len(BAD_KINDS))]
    return quantize16(_apply(x, kind, rng, rng.random())), kind


def heavy(x, kind: str, rng: np.random.Generator) -> np.ndarray:
    """Heaviest level of one corruption (used by tests). 'white_noise' etc. as in BAD_KINDS."""
    return quantize16(_apply(x, kind, rng, 1.0))


def augment_good(x, rng: np.random.Generator):
    """A still-scorable variant: mild noise (SNR >= 20 dB) or a gain change without clipping."""
    x = np.asarray(x, dtype=np.float64)
    kind = GOOD_KINDS[rng.integers(len(GOOD_KINDS))]
    if kind == 'noise_white':
        y = add_noise(x, rng.uniform(GOOD_MIN_SNR_DB, 40), 'white', rng)
    elif kind == 'noise_pink':
        y = add_noise(x, rng.uniform(GOOD_MIN_SNR_DB, 40), 'pink', rng)
    elif kind == 'gain':
        y = x * rng.uniform(0.3, 2.0)
    else:
        y = x.copy()
    return quantize16(cap_peak(y)), kind


# ---- labels and split ----------------------------------------------------

def read_sqi(path) -> dict[str, int]:
    """REFERENCE-SQI.csv rows `name,label,sqi` -> {name: sqi} (1 = good quality, 0 = poor)."""
    with open(path, newline='') as fh:
        return {row[0]: int(row[2]) for row in csv.reader(fh) if len(row) >= 3}


def variant_seed(seed: int, name: str, k: int) -> int:
    return int.from_bytes(hashlib.sha256(f'{seed}:{name}:{k}'.encode()).digest()[:8], 'little')


def split_records(names, seed: int, val_frac: float = 0.15, test_frac: float = 0.15, force_test=()):
    """Split by recording, stratified by source (first letter). Corruptions of a recording are
    generated after the split from its name, so they always stay in the same split."""
    forced = set(force_test)
    rng = np.random.default_rng(seed)
    out = {'train': [], 'val': [], 'test': sorted(forced)}
    groups: dict[str, list[str]] = {}
    for n in sorted(set(names) - forced):
        groups.setdefault(n[0], []).append(n)
    for key in sorted(groups):
        g = [groups[key][i] for i in rng.permutation(len(groups[key]))]
        n_te, n_va = int(round(test_frac * len(g))), int(round(val_frac * len(g)))
        out['test'] += g[:n_te]
        out['val'] += g[n_te:n_te + n_va]
        out['train'] += g[n_te + n_va:]
    return {k: sorted(v) for k, v in out.items()}


def list_wavs(raw_dir) -> list[str]:
    return sorted(p.stem for p in Path(raw_dir).glob('*.wav'))
