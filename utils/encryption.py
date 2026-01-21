"""
IshtirafAI - Data Encryption Utilities
=======================================
HIPAA-compliant encryption for PII (Personally Identifiable Information).
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import secrets
import hashlib


class PIIEncryption:
    """Encrypt/decrypt sensitive patient data."""
    
    def __init__(self, master_key: str = None):
        """
        Initialize with master encryption key.
        
        Args:
            master_key: Base64-encoded key or use environment variable
        """
        if master_key is None:
            master_key = os.environ.get('ISHTIRAF_ENCRYPTION_KEY')
        
        if not master_key:
            raise ValueError("Encryption key required. Set ISHTIRAF_ENCRYPTION_KEY env variable.")
        
        # Derive key using PBKDF2
        salt = b'ishtirafai_pii_salt_v1'  # Fixed salt for key derivation
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        derived_key = kdf.derive(master_key.encode())
        self.cipher = Fernet(base64.urlsafe_b64encode(derived_key))
    
    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt sensitive data."""
        if not plaintext:
            return None
        return self.cipher.encrypt(plaintext.encode('utf-8'))
    
    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt sensitive data."""
        if not ciphertext:
            return None
        return self.cipher.decrypt(ciphertext).decode('utf-8')
    
    @staticmethod
    def hash_ssn(ssn: str) -> str:
        """
        Create searchable hash of SSN.
        Use for lookups without exposing actual SSN.
        """
        if not ssn:
            return None
        # Normalize SSN (remove dashes, spaces)
        normalized = ''.join(c for c in ssn if c.isdigit())
        # Hash with pepper
        pepper = os.environ.get('ISHTIRAF_HASH_PEPPER', 'default_pepper')
        return hashlib.sha256(f"{normalized}{pepper}".encode()).hexdigest()
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet-compatible encryption key."""
        return Fernet.generate_key().decode()
    
    @staticmethod
    def mask_pii(value: str, visible_chars: int = 4) -> str:
        """
        Mask PII for display (e.g., SSN: ***-**-1234).
        
        Args:
            value: The value to mask
            visible_chars: Number of chars to show at end
        """
        if not value or len(value) <= visible_chars:
            return '*' * len(value) if value else ''
        
        masked_len = len(value) - visible_chars
        return '*' * masked_len + value[-visible_chars:]


class DataAnonymizer:
    """Anonymize patient data for research/analytics."""
    
    @staticmethod
    def anonymize_patient(patient_dict: dict) -> dict:
        """
        Remove all PII from patient record.
        
        Returns anonymized dict suitable for research export.
        """
        # Fields to keep (non-PII)
        safe_fields = ['age', 'gender', 'created_at']
        
        anonymized = {
            'anonymous_id': hashlib.sha256(str(patient_dict.get('id', '')).encode()).hexdigest()[:12],
        }
        
        for field in safe_fields:
            if field in patient_dict:
                anonymized[field] = patient_dict[field]
        
        return anonymized
    
    @staticmethod
    def anonymize_diagnosis(diagnosis_dict: dict) -> dict:
        """Anonymize diagnosis for research."""
        safe_fields = [
            'diagnosis_result', 'confidence', 'risk_score',
            'organ_type', 'findings', 'created_at'
        ]
        
        anonymized = {
            'anonymous_id': hashlib.sha256(str(diagnosis_dict.get('id', '')).encode()).hexdigest()[:12],
        }
        
        for field in safe_fields:
            if field in diagnosis_dict:
                anonymized[field] = diagnosis_dict[field]
        
        return anonymized


# Global encryption instance (initialized on app startup)
_pii_encryptor = None


def init_encryption(app):
    """Initialize PII encryption with app config."""
    global _pii_encryptor
    
    key = app.config.get('ENCRYPTION_KEY') or os.environ.get('ISHTIRAF_ENCRYPTION_KEY')
    
    if key:
        try:
            _pii_encryptor = PIIEncryption(key)
            print("✅ PII Encryption Initialized")
        except Exception as e:
            print(f"⚠️ PII Encryption failed: {e}")
    else:
        print("⚠️ No encryption key configured")
    
    return _pii_encryptor


def encrypt_pii(value: str) -> bytes:
    """Encrypt PII using global encryptor."""
    if _pii_encryptor:
        return _pii_encryptor.encrypt(value)
    return value.encode() if value else None


def decrypt_pii(value: bytes) -> str:
    """Decrypt PII using global encryptor."""
    if _pii_encryptor:
        return _pii_encryptor.decrypt(value)
    return value.decode() if value else None
