"""Reports sent out of the portal carry only stored facts.

Regression for two bugs:
- /api/v1/diagnoses/<id> built its "AI report" from a fixed template (utils/ai_expert.py):
  "345 Hz", "Grade II/VI", "AI confirms normal S1 and S2" - none of it from the model.
- FHIR export matched "normal" as a substring, so "REFER: ABNORMAL HEART SOUND" was
  coded as SNOMED "Normal heart sounds" with interpretation N, plus a 0% "confidence".
"""
import time
from datetime import datetime

import jwt
import pytest

from app import app, db
from models.medical import Patient, Diagnosis
from routes.mobile_api import JWT_SECRET
from utils.fhir_export import generate_fhir_observation

INVENTED = ['345 Hz', 'Grade II/VI', 'confirms', 'murmur', 'gallop', '200-500Hz']


def _row(label, risk=8.7):
    with app.app_context():
        p = Patient(name='Pat', age=9, gender='Female', contact='c')
        db.session.add(p)
        db.session.flush()
        d = Diagnosis(diagnosis_id=f'T-{label[:6]}-{risk}', patient_id=p.id, timestamp=datetime(2026, 11, 20),
                      device_id='PI5-T', diagnosis_result=label, risk_score=risk, recommendation='Stored advice.',
                      path_used='heart_v6', organ_mode='Heart')
        db.session.add(d)
        db.session.commit()
        return d.id


def _get(client, did):
    tok = jwt.encode({'user_id': 1, 'email': 'a@b.c', 'role': 'doctor', 'exp': int(time.time()) + 600},
                     JWT_SECRET, algorithm='HS256')
    return client.get(f'/api/v1/diagnoses/{did}', headers={'Authorization': f'Bearer {tok}'})


@pytest.mark.parametrize('label', ['REFER: ABNORMAL HEART SOUND', 'NO ABNORMALITY DETECTED',
                                   'UNSURE: RE-RECORD OR REFER', 'NORMAL', 'ABNORMAL'])
def test_mobile_report_has_no_invented_findings(client, label):
    resp = _get(client, _row(label))
    assert resp.status_code == 200
    rep = resp.get_json()['ai_report']
    text = str(rep)
    assert not [w for w in INVENTED if w.lower() in text.lower()], text
    assert rep['acoustic_metrics']['AI score'] == '87/100'
    assert 'Screening aid only - not a diagnosis.' in rep['advice']


def test_mobile_report_explains_refer_from_the_score(client):
    rep = _get(client, _row('REFER: ABNORMAL HEART SOUND')).get_json()['ai_report']
    assert 'refer band' in rep['explanation'] and '87/100' in rep['explanation']
    assert rep['advice'][-1] == 'Stored advice.'


def test_mobile_report_survives_missing_score(client):
    rep = _get(client, _row('NO ABNORMALITY DETECTED', risk=None)).get_json()['ai_report']
    assert rep['acoustic_metrics']['AI score'] == '--'


@pytest.mark.parametrize('label, code', [('REFER: ABNORMAL HEART SOUND', 'refer'),
                                         ('UNSURE: RE-RECORD OR REFER', 'unsure'),
                                         ('NO ABNORMALITY DETECTED', 'no-referral')])
def test_fhir_codes_the_referral_decision(app, label, code):
    with app.app_context():
        d = db.session.get(Diagnosis, _row(label))
        obs = generate_fhir_observation(d, d.patient)
    assert obs['valueCodeableConcept']['coding'][0]['code'] == code
    assert 'interpretation' not in obs
    assert 'snomed' not in str(obs).lower() and 'confidence' not in str(obs).lower()
    assert obs['component'][0]['valueQuantity']['value'] == 87


def test_fhir_pre_v2_row_has_no_value(app):
    with app.app_context():
        d = db.session.get(Diagnosis, _row('ABNORMAL'))
        obs = generate_fhir_observation(d, d.patient)
    assert 'valueCodeableConcept' not in obs and obs['dataAbsentReason']['coding'][0]['code'] == 'unknown'
