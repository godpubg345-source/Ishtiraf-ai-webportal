from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from utils.decorators import role_required
from models.user import User, db

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/dashboard')
@login_required
@role_required(['admin'])
def dashboard():
    users = User.query.all()
    # Calculate Stats
    total_users = len(users)
    doctors = len([u for u in users if u.role == 'doctor'])
    patients = len([u for u in users if u.role == 'patient'])
    admins = len([u for u in users if u.role == 'admin'])
    active_users = len([u for u in users if u.is_active])
    
    return render_template('admin/dashboard.html', 
                         users=users,
                         total_users=total_users,
                         doctors=doctors,
                         patients=patients,
                         admins=admins,
                         active_users=active_users)

@admin_bp.route('/update_role/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def update_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    
    # Prevent demoting yourself if you're the only admin
    if user.id == current_user.id and new_role != 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count == 1:
            flash("Cannot demote yourself! You are the only admin.", "error")
            return redirect(url_for('admin.dashboard'))
    
    if new_role in ['admin', 'doctor', 'patient', 'staff']:
        old_role = user.role
        user.role = new_role
        db.session.commit()
        flash(f"✅ User {user.name} role changed: {old_role} → {new_role}", "success")
    else:
        flash("Invalid role selected", "error")
        
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/promote/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def promote(user_id):
    """Promote a Doctor to Admin"""
    user = User.query.get_or_404(user_id)
    
    if user.role == 'admin':
        flash(f"{user.name} is already an Admin!", "error")
    else:
        user.role = 'admin'
        db.session.commit()
        flash(f"🚀 {user.name} promoted to Admin!", "success")
    
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/demote/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def demote(user_id):
    """Demote an Admin to Doctor"""
    user = User.query.get_or_404(user_id)
    
    # Prevent demoting yourself if you're the only admin
    if user.id == current_user.id:
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count == 1:
            flash("Cannot demote yourself! You are the only admin.", "error")
            return redirect(url_for('admin.dashboard'))
    
    if user.role != 'admin':
        flash(f"{user.name} is not an Admin!", "error")
    else:
        user.role = 'doctor'
        db.session.commit()
        flash(f"⬇️ {user.name} demoted to Doctor", "success")
    
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/toggle_status/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def toggle_status(user_id):
    """Activate/Deactivate a user (Ban/Unban)"""
    user = User.query.get_or_404(user_id)
    
    # Prevent deactivating yourself
    if user.id == current_user.id:
        flash("You cannot deactivate yourself!", "error")
        return redirect(url_for('admin.dashboard'))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = "🟢 Activated" if user.is_active else "🔴 Deactivated"
    flash(f"{status}: {user.name}", "success")
    
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash("You cannot delete yourself!", "error")
        return redirect(url_for('admin.dashboard'))
        
    user_name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f"🗑️ User {user_name} deleted permanently", "success")
    
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/create_user', methods=['GET', 'POST'])
@login_required
@role_required(['admin'])
def create_user():
    """Admin: Create a new user"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'doctor')
        
        # Validation
        if not name or not email or not password:
            flash('All fields are required', 'error')
            return redirect(url_for('admin.create_user'))
        
        if '@' not in email:
            flash('Invalid email address', 'error')
            return redirect(url_for('admin.create_user'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('admin.create_user'))
        
        # Check if email exists
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('admin.create_user'))
        
        # Validate role
        if role not in ['admin', 'doctor', 'patient', 'staff']:
            role = 'doctor'
        
        # Create user
        new_user = User(email=email, name=name, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        flash(f"✅ User '{name}' created successfully as {role.capitalize()}", 'success')
        return redirect(url_for('admin.dashboard'))
    
    return render_template('admin/create_user.html')


# ══════════════════════════════════════════════════════════════════════════════
# ENTERPRISE FEATURES - BULK IMPORT & AUDIT LOGS
# ══════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/bulk-import')
@login_required
@role_required(['admin', 'doctor'])
def bulk_import_page():
    """Show bulk import UI"""
    return render_template('admin/bulk_import.html')


@admin_bp.route('/audit-logs')
@login_required
@role_required(['admin'])
def audit_logs():
    """View audit logs - HIPAA compliance"""
    from sqlalchemy import text
    
    # Get filter params
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('user_id', '')
    
    # Build query
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = {}
    
    if action_filter:
        query += " AND action LIKE :action"
        params['action'] = f"%{action_filter}%"
    
    if user_filter:
        query += " AND user_id = :user_id"
        params['user_id'] = int(user_filter)
    
    query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params['limit'] = limit
    params['offset'] = (page - 1) * limit
    
    try:
        result = db.session.execute(text(query), params)
        logs = result.fetchall()
    except Exception as e:
        print(f"Audit log query error: {e}")
        logs = []
    
    users = User.query.all()
    
    return render_template('admin/audit_logs.html', logs=logs, users=users)


@admin_bp.route('/audit-logs/export')
@login_required
@role_required(['admin'])
def export_audit_logs():
    """Export audit logs to CSV"""
    from sqlalchemy import text
    import io
    from flask import Response
    
    try:
        result = db.session.execute(text("SELECT * FROM audit_logs ORDER BY created_at DESC"))
        logs = result.fetchall()
        
        # Create CSV
        output = io.StringIO()
        output.write("timestamp,user_email,action,resource_type,resource_id,ip_address,status\n")
        
        for log in logs:
            output.write(f"{log.created_at},{log.user_email},{log.action},{log.resource_type or ''},{log.resource_id or ''},{log.ip_address or ''},{log.response_status or ''}\n")
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=audit_logs_export.csv'}
        )
    except Exception as e:
        flash(f"Export failed: {e}", "error")
        return redirect(url_for('admin.audit_logs'))
