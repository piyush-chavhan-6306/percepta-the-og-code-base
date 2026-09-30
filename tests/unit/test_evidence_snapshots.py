"""
Unit and Integration Tests for Evidence Snapshot Extractor & Archival.
"""
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from backend.events.snapshots import get_snapshot_manager
from backend.main import create_app


def test_save_and_list_incident_snapshots():
    manager = get_snapshot_manager()
    inc_id = "INC_SNAP_UNIT_01"

    img = np.full((480, 640, 3), 100, dtype=np.uint8)
    boxes = [[100.0, 100.0, 200.0, 300.0]]

    meta = manager.save_snapshot(
        incident_id=inc_id,
        image=img,
        camera_id="CAM_NORTH_01",
        frame_number=45,
        trigger_reason="CRITICAL_LINE_CROSS",
        bounding_boxes=boxes,
    )

    assert meta.incident_id == inc_id
    assert meta.frame_number == 45
    assert meta.trigger_reason == "CRITICAL_LINE_CROSS"
    assert meta.file_uri.startswith("/api/evidence/snapshots/file/")

    # List snapshots
    snaps = manager.list_snapshots(inc_id)
    assert len(snaps) >= 1
    assert snaps[0].incident_id == inc_id


@pytest.mark.asyncio
async def test_evidence_snapshots_rest_api():
    manager = get_snapshot_manager()
    inc_id = "INC_SNAP_REST_02"
    img = np.full((240, 320, 3), 150, dtype=np.uint8)

    meta = manager.save_snapshot(
        incident_id=inc_id,
        image=img,
        camera_id="CAM_API_01",
        frame_number=10,
    )
    filename = meta.file_path.split("\\")[-1].split("/")[-1]

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. List snapshots for incident
        r_list = await client.get(f"/api/evidence/snapshots/{inc_id}")
        assert r_list.status_code == 200
        data = r_list.json()
        assert data["incident_id"] == inc_id
        assert data["count"] >= 1

        # 2. Fetch image file
        r_file = await client.get(f"/api/evidence/snapshots/file/{filename}")
        assert r_file.status_code == 200
        assert r_file.headers["content-type"] == "image/jpeg"
        assert len(r_file.content) > 0

        # 3. Non-existent file returns 404
        r_404 = await client.get("/api/evidence/snapshots/file/NON_EXISTENT_FILE.jpg")
        assert r_404.status_code == 404
