"""
IshtirafAI - Reports & Analytics Routes
========================================
Weekly automated reports, doctor performance, advanced analytics.
"""

from flask import Blueprint, render_template, request, jsonify, Response
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from models.user import db, User
from models.medical import Patient, Diagnosis
from utils.decorators import role_required
from sqlalchemy import func
import json

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


# ═══════════════════════════════════════════════════════════════════════════════
# WEEKLY REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

@reports_bp.route('/weekly')
@login_required
@role_required(['admin', 'doctor'])
def weekly_report():
    """Generate weekly statistics report."""
    
    # Date range (last 7 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    # Get diagnoses in range
    diagnoses = Diagnosis.query.filter(
        Diagnosis.timestamp >= start_date,
        Diagnosis.timestamp <= end_date
    ).all()
    
    # Calculate statistics
    total_scans = len(diagnoses)
    normal_count = sum(1 for d in diagnoses if 'normal' in (d.diagnosis_result or '').lower())
    abnormal_count = total_scans - normal_count
    critical_count = sum(1 for d in diagnoses if (d.risk_score or 0) >= 7)
    
    avg_confidence = sum((d.confidence or 0) for d in diagnoses) / total_scans if total_scans else 0
    avg_risk = sum((d.risk_score or 0) for d in diagnoses) / total_scans if total_scans else 0
    
    # Daily breakdown
    daily_stats = {}
    for d in diagnoses:
        if d.timestamp:
            day = d.timestamp.strftime('%Y-%m-%d')
            if day not in daily_stats:
                daily_stats[day] = {'total': 0, 'normal': 0, 'abnormal': 0}
            daily_stats[day]['total'] += 1
            if 'normal' in (d.diagnosis_result or '').lower():
                daily_stats[day]['normal'] += 1
            else:
                daily_stats[day]['abnormal'] += 1
    
    # Get new patients this week
    new_patients = Patient.query.filter(
        Patient.created_at >= start_date
    ).count()
    
    # Top diagnoses
    diagnosis_counts = {}
    for d in diagnoses:
        result = d.diagnosis_result or 'Unknown'
        diagnosis_counts[result] = diagnosis_counts.get(result, 0) + 1
    top_diagnoses = sorted(diagnosis_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    report_data = {
        'period': {
            'start': start_date.strftime('%Y-%m-%d'),
            'end': end_date.strftime('%Y-%m-%d')
        },
        'summary': {
            'total_scans': total_scans,
            'normal_count': normal_count,
            'abnormal_count': abnormal_count,
            'critical_count': critical_count,
            'new_patients': new_patients,
            'avg_confidence': round(avg_confidence * 100, 1),
            'avg_risk_score': round(avg_risk, 1)
        },
        'daily_breakdown': daily_stats,
        'top_diagnoses': top_diagnoses,
        'generated_at': datetime.utcnow().isoformat()
    }
    
    return render_template('reports/weekly.html', report=report_data)


@reports_bp.route('/api/weekly')
@login_required
def api_weekly_report():
    """API endpoint for weekly report data."""
    # Use same logic as above but return JSON
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    diagnoses = Diagnosis.query.filter(
        Diagnosis.timestamp >= start_date,
        Diagnosis.timestamp <= end_date
    ).all()
    
    total_scans = len(diagnoses)
    normal_count = sum(1 for d in diagnoses if 'normal' in (d.diagnosis_result or '').lower())
    
    return jsonify({
        'period': {'start': start_date.isoformat(), 'end': end_date.isoformat()},
        'total_scans': total_scans,
        'normal_count': normal_count,
        'abnormal_count': total_scans - normal_count
    })


# ═══════════════════════════════════════════════════════════════════════════════
# DOCTOR PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════════

@reports_bp.route('/doctor-performance')
@login_required
@role_required('admin')
def doctor_performance():
    """View performance metrics for all doctors."""
    
    # Get all doctors
    doctors = User.query.filter_by(role='doctor', is_active=True).all()
    
    performance_data = []
    for doctor in doctors:
        # In a real system, diagnoses would be linked to doctors
        # For now, we'll show placeholder data
        performance_data.append({
            'id': doctor.id,
            'name': doctor.name,
            'email': doctor.email,
            'total_diagnoses': 0,  # Would query from db
            'accuracy': 0,  # Would calculate from confirmed diagnoses
            'avg_response_time': 'N/A'
        })
    
    return render_template('reports/doctor_performance.html', doctors=performance_data)


# ═══════════════════════════════════════════════════════════════════════════════
# FHIR EXPORT ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

@reports_bp.route('/export/fhir/<int:patient_id>')
@login_required
def export_fhir(patient_id):
    """Export patient data in HL7 FHIR R4 format."""
    from utils.fhir_export import export_to_fhir_json
    
    patient = Patient.query.get_or_404(patient_id)
    fhir_json = export_to_fhir_json(patient)
    
    return Response(
        fhir_json,
        mimetype='application/fhir+json',
        headers={
            'Content-Disposition': f'attachment; filename=patient_{patient_id}_fhir.json'
        }
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

@reports_bp.route('/advanced')
@login_required
@role_required(['admin', 'doctor'])
def advanced_analytics():
    """Advanced analytics dashboard."""
    
    # Get all diagnoses
    diagnoses = Diagnosis.query.order_by(Diagnosis.timestamp.desc()).all()
    patients = Patient.query.all()
    
    # Calculate metrics
    total_diagnoses = len(diagnoses)
    total_patients = len(patients)
    
    # Organ distribution
    heart_count = sum(1 for d in diagnoses if d.organ_mode == 'Heart')
    lung_count = sum(1 for d in diagnoses if d.organ_mode == 'Lung')
    
    # Risk distribution
    low_risk = sum(1 for d in diagnoses if (d.risk_score or 0) < 4)
    medium_risk = sum(1 for d in diagnoses if 4 <= (d.risk_score or 0) < 7)
    high_risk = sum(1 for d in diagnoses if (d.risk_score or 0) >= 7)
    
    # Monthly trend (last 6 months)
    monthly_data = {}
    for d in diagnoses:
        if d.timestamp:
            month = d.timestamp.strftime('%Y-%m')
            monthly_data[month] = monthly_data.get(month, 0) + 1
    
    analytics = {
        'totals': {
            'diagnoses': total_diagnoses,
            'patients': total_patients
        },
        'organ_distribution': {
            'heart': heart_count,
            'lung': lung_count,
            'other': total_diagnoses - heart_count - lung_count
        },
        'risk_distribution': {
            'low': low_risk,
            'medium': medium_risk,
            'high': high_risk
        },
        'monthly_trend': monthly_data
    }
    
    return render_template('reports/advanced.html', analytics=analytics)
