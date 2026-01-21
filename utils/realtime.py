"""
IshtirafAI - Real-time WebSocket Module
========================================
Live diagnosis streaming and notifications.
"""

from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import current_user
from functools import wraps

# Global SocketIO instance
socketio = None


def init_socketio(app):
    """Initialize SocketIO with Flask app."""
    global socketio
    
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',  # Use 'eventlet' or 'gevent' in production
        logger=True,
        engineio_logger=True
    )
    
    register_handlers(socketio)
    print("✅ WebSocket Real-time Module Initialized")
    
    return socketio


def register_handlers(sio):
    """Register all WebSocket event handlers."""
    
    @sio.on('connect')
    def handle_connect():
        """Handle new WebSocket connection."""
        if current_user.is_authenticated:
            # Join user-specific room
            join_room(f"user_{current_user.id}")
            
            # Join organization room (for multi-tenancy)
            if hasattr(current_user, 'org_id'):
                join_room(f"org_{current_user.org_id}")
            
            # Join role-based room
            join_room(f"role_{current_user.role}")
            
            emit('connected', {
                'status': 'connected',
                'user_id': current_user.id,
                'role': current_user.role
            })
            
            print(f"🔌 WebSocket: User {current_user.email} connected")
        else:
            return False  # Reject unauthenticated connections
    
    @sio.on('disconnect')
    def handle_disconnect():
        """Handle WebSocket disconnection."""
        if current_user.is_authenticated:
            print(f"🔌 WebSocket: User {current_user.email} disconnected")
    
    @sio.on('subscribe_patient')
    def handle_subscribe_patient(data):
        """Subscribe to real-time updates for a specific patient."""
        patient_id = data.get('patient_id')
        if patient_id and current_user.is_authenticated:
            join_room(f"patient_{patient_id}")
            emit('subscribed', {'patient_id': patient_id})
    
    @sio.on('unsubscribe_patient')
    def handle_unsubscribe_patient(data):
        """Unsubscribe from patient updates."""
        patient_id = data.get('patient_id')
        if patient_id:
            leave_room(f"patient_{patient_id}")


def broadcast_new_diagnosis(diagnosis):
    """
    Broadcast new diagnosis to relevant clients.
    
    Call this after creating a new diagnosis.
    """
    global socketio
    if not socketio:
        return
    
    data = {
        'type': 'new_diagnosis',
        'patient_id': diagnosis.patient_id,
        'patient_name': diagnosis.patient.name if diagnosis.patient else 'Unknown',
        'diagnosis': diagnosis.diagnosis_result,
        'risk_score': diagnosis.risk_score,
        'confidence': diagnosis.confidence,
        'organ': diagnosis.organ_type,
        'timestamp': str(diagnosis.timestamp),
        'is_critical': diagnosis.risk_score >= 7
    }
    
    # Broadcast to patient-specific room
    socketio.emit('diagnosis_update', data, room=f"patient_{diagnosis.patient_id}")
    
    # Broadcast critical alerts to doctors
    if diagnosis.risk_score >= 7:
        socketio.emit('critical_alert', data, room='role_doctor')
        socketio.emit('critical_alert', data, room='role_admin')
    
    # Broadcast to organization
    if hasattr(diagnosis.patient, 'org_id'):
        socketio.emit('diagnosis_update', data, room=f"org_{diagnosis.patient.org_id}")


def broadcast_system_alert(message: str, level: str = 'info'):
    """
    Broadcast system-wide alert.
    
    Args:
        message: Alert message
        level: 'info', 'warning', 'error', 'critical'
    """
    global socketio
    if not socketio:
        return
    
    socketio.emit('system_alert', {
        'message': message,
        'level': level,
        'timestamp': str(__import__('datetime').datetime.utcnow())
    })


def notify_user(user_id: int, event: str, data: dict):
    """Send notification to specific user."""
    global socketio
    if socketio:
        socketio.emit(event, data, room=f"user_{user_id}")


# Client-side JavaScript helper (for templates)
WEBSOCKET_CLIENT_JS = """
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js"></script>
<script>
const socket = io();

socket.on('connect', function() {
    console.log('🔌 Connected to IshtirafAI Real-time');
});

socket.on('diagnosis_update', function(data) {
    console.log('📊 New Diagnosis:', data);
    // Update UI here
    if (window.onNewDiagnosis) {
        window.onNewDiagnosis(data);
    }
});

socket.on('critical_alert', function(data) {
    console.log('⚠️ CRITICAL ALERT:', data);
    // Show alert notification
    if (Notification.permission === 'granted') {
        new Notification('⚠️ Critical Diagnosis', {
            body: `Patient: ${data.patient_name} - Risk: ${data.risk_score}/10`,
            icon: '/static/img/alert-icon.png'
        });
    }
});

socket.on('system_alert', function(data) {
    console.log('📢 System Alert:', data);
});

// Subscribe to patient updates
function subscribeToPatient(patientId) {
    socket.emit('subscribe_patient', { patient_id: patientId });
}
</script>
"""
