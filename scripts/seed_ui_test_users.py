"""Create local demo accounts for UI checks (demo DB only, never production).

Usage (from the portal folder; refuses to run without the demo flag):
    ISHTIRAF_DEMO_SEED=1 PYTHONUTF8=1 python scripts/seed_ui_test_users.py

Credentials (demo only, local DB):
    doctor: ui.doctor@ishtiraf.test / UiDemo!2026
    admin : ui.admin@ishtiraf.test  / UiDemo!2026
Does not touch any existing account (the real admin is left alone).
"""
import os
import sys

if os.environ.get('ISHTIRAF_DEMO_SEED') != '1':
    sys.exit('Refusing: demo accounts with a known password. Set ISHTIRAF_DEMO_SEED=1 on a demo DB only.')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

from models.user import db, User  # noqa: E402

USERS = [
    ("ui.doctor@ishtiraf.test", "Dr. UI Tester", "doctor"),
    ("ui.admin@ishtiraf.test", "UI Admin Tester", "admin"),
]
PASSWORD = "UiDemo!2026"

with app.app_context():
    for email, name, role in USERS:
        if User.query.filter_by(email=email).first():
            print(f"exists: {email}")
            continue
        u = User(email=email, name=name, role=role, is_verified=True, is_active=True)
        u.set_password(PASSWORD)
        db.session.add(u)
        print(f"created: {email} ({role})")
    db.session.commit()

# Demo patients + results (labels exactly as utils/device_registry.LABEL stores them).
from datetime import datetime, timedelta  # noqa: E402
from models.medical import Patient, Diagnosis  # noqa: E402

DEMO = [
    ("Demo Patient A", 54, "Male", "REFER: ABNORMAL HEART SOUND", 8.7),
    ("Demo Patient B", 31, "Female", "NO ABNORMALITY DETECTED", 0.9),
    ("Demo Patient C", 67, "Female", "UNSURE: RE-RECORD OR REFER", 4.8),
    ("Demo Patient D", 12, "Male", "NO ABNORMALITY DETECTED", 1.4),
]
with app.app_context():
    now = datetime.utcnow()
    for i, (name, age, gender, label, risk) in enumerate(DEMO):
        did = f"DEMO-UI-{i + 1}"
        if Diagnosis.query.filter_by(diagnosis_id=did).first():
            continue
        p = Patient(name=name, age=age, gender=gender, contact=f"demo-{i + 1}")
        db.session.add(p)
        db.session.flush()
        db.session.add(Diagnosis(
            diagnosis_id=did, patient_id=p.id, timestamp=now - timedelta(hours=5 * i),
            device_id="PI5-DEMO-01", diagnosis_result=label, confidence=None,
            risk_score=risk, recommendation="Demo record for UI checks.",
            path_used="heart_v6", organ_mode="Heart"))
        print(f"demo patient: {name}")
    db.session.commit()
