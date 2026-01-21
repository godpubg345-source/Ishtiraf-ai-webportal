"""
Real-time Audio Analysis via WebSocket
"""
from flask import Blueprint, render_template
from flask_login import login_required
import base64
import numpy as np
from scipy import signal

realtime_bp = Blueprint('realtime', __name__, url_prefix='/realtime')


@realtime_bp.route('/analyzer')
@login_required
def analyzer():
    """Browser-based real-time audio analyzer"""
    return render_template('realtime/analyzer.html')


def process_audio_chunk(audio_base64, sample_rate=2000):
    """
    Process audio chunk received from browser.
    Returns analysis results.
    """
    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_base64)
        audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Determine Organ (Simple Logic for now, can be expanded)
        # Defaulting to Heart for Web Portal demo unless specified
        # In a full version, we'd pass 'mode' from frontend
        
        from utils.inference import analyze_heart, analyze_lung
        
        # Run Analysis (Defaulting to Heart for now)
        # TODO: Get 'mode' from request
        result = analyze_heart(audio_data, sr=sample_rate)
        
        if "error" in result:
             # Fallback to lung if heart fails or just return error
             pass

        return {
            'status': 'analyzed',
            'data': result
        }
    except Exception as e:
        return {'error': str(e)}
