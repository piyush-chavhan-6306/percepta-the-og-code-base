"""
Unit and Integration Tests for Security Zone Tactical Templates.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.zones.templates import (
    apply_tactical_template,
    list_tactical_templates,
)


def test_list_and_apply_tactical_templates():
    templates = list_tactical_templates()
    assert len(templates) >= 4
    template_ids = [t.template_id for t in templates]
    assert "BORDER_RESTRICTED_STRIP" in template_ids
    assert "VIRTUAL_PERIMETER_FENCE" in template_ids

    # Apply polygon template
    res_poly = apply_tactical_template("BORDER_RESTRICTED_STRIP", zone_id_suffix="TEST_01")
    assert res_poly["status"] == "applied"
    assert res_poly["type"] == "polygon"

    # Apply boundary template
    res_bound = apply_tactical_template("VIRTUAL_PERIMETER_FENCE", zone_id_suffix="TEST_02")
    assert res_bound["status"] == "applied"
    assert res_bound["type"] == "boundary"


@pytest.mark.asyncio
async def test_zone_templates_rest_api():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get templates list
        r_list = await client.get("/api/zones/templates")
        assert r_list.status_code == 200
        data = r_list.json()
        assert "templates" in data
        assert len(data["templates"]) >= 4

        # 2. Apply template via POST
        r_apply = await client.post(
            "/api/zones/apply-template",
            json={
                "template_id": "GATE_ACCESS_FUNNEL",
                "zone_id_suffix": "SECTOR_NORTH",
                "custom_name": "Sector North Gate Approach",
            },
        )
        assert r_apply.status_code == 200
        res = r_apply.json()
        assert res["status"] == "applied"
        assert res["name"] == "Sector North Gate Approach"
