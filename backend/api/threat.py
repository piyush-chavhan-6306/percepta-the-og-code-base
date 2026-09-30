"""
Border Intelligence Threat Level REST API.
Provides endpoints for querying real-time sector threat levels and threat matrices.
"""
from typing import Optional
from fastapi import APIRouter, Query

from backend.intelligence.threat_engine import ThreatAssessment, get_threat_engine

router = APIRouter(prefix="/api/threat", tags=["Threat Assessment"])


@router.get("/level", response_model=ThreatAssessment)
async def get_threat_level(
    camera_id: Optional[str] = Query(None, description="Optional camera ID filter"),
    lookback_seconds: int = Query(60, ge=10, le=3600, description="Rolling time window in seconds"),
) -> ThreatAssessment:
    """
    Retrieve real-time situational Threat Level & DEFCON Assessment.
    Aggregates active breaches, loitering dwell, and persistent tracks from verified SQLite logs.
    """
    engine = get_threat_engine()
    return await engine.evaluate_threat(camera_id=camera_id, lookback_seconds=lookback_seconds)
