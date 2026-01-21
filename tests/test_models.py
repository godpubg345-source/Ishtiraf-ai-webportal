"""
Model Tests
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.user import User


class TestUserModel:
    """Test User model"""
    
    def test_password_hashing(self):
        """Test password is properly hashed"""
        user = User(email='test@test.com', name='Test', role='doctor')
        user.set_password('testpass123')
        
        assert user.password_hash is not None
        assert user.password_hash != 'testpass123'
    
    def test_password_verification(self):
        """Test password verification works"""
        user = User(email='test@test.com', name='Test', role='doctor')
        user.set_password('correctpassword')
        
        assert user.check_password('correctpassword') == True
        assert user.check_password('wrongpassword') == False
    
    def test_user_defaults(self):
        """Test user default values"""
        user = User(email='test@test.com', name='Test', role='doctor')
        
        assert user.is_active == True
        assert user.is_verified == False
