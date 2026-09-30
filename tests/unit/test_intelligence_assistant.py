"""
Unit Tests for Grounded Natural-Language Surveillance Intelligence Assistant.
Tests intent recognition, controlled parameter-validated retrieval, 3-tier grounded answers,
anti-hallucination guardrails, refusal behaviors, and SQL injection safety.
"""
from datetime import datetime, timezone
import httpx
from httpx import ASGITransport
import pytest

from backend.database import init_db
from backend.events.schema import AlertEvent, EventType, SourceType, TrackingEvent, ZoneEvent
from backend.events.store import get_event_store
from backend.intelligence.assistant import ControlledQueryLayer, GroundedQueryResponse, SurveillanceAssistant
from backend.main import create_app


@pytest.fixture
async def setup_test_events():
    await init_db()
    from sqlalchemy import text
    from backend.database import get_session_factory
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text("DELETE FROM event_logs WHERE camera_id = 'cam_intel_test';"))
        await session.commit()

    store = get_event_store()

    cam = "cam_intel_test"
    t_id = "17"

    t0 = datetime(2026, 8, 23, 10, 15, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 23, 10, 15, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 23, 10, 15, 25, tzinfo=timezone.utc)

    # 1. Tracking Event
    ev_track = TrackingEvent(
        camera_id=cam,
        track_id=t_id,
        object_class="person",
        position=[250.0, 300.0],
        velocity=[5.0, 0.0],
        speed=5.0,
        direction=0.0,
        lifecycle="updated",
        timestamp=t0,
        source=SourceType.SIMULATION,
    )
    await store.record_event(ev_track)

    # 2. Zone Entry Event
    ev_entry = ZoneEvent(
        camera_id=cam,
        track_id=t_id,
        confidence=0.94,
        zone_id="restricted_alpha",
        zone_name="Sector Alpha Restricted",
        zone_severity="restricted",
        transition="entered",
        dwell_duration_seconds=0.0,
        timestamp=t0,
        source=SourceType.SIMULATION,
    )
    await store.record_event(ev_entry)

    # 3. Alert Event
    ev_alert = AlertEvent(
        camera_id=cam,
        track_id=t_id,
        confidence=0.94,
        severity="RESTRICTED",
        message="SECURITY ALERT: Track 17 (person) entered restricted zone 'Sector Alpha Restricted'",
        timestamp=t0,
        source=SourceType.SIMULATION,
    )
    await store.record_event(ev_alert)

    # 4. Loitering Zone Event
    ev_loiter = ZoneEvent(
        camera_id=cam,
        track_id=t_id,
        confidence=0.94,
        zone_id="restricted_alpha",
        zone_name="Sector Alpha Restricted",
        zone_severity="restricted",
        transition="loitering",
        dwell_duration_seconds=10.0,
        timestamp=t1,
        source=SourceType.SIMULATION,
    )
    await store.record_event(ev_loiter)

    # 5. Zone Exit Event
    ev_exit = ZoneEvent(
        camera_id=cam,
        track_id=t_id,
        confidence=0.92,
        zone_id="restricted_alpha",
        zone_name="Sector Alpha Restricted",
        zone_severity="restricted",
        transition="exited",
        dwell_duration_seconds=25.0,
        timestamp=t2,
        source=SourceType.SIMULATION,
    )
    await store.record_event(ev_exit)

    # 6. Virtual Boundary Crossing
    ev_cross = ZoneEvent(
        camera_id=cam,
        track_id=t_id,
        confidence=0.92,
        zone_id="tripwire_north",
        zone_name="North Perimeter Fence",
        zone_severity="critical",
        transition="crossed",
        timestamp=t2,
        source=SourceType.SIMULATION,
    )
    await store.record_event(ev_cross)

    return {"camera_id": cam, "track_id": t_id}


@pytest.mark.asyncio
async def test_track_entry_query_grounded(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("When did Track 17 enter the restricted zone?")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert len(res.observed_facts) >= 1
    assert any("Track 17 was recorded entering" in f for f in res.observed_facts)
    assert any("intrusion rule event" in r for r in res.rule_results)
    assert "Track 17 entered zone" in res.interpretation


@pytest.mark.asyncio
async def test_track_exit_query_grounded(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("When did Track 17 leave?")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("exiting zone" in f for f in res.observed_facts)
    assert "Track 17 exited zone" in res.interpretation


@pytest.mark.asyncio
async def test_track_dwell_duration_query_grounded(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("How long did Track 17 remain inside the zone?")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("maximum recorded dwell of 25.0 seconds" in f for f in res.observed_facts)
    assert "Track 17 remained in the zone for approximately 25.0 seconds" in res.interpretation


@pytest.mark.asyncio
async def test_track_movement_direction_query_grounded(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("What direction and speed was Track 17 moving?")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("velocity vector" in f for f in res.observed_facts)
    assert "px/frame speed" in res.interpretation


@pytest.mark.asyncio
async def test_alert_explanation_query(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Why was the alert generated for camera cam_intel_test?")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("SECURITY ALERT: Track 17" in f for f in res.observed_facts)
    assert "Recent alerts were triggered by security boundary crossings" in res.interpretation


@pytest.mark.asyncio
async def test_boundary_crossing_query(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Show all boundary crossings on this camera")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("crossed virtual boundary" in f for f in res.observed_facts)


@pytest.mark.asyncio
async def test_highest_risk_evidence_query(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Show evidence for the highest-risk event")

    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("Highest severity alert" in f for f in res.observed_facts)
    assert len(res.evidence) >= 1


@pytest.mark.asyncio
async def test_missing_track_produces_no_hallucination(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("When did Track 999 enter the restricted zone?")

    assert res.status == "no_records_found"
    assert res.grounding_status == "no_data"
    assert "No zone entry events recorded for Track 999" in res.interpretation
    assert len(res.observed_facts) == 0


@pytest.mark.asyncio
async def test_biometric_identity_query_refused(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Who is this person? Can you identify their face and tell me if it's John?")

    assert res.status == "unsupported_capability"
    assert res.grounding_status == "refusal"
    assert "CAPABILITY REFUSAL: The platform only maintains camera-local Track IDs" in res.interpretation
    assert len(res.observed_facts) == 0


@pytest.mark.asyncio
async def test_weapon_presence_query_refused(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Is Track 17 carrying a weapon or gun?")

    assert res.status == "unsupported_capability"
    assert res.grounding_status == "refusal"
    assert "CAPABILITY REFUSAL: The active computer vision detector (YOLOv8n) is configured for general surveillance classes" in res.interpretation


@pytest.mark.asyncio
async def test_subjective_intent_query_refused(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("What is their criminal intent? Are they planning to attack?")

    assert res.status == "unsupported_capability"
    assert res.grounding_status == "refusal"
    assert "CAPABILITY REFUSAL: Subjective human intent or criminal intent cannot be established" in res.interpretation


@pytest.mark.asyncio
async def test_cross_camera_identity_query_refused(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Is Track 17 on camera A the same person on camera B?")

    assert res.status == "unsupported_capability"
    assert res.grounding_status == "refusal"
    assert "CAPABILITY REFUSAL: Track IDs are strictly camera-local" in res.interpretation


@pytest.mark.asyncio
async def test_sql_injection_attempt_safely_rejected(setup_test_events):
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("Track 17'; SELECT * FROM event_logs; DROP TABLE event_logs; --")

    assert res.status == "invalid_query"
    assert res.grounding_status == "refusal"
    assert "SECURITY REFUSAL: Raw SQL keywords detected" in res.interpretation


@pytest.mark.asyncio
async def test_fastapi_intelligence_endpoint(setup_test_events):
    app = create_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"query": "When did Track 17 enter the restricted zone?"}
        resp = await client.post("/api/intelligence/query", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "answered"
        assert data["grounding_status"] == "grounded"
        assert len(data["observed_facts"]) >= 1
        assert "Track 17 entered zone" in data["interpretation"]


@pytest.mark.asyncio
async def test_live_cameras_query_grounded():
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("How many cameras are active?")
    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert len(res.rule_results) >= 1
    assert "PERCEPTA is monitoring" in res.interpretation


@pytest.mark.asyncio
async def test_live_zones_query_grounded():
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("What zones are configured?")
    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert len(res.rule_results) >= 1
    assert "perimeter enforcement" in res.interpretation


@pytest.mark.asyncio
async def test_live_system_status_query_grounded():
    assistant = SurveillanceAssistant()
    res = await assistant.answer_query("What is the current system status and fps?")
    assert res.status == "answered"
    assert res.grounding_status == "grounded"
    assert any("FPS" in f for f in res.observed_facts)
