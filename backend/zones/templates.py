"""
Border Intelligence Security Zone Tactical Templates Module.
Provides standard defense perimeter presets for fast, one-click zone and tripwire deployment.
"""
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.zones.security_zone import (
    SecurityZone,
    VirtualBoundary,
    ZoneSeverity,
    get_zone_monitor,
)


class ZoneTemplate(BaseModel):
    template_id: str
    name: str
    description: str
    zone_type: str  # "polygon" | "boundary"
    severity: str
    default_loitering_threshold_seconds: Optional[float] = None
    default_coordinates: Any  # List[Tuple[float, float]] or Tuple[Tuple, Tuple]


TACTICAL_TEMPLATES: List[ZoneTemplate] = [
    ZoneTemplate(
        template_id="BORDER_RESTRICTED_STRIP",
        name="Border Perimeter Buffer Strip",
        description="Linear buffer zone extending across the surveillance baseline.",
        zone_type="polygon",
        severity="restricted",
        default_loitering_threshold_seconds=1.5,
        default_coordinates=[[50.0, 450.0], [1230.0, 450.0], [1230.0, 700.0], [50.0, 700.0]],
    ),
    ZoneTemplate(
        template_id="GATE_ACCESS_FUNNEL",
        name="Gate Approach Corridor",
        description="Trapezoidal checkpoint approach zone monitoring vehicle and personnel funneling.",
        zone_type="polygon",
        severity="warning",
        default_loitering_threshold_seconds=3.0,
        default_coordinates=[[400.0, 100.0], [880.0, 100.0], [750.0, 650.0], [530.0, 650.0]],
    ),
    ZoneTemplate(
        template_id="CRITICAL_INFRASTRUCTURE_BOX",
        name="High-Security Asset Exclusion Box",
        description="Immediate exclusion boundary surrounding watchtowers, communication relays, or transformers.",
        zone_type="polygon",
        severity="critical",
        default_loitering_threshold_seconds=0.5,
        default_coordinates=[[200.0, 150.0], [550.0, 150.0], [550.0, 450.0], [200.0, 450.0]],
    ),
    ZoneTemplate(
        template_id="VIRTUAL_PERIMETER_FENCE",
        name="Virtual Border Fence Tripwire",
        description="Directional virtual tripwire line alerting on physical fence crossings.",
        zone_type="boundary",
        severity="critical",
        default_loitering_threshold_seconds=None,
        default_coordinates=[[100.0, 400.0], [1180.0, 400.0]],
    ),
]


def list_tactical_templates() -> List[ZoneTemplate]:
    """Retrieve all standard tactical security zone templates."""
    return TACTICAL_TEMPLATES


def apply_tactical_template(
    template_id: str,
    custom_name: Optional[str] = None,
    zone_id_suffix: str = "01",
) -> Dict[str, Any]:
    """Instantiate a tactical template into the active ZoneMonitor."""
    tmpl = next((t for t in TACTICAL_TEMPLATES if t.template_id == template_id), None)
    if not tmpl:
        raise ValueError(f"Template '{template_id}' not found")

    monitor = get_zone_monitor()
    name = custom_name or f"{tmpl.name} ({zone_id_suffix})"
    target_id = f"{tmpl.template_id}_{zone_id_suffix}"

    try:
        sev = ZoneSeverity(tmpl.severity.lower())
    except ValueError:
        sev = ZoneSeverity.RESTRICTED

    if tmpl.zone_type == "polygon":
        zone = SecurityZone(
            zone_id=target_id,
            name=name,
            polygon=tmpl.default_coordinates,
            severity=sev,
            loitering_threshold_seconds=tmpl.default_loitering_threshold_seconds,
        )
        monitor.add_zone(zone)
        return {
            "zone_id": zone.zone_id,
            "name": zone.name,
            "type": "polygon",
            "severity": zone.severity.value,
            "status": "applied",
        }
    else:
        pt1 = tuple(tmpl.default_coordinates[0])
        pt2 = tuple(tmpl.default_coordinates[1])
        bound = VirtualBoundary(
            boundary_id=target_id,
            name=name,
            pt1=pt1,
            pt2=pt2,
            severity=sev,
        )
        monitor.add_boundary(bound)
        return {
            "boundary_id": bound.boundary_id,
            "name": bound.name,
            "type": "boundary",
            "severity": bound.severity.value,
            "status": "applied",
        }
