"""
Unit and Integration Tests for Real-Time Threat Assessment & Sector Threat Index Engine.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.schema import AlertEvent, SourceType, TrackingEvent
from backend.events.store import get_event_store
from backend.intelligence.threat_engine import ThreatEngine, ThreatLevel
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_threat_engine_levels_and_scoring():
    store = get_event_store()
    engine = ThreatEngine(store=store)

    # 1. Baseline: zero alerts -> DEFCON_GREEN
    t0 = await engine.evaluate_threat(camera_id="cam_threat_test_0")
    assert t0.threat_level in (ThreatLevel.DEFCON_GREEN, ThreatLevel.DEFCON_YELLOW)
    assert t0.threat_score >= 0.0

    # 2. Inject Critical Boundary Crossings -> DEFCON_RED
    alert1 = AlertEvent(
        camera_id="cam_threat_test_1",
        track_id="101",
        severity="CRITICAL",
        message="BORDER BREACH: Track 101 crossed virtual boundary",
        source=SourceType.SIMULATION,
    )
    alert2 = AlertEvent(
        camera_id="cam_threat_test_1",
        track_id="102",
        severity="CRITICAL",
        message="BORDER BREACH: Track 102 crossed virtual boundary",
        source=SourceType.SIMULATION,
    )
    alert3 = AlertEvent(
        camera_id="cam_threat_test_1",
        track_id="103",
        severity="RESTRICTED",
        message="SECURITY ALERT: Track 103 entered restricted zone",
        source=SourceType.SIMULATION,
    )
    await store.record_event(alert1)
    await store.record_event(alert2)
    await store.record_event(alert3)

    t1 = await engine.evaluate_threat(camera_id="cam_threat_test_1", lookback_seconds=60)
    assert t1.threat_score >= 80.0
    assert t1.threat_level == ThreatLevel.DEFCON_RED
    assert len(t1.contributing_factors) >= 1
    assert "critical" in str(t1.contributing_factors).lower() or "breach" in str(t1.contributing_factors).lower()


@pytest.mark.asyncio
async def test_threat_level_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/threat/level?lookback_seconds=60")
        assert r.status_code == 200
        data = r.json()
        assert "threat_level" in data
        assert "threat_score" in data
        assert "contributing_factors" in data
        assert "recommended_action" in data
