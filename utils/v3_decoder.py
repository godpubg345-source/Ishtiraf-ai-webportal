"""
IshtirafAI Web Portal - V3.0 Decoder Utilities
================================================
Decodes JAB Code payloads containing neural-compressed audio.
"""

import os
import sys
import json
import zlib
import base64

# Add Model_Training path for shared modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Navigate: utils -> IshtirafAI_WebPortal -> IshtirafAI_Project -> Model_Training/2_App_Core
MODEL_CORE = os.path.join(SCRIPT_DIR, '..', '..', 'Model_Training', '2_App_Core')
MODEL_CORE = os.path.normpath(MODEL_CORE)  # Normalize the path
print(f"[V3 Decoder] Looking for modules in: {MODEL_CORE}")
if MODEL_CORE not in sys.path:
    sys.path.insert(0, MODEL_CORE)


# Import V3 modules
try:
    from neural_audio_codec import MedicalAudioCodec, NeuralAudioDecoder
    NEURAL_CODEC_AVAILABLE = True
except ImportError:
    NEURAL_CODEC_AVAILABLE = False
    print("⚠️ Neural Audio Codec not available in Web Portal")

try:
    from jabcode_generator import JABCodeGenerator
    JABCODE_AVAILABLE = True
except ImportError:
    JABCODE_AVAILABLE = False
    print("⚠️ JAB Code generator not available in Web Portal")

try:
    from secure_payload import SecurePayloadEncoder, ReplayProtector
    SECURE_PAYLOAD_AVAILABLE = True
except ImportError:
    SECURE_PAYLOAD_AVAILABLE = False
    print("⚠️ Secure Payload not available in Web Portal")

# Combined flag
V3_DECODE_AVAILABLE = NEURAL_CODEC_AVAILABLE and SECURE_PAYLOAD_AVAILABLE
if V3_DECODE_AVAILABLE:
    print("🚀 V3.0 Decoder ACTIVE in Web Portal")


class V3Decoder:
    """
    Decodes V3.0 payloads from scanned JAB codes.
    """
    
    def __init__(self):
        if V3_DECODE_AVAILABLE:
            self.codec = MedicalAudioCodec()
            self.signer = SecurePayloadEncoder()
            self.replay_protector = ReplayProtector()
        else:
            self.codec = None
            self.signer = None
            self.replay_protector = None
            
    def decode_payload(self, raw_bytes: bytes, verify_signature: bool = True) -> dict:
        """
        Decode a V3.0 signed payload.
        
        Args:
            raw_bytes: Raw bytes from scanned JAB code
            verify_signature: Whether to verify Ed25519 signature
            
        Returns:
            Dict with 'metadata', 'audio' (optional), and 'security' info
        """
        if not V3_DECODE_AVAILABLE:
            return {"error": "V3.0 decoder not available"}
            
        try:
            # 1. Decode signed envelope
            envelope = self.signer.decode(raw_bytes, verify=verify_signature)
            
            # 2. Extract inner payload (hex-encoded compressed data)
            inner_hex = envelope.get('p', '')
            if not inner_hex:
                return {"error": "Empty payload"}
                
            inner_bytes = bytes.fromhex(inner_hex)
            
            # 3. Decompress and decode audio+metadata
            audio, metadata = self.codec.decompress(inner_bytes)
            
            # 4. Check replay
            device_id = envelope.get('_meta', {}).get('device_id', 'unknown')
            counter = envelope.get('_meta', {}).get('counter', 0)
            
            is_replay = False
            if self.replay_protector:
                is_valid = self.replay_protector.check_and_record(device_id, counter)
                is_replay = not is_valid
            
            return {
                "status": "success",
                "metadata": metadata,
                "audio": audio.tolist() if audio is not None else None,
                "audio_samples": len(audio) if audio is not None else 0,
                "security": {
                    "signature_verified": verify_signature,
                    "counter": counter,
                    "timestamp": envelope.get('_meta', {}).get('timestamp'),
                    "is_replay": is_replay
                }
            }
            
        except Exception as e:
            return {"error": str(e)}
            
    def decode_from_image(self, image_path: str) -> dict:
        """
        Decode V3.0 payload from a JAB code image file.
        """
        if not JABCODE_AVAILABLE:
            return {"error": "JAB Code decoder not available"}
            
        try:
            from PIL import Image
            
            jab_gen = JABCodeGenerator()
            img = Image.open(image_path)
            raw_bytes = jab_gen.decode(img)
            
            return self.decode_payload(raw_bytes)
            
        except Exception as e:
            return {"error": f"Image decode failed: {e}"}
            
    def decode_from_base64(self, b64_data: str) -> dict:
        """
        Decode V3.0 payload from base64-encoded bytes.
        """
        try:
            raw_bytes = base64.b64decode(b64_data)
            return self.decode_payload(raw_bytes)
        except Exception as e:
            return {"error": f"Base64 decode failed: {e}"}


# Global decoder instance
_decoder = None

def get_decoder() -> V3Decoder:
    """Get or create the global V3 decoder instance."""
    global _decoder
    if _decoder is None:
        _decoder = V3Decoder()
    return _decoder
