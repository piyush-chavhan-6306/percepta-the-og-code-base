"""
Unit and Integration Tests for Operator Incident Annotations & Escalation Log.
"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.schema import AlertEvent, SourceType
from backend.events.store import get_event_store
from backend.incidents.annotations import get_annotation_manager
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_operator_annotations_workflow():
    manager = get_annotation_manager()
    inc_id = f"INC-ANN-{uuid.uuid4().hex[:8]}"

    # Add 2 operator annotations
    a1 = await manager.add_annotation(
        incident_id=inc_id,
        operator_callsign="Officer Sharma",
        note="Inspected feed. Target moving towards secondary fence line.",
        disposition="INVESTIGATING",
    )
    assert a1.incident_id == inc_id
    assert a1.operator_callsign == "Officer Sharma"

    a2 = await manager.add_annotation(
        incident_id=inc_id,
        operator_callsign="Duty Officer Verma",
        note="Dispatched QRF Bravo team to Sector Alpha Gate.",
        disposition="QRF_DISPATCHED",
    )
    assert a2.disposition == "QRF_DISPATCHED"

    # Retrieve annotations
    notes = await manager.get_annotations(inc_id)
    assert len(notes) == 2
    assert notes[0].operator_callsign == "Officer Sharma"
    assert notes[1].operator_callsign == "Duty Officer Verma"


@pytest.mark.asyncio
async def test_operator_annotations_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    inc_id = f"INC-REST-{uuid.uuid4().hex[:8]}"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Post note
        r_post = await client.post(
            f"/api/incidents/{inc_id}/notes",
            json={
                "operator_callsign": "Captain Rao",
                "note": "Perimeter breach verified via PTZ thermal confirmation.",
                "disposition": "VERIFIED_BREACH",
            },
        )
        assert r_post.status_code == 200
        data = r_post.json()
        assert data["operator_callsign"] == "Captain Rao"
        assert data["disposition"] == "VERIFIED_BREACH"

        # 2. Get notes
        r_get = await client.get(f"/api/incidents/{inc_id}/notes")
        assert r_get.status_code == 200
        get_data = r_get.json()
        assert get_data["incident_id"] == inc_id
        assert get_data["count"] == 1
        assert get_data["annotations"][0]["note"] == "Perimeter breach verified via PTZ thermal confirmation."
