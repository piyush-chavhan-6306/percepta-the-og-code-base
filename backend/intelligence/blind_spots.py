"""
PERCEPTA Predicted Blind Spot & Perimeter Coverage Analysis Engine.

Evaluates coverage health, field-of-view gaps, sensor occlusion,
and offline camera vulnerabilities across registered surveillance sectors.
Provides deterministic, explainable blind spot assessments without fabricating geospatial coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from backend.ingestion.camera_manager import get_camera_manager
from backend.ingestion.optical_diagnostics import evaluate_camera_trust

logger = logging.getLogger(__name__)


@dataclass
class BlindSpotZone:
    blind_spot_id: str
    camera_id: Optional[str]
    sector_name: str
    severity: str                     # "CRITICAL" | "HIGH" | "MEDIUM"
    risk_level: str                  # "UNMONITORED_GAP" | "LENS_OCCLUDED" | "STREAM_OFFLINE" | "LOW_ILLUMINATION_SHADOW"
    reason: str
    impact: str
    recommended_action: str
    coverage_gap_ratio: float        # 0.0 - 1.0
    uncertainty: str                 # "LOW" | "MODERATE" | "HIGH"
    detected_at: str


@dataclass
class BlindSpotReport:
    total_sectors: int
    active_monitored_sectors: int
    blind_spot_count: int
    perimeter_coverage_score: float  # 0.0 - 100.0%
    overall_risk: str                # "LOW" | "ELEVATED" | "CRITICAL"
    blind_spots: List[BlindSpotZone]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sectors": self.total_sectors,
            "active_monitored_sectors": self.active_monitored_sectors,
            "blind_spot_count": self.blind_spot_count,
            "perimeter_coverage_score": round(self.perimeter_coverage_score, 1),
            "overall_risk": self.overall_risk,
            "blind_spots": [
                {
                    "blind_spot_id": b.blind_spot_id,
                    "camera_id": b.camera_id,
                    "sector_name": b.sector_name,
                    "severity": b.severity,
                    "risk_level": b.risk_level,
                    "reason": b.reason,
                    "impact": b.impact,
                    "recommended_action": b.recommended_action,
                    "coverage_gap_ratio": round(b.coverage_gap_ratio, 2),
                    "uncertainty": b.uncertainty,
                    "detected_at": b.detected_at,
                }
                for b in self.blind_spots
            ],
            "timestamp": self.timestamp,
        }


class BlindSpotAnalyzer:
    """Analyzes real sensor telemetry, optical health, and camera registry to find coverage gaps."""

    async def analyze_coverage(self) -> BlindSpotReport:
        now_iso = datetime.now(timezone.utc).isoformat()
        manager = get_camera_manager()
        cams = manager.list_cameras()

        blind_spots: List[BlindSpotZone] = []

        if not cams:
            return BlindSpotReport(
                total_sectors=0,
                active_monitored_sectors=0,
                blind_spot_count=1,
                perimeter_coverage_score=0.0,
                overall_risk="CRITICAL",
                blind_spots=[
                    BlindSpotZone(
                        blind_spot_id="BS-ZERO-SENSORS",
                        camera_id=None,
                        sector_name="Entire Perimeter",
                        severity="CRITICAL",
                        risk_level="UNMONITORED_GAP",
                        reason="No surveillance cameras are currently registered or online.",
                        impact="Complete perimeter vulnerability. 100% blind sector.",
                        recommended_action="Register and start video feeds for border post sectors.",
                        coverage_gap_ratio=1.0,
                        uncertainty="LOW",
                        detected_at=now_iso,
                    )
                ],
                timestamp=now_iso,
            )

        healthy_count = 0

        for cam in cams:
            cam_id = cam.get("camera_id") if isinstance(cam, dict) else cam.camera_id
            name = (cam.get("name") if isinstance(cam, dict) else cam.name) or cam_id
            loc = (cam.get("location_label") if isinstance(cam, dict) else cam.location_label) or f"Sector {cam_id}"
            is_running = cam.get("is_running") if isinstance(cam, dict) else cam.is_running
            status_val = cam.get("status") if isinstance(cam, dict) else getattr(cam, "status", "online")

            if not is_running or status_val != "online":
                # Camera is offline or stopped
                blind_spots.append(
                    BlindSpotZone(
                        blind_spot_id=f"BS-OFFLINE-{cam_id}",
                        camera_id=cam_id,
                        sector_name=f"{loc} ({name})",
                        severity="CRITICAL",
                        risk_level="STREAM_OFFLINE",
                        reason=f"Camera '{name}' ({cam_id}) stream is inactive / stopped.",
                        impact=f"Entire sector monitored by {cam_id} is completely unobserved.",
                        recommended_action=f"Restart camera perception loop on {cam_id} or dispatch roving guard.",
                        coverage_gap_ratio=1.0,
                        uncertainty="LOW",
                        detected_at=now_iso,
                    )
                )
                continue

            # Camera is online; evaluate optical telemetry
            trust_rep = await evaluate_camera_trust(cam_id)
            if not trust_rep.is_trusted or trust_rep.trust_score < 50.0:
                blind_spots.append(
                    BlindSpotZone(
                        blind_spot_id=f"BS-DEGRADED-{cam_id}",
                        camera_id=cam_id,
                        sector_name=f"{loc} ({name})",
                        severity="HIGH",
                        risk_level="LENS_OCCLUDED",
                        reason=f"Optical degradation on {cam_id}: {trust_rep.summary} (Trust score: {trust_rep.trust_score}%)",
                        impact="Severe detection false-negatives possible due to blur/glare/darkness.",
                        recommended_action="Inspect lens for physical obstruction, spray, or clean optical dome.",
                        coverage_gap_ratio=0.75,
                        uncertainty="MODERATE",
                        detected_at=now_iso,
                    )
                )
            elif trust_rep.trust_score < 80.0:
                blind_spots.append(
                    BlindSpotZone(
                        blind_spot_id=f"BS-PARTIAL-{cam_id}",
                        camera_id=cam_id,
                        sector_name=f"{loc} ({name})",
                        severity="MEDIUM",
                        risk_level="LOW_ILLUMINATION_SHADOW",
                        reason=f"Suboptimal lighting or partial glare on {cam_id} (Trust: {trust_rep.trust_score}%). Peripheral shadow zone detected.",
                        impact="Small targets or low-contrast camouflage may evade peripheral detection.",
                        recommended_action="Switch sensor mode to IR night vision or engage tactical floodlight.",
                        coverage_gap_ratio=0.30,
                        uncertainty="MODERATE",
                        detected_at=now_iso,
                    )
                )
                healthy_count += 1
            else:
                healthy_count += 1

        # Check multi-camera handover gaps: if only 1 camera exists, the inter-sector perimeter boundary is a blind spot
        if len(cams) == 1:
            blind_spots.append(
                BlindSpotZone(
                    blind_spot_id="BS-TOPOLOGY-SINGLE-CAM",
                    camera_id=None,
                    sector_name="Adjacent Perimeter Inter-Sector Boundary",
                    severity="MEDIUM",
                    risk_level="UNMONITORED_GAP",
                    reason="Only single camera node deployed. Flank transit corridors lack overlap redundancy.",
                    impact="Cross-sector target tracking handover unavailable beyond primary camera FOV.",
                    recommended_action="Deploy secondary camera node (CAM-02) covering lateral boundary sector.",
                    coverage_gap_ratio=0.45,
                    uncertainty="HIGH",
                    detected_at=now_iso,
                )
            )

        total_sectors = max(len(cams), 1)
        coverage_pct = (healthy_count / total_sectors) * 100.0
        if any(b.severity == "CRITICAL" for b in blind_spots):
            overall_risk = "CRITICAL"
        elif any(b.severity == "HIGH" for b in blind_spots):
            overall_risk = "ELEVATED"
        else:
            overall_risk = "LOW"

        return BlindSpotReport(
            total_sectors=total_sectors,
            active_monitored_sectors=healthy_count,
            blind_spot_count=len(blind_spots),
            perimeter_coverage_score=coverage_pct,
            overall_risk=overall_risk,
            blind_spots=blind_spots,
            timestamp=now_iso,
        )


_analyzer_instance: Optional[BlindSpotAnalyzer] = None


def get_blind_spot_analyzer() -> BlindSpotAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BlindSpotAnalyzer()
    return _analyzer_instance
