"""
IshtirafAI Mobile API
REST endpoints for Flutter/Mobile App
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models.user import db, User
from models.medical import Patient, Diagnosis
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta
import jwt
import os
import secrets

mobile_api = Blueprint('mobile_api', __name__, url_prefix='/api/v1')

# JWT Config
# Never hardcode: production requires JWT_SECRET (see config.get_config); dev gets a per-process random key
JWT_SECRET = os.environ.get('JWT_SECRET') or secrets.token_hex(32)
JWT_EXPIRY_HOURS = 24


def generate_token(user):
    """Generate JWT token for mobile auth"""
    payload = {
        'user_id': user.id,
        'email': user.email,
        'role': user.role,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def token_required(f):
    """Decorator to require valid JWT token"""
    from functools import wraps
    
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.current_user_id = payload['user_id']
            request.current_user_email = payload['email']
            request.current_user_role = payload['role']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    return decorated


# ============ AUTH ENDPOINTS ============

@mobile_api.route('/auth/login', methods=['POST'])
def mobile_login():
    """Mobile login - returns JWT token"""
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.check_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = generate_token(user)
    
    return jsonify({
        'token': token,
        'user': {
            'id': user.id,
            'email': user.email,
            'name': user.name,
            'role': user.role
        }
    })


@mobile_api.route('/auth/refresh', methods=['POST'])
@token_required
def refresh_token():
    """Refresh JWT token"""
    user = User.query.get(request.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    new_token = generate_token(user)
    return jsonify({'token': new_token})


@mobile_api.route('/auth/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current authenticated user"""
    user = User.query.get(request.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'role': user.role
    })


@mobile_api.route('/auth/me', methods=['PUT'])
@token_required
def update_profile():
    """Update user profile"""
    user = User.query.get(request.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        user.name = data['name'].strip()
    
    db.session.commit()
    
    return jsonify({
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'message': 'Profile updated successfully'
    })


@mobile_api.route('/auth/change-password', methods=['POST'])
@token_required
def change_password():
    """Change user password"""
    user = User.query.get(request.current_user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not old_password or not new_password:
        return jsonify({'error': 'Old and new passwords required'}), 400
    
    if not user.check_password(old_password):
        return jsonify({'error': 'Invalid old password'}), 401
    
    user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'message': 'Password changed successfully'})


# ============ PATIENT ENDPOINTS ============

@mobile_api.route('/patients', methods=['GET'])
@token_required
def list_patients():
    """List all patients (paginated)"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    
    query = Patient.query
    
    if search:
        query = query.filter(Patient.name.ilike(f'%{search}%'))
    
    pagination = query.order_by(Patient.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    patients = [{
        'id': p.id,
        'name': p.name,
        'age': p.age,
        'gender': p.gender,
        'contact': p.contact,
        'diagnosis_count': len(p.diagnoses) if hasattr(p, 'diagnoses') else 0
    } for p in pagination.items]
    
    return jsonify({
        'patients': patients,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@mobile_api.route('/patients/<int:patient_id>', methods=['GET'])
@token_required
def get_patient(patient_id):
    """Get single patient with diagnoses"""
    patient = Patient.query.get_or_404(patient_id)
    
    diagnoses = [{
        'id': d.id,
        'diagnosis_id': d.diagnosis_id,
        'result': d.diagnosis_result,
        'risk_score': d.risk_score,
        'confidence': d.confidence,
        'timestamp': d.timestamp.isoformat() if d.timestamp else None,
        'organ_mode': d.organ_mode
    } for d in patient.diagnoses] if hasattr(patient, 'diagnoses') else []
    
    return jsonify({
        'id': patient.id,
        'name': patient.name,
        'age': patient.age,
        'gender': patient.gender,
        'contact': patient.contact,
        'diagnoses': diagnoses
    })


@mobile_api.route('/patients', methods=['POST'])
@token_required
def create_patient():
    """Create new patient"""
    data = request.get_json()
    
    name = data.get('name', '').strip()
    age = data.get('age')
    gender = data.get('gender', '')
    contact = data.get('contact', '')
    
    if not name or not age or not gender:
        return jsonify({'error': 'Name, age, and gender required'}), 400
    
    patient = Patient(
        name=name,
        age=int(age),
        gender=gender,
        contact=contact
    )
    db.session.add(patient)
    db.session.commit()
    
    return jsonify({
        'id': patient.id,
        'name': patient.name,
        'message': 'Patient created successfully'
    }), 201


@mobile_api.route('/patients/<int:patient_id>', methods=['PUT'])
@token_required
def update_patient(patient_id):
    """Update existing patient"""
    patient = Patient.query.get_or_404(patient_id)
    data = request.get_json()
    
    patient.name = data.get('name', patient.name).strip()
    patient.age = int(data.get('age', patient.age))
    patient.gender = data.get('gender', patient.gender)
    patient.contact = data.get('contact', patient.contact)
    
    db.session.commit()
    
    return jsonify({
        'id': patient.id,
        'name': patient.name,
        'message': 'Patient updated successfully'
    })


@mobile_api.route('/patients/<int:patient_id>', methods=['DELETE'])
@token_required
def delete_patient(patient_id):
    """Delete patient and all associated diagnoses"""
    patient = Patient.query.get_or_404(patient_id)
    
    # Delete associated diagnoses first
    Diagnosis.query.filter_by(patient_id=patient_id).delete()
    
    db.session.delete(patient)
    db.session.commit()
    
    return jsonify({'message': 'Patient deleted successfully'}), 200


# ============ DIAGNOSIS ENDPOINTS ============

@mobile_api.route('/diagnoses', methods=['GET'])
@token_required
def list_diagnoses():
    """List recent diagnoses"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    pagination = Diagnosis.query.order_by(Diagnosis.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    diagnoses = [{
        'id': d.id,
        'diagnosis_id': d.diagnosis_id,
        'patient_id': d.patient_id,
        'patient_name': d.patient.name if d.patient else 'Unknown',
        'result': d.diagnosis_result,
        'risk_score': d.risk_score,
        'confidence': d.confidence,
        'timestamp': d.timestamp.isoformat() if d.timestamp else None
    } for d in pagination.items]
    
    return jsonify({
        'diagnoses': diagnoses,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })


@mobile_api.route('/diagnoses/<int:diagnosis_id>', methods=['GET'])
@token_required
def get_diagnosis(diagnosis_id):
    """Get diagnosis with AI report"""
    from utils.ai_expert import AIExpertSystem
    
    diagnosis = Diagnosis.query.get_or_404(diagnosis_id)
    
    # Generate AI report
    ai_report = AIExpertSystem.generate_report(
        diagnosis.diagnosis_result or 'Unknown',
        'A' if diagnosis.risk_score >= 5 else 'N',
        diagnosis.risk_score or 0,
        diagnosis.organ_mode or 'Heart'
    )
    
    return jsonify({
        'id': diagnosis.id,
        'diagnosis_id': diagnosis.diagnosis_id,
        'patient_id': diagnosis.patient_id,
        'patient_name': diagnosis.patient.name if diagnosis.patient else 'Unknown',
        'result': diagnosis.diagnosis_result,
        'risk_score': diagnosis.risk_score,
        'confidence': diagnosis.confidence,
        'recommendation': diagnosis.recommendation,
        'device_id': diagnosis.device_id,
        'organ_mode': diagnosis.organ_mode,
        'timestamp': diagnosis.timestamp.isoformat() if diagnosis.timestamp else None,
        'ai_report': {
            'explanation': ai_report.get('explanation'),
            'advice': ai_report.get('advice'),
            'acoustic_metrics': ai_report.get('acoustic_metrics')
        }
    })


# ============ QR SCAN ENDPOINT ============

@mobile_api.route('/scan', methods=['POST'])
@token_required
def mobile_scan():
    """Process QR payload from mobile scanner"""
    import base64
    import json
    
    data = request.get_json()
    payload = data.get('payload', '')
    
    if not payload:
        return jsonify({'error': 'No payload provided'}), 400
    
    try:
        # Decode base64 payload (Lite Mode)
        missing_padding = len(payload) % 4
        if missing_padding:
            payload += '=' * (4 - missing_padding)
        
        json_str = base64.urlsafe_b64decode(payload).decode('utf-8')
        raw_data = json.loads(json_str)
        
        # Expand Lite Mode keys
        organ_map = {'H': 'Heart', 'L': 'Lung'}
        status_map = {'N': 'Normal', 'A': 'Abnormal'}
        
        expanded = {
            'diagnosis': raw_data.get('d', 'Unknown'),
            'status': status_map.get(raw_data.get('s'), 'Unknown'),
            'risk_score': raw_data.get('r', 0),
            'confidence': raw_data.get('c', 0),
            'organ': organ_map.get(raw_data.get('o'), 'Heart'),
            'timestamp': raw_data.get('t', 'N/A')
        }
        
        # Generate AI report
        from utils.ai_expert import AIExpertSystem
        ai_report = AIExpertSystem.generate_report(
            expanded['diagnosis'],
            raw_data.get('s', 'N'),
            expanded['risk_score'],
            expanded['organ']
        )
        
        return jsonify({
            'success': True,
            'data': expanded,
            'ai_report': ai_report
        })
        
    except Exception as e:
        return jsonify({'error': f'Invalid QR payload: {str(e)}'}), 400


# ============ STATS ENDPOINT ============

@mobile_api.route('/stats', methods=['GET'])
@token_required
def get_stats():
    """Dashboard stats for mobile"""
    total_patients = Patient.query.count()
    total_diagnoses = Diagnosis.query.count()
    
    # High risk count
    high_risk = Diagnosis.query.filter(Diagnosis.risk_score >= 7).count()
    
    # Today's diagnoses
    today = datetime.now().date()
    today_count = Diagnosis.query.filter(
        db.func.date(Diagnosis.timestamp) == today
    ).count()
    
    return jsonify({
        'total_patients': total_patients,
        'total_diagnoses': total_diagnoses,
        'high_risk_count': high_risk,
        'today_diagnoses': today_count
    })
