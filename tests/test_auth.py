"""
Authentication Route Tests
"""
import pytest


class TestAuthRoutes:
    """Test authentication endpoints"""
    
    def test_login_page_loads(self, client):
        """Test login page is accessible"""
        response = client.get('/auth/login')
        assert response.status_code == 200
        assert b'Login' in response.data or b'login' in response.data
    
    def test_register_page_loads(self, client):
        """Test register page is accessible"""
        response = client.get('/auth/register')
        assert response.status_code == 200
        assert b'Register' in response.data or b'register' in response.data
    
    def test_login_with_invalid_credentials(self, client):
        """Test login fails with wrong credentials"""
        response = client.post('/auth/login', data={
            'email': 'wrong@email.com',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        assert b'Invalid' in response.data or b'invalid' in response.data
    
    def test_register_new_user(self, client, sample_user):
        """Test user registration"""
        response = client.post('/auth/register', data=sample_user, follow_redirects=True)
        assert response.status_code == 200
    
    def test_forgot_password_page_loads(self, client):
        """Test forgot password page"""
        response = client.get('/auth/forgot-password')
        assert response.status_code == 200
    
    def test_logout_redirects_to_login(self, authenticated_client):
        """Test logout redirects properly"""
        response = authenticated_client.get('/auth/logout', follow_redirects=True)
        assert response.status_code == 200
