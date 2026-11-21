"""Config safety tests"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(RuntimeError):
        config.get_config()


def test_production_with_secret_key(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'test-only-key')
    assert config.get_config() is config.ProductionConfig


def test_admin_script_has_no_hardcoded_password():
    src = open(os.path.join(os.path.dirname(config.__file__), 'create_admin_auto.py'), encoding='utf-8').read()
    assert 'admin123' not in src
