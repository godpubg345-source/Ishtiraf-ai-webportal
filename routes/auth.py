from flask import Blueprint, render_template, redirect, url_for, request, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models.user import User, db
import pyotp
import secrets
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

# Store reset tokens (in production, store in database)
reset_tokens = {}

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            # Check if user is active
            if not user.is_active:
                flash('Your account has been deactivated. Contact admin.', 'error')
                return render_template('auth/login.html')
            
            # 2FA Step (Simplified for now - direct login)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
            
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('auth.register'))
        
        # --- CRITICAL LOGIC FIX: First User = Super Admin ---
        user_count = User.query.count()
        
        if user_count == 0:
            role = 'admin'
            flash('🎉 Welcome! You are the first user, so you are the SUPER ADMIN.', 'success')
        else:
            role = 'doctor'
            
        new_user = User(email=email, name=name, role=role)
        new_user.set_password(password)
        new_user.otp_secret = pyotp.random_base32()
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('dashboard'))
        
    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset"""
    from flask import current_app
    from flask_mail import Message
    
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate reset token
            token = secrets.token_urlsafe(32)
            reset_tokens[token] = {
                'user_id': user.id,
                'expires': datetime.now() + timedelta(hours=1)
            }
            
            # Build reset URL
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # Try to send email
            try:
                if current_app.config.get('MAIL_USERNAME'):
                    msg = Message(
                        subject='IshtirafAI - Password Reset',
                        sender=current_app.config.get('MAIL_USERNAME'),
                        recipients=[user.email]
                    )
                    msg.html = f'''
                    <div style="font-family: Arial; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #1f6aa5;">IshtirafAI Password Reset</h2>
                        <p>Hello <strong>{user.name}</strong>,</p>
                        <p>You requested a password reset. Click the button below to set a new password:</p>
                        <p style="margin: 30px 0;">
                            <a href="{reset_url}" style="background: #1f6aa5; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Reset Password
                            </a>
                        </p>
                        <p style="color: #888; font-size: 12px;">This link expires in 1 hour.</p>
                        <p style="color: #888; font-size: 12px;">If you didn't request this, ignore this email.</p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                        <p style="color: #888; font-size: 12px;">IshtirafAI Medical Diagnostic System</p>
                    </div>
                    '''
                    current_app.mail.send(msg)
                    flash('Password reset link sent to your email!', 'success')
                else:
                    # Demo mode - no email configured
                    flash(f'Demo Mode: Reset link generated. Click below or check URL.', 'success')
                    return redirect(url_for('auth.reset_password', token=token))
            except Exception as e:
                print(f"Email send error: {e}")
                # Fallback to showing token
                flash(f'Email failed. Use this link: {reset_url[:50]}...', 'warning')
                return redirect(url_for('auth.reset_password', token=token))
        else:
            # Don't reveal if email exists
            flash('If an account exists, a reset link has been sent.', 'success')
    
    
    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    # Validate token
    token_data = reset_tokens.get(token)
    if not token_data:
        flash('Invalid or expired reset link', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if datetime.now() > token_data['expires']:
        del reset_tokens[token]
        flash('Reset link has expired', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    user = User.query.get(token_data['user_id'])
    if not user:
        flash('User not found', 'error')
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return render_template('auth/reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('auth/reset_password.html', token=token)
        
        # Update password
        user.set_password(new_password)
        db.session.commit()
        
        # Remove used token
        del reset_tokens[token]
        
        flash('Password reset successful! You can now login.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)

