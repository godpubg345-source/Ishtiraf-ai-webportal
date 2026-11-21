"""Evaluation harness: run a saved heart model on raw recordings through ishtiraf_core
preprocessing and report screening metrics.

CLI:
    python -m ishtiraf_core.evaluation --model path/to/model.h5|.tflite \
        --raw-dir Model_Training/0_Data_Vault/Raw_PhysioNet --fold 1 \
        [--custom-layers Model_Training/1_AI_Engine/attention_crnn.py] [--windows first|all]
"""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.stats import rankdata

from . import preprocessing as pp
from .datasets import physionet2016 as ph

Predictor = Callable[[np.ndarray], np.ndarray]  # (n, 65, 155, 1) float32 -> (n,) probabilities


def binary_metrics(y_true, prob, threshold: float = 0.5) -> dict:
    """Screening metrics; AUC is the Mann-Whitney statistic with average ranks for ties."""
    y = np.asarray(y_true).astype(int).ravel()
    p = np.asarray(prob, dtype=np.float64).ravel()
    pos, neg = y == 1, y == 0
    n_pos, n_neg = int(pos.sum()), int(neg.sum())
    ranks = rankdata(p)
    auc = (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg) if n_pos and n_neg else float('nan')
    pred = p > threshold
    tp, fn = int((pred & pos).sum()), int((~pred & pos).sum())
    tn, fp = int((~pred & neg).sum()), int((pred & neg).sum())

    def div(a, b):
        return a / b if b else float('nan')

    sens, ppv = div(tp, tp + fn), div(tp, tp + fp)
    return {
        'n': len(y), 'n_abnormal': n_pos, 'threshold': threshold,
        'tp': tp, 'fn': fn, 'tn': tn, 'fp': fp,
        'auc': float(auc), 'sensitivity': sens, 'specificity': div(tn, tn + fp),
        'accuracy': div(tp + tn, len(y)), 'ppv': ppv, 'npv': div(tn, tn + fn),
        'f1': div(2 * ppv * sens, ppv + sens) if tp else 0.0,
    }


def stratified_folds(y, n_splits: int = 5, seed: int = 42):
    """Exactly the split used by Model_Training/1_AI_Engine/trainer_enhanced.py."""
    from sklearn.model_selection import StratifiedKFold
    y = np.asarray(y).ravel()
    return list(StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(np.zeros(len(y)), y))


def aggregate_windows(window_probs, mode: str = 'mean') -> float:
    """One probability per recording from its 5 s windows."""
    w = np.asarray(window_probs, dtype=np.float64).ravel()
    if mode == 'first':
        return float(w[0])
    if mode == 'mean':
        return float(w.mean())
    raise ValueError(f'unknown mode {mode!r}')


def _custom_objects(module_path) -> dict:
    spec = importlib.util.spec_from_file_location('ishtiraf_custom_layers', str(module_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    import tensorflow as tf
    return {n: o for n, o in vars(mod).items() if inspect.isclass(o) and issubclass(o, tf.keras.layers.Layer)}


def load_predictor(model_path, custom_layers=None, batch_size: int = 128) -> Predictor:
    """Load a Keras (.h5/.keras) or TFLite model and return a batch -> probability function."""
    import tensorflow as tf
    model_path = Path(model_path)
    if model_path.suffix == '.tflite':
        interp = tf.lite.Interpreter(model_path=str(model_path))
        interp.allocate_tensors()
        inp, out = interp.get_input_details()[0], interp.get_output_details()[0]

        def predict(x):
            res = []
            for sample in np.asarray(x, dtype=np.float32):
                interp.set_tensor(inp['index'], sample[None].astype(inp['dtype']))
                interp.invoke()
                res.append(float(np.ravel(interp.get_tensor(out['index']))[-1]))
            return np.asarray(res)
        return predict

    objects = _custom_objects(custom_layers) if custom_layers else None
    model = tf.keras.models.load_model(str(model_path), custom_objects=objects, compile=False)

    def predict(x):
        return np.asarray(model.predict(np.asarray(x, dtype=np.float32), verbose=0, batch_size=batch_size)).reshape(len(x), -1)[:, -1]
    return predict


def evaluate_records(predict: Predictor, records, windows: str = 'first', threshold: float = 0.5) -> dict:
    """Predict each recording from its wav file and compute metrics."""
    feats, owner = [], []
    for i, rec in enumerate(records):
        x = pp.model_input(pp.load_audio(rec.wav_path), pp.SAMPLE_RATE)
        if windows == 'first':
            x = x[:1]
        feats.append(x)
        owner.extend([i] * len(x))
    probs = predict(np.concatenate(feats))
    owner = np.asarray(owner)
    rec_prob = np.array([aggregate_windows(probs[owner == i], 'mean') for i in range(len(records))])
    m = binary_metrics([r.label for r in records], rec_prob, threshold)
    m['windows'] = windows
    m['n_windows'] = int(len(probs))
    return m


def evaluate_fold(predict: Predictor, raw_dir, fold: int, n_splits: int = 5, seed: int = 42,
                  windows: str = 'first', threshold: float = 0.5) -> dict:
    """Metrics on the held-out recordings of one cross-validation fold (1-based)."""
    records = ph.list_records(raw_dir)
    _, val_idx = stratified_folds([r.label for r in records], n_splits, seed)[fold - 1]
    m = evaluate_records(predict, [records[i] for i in val_idx], windows, threshold)
    m['fold'] = fold
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description='Evaluate an IshtirafAI heart model on raw recordings')
    ap.add_argument('--model', required=True)
    ap.add_argument('--raw-dir', required=True)
    ap.add_argument('--custom-layers', help='Python file defining custom Keras layers')
    ap.add_argument('--fold', type=int, help='evaluate one CV fold (1-based); omit for all records')
    ap.add_argument('--n-splits', type=int, default=5)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--windows', choices=['first', 'all'], default='first')
    ap.add_argument('--threshold', type=float, default=0.5)
    a = ap.parse_args(argv)
    predict = load_predictor(a.model, a.custom_layers)
    if a.fold:
        m = evaluate_fold(predict, a.raw_dir, a.fold, a.n_splits, a.seed, a.windows, a.threshold)
    else:
        m = evaluate_records(predict, ph.list_records(a.raw_dir), a.windows, a.threshold)
    print(json.dumps(m, indent=2))
    return m


if __name__ == '__main__':
    main()
