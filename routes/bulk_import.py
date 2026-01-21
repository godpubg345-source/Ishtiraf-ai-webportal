"""
IshtirafAI - Bulk Import API Routes
====================================
Import patients from CSV/Excel files.
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import pandas as pd
import io

bulk_bp = Blueprint('bulk', __name__, url_prefix='/api/bulk')


@bulk_bp.route('/import/patients', methods=['POST'])
@login_required
def bulk_import_patients():
    """
    Bulk import patients from CSV file.
    
    Required columns: name, age, gender
    Optional columns: contact, medical_history
    
    Returns:
        {
            "imported": 50,
            "failed": 2,
            "errors": [{"row": 3, "error": "Invalid age"}]
        }
    """
    from utils.rbac import require_permission
    from utils.audit import log_audit
    from models.medical import Patient, db
    
    # Check permission
    if current_user.role not in ['admin', 'doctor']:
        return jsonify({'error': 'Permission denied'}), 403
    
    # Get uploaded file
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400
    
    # Check file type
    allowed_extensions = {'csv', 'xlsx', 'xls'}
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in allowed_extensions:
        return jsonify({'error': f'Invalid file type. Allowed: {allowed_extensions}'}), 400
    
    try:
        # Read file
        if ext == 'csv':
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        
        # Validate required columns
        required_columns = ['name', 'age', 'gender']
        missing = [c for c in required_columns if c.lower() not in [col.lower() for col in df.columns]]
        if missing:
            return jsonify({
                'error': f'Missing required columns: {missing}',
                'found_columns': list(df.columns)
            }), 400
        
        # Normalize column names
        df.columns = [c.lower().strip() for c in df.columns]
        
        # Process rows
        imported = 0
        failed = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                # Validate data
                name = str(row.get('name', '')).strip()
                if not name or len(name) < 2:
                    raise ValueError("Name too short")
                
                age = int(row.get('age', 0))
                if age < 0 or age > 150:
                    raise ValueError(f"Invalid age: {age}")
                
                gender = str(row.get('gender', '')).strip().upper()
                if gender not in ['M', 'F', 'MALE', 'FEMALE', 'OTHER']:
                    gender = 'OTHER'
                else:
                    gender = 'M' if gender in ['M', 'MALE'] else 'F' if gender in ['F', 'FEMALE'] else 'O'
                
                # Create patient
                patient = Patient(
                    name=name,
                    age=age,
                    gender=gender,
                    contact=str(row.get('contact', ''))[:50] if 'contact' in row else None,
                    # org_id=current_user.org_id,  # For multi-tenancy
                    # created_by=current_user.id
                )
                
                db.session.add(patient)
                imported += 1
                
            except Exception as e:
                failed += 1
                errors.append({
                    'row': idx + 2,  # +2 for header and 0-index
                    'name': str(row.get('name', 'Unknown'))[:50],
                    'error': str(e)
                })
        
        # Commit all successful imports
        db.session.commit()
        
        # Log audit
        log_audit(
            action='BULK_IMPORT_PATIENTS',
            resource_type='patient',
            extra_data={'imported': imported, 'failed': failed}
        )
        
        return jsonify({
            'success': True,
            'imported': imported,
            'failed': failed,
            'errors': errors[:20]  # Limit error details
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@bulk_bp.route('/export/patients', methods=['GET'])
@login_required
def export_patients():
    """Export all patients to CSV."""
    from models.medical import Patient
    from utils.encryption import PIIEncryption
    
    if current_user.role not in ['admin', 'doctor']:
        return jsonify({'error': 'Permission denied'}), 403
    
    patients = Patient.query.all()
    
    data = []
    for p in patients:
        data.append({
            'id': p.id,
            'name': p.name,
            'age': p.age,
            'gender': p.gender,
            'contact': PIIEncryption.mask_pii(p.contact or '', 4) if p.contact else '',
            'created_at': str(p.created_at) if hasattr(p, 'created_at') else ''
        })
    
    df = pd.DataFrame(data)
    
    # Convert to CSV
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=patients_export.csv'}
    )


@bulk_bp.route('/template/patients', methods=['GET'])
def download_template():
    """Download CSV template for patient import."""
    template = """name,age,gender,contact
John Doe,45,M,+1234567890
Jane Smith,32,F,+0987654321
Ahmed Hassan,28,M,
"""
    from flask import Response
    return Response(
        template,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=patient_import_template.csv'}
    )
