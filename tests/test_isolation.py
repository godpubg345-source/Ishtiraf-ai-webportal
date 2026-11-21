"""Tests must never touch the real portal database."""
from app import app, db


def test_tests_do_not_use_real_database():
    with app.app_context():
        assert 'ishtiraf_ai.db' not in str(db.engine.url)
