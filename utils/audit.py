"""
IshtirafAI - Audit Logging System
==================================
HIPAA-compliant audit trail for all sensitive operations.
"""

from datetime import datetime
from flask import request
from flask_login import current_user
from functools import wraps
import json


class AuditLog:
    """Audit log entry model."""
    
    def __init__(self, db):
        self.db = db
        self._create_table()
    
    def _create_table(self):
        """Create audit_logs table if not exists."""
        from sqlalchemy import text
        try:
            self.db.session.execute(text('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_email VARCHAR(255),
                    action VARCHAR(100) NOT NULL,
                    resource_type VARCHAR(50),
                    resource_id INTEGER,
                    ip_address VARCHAR(45),
                    user_agent TEXT,
                    request_method VARCHAR(10),
                    request_path TEXT,
                    request_data TEXT,
                    response_status INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            '''))
            self.db.session.commit()
        except Exception as e:
            print(f"Audit table exists or error: {e}")


# Global audit logger instance
_audit_logger = None


def init_audit_logging(app, db):
    """Initialize audit logging for the Flask app."""
    global _audit_logger
    
    with app.app_context():
        _audit_logger = AuditLog(db)
    
    # Register after_request handler for automatic logging
    @app.after_request
    def log_response_status(response):
        # Only log API requests and sensitive actions
        if request.path.startswith('/api/') or request.path.startswith('/admin/'):
            log_audit(
                action=f"{request.method}_{request.endpoint or 'unknown'}",
                response_status=response.status_code
            )
        return response
    
    print("✅ Audit Logging Initialized")
    return _audit_logger


def log_audit(action: str, resource_type: str = None, resource_id: int = None, 
              extra_data: dict = None, response_status: int = None):
    """
    Log an audit event.
    
    Args:
        action: Action performed (e.g., 'VIEW_PATIENT', 'CREATE_DIAGNOSIS')
        resource_type: Type of resource accessed ('patient', 'diagnosis')
        resource_id: ID of the specific resource
        extra_data: Additional data to log
        response_status: HTTP response status code
    """
    global _audit_logger
    
    if _audit_logger is None:
        return
    
    try:
        from models.user import db
        from sqlalchemy import text
        
        user_id = current_user.id if current_user.is_authenticated else None
        user_email = current_user.email if current_user.is_authenticated else 'anonymous'
        
        # Sanitize request data (remove sensitive fields)
        request_data = None
        if request.is_json:
            data = request.get_json(silent=True) or {}
            # Remove sensitive fields
            sanitized = {k: v for k, v in data.items() 
                        if k.lower() not in ('password', 'password_hash', 'token', 'secret')}
            if sanitized:
                request_data = json.dumps(sanitized)[:1000]  # Limit size
        
        # Insert audit log
        db.session.execute(text('''
            INSERT INTO audit_logs 
            (user_id, user_email, action, resource_type, resource_id, 
             ip_address, user_agent, request_method, request_path, 
             request_data, response_status, created_at)
            VALUES 
            (:user_id, :user_email, :action, :resource_type, :resource_id,
             :ip_address, :user_agent, :request_method, :request_path,
             :request_data, :response_status, :created_at)
        '''), {
            'user_id': user_id,
            'user_email': user_email,
            'action': action,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'ip_address': request.remote_addr,
            'user_agent': str(request.user_agent)[:500],
            'request_method': request.method,
            'request_path': request.path[:500],
            'request_data': request_data,
            'response_status': response_status,
            'created_at': datetime.utcnow()
        })
        db.session.commit()
        
    except Exception as e:
        print(f"Audit log error: {e}")


def audit_action(action: str, resource_type: str = None):
    """
    Decorator to automatically log an action.
    
    Usage:
        @app.route('/api/patients/<int:id>')
        @login_required
        @audit_action('VIEW_PATIENT', 'patient')
        def get_patient(id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get resource_id from kwargs if available
            resource_id = kwargs.get('id') or kwargs.get('patient_id') or kwargs.get('diagnosis_id')
            
            # Execute the function
            result = f(*args, **kwargs)
            
            # Log the action
            log_audit(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id
            )
            
            return result
        return decorated_function
    return decorator


def get_audit_logs(user_id: int = None, resource_type: str = None, 
                   limit: int = 100, offset: int = 0):
    """Retrieve audit logs with optional filtering."""
    from models.user import db
    from sqlalchemy import text
    
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = {}
    
    if user_id:
        query += " AND user_id = :user_id"
        params['user_id'] = user_id
    
    if resource_type:
        query += " AND resource_type = :resource_type"
        params['resource_type'] = resource_type
    
    query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params['limit'] = limit
    params['offset'] = offset
    
    result = db.session.execute(text(query), params)
    return result.fetchall()
