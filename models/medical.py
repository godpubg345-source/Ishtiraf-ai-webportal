from models.user import db
from datetime import datetime

class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    contact = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    diagnoses = db.relationship('Diagnosis', backref='patient', lazy=True)

class Diagnosis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    diagnosis_id = db.Column(db.String(50), unique=True, nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    device_id = db.Column(db.String(50))
    
    # Clinical Data
    diagnosis_result = db.Column(db.String(50))
    confidence = db.Column(db.Float)
    risk_score = db.Column(db.Float)
    recommendation = db.Column(db.Text)
    path_used = db.Column(db.String(50))
    rms_value = db.Column(db.Float)
    
    # Symptoms
    sym_chest_pain = db.Column(db.Boolean, default=False)
    sym_shortness = db.Column(db.Boolean, default=False)
    sym_history = db.Column(db.Boolean, default=False)
    
    patient_mode = db.Column(db.String(20))
    organ_mode = db.Column(db.String(20))
