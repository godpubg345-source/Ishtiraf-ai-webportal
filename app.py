from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
import json
import sys

# Emoji in startup prints crash Windows when output is redirected (cp1252); never let logging kill the app
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except Exception:
        pass
import zlib
import base64
import logging
import uuid
from cryptography.fernet import Fernet
import os
from datetime import datetime
from utils.pdf_generator import generate_patient_pdf
from config import get_config

# Import Models & Blueprints
from models.user import db, User
from models.medical import Patient, Diagnosis
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.settings import settings_bp
from routes.analytics import analytics_bp
from routes.realtime import realtime_bp
from routes.bulk_import import bulk_bp
from routes.mobile_api import mobile_api
from routes.security import security_bp
from routes.reports import reports_bp

# Enterprise Features
from utils.rbac import require_permission, require_role, rbac_context_processor
from utils.audit import log_audit, init_audit_logging, audit_action
from utils.ai_expert import AIExpertSystem
from utils.notifications import init_notifications, notifications
from utils.rate_limiter import init_rate_limiter, rate_limiter, limit_auth, limit_api


app = Flask(__name__)
CORS(app)

# Load Configuration from config.py
config_class = get_config()
app.config.from_object(config_class)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('IshtirafAI')

# Initialize DB & Login Manager
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

# Initialize AI Models
try:
    from utils.inference import load_models
    with app.app_context():
        print("⏳ Loading AI Models...")
        load_models()
        print("✅ AI Models Ready")
except Exception as e:
    print(f"❌ Error loading AI models: {e}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(admin_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(realtime_bp)
app.register_blueprint(bulk_bp)  # Bulk import API
app.register_blueprint(mobile_api)  # Mobile App REST API v1
app.register_blueprint(security_bp)  # Security & Compliance routes
app.register_blueprint(reports_bp)  # Reports & Analytics

# ══════════════════════════════════════════════════════════════════════════════
# ENTERPRISE FEATURES INITIALIZATION
# ══════════════════════════════════════════════════════════════════════════════

# 1. RBAC - Add permission helpers to Jinja templates
app.context_processor(rbac_context_processor)

# 2. Audit Logging - HIPAA compliant
with app.app_context():
    init_audit_logging(app, db)

# 3. Rate Limiter
init_rate_limiter(app)

# 4. Notification Service
init_notifications(app)

print("✅ Enterprise Features Loaded: RBAC, Audit, Notifications, Rate Limiting")


# Initialize Flask-Mail
from flask_mail import Mail
mail = Mail(app)

# Make mail accessible to blueprints
app.mail = mail

# Encryption Key
try:
    with open(os.path.join(BASE_DIR, '..', 'Model_Training', '2_App_Core', 'secret.key'), 'rb') as key_file:
        ENCRYPTION_KEY = key_file.read()
    cipher = Fernet(ENCRYPTION_KEY)
    print("Encryption Key Loaded Successfully.")
except Exception as e:
    print(f"Warning: Could not load encryption key: {e}")
    ENCRYPTION_KEY = None

@app.route('/')
@login_required
def index():
    return render_template('index.html', user=current_user)

@app.route('/dashboard')
@login_required
def dashboard():
    patients = Patient.query.order_by(Patient.created_at.desc()).all()
    
    total_patients = len(patients)
    critical_count = 0
    healthy_count = 0
    total_risk = 0
    diagnosis_count = 0

    for p in patients:
        for d in p.diagnoses:
            diagnosis_count += 1
            total_risk += d.risk_score
            if "NORMAL" in d.diagnosis_result:
                healthy_count += 1
            else:
                critical_count += 1
    
    avg_risk = round(total_risk / diagnosis_count, 1) if diagnosis_count > 0 else 0

    return render_template('dashboard.html', 
                         patients=patients,
                         critical_count=critical_count,
                         healthy_count=healthy_count,
                         avg_risk=avg_risk,
                         user=current_user)

@app.route('/patient/<int:id>')
@login_required
def patient_detail(id):
    patient = Patient.query.get_or_404(id)
    total_risk = sum([d.risk_score for d in patient.diagnoses])
    avg_risk = round(total_risk / len(patient.diagnoses), 1) if patient.diagnoses else 0
    return render_template('patient_detail.html', patient=patient, avg_risk=avg_risk, user=current_user)


@app.route('/register-patient', methods=['GET', 'POST'])
@login_required
def register_patient():
    """Register a new patient and generate unique Patient ID"""
    from flask import flash
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        age = request.form.get('age', 0)
        gender = request.form.get('gender', '')
        contact = request.form.get('contact', '').strip()
        medical_history = request.form.get('medical_history', '').strip()
        
        if not name or not age or not gender:
            flash('Name, Age, and Gender are required!', 'error')
            return redirect(url_for('register_patient'))
        
        # Check if patient already exists
        existing = Patient.query.filter_by(name=name, contact=contact).first()
        if existing:
            flash(f'Patient already exists! ID: PAT-{existing.id:04d}', 'error')
            return redirect(url_for('patient_detail', id=existing.id))
        
        # Create new patient
        new_patient = Patient(
            name=name,
            age=int(age),
            gender=gender,
            contact=contact
        )
        db.session.add(new_patient)
        db.session.commit()
        
        patient_id = f"PAT-{new_patient.id:04d}"
        flash(f'✅ Patient registered successfully! ID: {patient_id}', 'success')
        return redirect(url_for('patient_detail', id=new_patient.id))
    
    return render_template('register_patient.html', user=current_user)

@app.route('/export_pdf/<int:diagnosis_id>')
@login_required
def export_pdf(diagnosis_id):
    diagnosis = Diagnosis.query.get_or_404(diagnosis_id)
    patient = diagnosis.patient
    pdf_buffer = generate_patient_pdf(patient, diagnosis)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"Report_{patient.name}_{diagnosis.timestamp.strftime('%Y%m%d')}.pdf",
        mimetype='application/pdf'
    )

# API Endpoints

@app.route('/health')
def health_check():
    """Health check endpoint for Docker"""
    return jsonify({'status': 'healthy', 'service': 'IshtirafAI WebPortal'})


@app.route('/api/analyze-audio', methods=['POST'])
@login_required
def analyze_audio():
    """API endpoint to analyze audio from browser"""
    try:
        data = request.get_json()
        audio_base64 = data.get('audio')
        
        if not audio_base64:
            return jsonify({'error': 'No audio data provided'}), 400
        
        # Process audio (simplified - full analysis requires TF model)
        from routes.realtime import process_audio_chunk
        result = process_audio_chunk(audio_base64)
        
        return jsonify({
            'status': 'processed',
            'message': 'Audio received and processed. For full AI diagnosis, use the desktop application.',
            **result
        })
    except Exception as e:
        logger.error(f"Audio analysis error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/decrypt_qr', methods=['POST'])
def decrypt_qr():
    if not ENCRYPTION_KEY:
        return jsonify({"error": "Encryption key not configured"}), 500
    try:
        data = request.json
        encrypted_payload = data.get('payload')
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_payload)
        compressed_bytes = cipher.decrypt(encrypted_bytes)
        json_str = zlib.decompress(compressed_bytes).decode("utf-8")
        diagnosis_data = json.loads(json_str)
        return jsonify({"status": "success", "data": diagnosis_data})
    except Exception as e:
        print(f"Decryption Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/api/save_patient', methods=['POST'])
def save_patient():
    try:
        data = request.json
        patient_data = data.get('patient')
        diagnosis_data = data.get('diagnosis')
        
        patient = Patient.query.filter_by(name=patient_data['name']).first()
        if not patient:
            patient = Patient(
                name=patient_data['name'],
                age=int(patient_data['age']),
                gender=patient_data['gender'],
                contact=patient_data.get('contact', '')
            )
            db.session.add(patient)
            db.session.commit()
            
        new_diagnosis = Diagnosis(
            diagnosis_id=diagnosis_data['diagnosis_id'],
            patient_id=patient.id,
            timestamp=datetime.strptime(diagnosis_data['timestamp'], '%Y-%m-%d %H:%M:%S'),
            device_id=diagnosis_data['device_id'],
            diagnosis_result=diagnosis_data['diagnosis'],
            confidence=float(diagnosis_data['confidence']),
            risk_score=float(diagnosis_data['risk_score']),
            recommendation=diagnosis_data['recommendation'],
            path_used=diagnosis_data['path_used'],
            rms_value=float(diagnosis_data['rms_value']),
            sym_chest_pain=diagnosis_data['symptoms']['chest_pain'],
            sym_shortness=diagnosis_data['symptoms']['shortness'],
            sym_history=diagnosis_data['symptoms']['history'],
            patient_mode=diagnosis_data['patient_mode'],
            organ_mode=diagnosis_data['organ_mode']
        )
        db.session.add(new_diagnosis)
        db.session.commit()
        return jsonify({"status": "success", "message": "Record Saved Successfully"})
    except Exception as e:
        print(f"Save Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Web Portal 2.0 Routes ---

@app.route('/qr-scanner')
def qr_scanner():
    """Camera-based QR scanner page"""
    return render_template('qr_scanner.html')


@app.route('/api/scan_qr_image', methods=['POST'])
def scan_qr_image():
    """
    Server-side QR decoder for uploaded images.
    Uses cv2 with preprocessing for better detection.
    """
    try:
        if 'image' not in request.files:
            return jsonify({"error": "No image uploaded"}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
            
        # Save temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name
            
        try:
            import cv2
            import numpy as np
            
            # Load image
            img = cv2.imread(tmp_path)
            if img is None:
                return jsonify({"error": "Could not load image"}), 400
                
            detector = cv2.QRCodeDetector()
            
            # Try 1: Direct detection
            data, bbox, _ = detector.detectAndDecode(img)
            if data: return jsonify({"success": True, "data": data})
            
            # Preprocessing 1: Grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            data, bbox, _ = detector.detectAndDecode(gray)
            if data: return jsonify({"success": True, "data": data})
            
            # Preprocessing 2: Otsu's Binarization (Automatic Threshold)
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            data, bbox, _ = detector.detectAndDecode(otsu)
            if data: return jsonify({"success": True, "data": data})
            
            # Preprocessing 3: Strong Contrast (CLAHE)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            contrast = clahe.apply(gray)
            data, bbox, _ = detector.detectAndDecode(contrast)
            if data: return jsonify({"success": True, "data": data})
            
            # Preprocessing 4: Sharpening kernel
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(gray, -1, kernel)
            data, bbox, _ = detector.detectAndDecode(sharpened)
            if data: return jsonify({"success": True, "data": data})

            # Preprocessing 5: Scale Up (Zoom)
            scale = 2.0
            scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            data, bbox, _ = detector.detectAndDecode(scaled)
            if data: return jsonify({"success": True, "data": data})
            
            # Preprocessing 6: Adaptive Threshold (Noise removal)
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            data, bbox, _ = detector.detectAndDecode(adaptive)
            if data: return jsonify({"success": True, "data": data})
            
            # Preprocessing 7: Factor for dark mode (Invert)
            inverted = cv2.bitwise_not(gray)
            data, bbox, _ = detector.detectAndDecode(inverted)
            if data: return jsonify({"success": True, "data": data})
            
            return jsonify({"error": "Still no QR found. Please use the '📋 COPY URL' button on the dashboard instead."}), 400

                    
        finally:
            # Cleanup temp file
            os.unlink(tmp_path)
            
    except ImportError as e:
        logger.error(f"Missing library: {e}")
        return jsonify({"error": "OpenCV not installed on server"}), 500
    except Exception as e:
        logger.error(f"QR Scan Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/scan')
def scan_qr():
    # Support both ?p= (new minimal) and ?payload= (legacy)
    payload = request.args.get('p') or request.args.get('payload')
    if not payload:
        # Redirect to camera scanner if no payload
        return redirect(url_for('qr_scanner'))
    
    # FIX: Handle case where user pastes FULL URL instead of just payload
    if payload.startswith('http://') or payload.startswith('https://'):
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(payload)
            query_params = parse_qs(parsed.query)
            # Check both ?p= and ?payload=
            if 'p' in query_params:
                payload = query_params['p'][0]
            elif 'payload' in query_params:
                payload = query_params['payload'][0]
            print(f"📦 Extracted payload from URL: {len(payload)} chars")
        except Exception as e:
            print(f"URL parse error: {e}")

        
    try:
        # Decrypt Payload
        encrypted_bytes = base64.urlsafe_b64decode(payload)
        
        try:
            # 1. Try Decrypting (Old Secure Mode)
            decrypted_bytes = cipher.decrypt(encrypted_bytes)
            
            # Try decoding as raw JSON first (New Minimal Format - No Zlib)
            try:
                json_str = decrypted_bytes.decode("utf-8")
                raw_data = json.loads(json_str)
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Fallback to Zlib decompress (Old Format)
                json_str = zlib.decompress(decrypted_bytes).decode("utf-8")
                raw_data = json.loads(json_str)
                
        except Exception:
            # 2. Fallback to Plain Base64 (New Lite Mode v3.2)
            # This handles unencrypted QRs for better scannability
            print("⚠️ Decryption failed, attempting Lite Mode decode...")
            try:
                json_str = encrypted_bytes.decode("utf-8")
                raw_data = json.loads(json_str)
                print("✅ Lite Mode (Unencrypted) Payload Detected")
            except Exception as e_lite:
                print(f"Login failed: {e_lite}")
                raise Exception("Invalid QR Payload")

        print(f"📦 Decoded payload: {raw_data}")
        
        # Check if it's a minimal payload (new format) or full payload (old format)
        if 's' in raw_data and len(raw_data) <= 10:
            # MINIMAL format: expand to full format for template
            status_map = {'N': 'Normal', 'A': 'Abnormal'}
            organ_map = {'H': 'Heart', 'L': 'Lung'}
            
            # Get diagnosis and status
            diagnosis = raw_data.get('d', 'Unknown')
            status = raw_data.get('s', 'N')
            risk = raw_data.get('r', 0)
            organ = organ_map.get(raw_data.get('o', 'H'), 'Heart')
            
            # GENERATE AI REPORT (New v3.3 Feature)
            ai_report = AIExpertSystem.generate_report(diagnosis, status, risk, organ)
            findings = [] # Legacy findings list (kept for back-compat if needed)

            # Generate recommendation
            if risk >= 7:
                recommendation = 'URGENT: Consult cardiologist immediately'
            elif status == 'A':
                recommendation = 'Schedule cardiology consultation soon'
            else:
                recommendation = 'Routine checkup recommended'

            diagnosis_data = {
                'diagnosis': diagnosis,
                'status': status_map.get(status, 'Unknown'),
                'risk_score': risk,
                'confidence': raw_data.get('c', 0),
                'organ': organ,
                'timestamp': raw_data.get('t', 'N/A'),
                'device_id': 'IshtirafAI-Steth',
                'findings': findings,
                'advanced_metrics': ai_report['acoustic_metrics'],
                'ai_explanation': ai_report['explanation'],
                'ai_advice': ai_report['advice'],
                'recommendation': recommendation
            }
        else:
            # Old full format
            diagnosis_data = raw_data
            # Ensure findings and metrics exist for old payloads too
            if 'findings' not in diagnosis_data: diagnosis_data['findings'] = []
            if 'advanced_metrics' not in diagnosis_data: diagnosis_data['advanced_metrics'] = {}
        
        return render_template('public_scan.html', diagnosis=diagnosis_data, payload=payload)
    except Exception as e:
        print(f"Scan Error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error reading QR Code: {str(e)}", 400


# --- V3.0 High-Capacity Optical Transfer Routes ---

@app.route('/scan/v3')
def scan_v3():
    """V3.0: Decode JAB Code with neural audio."""
    return render_template('scan_v3.html')


@app.route('/api/decode_v3', methods=['POST'])
def api_decode_v3():
    """API: Decode V3.0 payload (base64 or raw bytes)."""
    try:
        from utils.v3_decoder import get_decoder, V3_DECODE_AVAILABLE
        
        if not V3_DECODE_AVAILABLE:
            return jsonify({"error": "V3.0 decoder not available on server"}), 501
            
        data = request.get_json()
        payload_b64 = data.get('payload')
        
        if not payload_b64:
            return jsonify({"error": "No payload provided"}), 400
            
        decoder = get_decoder()
        result = decoder.decode_from_base64(payload_b64)
        
        if "error" in result:
            return jsonify(result), 400
            
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"V3 Decode Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/playback_audio', methods=['POST'])
def api_playback_audio():
    """API: Stream reconstructed audio as WAV."""
    try:
        from utils.v3_decoder import get_decoder, V3_DECODE_AVAILABLE
        import numpy as np
        import io
        from scipy.io import wavfile
        
        if not V3_DECODE_AVAILABLE:
            return jsonify({"error": "V3.0 decoder not available"}), 501
            
        data = request.get_json()
        audio_samples = data.get('audio')
        sample_rate = data.get('sample_rate', 4000)
        
        if not audio_samples:
            return jsonify({"error": "No audio data"}), 400
            
        # Convert to numpy and create WAV
        audio = np.array(audio_samples, dtype=np.float32)
        audio_int16 = (audio * 32767).astype(np.int16)
        
        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sample_rate, audio_int16)
        wav_buffer.seek(0)
        
        return send_file(
            wav_buffer,
            mimetype='audio/wav',
            as_attachment=False,
            download_name='reconstructed_audio.wav'
        )
        
    except Exception as e:
        logger.error(f"Playback Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/save_to_account', methods=['POST'])
@login_required
def save_to_account():
    payload = request.form.get('payload')
    try:
        # Decrypt again to ensure security
        encrypted_bytes = base64.urlsafe_b64decode(payload)
        compressed_bytes = cipher.decrypt(encrypted_bytes)
        json_str = zlib.decompress(compressed_bytes).decode("utf-8")
        data = json.loads(json_str)
        
        # Create Patient Record (Self)
        patient = Patient.query.filter_by(name=current_user.name).first()
        if not patient:
            patient = Patient(
                name=current_user.name,
                age=30, # Placeholder, should ask user
                gender="Unknown",
                contact=current_user.email
            )
            db.session.add(patient)
            db.session.commit()
            
        # Create Diagnosis
        new_diagnosis = Diagnosis(
            diagnosis_id=data.get('diagnosis_id', f"DIAG-{int(datetime.now().timestamp())}"),
            patient_id=patient.id,
            timestamp=datetime.strptime(data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S'),
            device_id=data.get('device_id', 'UNKNOWN'),
            diagnosis_result=data.get('diagnosis'),
            confidence=float(data.get('confidence', 0)),
            risk_score=float(data.get('risk_score', 0)),
            recommendation=data.get('recommendation', ''),
            path_used=data.get('path_used', 'Unknown'),
            rms_value=float(data.get('rms_value', 0)),
            sym_chest_pain=data.get('symptoms', {}).get('chest_pain', False),
            sym_shortness=data.get('symptoms', {}).get('shortness', False),
            sym_history=data.get('symptoms', {}).get('history', False),
            patient_mode=data.get('patient_mode', 'Adult'),
            organ_mode=data.get('organ_mode', 'Raw')
        )
        db.session.add(new_diagnosis)
        db.session.commit()
        
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"Save Error: {e}")
        return f"Error saving record: {str(e)}", 400


@app.route('/save-from-qr', methods=['POST'])
def save_from_qr():
    """
    Saves patient info (from form) + diagnosis (from QR payload).
    This is the main flow: Pi5 scan → QR → Phone scan → Portal form → Save
    """
    from flask import flash
    
    payload = request.form.get('payload')
    name = request.form.get('name', '').strip()
    age = request.form.get('age', 0)
    gender = request.form.get('gender', '')
    contact = request.form.get('contact', '').strip()
    
    if not name or not age or not gender:
        flash('Name, Age, and Gender are required!', 'error')
        return redirect(request.referrer or url_for('dashboard'))
    
    try:
        # Decrypt/Decode Payload (Hybrid Mode)
        raw_data = {}
        try:
            # 1. Try Legacy Encrypted Format
            encrypted_bytes = base64.urlsafe_b64decode(payload)
            compressed_bytes = cipher.decrypt(encrypted_bytes)
            json_str = zlib.decompress(compressed_bytes).decode("utf-8")
            raw_data = json.loads(json_str)
        except Exception:
            # 2. Fallback to Lite Mode (Base64 JSON)
            try:
                # Add padding if needed
                missing_padding = len(payload) % 4
                if missing_padding:
                    payload += '=' * (4 - missing_padding)
                json_str = base64.urlsafe_b64decode(payload).decode("utf-8")
                raw_data = json.loads(json_str)
            except Exception as e:
                raise Exception(f"Invalid QR Payload: {e}")

        # Expand Keys if Lite Mode
        if 'd' in raw_data:
            organ_map = {'H': 'Heart', 'L': 'Lung'}
            status_map = {'N': 'Normal', 'A': 'Abnormal'}
            data = {
                'diagnosis': raw_data.get('d', 'Unknown'),
                'risk_score': raw_data.get('r', 0),
                'confidence': raw_data.get('c', 0),
                'timestamp': raw_data.get('t', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                'device_id': 'IshtirafAI-Steth',
                'recommendation': 'Generated via AI Expert System',
                'symptoms': {},
                'patient_mode': 'Adult', 
                'organ_mode': organ_map.get(raw_data.get('o'), 'Heart')
            }
        else:
            data = raw_data

        # Find or Create Patient
        patient = Patient.query.filter_by(name=name, contact=contact).first()
        if not patient:
            patient = Patient(
                name=name,
                age=int(age),
                gender=gender,
                contact=contact
            )
            db.session.add(patient)
            db.session.commit()
        
        # Create Diagnosis linked to patient
        new_diagnosis = Diagnosis(
            diagnosis_id=data.get('diagnosis_id', f"DIAG-{int(datetime.now().timestamp())}"),
            patient_id=patient.id,
            timestamp=datetime.strptime(data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')), '%Y-%m-%d %H:%M:%S'),
            device_id=data.get('device_id', 'RPI5-TOUCH'),
            diagnosis_result=data.get('diagnosis', 'Unknown'),
            confidence=float(data.get('confidence', 0)),
            risk_score=float(data.get('risk_score', 0)),
            recommendation=data.get('recommendation', 'Consult physician'),
            path_used=data.get('path_used', 'Unknown'),
            rms_value=float(data.get('rms_value', 0)),
            sym_chest_pain=data.get('symptoms', {}).get('chest_pain', False),
            sym_shortness=data.get('symptoms', {}).get('shortness', False),
            sym_history=data.get('symptoms', {}).get('history', False),
            patient_mode=data.get('patient_mode', 'Adult'),
            organ_mode=data.get('organ_mode', 'Heart')
        )
        db.session.add(new_diagnosis)
        db.session.commit()
        
        flash(f'✅ Record saved for {name}!', 'success')
        return redirect(url_for('patient_detail', id=patient.id))
        
    except Exception as e:
        logger.error(f"Save from QR Error: {e}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    logger.warning(f"404 Error: {request.url}")
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    error_id = str(uuid.uuid4())[:8]
    logger.error(f"500 Error [{error_id}]: {str(e)}")
    return render_template('errors/500.html', error_id=error_id), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Database Migration: Add is_active if missing
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text("SELECT is_active FROM user LIMIT 1"))
        except Exception:
            logger.info("Migrating Database: Adding 'is_active' column...")
            try:
                with db.engine.connect() as conn:
                    conn.execute(db.text("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                    conn.commit()
                logger.info("Migration Successful: 'is_active' column added.")
            except Exception as e:
                logger.error(f"Migration Failed: {e}")

    # Run on 0.0.0.0 to be accessible from phone
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=app.config.get('DEBUG', True), host=host, port=port)
