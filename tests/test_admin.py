"""
Admin Route Tests
"""
import pytest


class TestAdminRoutes:
    """Test admin panel endpoints"""
    
    def test_admin_dashboard_requires_login(self, client):
        """Test admin dashboard redirects when not logged in"""
        response = client.get('/admin/dashboard', follow_redirects=True)
        assert b'Login' in response.data or b'login' in response.data
    
    def test_admin_dashboard_accessible_by_admin(self, authenticated_client):
        """Test admin can access dashboard"""
        response = authenticated_client.get('/admin/dashboard')
        assert response.status_code == 200
        assert b'Admin' in response.data or b'User' in response.data
    
    def test_create_user_page_loads(self, authenticated_client):
        """Test create user page is accessible"""
        response = authenticated_client.get('/admin/create_user')
        assert response.status_code == 200
    
    def test_create_user_success(self, authenticated_client):
        """Test admin can create new user"""
        response = authenticated_client.post('/admin/create_user', data={
            'name': 'New Doctor',
            'email': 'newdoctor@test.com',
            'password': 'doctor123',
            'role': 'doctor'
        }, follow_redirects=True)
        assert response.status_code == 200


class TestAnalyticsRoutes:
    """Test analytics endpoints"""
    
    def test_analytics_dashboard_loads(self, authenticated_client):
        """Test analytics dashboard is accessible"""
        response = authenticated_client.get('/analytics/dashboard')
        assert response.status_code == 200
    
    def test_analytics_api_returns_json(self, authenticated_client):
        """Test API returns valid JSON"""
        response = authenticated_client.get('/analytics/api/stats')
        assert response.status_code == 200
        assert response.content_type == 'application/json'
