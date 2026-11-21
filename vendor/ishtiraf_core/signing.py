"""Signed device results: the Pi signs each screening result, the portal verifies it.

Token (fits in a QR URL):  I1.<base64url(canonical JSON)>.<base64url(Ed25519 signature)>
The signature covers the ASCII bytes "I1.<payload>", so every character is protected.
JSON = {"v": 1, "dev": device id, "n": monotonic counter, "ts": unix time, ...claims}.

There is deliberately no fallback: if the key, the library or the signature is missing or
wrong, verification raises InvalidToken. Results are signed, not encrypted, so the claims
must not contain patient identifiers.
"""
from __future__ import annotations

import base64
import binascii
import json
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PREFIX = 'I1'
VERSION = 1
RESERVED = ('v', 'dev', 'n', 'ts')
DEFAULT_MAX_AGE_S = 24 * 3600
DEFAULT_MAX_FUTURE_S = 300


class InvalidToken(Exception):
    """The QR result is not a valid, fresh, signed result from a trusted device."""


@dataclass(frozen=True)
class VerifiedResult:
    device_id: str
    counter: int
    ts: int
    claims: dict


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode('ascii').rstrip('=')


def _b64d(s: str) -> bytes:
    """Strict: the text must be the canonical unpadded encoding of the bytes."""
    try:
        raw = base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
    except (binascii.Error, ValueError) as e:
        raise InvalidToken(f'bad encoding: {e}') from None
    if _b64e(raw) != s:
        raise InvalidToken('non-canonical encoding')
    return raw


def generate_device_key() -> tuple[str, str]:
    """New Ed25519 key pair as (private seed hex, public key hex)."""
    seed = secrets.token_bytes(32)
    return seed.hex(), _public_hex(seed)


def _private(seed_hex: str) -> Ed25519PrivateKey:
    try:
        seed = bytes.fromhex(seed_hex)
    except ValueError:
        raise ValueError('seed must be hex') from None
    if len(seed) != 32:
        raise ValueError('seed must be 32 bytes')
    return Ed25519PrivateKey.from_private_bytes(seed)


def _public_hex(seed: bytes) -> str:
    from cryptography.hazmat.primitives import serialization
    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def public_key_hex(seed_hex: str) -> str:
    _private(seed_hex)
    return _public_hex(bytes.fromhex(seed_hex))


def sign_result(claims: dict, *, device_id: str, seed_hex: str, counter: int, ts: int) -> str:
    clash = [k for k in RESERVED if k in claims]
    if clash:
        raise ValueError(f'claims may not use reserved keys {clash}')
    body = {'v': VERSION, 'dev': device_id, 'n': int(counter), 'ts': int(ts), **claims}
    payload = _b64e(json.dumps(body, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    signed_part = f'{PREFIX}.{payload}'
    sig = _private(seed_hex).sign(signed_part.encode('ascii'))
    return f'{signed_part}.{_b64e(sig)}'


def verify_result(token: str, trusted_devices: dict, *, now: int,
                  max_age_s: int = DEFAULT_MAX_AGE_S, max_future_s: int = DEFAULT_MAX_FUTURE_S) -> VerifiedResult:
    """Return the verified result or raise InvalidToken with the reason."""
    if not isinstance(token, str):
        raise InvalidToken('token must be text')
    parts = token.split('.')
    if len(parts) != 3 or parts[0] != PREFIX or not parts[1] or not parts[2]:
        raise InvalidToken('not a signed IshtirafAI result (unsigned or old device software)')
    payload_raw, sig = _b64d(parts[1]), _b64d(parts[2])
    if len(sig) != 64:
        raise InvalidToken('bad signature length')
    try:
        body = json.loads(payload_raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidToken('payload is not JSON') from None
    if not isinstance(body, dict) or body.get('v') != VERSION:
        raise InvalidToken('unsupported payload version')
    dev, n, ts = body.get('dev'), body.get('n'), body.get('ts')
    if not isinstance(dev, str) or not isinstance(n, int) or n < 1 or not isinstance(ts, int):
        raise InvalidToken('payload is missing device, counter or time')
    pub_hex = trusted_devices.get(dev)
    if not pub_hex:
        raise InvalidToken(f'unknown device {dev!r} (not registered on this portal)')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(sig, f'{PREFIX}.{parts[1]}'.encode('ascii'))
    except (InvalidSignature, ValueError):
        raise InvalidToken('signature does not match the registered device key') from None
    if ts > now + max_future_s:
        raise InvalidToken('result time is in the future (check the device clock)')
    if now - ts > max_age_s:
        raise InvalidToken('result expired (scan the QR again from the device)')
    claims = {k: v for k, v in body.items() if k not in RESERVED}
    return VerifiedResult(dev, n, ts, claims)
