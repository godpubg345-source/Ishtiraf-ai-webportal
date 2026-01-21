"""
IshtirafAI - Role-Based Access Control (RBAC)
==============================================
HIPAA-compliant permission system with role hierarchy.
"""

from functools import wraps
from flask import abort, jsonify, request
from flask_login import current_user

# Role Hierarchy: admin > doctor > nurse > technician
ROLE_HIERARCHY = {
    'admin': 100,
    'doctor': 80,
    'nurse': 60,
    'technician': 40,
    'viewer': 20
}

# Permission Matrix
PERMISSIONS = {
    'admin': ['*'],  # All permissions
    'doctor': [
        'view_patient', 'create_patient', 'edit_patient',
        'view_diagnosis', 'create_diagnosis', 
        'export_data', 'view_analytics'
    ],
    'nurse': [
        'view_patient', 'create_patient',
        'view_diagnosis'
    ],
    'technician': [
        'create_diagnosis', 'view_diagnosis'
    ],
    'viewer': [
        'view_patient', 'view_diagnosis'
    ]
}


def has_permission(user_role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    if not user_role:
        return False
    
    role_perms = PERMISSIONS.get(user_role.lower(), [])
    
    # Admin has wildcard access
    if '*' in role_perms:
        return True
    
    return permission in role_perms


def has_role_level(user_role: str, required_role: str) -> bool:
    """Check if user role is at or above required level."""
    user_level = ROLE_HIERARCHY.get(user_role.lower(), 0)
    required_level = ROLE_HIERARCHY.get(required_role.lower(), 100)
    return user_level >= required_level


def require_permission(permission: str):
    """
    Decorator to require a specific permission.
    
    Usage:
        @app.route('/api/patients')
        @login_required
        @require_permission('view_patient')
        def list_patients():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            
            if not has_permission(current_user.role, permission):
                # Log unauthorized access attempt
                print(f"⛔ ACCESS DENIED: User {current_user.email} tried to access {permission}")
                
                if request.is_json:
                    return jsonify({
                        'error': 'Access denied',
                        'message': f'Permission "{permission}" required',
                        'your_role': current_user.role
                    }), 403
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_role(role: str):
    """
    Decorator to require minimum role level.
    
    Usage:
        @app.route('/admin/settings')
        @login_required
        @require_role('admin')
        def admin_settings():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            
            if not has_role_level(current_user.role, role):
                if request.is_json:
                    return jsonify({
                        'error': 'Insufficient privileges',
                        'required_role': role,
                        'your_role': current_user.role
                    }), 403
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_same_org(f):
    """
    Decorator to ensure user can only access their organization's data.
    For multi-tenancy support.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        
        # If accessing a specific resource, check org_id matches
        resource_org_id = kwargs.get('org_id')
        if resource_org_id and resource_org_id != current_user.org_id:
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


# Context processor to make permissions available in templates
def rbac_context_processor():
    """Add RBAC helpers to Jinja2 templates."""
    def can(permission):
        if not current_user.is_authenticated:
            return False
        return has_permission(current_user.role, permission)
    
    def is_role(role):
        if not current_user.is_authenticated:
            return False
        return current_user.role.lower() == role.lower()
    
    def min_role(role):
        if not current_user.is_authenticated:
            return False
        return has_role_level(current_user.role, role)
    
    return {
        'can': can,
        'is_role': is_role,
        'min_role': min_role,
        'PERMISSIONS': PERMISSIONS,
        'ROLE_HIERARCHY': ROLE_HIERARCHY
    }
