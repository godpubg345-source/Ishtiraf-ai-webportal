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
    """Decode base64 float32 PCM and score it with the shared heart engine.

    Returns (http_status, body). 400 = bad input, 422 = audio not usable,
    503 = AI model not available, 200 = result.
    """
    from utils.inference import analyze_heart, get_engine
    import binascii
    try:
        sample_rate = int(sample_rate)
    except (TypeError, ValueError):
        return 400, {'error': 'sample_rate must be an integer'}
    if not 1000 <= sample_rate <= 96000:
        return 400, {'error': 'sample_rate must be between 1000 and 96000 Hz'}
    try:
        raw = base64.b64decode(audio_base64, validate=True)
        audio = np.frombuffer(raw, dtype=np.float32)
    except (binascii.Error, ValueError, TypeError):
        return 400, {'error': 'audio must be base64-encoded float32 PCM'}
    if audio.size == 0:
        return 400, {'error': 'empty audio'}
    if not get_engine().available:
        return 503, {'status': 'NO RESULT', 'error': 'AI model not available', 'reason': get_engine().error}
    result = analyze_heart(audio.astype(np.float64), sample_rate)
    if result['status'] == 'NO RESULT':
        return 422, result
    return 200, {'status': 'analyzed', 'data': result}
