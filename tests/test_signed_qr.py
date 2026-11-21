"""P0.7: the portal shows and saves a QR result only if a registered device signed it."""
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORTAL / 'vendor'))
from ishtiraf_core import signing  # noqa: E402

DEV = 'PI5-test000001'


@pytest.fixture
def device(tmp_path, monkeypatch):
    seed, pub = signing.generate_device_key()
    reg = tmp_path / 'trusted_devices.json'
    monkeypatch.setenv('TRUSTED_DEVICES_FILE', str(reg))
    from utils import device_registry
    device_registry.register(DEV, pub, label='test rig')
    counter = iter(range(1, 10_000))

    def make(st='A', sc=88, *, ts=None, n=None, dev=DEV, key=seed):
        claims = {'st': st, 'sc': sc, 'w': 3, 'm': 'heart_attention_v4', 'loc': 'MITRAL'}
        return signing.sign_result(claims, device_id=dev, seed_hex=key,
                                   counter=n or next(counter), ts=int(time.time()) if ts is None else ts)
    return make


def _tamper(token):
    head, payload, sig = token.split('.')
    body = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    body['st'], body['sc'] = 'N', 2
    forged = base64.urlsafe_b64encode(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).decode().rstrip('=')
    return f'{head}.{forged}.{sig}'


def _save(client, token, name='Ali'):
    return client.post('/save-from-qr', data={'payload': token, 'name': name, 'age': '40', 'gender': 'Male'})


def test_scan_shows_verified_result(authenticated_client, device):
    resp = authenticated_client.get(f'/scan?p={device()}')
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert DEV in html and '88' in html and 'Signature verified' in html
    assert 'name="payload"' in html


def test_scan_accepts_full_url(authenticated_client, device):
    resp = authenticated_client.get('/scan', query_string={'p': f'http://10.0.0.5:5000/scan?p={device()}'})
    assert resp.status_code == 200


@pytest.mark.parametrize('kind', ['tampered', 'unsigned', 'unknown_device', 'expired', 'wrong_key'])
def test_scan_rejects_untrusted(authenticated_client, device, kind):
    if kind == 'tampered':
        token = _tamper(device())
    elif kind == 'unsigned':
        token = base64.urlsafe_b64encode(b'{"d":"Normal","s":"N","r":1,"c":99}').decode()
    elif kind == 'unknown_device':
        token = device(dev='PI5-stranger')
    elif kind == 'expired':
        token = device(ts=int(time.time()) - 3 * 24 * 3600)
    else:
        token = device(key=signing.generate_device_key()[0])
    resp = authenticated_client.get('/scan', query_string={'p': token})
    html = resp.get_data(as_text=True)
    assert resp.status_code == 400
    assert 'name="payload"' not in html and 'Save to Database' not in html


def _diagnoses():
    from app import app
    from models.medical import Diagnosis
    with app.app_context():
        return [(d.diagnosis_id, d.device_id, d.risk_score, d.confidence, d.diagnosis_result) for d in Diagnosis.query.all()]


def test_save_signed_result_once(authenticated_client, device):
    token = device(sc=88, n=7)
    assert _save(authenticated_client, token).status_code == 302
    assert _diagnoses() == [(f'QR-{DEV}-7', DEV, 8.8, None, 'REFER: ABNORMAL HEART SOUND')]
    _save(authenticated_client, token)  # replay of the same QR
    assert len(_diagnoses()) == 1


def test_saved_record_page_renders(authenticated_client, device):
    resp = _save(authenticated_client, device())
    page = authenticated_client.get(resp.headers['Location'])
    assert page.status_code == 200


@pytest.mark.parametrize('kind', ['tampered', 'unsigned', 'no_result'])
def test_save_refuses_untrusted_or_empty(authenticated_client, device, kind):
    token = {'tampered': lambda: _tamper(device()),
             'unsigned': lambda: base64.urlsafe_b64encode(b'{"d":"x","s":"N","r":1}').decode(),
             'no_result': lambda: device(st='X', sc=None)}[kind]()
    _save(authenticated_client, token)
    assert _diagnoses() == []


def _mobile_token():
    import jwt
    from routes.mobile_api import JWT_SECRET
    return jwt.encode({'user_id': 1, 'email': 'a@b.c', 'role': 'doctor', 'exp': int(time.time()) + 600},
                      JWT_SECRET, algorithm='HS256')


def test_mobile_scan_verifies(client, device):
    h = {'Authorization': f'Bearer {_mobile_token()}'}
    ok = client.post('/api/v1/scan', json={'payload': device(sc=88)}, headers=h)
    assert ok.status_code == 200 and ok.get_json()['data']['score'] == 88
    assert ok.get_json()['data']['device_id'] == DEV
    bad = client.post('/api/v1/scan', json={'payload': _tamper(device())}, headers=h)
    assert bad.status_code == 400


def test_register_script(tmp_path):
    reg = tmp_path / 'reg.json'
    pub = signing.generate_device_key()[1]
    run = lambda *a: subprocess.run([sys.executable, str(PORTAL / 'scripts' / 'register_device.py'), *a],  # noqa: E731
                                    capture_output=True, text=True, env={'TRUSTED_DEVICES_FILE': str(reg), 'SYSTEMROOT': 'C:\\Windows'})
    assert run('PI5-abc', pub).returncode == 0
    assert json.loads(reg.read_text())['devices']['PI5-abc']['public_key'] == pub
    assert run('PI5-bad', 'zz' * 32).returncode != 0
    assert 'PI5-bad' not in reg.read_text()


def test_unsure_result_is_shown_and_saved_as_unsure(authenticated_client, device):
    token = device(st='U', sc=41, n=9)
    html = authenticated_client.get(f'/scan?p={token}').get_data(as_text=True)
    assert 'UNSURE: RE-RECORD OR REFER' in html and 'Record again' in html
    _save(authenticated_client, token)
    assert _diagnoses() == [(f'QR-{DEV}-9', DEV, 4.1, None, 'UNSURE: RE-RECORD OR REFER')]
