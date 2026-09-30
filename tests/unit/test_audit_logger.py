"""
Unit and Integration Tests for Administrative Audit Log Engine.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.audit_logger import get_audit_logger
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_audit_logger_workflow():
    logger = get_audit_logger()

    entry1 = await logger.log_action(
        action="CAMERA_REGISTER",
        details={"camera_id": "CAM_TEST_AUDIT_01", "type": "rtsp"},
        actor="COMM_OFFICER_01",
    )
    assert entry1.action == "CAMERA_REGISTER"
    assert entry1.actor == "COMM_OFFICER_01"

    entry2 = await logger.log_action(
        action="PROFILE_SWITCH",
        details={"profile": "HIGH_SENSITIVITY_NIGHT"},
        actor="DUTY_COMMANDER",
    )
    assert entry2.action == "PROFILE_SWITCH"

    logs = await logger.get_audit_logs(limit=10)
    assert len(logs) >= 2
    actions = [l.action for l in logs]
    assert "CAMERA_REGISTER" in actions or "PROFILE_SWITCH" in actions


@pytest.mark.asyncio
async def test_audit_logs_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/system/audit-logs?limit=50")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert "audit_logs" in data
        assert isinstance(data["audit_logs"], list)
