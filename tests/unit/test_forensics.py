"""
Unit and Integration Tests for Cryptographic Forensic Chain of Custody & Tamper Verification.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.events.forensics import compute_event_hash, get_forensics_engine
from backend.events.schema import AlertEvent, SourceType
from backend.events.store import get_event_store
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_compute_event_hash_deterministic():
    rec1 = {
        "seq_id": 1,
        "event_id": "test-uuid-1",
        "timestamp": "2026-08-24T00:00:00Z",
        "camera_id": "CAM-01",
        "track_id": "5",
        "event_type": "ALERT",
        "payload": '{"severity": "CRITICAL"}',
    }
    rec2 = dict(rec1)
    rec3 = dict(rec1)
    rec3["payload"] = '{"severity": "WARNING"}'

    h1 = compute_event_hash(rec1)
    h2 = compute_event_hash(rec2)
    h3 = compute_event_hash(rec3)

    assert len(h1) == 64
    assert h1 == h2
    assert h1 != h3


@pytest.mark.asyncio
async def test_forensics_rest_api_verify_and_audit():
    store = get_event_store()
    alert = AlertEvent(
        camera_id="cam_forensic_test",
        track_id="44",
        severity="CRITICAL",
        message="BORDER INTRUSION: Sector Bravo Fence Crossed",
        source=SourceType.SIMULATION,
    )
    await store.record_event(alert)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Verify single event
        r_ver = await client.get(f"/api/evidence/verify/{alert.event_id}")
        assert r_ver.status_code == 200
        data = r_ver.json()
        assert data["is_authentic"] is True
        assert len(data["computed_hash"]) == 64
        assert "VERIFIED_AUTHENTIC" in data["audit_verdict"]

        # 2. Verify non-existent event returns 404
        r_404 = await client.get("/api/evidence/verify/NON-EXISTENT-UUID")
        assert r_404.status_code == 404

        # 3. Database integrity audit
        r_aud = await client.get("/api/evidence/audit-integrity?limit=50")
        assert r_aud.status_code == 200
        rep = r_aud.json()
        assert rep["total_records_checked"] >= 1
        assert rep["tampered_records_count"] == 0
        assert rep["integrity_status"] == "CERTIFIED_TAMPER_FREE"
        assert len(rep["chain_root_hash"]) == 64
