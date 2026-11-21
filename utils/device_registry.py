"""Trusted stethoscope devices and verification of their signed QR results (P0.7).

Registry file: $TRUSTED_DEVICES_FILE or instance/trusted_devices.json (not in git). It holds
public keys only. Register a device with scripts/register_device.py <device_id> <public_key_hex>.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_PORTAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PORTAL / 'vendor'))

from ishtiraf_core.signing import InvalidToken, VerifiedResult, verify_result  # noqa: E402,F401

STATUS = {'N': 'NORMAL', 'A': 'ABNORMAL', 'U': 'UNSURE', 'X': 'NO RESULT'}
LABEL = {'NORMAL': 'NO ABNORMALITY DETECTED', 'ABNORMAL': 'REFER: ABNORMAL HEART SOUND',
         'UNSURE': 'UNSURE: RE-RECORD OR REFER', 'NO RESULT': 'NO RESULT'}


def registry_path() -> Path:
    return Path(os.environ.get('TRUSTED_DEVICES_FILE') or _PORTAL / 'instance' / 'trusted_devices.json')


def _read() -> dict:
    p = registry_path()
    if not p.exists():
        return {'devices': {}}
    return json.loads(p.read_text(encoding='utf-8'))


def trusted_devices() -> dict:
    return {dev: rec['public_key'] for dev, rec in _read().get('devices', {}).items()}


def register(device_id: str, public_key_hex: str, label: str = '') -> None:
    if not device_id or len(device_id) > 40 or not device_id.replace('-', '').isalnum():
        raise ValueError('device id must be 1-40 letters, digits or dashes')
    try:
        if len(bytes.fromhex(public_key_hex)) != 32:
            raise ValueError
    except ValueError:
        raise ValueError('public key must be 64 hex characters (Ed25519)') from None
    data = _read()
    data.setdefault('devices', {})[device_id] = {
        'public_key': public_key_hex.lower(), 'label': label,
        'registered': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(tmp, p)


def extract_token(text: str) -> str:
    """Accept the bare token or the full URL the Pi's COPY URL button gives."""
    text = (text or '').strip()
    if text.startswith(('http://', 'https://')):
        q = parse_qs(urlparse(text).query)
        text = (q.get('p') or q.get('payload') or [''])[0]
    return text


def verify_qr(text: str, *, now: int | None = None) -> VerifiedResult:
    return verify_result(extract_token(text), trusted_devices(), now=int(time.time()) if now is None else now)


CAVEATS = ['Screening aid only - not a diagnosis.',
           'The AI score (0-100) is not a probability or a confidence %.',
           'In cross-validation about 1 in 30 abnormal recordings was cleared as NO REFER (held-out sensitivity 0.97).']


def advice(d: dict) -> tuple[str, str]:
    """(explanation, recommendation) in plain words, from the verified result only."""
    if d['status'] == 'ABNORMAL':
        return (f"The validated heart model ({d['model']}) scored this recording {d['score']}/100, in the refer "
                "band: the heart sound looks abnormal. The model does not name a disease.",
                'Refer for clinical review and echocardiography.')
    if d['status'] == 'UNSURE':
        return (f"The validated heart model ({d['model']}) scored this recording {d['score']}/100, between the "
                "no-refer and refer cut-offs: the screen cannot clear this patient.",
                'Record again (quiet room, firm contact). If it stays unsure, refer.')
    if d['status'] == 'NORMAL':
        return (f"The validated heart model ({d['model']}) scored this recording {d['score']}/100, below the "
                "no-refer cut-off: no abnormality detected.",
                'No referral needed from this screen. Refer anyway if symptoms or findings suggest heart disease.')
    return ('The device produced no result (recording too short or AI model unavailable).',
            'Record again on the device.')


def facts(d: dict) -> dict:
    return {'AI score': '--' if d['score'] is None else f"{d['score']}/100", 'Decision rule': f"{d['model']}.decision.json",
            'Windows analysed': d['n_windows'], 'Model': d['model'], 'Location': d['location'],
            'Device': d['device_id'], 'Result no.': d['counter'],
            'Signature': 'Signature verified (Ed25519)'}


def describe(res: VerifiedResult) -> dict:
    """Plain facts from a verified result. Nothing here is invented or rule-based."""
    c = res.claims
    status = STATUS.get(c.get('st'), 'NO RESULT')
    score = c.get('sc') if isinstance(c.get('sc'), (int, float)) else None
    return {
        'status': status, 'diagnosis': LABEL[status], 'score': score,
        'risk_score': None if score is None else round(score / 10, 1),
        'n_windows': c.get('w'), 'model': c.get('m'), 'location': c.get('loc'),
        'device_id': res.device_id, 'counter': res.counter,
        'recorded_at': datetime.fromtimestamp(res.ts).strftime('%Y-%m-%d %H:%M:%S'),
        'diagnosis_id': f'QR-{res.device_id}-{res.counter}',
    }
