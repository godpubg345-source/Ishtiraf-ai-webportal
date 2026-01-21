"""
Analytics Routes - Dashboard with Charts
"""
from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from utils.decorators import role_required
from models.user import User
from models.medical import Patient, Diagnosis
from sqlalchemy import func
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')


@analytics_bp.route('/dashboard')
@login_required
@role_required(['admin'])
def dashboard():
    """Analytics Dashboard with visualizations"""
    # Get basic stats
    total_users = User.query.count()
    total_patients = Patient.query.count()
    total_diagnoses = Diagnosis.query.count()
    
    # Get risk distribution
    diagnoses = Diagnosis.query.all()
    risk_low = len([d for d in diagnoses if d.risk_score <= 3])
    risk_medium = len([d for d in diagnoses if 4 <= d.risk_score <= 6])
    risk_high = len([d for d in diagnoses if d.risk_score >= 7])
    
    return render_template('analytics/dashboard.html',
                         total_users=total_users,
                         total_patients=total_patients,
                         total_diagnoses=total_diagnoses,
                         risk_low=risk_low,
                         risk_medium=risk_medium,
                         risk_high=risk_high)


@analytics_bp.route('/api/stats')
@login_required
@role_required(['admin'])
def api_stats():
    """API endpoint for chart data"""
    # Users by role
    users = User.query.all()
    roles = {}
    for user in users:
        roles[user.role] = roles.get(user.role, 0) + 1
    
    # Diagnoses per day (last 7 days)
    today = datetime.utcnow().date()
    daily_diagnoses = []
    for i in range(7):
        day = today - timedelta(days=i)
        count = Diagnosis.query.filter(
            func.date(Diagnosis.timestamp) == day
        ).count()
        daily_diagnoses.append({
            'date': day.strftime('%Y-%m-%d'),
            'count': count
        })
    daily_diagnoses.reverse()
    
    # Risk distribution
    diagnoses = Diagnosis.query.all()
    risk_dist = {
        'Low (0-3)': len([d for d in diagnoses if d.risk_score <= 3]),
        'Medium (4-6)': len([d for d in diagnoses if 4 <= d.risk_score <= 6]),
        'High (7-10)': len([d for d in diagnoses if d.risk_score >= 7])
    }
    
    return jsonify({
        'users_by_role': roles,
        'daily_diagnoses': daily_diagnoses,
        'risk_distribution': risk_dist
    })
