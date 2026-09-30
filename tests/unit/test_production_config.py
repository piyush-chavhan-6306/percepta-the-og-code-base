"""
Unit tests for production configuration, CORS settings, and environment management.
"""
from backend.config import Settings


def test_settings_cors_origins_and_version():
    settings = Settings(
        APP_NAME="Border Intelligence Test",
        API_VERSION="0.1.0",
        CORS_ORIGINS=["http://localhost:3000", "http://127.0.0.1:3000"],
    )
    assert settings.APP_NAME == "Border Intelligence Test"
    assert settings.API_VERSION == "0.1.0"
    assert "http://localhost:3000" in settings.CORS_ORIGINS
    assert len(settings.CORS_ORIGINS) == 2
