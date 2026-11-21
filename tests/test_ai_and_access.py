"""P0.5: the portal must score audio exactly like the Pi, refuse to guess without a model,
keep patient-data routes behind login and never expose the debugger on the network."""
import base64
import filecmp
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

PORTAL = Path(__file__).resolve().parents[1]
REPO = PORTAL.parent
RAW = REPO / 'Model_Training' / '0_Data_Vault' / 'Raw_PhysioNet'
has_runtime = any(importlib.util.find_spec(m) for m in ('ai_edge_litert', 'tflite_runtime', 'tensorflow'))
needs_runtime = pytest.mark.skipif(not has_runtime, reason='no TFLite runtime installed')
needs_data = pytest.mark.skipif(not RAW.exists(), reason='PhysioNet data not on this machine')

PATIENT_DATA_ROUTES = [
    ('get', '/qr-scanner'), ('get', '/scan?p=eyJzIjoiTiJ9'), ('get', '/scan/v3'),
    ('post', '/api/decrypt_qr'), ('post', '/api/save_patient'), ('post', '/api/scan_qr_image'),
    ('post', '/api/decode_v3'), ('post', '/api/playback_audio'), ('post', '/save-from-qr'),
    ('post', '/api/analyze-audio'),
]


def _b64(audio):
    return base64.b64encode(np.asarray(audio, dtype=np.float32).tobytes()).decode()


@pytest.mark.parametrize('method,url', PATIENT_DATA_ROUTES)
def test_patient_data_routes_require_login(client, method, url):
    resp = getattr(client, method)(url, json={} if method == 'post' else None)
    assert resp.status_code in (301, 302, 401), f'{url} answered {resp.status_code} without login'
    if resp.status_code in (301, 302):
        assert '/auth/login' in resp.headers['Location']


@needs_runtime
@needs_data
@pytest.mark.parametrize('name', ['a0001', 'a0007', 'e00133'])
def test_portal_score_equals_core_engine_and_pi(authenticated_client, name):
    import soundfile as sf
    sys.path.insert(0, str(PORTAL / 'vendor'))
    from ishtiraf_core.engine import HeartEngine
    audio, sr = sf.read(RAW / f'{name}.wav')
    audio32 = np.asarray(audio, dtype=np.float32)
    resp = authenticated_client.post('/api/analyze-audio', json={'audio': _b64(audio32), 'sample_rate': sr})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    ref = HeartEngine(REPO / 'Model_Training' / '1_AI_Engine' / 'Saved_Models' / 'heart_attention_v4.tflite').score(audio32, sr)
    assert data['status'] == ref.status
    assert data['probability'] == pytest.approx(ref.prob, abs=1e-6)
    assert data['score'] == ref.score
    assert 'confidence' not in data and 'diagnosis' not in data
    pi_engine = REPO / 'Pi5_USB_Package' / 'heart_engine.py'
    if pi_engine.exists():
        spec = importlib.util.spec_from_file_location('pi_heart_engine', pi_engine)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert data['probability'] == pytest.approx(mod.HeartEngine().score(audio32, sr).prob, abs=1e-6)


def test_analyze_audio_503_when_model_missing(authenticated_client, monkeypatch, tmp_path):
    from utils import inference
    sys.path.insert(0, str(PORTAL / 'vendor'))
    from ishtiraf_core.engine import HeartEngine
    monkeypatch.setattr(inference, '_engine', HeartEngine(tmp_path / 'missing.tflite'))
    resp = authenticated_client.post('/api/analyze-audio', json={'audio': _b64(np.zeros(20000)), 'sample_rate': 2000})
    assert resp.status_code == 503
    assert resp.get_json()['status'] == 'NO RESULT'


@pytest.mark.parametrize('payload', [{}, {'audio': 'not-base64!!'}, {'audio': _b64(np.zeros(100)), 'sample_rate': 5}])
def test_analyze_audio_rejects_bad_input(authenticated_client, payload):
    resp = authenticated_client.post('/api/analyze-audio', json=payload)
    assert resp.status_code in (400, 422)


@needs_runtime
def test_analyze_audio_too_short_is_not_a_result(authenticated_client):
    resp = authenticated_client.post('/api/analyze-audio', json={'audio': _b64(np.zeros(1000)), 'sample_rate': 2000})
    assert resp.status_code == 422
    assert resp.get_json()['status'] == 'NO RESULT'


@pytest.mark.parametrize('env,expected_debug', [
    ({'FLASK_DEBUG': '1'}, True),
    ({'FLASK_DEBUG': '1', 'HOST': '0.0.0.0'}, False),
    ({'HOST': '0.0.0.0'}, False),
    ({}, False),
])
def test_debugger_never_exposed_on_network(env, expected_debug):
    from config import run_options
    host, port, debug = run_options(env)
    assert debug is expected_debug
    assert host == env.get('HOST', '127.0.0.1')


def test_vendored_core_is_identical_to_source():
    src = REPO / 'ishtiraf_core' / 'src' / 'ishtiraf_core'
    if not src.exists():
        pytest.skip('portal checked out without the monorepo')
    dst = PORTAL / 'vendor' / 'ishtiraf_core'
    for rel in sorted(p.relative_to(src) for p in src.rglob('*.py')):
        assert (dst / rel).exists() and filecmp.cmp(src / rel, dst / rel, shallow=False), \
            f'vendored {rel} differs; run tools/sync_core.py'
