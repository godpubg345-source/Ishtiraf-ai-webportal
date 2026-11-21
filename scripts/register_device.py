"""Register a stethoscope device so the portal trusts its signed QR results.

    python scripts/register_device.py <device_id> <public_key_hex> [--label "Clinic A"]

Get both values on the device with:  python3 device_identity.py --show
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.device_registry import register, registry_path  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('device_id')
    ap.add_argument('public_key_hex')
    ap.add_argument('--label', default='')
    a = ap.parse_args(argv)
    try:
        register(a.device_id, a.public_key_hex, a.label)
    except ValueError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    print(f'registered {a.device_id} in {registry_path()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
