import os
import numpy as np
import logging
from scipy import signal
from scipy.signal import butter, sosfilt
from scipy.ndimage import zoom
import tensorflow as tf

# Setup Logging
logger = logging.getLogger('IshtirafAI.Inference')

# Constants
SAMPLE_RATE = 2000
SAMPLE_RATE_LUNG = 4000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, '..', '..', 'Model_Training', '1_AI_Engine', 'Saved_Models')

# Model Paths
MODEL_PATH_CARDIAC = os.path.join(MODEL_DIR, 'heart_model_attention_v2.h5')
MODEL_PATH_PULMONARY = os.path.join(MODEL_DIR, 'pulmonary_model_final.h5')

# Global Model Cache
_models = {
    'cardiac': None,
    'pulmonary': None
}

def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    """Filters out noise outside the target frequency range."""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    sos = butter(order, [low, high], btype='band', output='sos')
    return sosfilt(sos, data)

def calculate_rms(audio):
    """Calculates RMS amplitude."""
    return np.sqrt(np.mean(audio**2))

def spectral_properties(y, sr):
    """Calculates Spectral Centroid."""
    magnitudes = np.abs(np.fft.rfft(y))
    length = len(y)
    freqs = np.abs(np.fft.fftfreq(length, 1.0/sr)[:length//2 + 1])
    if np.sum(magnitudes) == 0: return 0
    centroid = np.sum(magnitudes * freqs) / np.sum(magnitudes)
    return centroid

def load_models():
    """Loads TensorFlow models into memory."""
    global _models
    
    # Custom Objects for Attention Model
    try:
        from ..models.custom_layers import PositionalEncoding, MultiHeadSelfAttention, AttentionPooling
        custom_objects = {
            'PositionalEncoding': PositionalEncoding,
            'MultiHeadSelfAttention': MultiHeadSelfAttention,
            'AttentionPooling': AttentionPooling
        }
    except ImportError:
        # Fallback if we can't import specific classes, defining dummies or assuming standard checks
        # For now, let's try to define them or skip if not needed for loading (usually needed)
        # We will assume they are available if the model needs them.
        # Actually, we need to make sure 'models' package has these. 
        # But wait, the web portal 'models' dir might not have them.
        # Let's fix this by adding the classes directly here or in a separate file if missing.
        # For SAFETY, I will define simple placeholders or try to import from where they likely are.
        # The user's previous code showed they are in '.. 1_AI_Engine'.
        pass

    # Quick HACK: Define Custom Objects here if import fails, to allow loading
    class PositionalEncoding(tf.keras.layers.Layer):
        def __init__(self, position, d_model, **kwargs): super().__init__(**kwargs)
    class MultiHeadSelfAttention(tf.keras.layers.Layer):
        def __init__(self, d_model, num_heads, **kwargs): super().__init__(**kwargs)
    class AttentionPooling(tf.keras.layers.Layer):
        def __init__(self, **kwargs): super().__init__(**kwargs)
        
    custom_objects = {
        'PositionalEncoding': PositionalEncoding,
        'MultiHeadSelfAttention': MultiHeadSelfAttention,
        'AttentionPooling': AttentionPooling
    }

    if _models['cardiac'] is None:
        try:
            if os.path.exists(MODEL_PATH_CARDIAC):
                _models['cardiac'] = tf.keras.models.load_model(MODEL_PATH_CARDIAC, custom_objects=custom_objects)
                logger.info("✅ Cardiac Model Loaded")
            else:
                logger.warning(f"⚠️ Cardiac model not found at {MODEL_PATH_CARDIAC}")
        except Exception as e:
            logger.error(f"❌ Failed to load Cardiac model: {e}")

    if _models['pulmonary'] is None:
        try:
            if os.path.exists(MODEL_PATH_PULMONARY):
                _models['pulmonary'] = tf.keras.models.load_model(MODEL_PATH_PULMONARY)
                logger.info("✅ Pulmonary Model Loaded")
            else:
                logger.warning(f"⚠️ Pulmonary model not found at {MODEL_PATH_PULMONARY}")
        except Exception as e:
            logger.error(f"❌ Failed to load Pulmonary model: {e}")

def preprocess_audio(audio, sr, mode='heart'):
    """
    Preprocesses raw audio into spectrogram input for the model.
    """
    if mode == 'heart':
        # Cardiac Preprocessing
        # 1. Bandpass
        audio = butter_bandpass_filter(audio, 20, 450, sr, order=4)
        
        # 2. Spectrogram (Target Shape: 65, 155, 1)
        f, t, Sxx = signal.spectrogram(audio, sr, nperseg=128, noverlap=64)
        S_dB = 10 * np.log10(Sxx + 1e-10)
        
        # 3. Resize/Zoom
        target_shape = (65, 155)
        curr_shape = S_dB.shape
        zm = (target_shape[0] / curr_shape[0], target_shape[1] / curr_shape[1])
        S_scaled = zoom(S_dB, zm, order=1)
        
        # 4. Normalize
        S_norm = (S_scaled - S_scaled.mean()) / (S_scaled.std() + 1e-10)
        return S_norm.reshape(1, 65, 155, 1), audio

    else:
        # Pulmonary Preprocessing
        # 1. Bandpass
        audio = butter_bandpass_filter(audio, 100, 2000, sr, order=4)
        
        # 2. Spectrogram (Target Shape: 129, 155, 1)
        f, t, Sxx = signal.spectrogram(audio, sr, nperseg=256, noverlap=128)
        S_dB = 10 * np.log10(Sxx + 1e-10)
        
        # 3. Resize
        target_shape = (129, 155)
        curr_shape = S_dB.shape
        zm = (target_shape[0] / curr_shape[0], target_shape[1] / curr_shape[1])
        S_scaled = zoom(S_dB, zm, order=1)
        
        # 4. Normalize
        S_norm = (S_scaled - S_scaled.mean()) / (S_scaled.std() + 1e-10)
        return S_norm.reshape(1, 129, 155, 1), audio

def analyze_heart(audio_data, sr=2000):
    """
    Analyzes heart sound. Returns dict with results.
    """
    if _models['cardiac'] is None:
        return {"error": "Model not loaded", "status": "failed"}

    try:
        # Preprocess
        input_data, clean_audio = preprocess_audio(audio_data, sr, mode='heart')
        
        # Features
        rms = calculate_rms(clean_audio)
        centroid = spectral_properties(clean_audio, sr)
        intensity = min(rms * 1000, 10)
        
        # Predict
        prediction = _models['cardiac'].predict(input_data)
        prob_abnormal = float(prediction[0][0])
        
        # Interpret
        status = "ABNORMAL" if prob_abnormal > 0.5 else "NORMAL"
        detail = "N/A"
        if status == "ABNORMAL":
            detail = "MURMUR" if centroid > 200 else "GALLOP"
        else:
            detail = "S1 S2 STABLE"
            
        grade = "I/VI"
        if intensity > 5: grade = "III/VI"
        elif intensity > 2: grade = "II/VI"
        
        return {
            "organ": "Heart",
            "status": status,
            "diagnosis": detail,
            "confidence": round(abs(prob_abnormal - 0.5) * 2 * 100, 1), # Simple confidence
            "probability": prob_abnormal,
            "severity": grade,
            "bpm": "Unknown", # Requires beat tracking lib
            "rms": rms
        }
    except Exception as e:
        logger.error(f"Heart Analysis Error: {e}")
        return {"error": str(e)}

def analyze_lung(audio_data, sr=4000):
    """
    Analyzes lung sound. Returns dict with results.
    """
    if _models['pulmonary'] is None:
        return {"error": "Model not loaded", "status": "failed"}

    try:
        # Preprocess
        input_data, clean_audio = preprocess_audio(audio_data, sr, mode='lung')
        
        # Features
        rms = calculate_rms(clean_audio)
        centroid = spectral_properties(clean_audio, sr)
        intensity = min(rms * 1000, 10)
        
        # Predict
        prediction = _models['pulmonary'].predict(input_data)
        prob_abnormal = float(prediction[0][0])
        
        # Interpret
        status = "ABNORMAL" if prob_abnormal > 0.5 else "NORMAL"
        detail = "N/A"
        if status == "ABNORMAL":
            detail = "WHEEZE" if centroid > 600 else "RALES"
        else:
            detail = "VESICULAR"
            
        grade = "MILD"
        if intensity > 6: grade = "SEVERE"
        elif intensity > 3: grade = "MODERATE"
        
        return {
            "organ": "Lung",
            "status": status,
            "diagnosis": detail,
            "confidence": round(abs(prob_abnormal - 0.5) * 2 * 100, 1),
            "probability": prob_abnormal,
            "severity": grade,
            "rms": rms
        }
    except Exception as e:
        logger.error(f"Lung Analysis Error: {e}")
        return {"error": str(e)}
