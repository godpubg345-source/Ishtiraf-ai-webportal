from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import LoginManager, login_required, current_user
import sys

# Emoji in startup prints crash Windows when output is redirected (cp1252); never let logging kill the app
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except Exception:
        pass
import logging
import uuid
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
from utils import device_registry
from markupsafe import escape
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

@app.route('/')
@login_required
def index():
    # The old scan page used the retired Fernet QR; the signed flow starts at /qr-scanner.
    return redirect(url_for('qr_scanner'))

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
    """Score browser/device audio with the shared heart engine (same result as the Pi).

    JSON: {"audio": base64 float32 PCM, "sample_rate": int (default 2000)}
    """
    data = request.get_json(silent=True) or {}
    if not data.get('audio'):
        return jsonify({'error': 'No audio data provided'}), 400
    from routes.realtime import process_audio_chunk
    status, body = process_audio_chunk(data['audio'], data.get('sample_rate', 2000))
    return jsonify(body), status


# --- Web Portal 2.0 Routes ---

@app.route('/qr-scanner')
@login_required  # patient data: never public
def qr_scanner():
    """Camera-based QR scanner page"""
    return render_template('qr_scanner.html')


@app.route('/api/scan_qr_image', methods=['POST'])
@login_required  # patient data: never public
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
@login_required  # patient data: never public
def scan_qr():
    """Show a QR result only if a registered device signed it (P0.7). No unsigned fallback."""
    payload = request.args.get('p') or request.args.get('payload')
    if not payload:
        return redirect(url_for('qr_scanner'))
    try:
        res = device_registry.verify_qr(payload)
    except device_registry.InvalidToken as e:
        logger.warning(f"Rejected QR: {e}")
        return (f"<h2>QR result rejected</h2><p>{escape(str(e))}</p>"
                f"<p><a href='{url_for('qr_scanner')}'>Scan again</a></p>"), 400
    d = device_registry.describe(res)
    explanation, recommendation = device_registry.advice(d)
    view = {
        'diagnosis': d['diagnosis'], 'status': d['status'], 'organ': 'Heart',
        'score': d['score'], 'risk_score': d['risk_score'], 'timestamp': d['recorded_at'],
        'device_id': d['device_id'], 'findings': [],
        'ai_explanation': explanation, 'recommendation': recommendation,
        'advanced_metrics': device_registry.facts(d),
        'ai_advice': device_registry.CAVEATS,
    }
    return render_template('public_scan.html', diagnosis=view, payload=device_registry.extract_token(payload))


@app.route('/save-from-qr', methods=['POST'])
@login_required  # patient data: never public
def save_from_qr():
    """Save patient info (form) + the signed device result (QR). Pi -> QR -> portal -> save.

    The token is verified again here; the diagnosis id is QR-<device>-<counter>, so the same
    QR can be saved only once.
    """
    from flask import flash
    from sqlalchemy.exc import IntegrityError

    payload = request.form.get('payload', '')
    name = request.form.get('name', '').strip()
    age = request.form.get('age', 0)
    gender = request.form.get('gender', '')
    contact = request.form.get('contact', '').strip()

    if not name or not age or not gender:
        flash('Name, Age, and Gender are required!', 'error')
        return redirect(request.referrer or url_for('dashboard'))

    try:
        res = device_registry.verify_qr(payload)
    except device_registry.InvalidToken as e:
        logger.warning(f"Rejected QR save: {e}")
        flash(f'QR result rejected: {e}', 'error')
        return redirect(url_for('dashboard'))
    d = device_registry.describe(res)
    if d['status'] == 'NO RESULT':
        flash('This QR has no result to save. Record again on the device.', 'error')
        return redirect(url_for('dashboard'))
    existing = Diagnosis.query.filter_by(diagnosis_id=d['diagnosis_id']).first()
    if existing:
        flash('This result was already saved.', 'info')
        return redirect(url_for('patient_detail', id=existing.patient_id))

    try:
        patient = Patient.query.filter_by(name=name, contact=contact).first()
        if not patient:
            patient = Patient(name=name, age=int(age), gender=gender, contact=contact)
            db.session.add(patient)
            db.session.flush()
        _, recommendation = device_registry.advice(d)
        db.session.add(Diagnosis(
            diagnosis_id=d['diagnosis_id'], patient_id=patient.id,
            timestamp=datetime.strptime(d['recorded_at'], '%Y-%m-%d %H:%M:%S'),
            device_id=d['device_id'], diagnosis_result=d['diagnosis'],
            confidence=None,  # the model score is not a calibrated confidence
            risk_score=d['risk_score'], recommendation=recommendation,
            path_used=d['model'], rms_value=None, organ_mode='Heart'))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash('This result was already saved.', 'info')
        return redirect(url_for('dashboard'))
    except (ValueError, TypeError) as e:
        db.session.rollback()
        flash(f'Error: {e}', 'error')
        return redirect(url_for('dashboard'))

    flash(f'Record saved for {name}.', 'success')
    return redirect(url_for('patient_detail', id=patient.id))


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

    # Localhost by default. For phones on the LAN set HOST=0.0.0.0; the debugger is then
    # always off (it allows code execution), see config.run_options.
    from config import run_options
    host, port, debug = run_options(os.environ)
    app.run(debug=debug, host=host, port=port)
