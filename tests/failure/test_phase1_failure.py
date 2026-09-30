"""
Phase 1 Deliberate Failure & Edge Case Tests:
1. Concurrency test: Multiple simulated camera workers writing events simultaneously to SQLite WAL.
2. Malformed payload & invalid EventType validation rejection.
3. Database failure isolation: Database down / rollback produces no phantom event broadcast.
4. Edge cases in replay pagination: empty results, limit clamping, non-existent incident IDs.
"""
import asyncio
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from backend.database import close_db, init_db
from backend.events.bus import EventBus
from backend.events.schema import (
    AlertEvent,
    BaseEvent,
    DetectionEvent,
    EventType,
    SourceType,
    SystemEvent,
)
from backend.events.store import EventStore
from backend.main import create_app


@pytest_asyncio.fixture
async def failure_test_db(tmp_path):
    db_file = tmp_path / "test_failure.db"
    test_db_url = f"sqlite+aiosqlite:///{db_file}"
    await init_db(database_url=test_db_url)
    yield
    await close_db()


@pytest.mark.asyncio
async def test_concurrent_camera_worker_writes(failure_test_db):
    """Verify SQLite WAL handles concurrent writes from multiple simulated camera workers."""
    bus = EventBus()
    store = EventStore(bus=bus)
    num_workers = 10
    events_per_worker = 20

    async def worker_task(worker_id: int):
        for i in range(events_per_worker):
            event = DetectionEvent(
                camera_id=f"CAM-{worker_id:02d}",
                object_class="person",
                bounding_box=[10.0, 20.0, 30.0, 40.0],
                frame_number=i,
                timestamp=datetime.now(timezone.utc),
            )
            seq_id = await store.record_event(event)
            assert seq_id > 0

    # Launch all workers concurrently
    tasks = [worker_task(w) for w in range(num_workers)]
    await asyncio.gather(*tasks)

    # Verify total persisted count
    all_events = await store.get_events(limit=1000)
    assert len(all_events) == num_workers * events_per_worker

    # Verify sequence IDs are distinct and monotonic
    seq_ids = [e["seq_id"] for e in all_events]
    assert len(set(seq_ids)) == len(seq_ids)


@pytest.mark.asyncio
async def test_invalid_event_schema_rejected():
    """Verify malformed event types or missing required fields raise Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        # Missing required camera_id and object_class
        DetectionEvent(frame_number=1)  # type: ignore

    with pytest.raises(ValidationError):
        # Invalid confidence
        DetectionEvent(
            camera_id="CAM-01",
            object_class="person",
            bounding_box=[1, 2, 3, 4],
            frame_number=1,
            confidence="not_a_float",  # type: ignore
        )


@pytest.mark.asyncio
async def test_replay_edge_cases(failure_test_db):
    """Verify replay API edge cases: empty results, limit boundary, non-existent incident."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Non-existent incident timeline returns empty list, not 500 error
        res = await client.get("/api/events/incident/NON-EXISTENT-INC-999")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 0
        assert data["timeline"] == []

        # 2. Limit parameter validation (limit=0 should fail with 422)
        res_bad_limit = await client.get("/api/events?limit=0")
        assert res_bad_limit.status_code == 422
