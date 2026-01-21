"""
Settings & Profile Management Routes
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.user import User, db
import bcrypt

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """View and update profile"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        
        if not name:
            flash('Name cannot be empty', 'error')
            return redirect(url_for('settings.profile'))
        
        if not email or '@' not in email:
            flash('Invalid email address', 'error')
            return redirect(url_for('settings.profile'))
        
        # Check if email is taken by another user
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != current_user.id:
            flash('Email is already in use', 'error')
            return redirect(url_for('settings.profile'))
        
        # Update user
        current_user.name = name
        current_user.email = email
        db.session.commit()
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('settings.profile'))
    
    return render_template('settings/profile.html', user=current_user)


@settings_bp.route('/security', methods=['GET', 'POST'])
@login_required
def security():
    """Change password"""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Verify current password
        if not current_user.check_password(current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('settings.security'))
        
        # Validate new password
        if len(new_password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('settings.security'))
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('settings.security'))
        
        # Update password
        current_user.set_password(new_password)
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('settings.security'))
    
    return render_template('settings/security.html', user=current_user)


@settings_bp.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    """Setup Two-Factor Authentication"""
    import pyotp
    import qrcode
    import io
    import base64
    
    if request.method == 'POST':
        # Verify the code
        totp_code = request.form.get('totp_code', '').strip()
        
        if not current_user.otp_secret:
            flash('2FA not initialized. Please refresh and try again.', 'error')
            return redirect(url_for('settings.setup_2fa'))
        
        totp = pyotp.TOTP(current_user.otp_secret)
        
        if totp.verify(totp_code):
            current_user.is_2fa_enabled = True
            db.session.commit()
            flash('✅ Two-Factor Authentication enabled successfully!', 'success')
            return redirect(url_for('settings.security'))
        else:
            flash('Invalid verification code. Please try again.', 'error')
            return redirect(url_for('settings.setup_2fa'))
    
    # Generate new secret if not exists
    if not current_user.otp_secret:
        current_user.otp_secret = pyotp.random_base32()
        db.session.commit()
    
    # Generate QR code
    totp = pyotp.TOTP(current_user.otp_secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email,
        issuer_name='IshtirafAI'
    )
    
    # Create QR image
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    qr_img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return render_template('settings/setup_2fa.html', 
                         qr_code=qr_base64,
                         secret=current_user.otp_secret)


@settings_bp.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Disable Two-Factor Authentication"""
    password = request.form.get('password', '')
    
    if not current_user.check_password(password):
        flash('Invalid password', 'error')
        return redirect(url_for('settings.security'))
    
    current_user.is_2fa_enabled = False
    current_user.otp_secret = None
    db.session.commit()
    
    flash('Two-Factor Authentication has been disabled.', 'success')
    return redirect(url_for('settings.security'))

