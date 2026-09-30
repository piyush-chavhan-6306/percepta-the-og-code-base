"""
Unit and Integration Tests for Configurable Surveillance Operation Profiles.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import get_settings
from backend.config_profiles import (
    get_active_profile,
    list_operational_profiles,
    set_active_profile,
)
from backend.main import create_app


def test_operational_profiles_switching():
    profiles = list_operational_profiles()
    assert len(profiles) >= 4
    prof_ids = [p.profile_id for p in profiles]
    assert "STANDARD_DAY" in prof_ids
    assert "HIGH_SENSITIVITY_NIGHT" in prof_ids
    assert "ADVERSE_WEATHER_STORM" in prof_ids

    # Switch to Night Mode
    night = set_active_profile("HIGH_SENSITIVITY_NIGHT")
    assert night.profile_id == "HIGH_SENSITIVITY_NIGHT"
    assert get_active_profile().profile_id == "HIGH_SENSITIVITY_NIGHT"
    settings = get_settings()
    assert settings.CONFIDENCE_THRESHOLD == 0.15
    assert settings.DEFAULT_FRAME_STRIDE == 1

    # Reset back to Standard Day
    day = set_active_profile("STANDARD_DAY")
    assert day.profile_id == "STANDARD_DAY"
    assert settings.CONFIDENCE_THRESHOLD == 0.25


@pytest.mark.asyncio
async def test_operational_profiles_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get profiles
        r_get = await client.get("/api/system/profiles")
        assert r_get.status_code == 200
        data = r_get.json()
        assert "active_profile" in data
        assert "available_profiles" in data

        # 2. Apply Storm Profile
        r_apply = await client.post(
            "/api/system/profiles/apply",
            json={"profile_id": "ADVERSE_WEATHER_STORM"},
        )
        assert r_apply.status_code == 200
        res = r_apply.json()
        assert res["status"] == "applied"
        assert res["active_profile"]["profile_id"] == "ADVERSE_WEATHER_STORM"

        # 3. Apply invalid profile returns 404
        r_bad = await client.post(
            "/api/system/profiles/apply",
            json={"profile_id": "INVALID_PROFILE_NAME"},
        )
        assert r_bad.status_code == 404

    # Reset back to baseline
    set_active_profile("STANDARD_DAY")
