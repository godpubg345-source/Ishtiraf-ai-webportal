"""UI redesign: every main page renders, and results show the right screening outcome.

The old dashboard tested `"NORMAL" in result`, which is also true for
"REFER: ABNORMAL HEART SOUND", so refer cases were shown as NORMAL. These tests pin
the four outcomes (REFER / UNSURE / NO REFER / NO RESULT) and that no invented numbers
(fake accuracy %, fake vitals) come back.
"""
from datetime import datetime

import pytest

from app import app, db
from models.medical import Patient, Diagnosis

PAGES = ['/dashboard', '/register-patient', '/qr-scanner', '/realtime/analyzer',
         '/admin/dashboard', '/admin/bulk-import', '/admin/audit-logs', '/settings/profile']


def _add(name, label, risk, did):
    with app.app_context():
        p = Patient(name=name, age=40, gender='Female', contact=did)
        db.session.add(p)
        db.session.flush()
        db.session.add(Diagnosis(diagnosis_id=did, patient_id=p.id, timestamp=datetime(2026, 11, 20, 10, 0),
                                 device_id='PI5-T', diagnosis_result=label, risk_score=risk,
                                 recommendation='r', path_used='heart_v6', organ_mode='Heart'))
        db.session.commit()
        return p.id


def _badges(html):
    """Outcome labels shown inside status badges, in page order."""
    import re
    return re.findall(r'class="status status--(\w+)[^"]*"[^>]*><span class="dot"[^>]*></span>([A-Z ]+)<', html)


@pytest.mark.parametrize('url', PAGES)
def test_main_pages_render_with_new_shell(authenticated_client, url):
    resp = authenticated_client.get(url)
    assert resp.status_code == 200, url
    html = resp.get_data(as_text=True)
    assert 'css/app.css' in html and 'class="sidebar"' in html
    assert 'cdn.tailwindcss.com' not in html and 'fonts.googleapis.com' not in html  # offline-safe


def test_login_and_register_pages_render(client):
    for url, word in [('/auth/login', 'Sign in'), ('/auth/register', 'Register'), ('/auth/forgot-password', 'reset')]:
        html = client.get(url).get_data(as_text=True)
        assert word in html and 'css/app.css' in html


def test_dashboard_empty_state(authenticated_client):
    html = authenticated_client.get('/dashboard').get_data(as_text=True)
    assert 'No results saved yet' in html


def test_dashboard_maps_each_result_to_the_right_outcome(authenticated_client):
    _add('Pat Refer', 'REFER: ABNORMAL HEART SOUND', 8.8, 'T-1')
    _add('Pat Unsure', 'UNSURE: RE-RECORD OR REFER', 4.1, 'T-2')
    _add('Pat Clear', 'NO ABNORMALITY DETECTED', 0.9, 'T-3')
    html = authenticated_client.get('/dashboard').get_data(as_text=True)
    rows = html.split('<tbody id="diagnosisTable">')[1].split('</tbody>')[0]
    by_name = {chunk.split('</a>')[0].rsplit('>', 1)[-1]: _badges(chunk)[0]
               for chunk in rows.split('<tr ')[1:]}
    assert by_name == {'Pat Refer': ('refer', 'REFER'), 'Pat Unsure': ('unsure', 'UNSURE'),
                       'Pat Clear': ('clear', 'NO REFER')}
    # AI score is shown as 0-100, never as a confidence/accuracy percentage
    assert '88' in rows and 'Confidence' not in html and 'Accuracy' not in html


def test_patient_detail_shows_real_history_only(authenticated_client):
    pid = _add('Pat Detail', 'REFER: ABNORMAL HEART SOUND', 8.7, 'T-9')
    html = authenticated_client.get(f'/patient/{pid}').get_data(as_text=True)
    assert ('refer', 'REFER') in _badges(html)
    assert '87' in html and 'T-9' in html
    assert 'Heart Rate' not in html and 'bpm' not in html  # no invented vitals


def test_legacy_labels_still_map(app):
    from flask import render_template_string
    tpl = '{% import "partials/ui.html" as ui %}{% for t in items %}{{ ui.status_key(t)|trim }},{% endfor %}'
    with app.test_request_context():
        out = render_template_string(tpl, items=['NORMAL', 'ABNORMAL', 'NO RESULT', '', None, 'UNSURE: X'])
    assert out == 'clear,refer,none,none,none,unsure,'


def test_blank_user_name_does_not_break_the_shell(client):
    """Review finding: initials() crashed (500 on every page) for a name of only spaces."""
    from models.user import User
    with app.app_context():
        u = User(email='blank@test.com', name='   ', role='doctor')
        u.set_password('pw123456')
        db.session.add(u)
        db.session.commit()
    client.post('/auth/login', data={'email': 'blank@test.com', 'password': 'pw123456'})
    assert client.get('/dashboard').status_code == 200
