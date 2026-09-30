"""
Unit and Integration Tests for Database Health & Enterprise Migration Diagnostics.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import init_db
from backend.database_diagnostics import inspect_database_diagnostics
from backend.main import create_app


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_database_diagnostics_direct():
    diag = await inspect_database_diagnostics()
    assert "journal_mode" in diag
    assert diag["journal_mode"] == "WAL"
    assert "page_size_bytes" in diag
    assert "total_pages" in diag
    assert "health_probe_latency_ms" in diag
    assert "enterprise_migration" in diag
    assert diag["enterprise_migration"]["status"] == "READY_FOR_POSTGRESQL"


@pytest.mark.asyncio
async def test_database_diagnostics_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/api/system/db-diagnostics")
        assert r.status_code == 200
        data = r.json()
        assert data["journal_mode"] == "WAL"
        assert "db_file_size_mb" in data
        assert "enterprise_migration" in data
        assert data["enterprise_migration"]["status"] == "READY_FOR_POSTGRESQL"
