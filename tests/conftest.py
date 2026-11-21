"""
IshtirafAI WebPortal - Test Configuration
"""
import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models.user import User


@pytest.fixture
def client():
    """Create test client"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()


@pytest.fixture(name='app')
def app_fixture():
    """Flask app configured for tests, with a fresh in-memory database"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def authenticated_client(client):
    """Create authenticated test client"""
    with app.app_context():
        # Create test user
        user = User(email='test@test.com', name='Test User', role='admin')
        user.set_password('testpass123')
        db.session.add(user)
        db.session.commit()
    
    # Login
    client.post('/auth/login', data={
        'email': 'test@test.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    
    return client


@pytest.fixture
def sample_user():
    """Return sample user data"""
    return {
        'email': 'sample@test.com',
        'name': 'Sample User',
        'password': 'samplepass123'
    }
