"""Heart-sound preprocessing shared by training, the web portal and the Pi.

This reproduces exactly how the 2025-12-15 Attention-CRNN training data
(Processed_Spectrograms/X_data.npy) was built by Model_Training/1_AI_Engine/preprocessor.py
(STFT mode): mono, resample to 2 kHz, pad/trim to 5 s, STFT (nperseg=128, noverlap=64),
power in dB. No bandpass filter and no per-sample normalization: the model was trained
on raw dB values, so anything else at inference time breaks it.
"""
from __future__ import annotations

import numpy as np
from scipy import signal

SAMPLE_RATE = 2000
WINDOW_SECONDS = 5
WINDOW_SAMPLES = SAMPLE_RATE * WINDOW_SECONDS
NPERSEG = 128
NOVERLAP = 64
SPEC_SHAPE = (NPERSEG // 2 + 1, (WINDOW_SAMPLES - NPERSEG) // (NPERSEG - NOVERLAP) + 1)  # (65, 155)
_EPS = 1e-10


def to_mono(audio: np.ndarray) -> np.ndarray:
    audio = np.asarray(audio, dtype=np.float64)
    return audio.mean(axis=1) if audio.ndim > 1 else audio


def resample(audio: np.ndarray, sr: int) -> np.ndarray:
    """Resample to SAMPLE_RATE with the same FFT method used for training."""
    audio = to_mono(audio)
    if sr == SAMPLE_RATE:
        return audio
    return signal.resample(audio, int(len(audio) * float(SAMPLE_RATE) / sr))


def load_audio(path) -> np.ndarray:
    """Read a wav file and return mono float64 audio at SAMPLE_RATE."""
    import soundfile as sf  # only needed for files; the Pi mic path does not use it
    audio, sr = sf.read(str(path))
    return resample(audio, sr)


def fix_length(audio: np.ndarray, n: int = WINDOW_SAMPLES) -> np.ndarray:
    """Zero-pad or trim to n samples (training used the first 5 s)."""
    audio = np.asarray(audio, dtype=np.float64)
    if len(audio) < n:
        return np.pad(audio, (0, n - len(audio)))
    return audio[:n]


def window_features(window: np.ndarray) -> np.ndarray:
    """One 5 s window -> (65, 155) float32 spectrogram in dB."""
    window = np.asarray(window, dtype=np.float64)
    if len(window) != WINDOW_SAMPLES:
        raise ValueError(f'window must have {WINDOW_SAMPLES} samples, got {len(window)}')
    _, _, sxx = signal.spectrogram(window, SAMPLE_RATE, nperseg=NPERSEG, noverlap=NOVERLAP)
    return (10 * np.log10(sxx + _EPS)).astype(np.float32)


def split_windows(audio: np.ndarray) -> list[np.ndarray]:
    """Consecutive non-overlapping 5 s windows; the last one is zero-padded."""
    audio = np.asarray(audio, dtype=np.float64)
    n = max(1, int(np.ceil(len(audio) / WINDOW_SAMPLES)))
    return [fix_length(audio[i * WINDOW_SAMPLES:(i + 1) * WINDOW_SAMPLES]) for i in range(n)]


def model_input(audio: np.ndarray, sr: int) -> np.ndarray:
    """Audio at any rate/length -> (n_windows, 65, 155, 1) float32 batch for the model.

    Window 0 is identical to the training feature of the same recording.
    """
    audio = resample(audio, sr)
    feats = [window_features(w) for w in split_windows(audio)]
    return np.stack(feats)[..., np.newaxis].astype(np.float32)
