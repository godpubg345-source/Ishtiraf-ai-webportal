"""
IshtirafAI - Security & Compliance Routes
==========================================
Login history, IP whitelisting, GDPR data export, session management.
"""

from flask import Blueprint, render_template, request, jsonify, Response, send_file
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models.user import db, User
from models.medical import Patient, Diagnosis
from utils.decorators import role_required
import json
import csv
import io

security_bp = Blueprint('security', __name__, url_prefix='/security')


# ═══════════════════════════════════════════════════════════════════════════════
# LOGIN HISTORY
# ═══════════════════════════════════════════════════════════════════════════════

@security_bp.route('/login-history')
@login_required
def login_history():
    """Display login history for current user."""
    from sqlalchemy import text
    
    try:
        result = db.session.execute(text('''
            SELECT * FROM audit_logs 
            WHERE user_id = :user_id AND action LIKE '%login%'
            ORDER BY created_at DESC 
            LIMIT 20
        '''), {'user_id': current_user.id})
        
        logs = []
        for row in result:
            logs.append({
                'id': row.id,
                'ip_address': row.ip_address,
                'user_agent': row.user_agent,
                'created_at': row.created_at,
                'response_status': row.response_status
            })
    except Exception as e:
        logs = []
        print(f"Login history error: {e}")
    
    return render_template('settings/login_history.html', logs=logs)


@security_bp.route('/api/login-history')
@login_required
def api_login_history():
    """API endpoint for login history."""
    from sqlalchemy import text
    
    try:
        result = db.session.execute(text('''
            SELECT id, ip_address, user_agent, created_at, response_status
            FROM audit_logs 
            WHERE user_id = :user_id AND action LIKE '%login%'
            ORDER BY created_at DESC 
            LIMIT 20
        '''), {'user_id': current_user.id})
        
        logs = []
        for row in result:
            logs.append({
                'id': row.id,
                'ip_address': row.ip_address,
                'device': parse_user_agent(row.user_agent),
                'created_at': row.created_at.isoformat() if row.created_at else None,
                'success': row.response_status == 200
            })
        
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def parse_user_agent(ua_string):
    """Parse user agent to determine device type."""
    if not ua_string:
        return {'type': 'unknown', 'browser': 'Unknown'}
    
    ua = ua_string.lower()
    
    device_type = 'desktop'
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
        device_type = 'mobile'
    elif 'tablet' in ua or 'ipad' in ua:
        device_type = 'tablet'
    
    browser = 'Unknown'
    if 'chrome' in ua:
        browser = 'Chrome'
    elif 'firefox' in ua:
        browser = 'Firefox'
    elif 'safari' in ua:
        browser = 'Safari'
    elif 'edge' in ua:
        browser = 'Edge'
    
    return {'type': device_type, 'browser': browser}


# ═══════════════════════════════════════════════════════════════════════════════
# GDPR DATA EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

@security_bp.route('/export-my-data')
@login_required
def export_my_data():
    """GDPR-compliant export of user's personal data."""
    
    user_data = {
        'profile': {
            'id': current_user.id,
            'email': current_user.email,
            'name': current_user.name,
            'role': current_user.role,
            'created_at': current_user.created_at.isoformat() if current_user.created_at else None,
            'is_verified': current_user.is_verified,
            'is_active': current_user.is_active
        },
        'export_date': datetime.utcnow().isoformat(),
        'data_controller': 'IshtirafAI Medical Diagnostic System'
    }
    
    # Add audit logs
    try:
        from sqlalchemy import text
        result = db.session.execute(text('''
            SELECT action, created_at, ip_address 
            FROM audit_logs 
            WHERE user_id = :user_id 
            ORDER BY created_at DESC
        '''), {'user_id': current_user.id})
        
        user_data['activity_log'] = [
            {
                'action': row.action,
                'timestamp': row.created_at.isoformat() if row.created_at else None,
                'ip_address': row.ip_address
            }
            for row in result
        ]
    except:
        user_data['activity_log'] = []
    
    # Create JSON response
    response = Response(
        json.dumps(user_data, indent=2),
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename=ishtirafai_data_export_{current_user.id}.json'
        }
    )
    
    return response


@security_bp.route('/export-patient-data/<int:patient_id>')
@login_required
def export_patient_data(patient_id):
    """Export all data for a specific patient (GDPR request)."""
    
    patient = Patient.query.get_or_404(patient_id)
    
    patient_data = {
        'patient': {
            'id': patient.id,
            'name': patient.name,
            'age': patient.age,
            'gender': patient.gender,
            'contact': patient.contact,
            'created_at': patient.created_at.isoformat() if patient.created_at else None
        },
        'diagnoses': [],
        'export_date': datetime.utcnow().isoformat(),
        'data_controller': 'IshtirafAI Medical Diagnostic System'
    }
    
    for d in patient.diagnoses:
        patient_data['diagnoses'].append({
            'diagnosis_id': d.diagnosis_id,
            'timestamp': d.timestamp.isoformat() if d.timestamp else None,
            'result': d.diagnosis_result,
            'confidence': d.confidence,
            'risk_score': d.risk_score,
            'recommendation': d.recommendation,
            'organ_mode': d.organ_mode,
            'symptoms': {
                'chest_pain': d.sym_chest_pain,
                'shortness_of_breath': d.sym_shortness,
                'medical_history': d.sym_history
            }
        })
    
    response = Response(
        json.dumps(patient_data, indent=2),
        mimetype='application/json',
        headers={
            'Content-Disposition': f'attachment; filename=patient_{patient_id}_data.json'
        }
    )
    
    return response


# ═══════════════════════════════════════════════════════════════════════════════
# IP WHITELISTING (Admin Only)
# ═══════════════════════════════════════════════════════════════════════════════

# Store whitelist in memory (in production, use database)
IP_WHITELIST = set()
IP_WHITELIST_ENABLED = False

@security_bp.route('/ip-whitelist', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def ip_whitelist():
    """Manage IP whitelist for admin access."""
    global IP_WHITELIST, IP_WHITELIST_ENABLED
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            ip = request.form.get('ip')
            if ip:
                IP_WHITELIST.add(ip)
        elif action == 'remove':
            ip = request.form.get('ip')
            IP_WHITELIST.discard(ip)
        elif action == 'toggle':
            IP_WHITELIST_ENABLED = not IP_WHITELIST_ENABLED
        
        return jsonify({
            'success': True,
            'enabled': IP_WHITELIST_ENABLED,
            'whitelist': list(IP_WHITELIST)
        })
    
    return render_template('settings/ip_whitelist.html', 
                         whitelist=list(IP_WHITELIST),
                         enabled=IP_WHITELIST_ENABLED,
                         current_ip=request.remote_addr)


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@security_bp.route('/api/session-info')
@login_required
def session_info():
    """Get current session information."""
    from flask import session
    
    return jsonify({
        'user_id': current_user.id,
        'email': current_user.email,
        'role': current_user.role,
        'session_permanent': session.permanent,
        'ip_address': request.remote_addr
    })


@security_bp.route('/api/extend-session', methods=['POST'])
@login_required
def extend_session():
    """Extend the current session."""
    from flask import session
    session.permanent = True
    session.modified = True
    
    return jsonify({
        'success': True,
        'message': 'Session extended successfully'
    })


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVE SESSIONS (Show where user is logged in)
# ═══════════════════════════════════════════════════════════════════════════════

@security_bp.route('/active-sessions')
@login_required
def active_sessions():
    """Show active sessions for current user."""
    # In production, this would query a sessions table
    # For now, we show the current session only
    
    sessions = [{
        'id': 1,
        'ip_address': request.remote_addr,
        'user_agent': request.user_agent.string,
        'device': parse_user_agent(request.user_agent.string),
        'last_active': datetime.utcnow().isoformat(),
        'current': True
    }]
    
    return render_template('settings/active_sessions.html', sessions=sessions)
