"""
Border Intelligence Natural-Language Surveillance Intelligence API Module.
Provides REST API endpoint POST /api/intelligence/query for operator intelligence queries.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.intelligence.assistant import (
    GroundedQueryResponse,
    SurveillanceAssistant,
    get_surveillance_assistant,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


class IntelligenceQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural-language question from operator")
    camera_id: Optional[str] = Field(None, description="Optional camera ID filter")
    start_time: Optional[datetime] = Field(None, description="Optional start timestamp filter")
    end_time: Optional[datetime] = Field(None, description="Optional end timestamp filter")


class IntelligenceQueryResponse(BaseModel):
    query: str
    status: str
    observed_facts: List[str]
    rule_results: List[str]
    interpretation: str
    evidence: List[Dict[str, Any]]
    grounding_status: str


@router.post("/query", response_model=IntelligenceQueryResponse)
async def query_surveillance_intelligence(
    request: IntelligenceQueryRequest,
    assistant: SurveillanceAssistant = Depends(get_surveillance_assistant),
) -> Dict[str, Any]:
    """
    Operator Natural-Language Intelligence Query Endpoint:
    Receives an operator question, retrieves grounded records from SQLite EventStore,
    applies guardrails against hallucinated claims, and returns a structured 3-tier response.
    """
    response: GroundedQueryResponse = await assistant.answer_query(
        query=request.query,
        camera_id=request.camera_id,
        start_time=request.start_time,
        end_time=request.end_time,
    )
    return response.to_dict()


@router.get("/blind-spots")
async def get_predicted_blind_spots():
    """Evaluate surveillance perimeter coverage gaps, sensor occlusion, and predicted blind spots."""
    from backend.intelligence.blind_spots import get_blind_spot_analyzer
    analyzer = get_blind_spot_analyzer()
    report = await analyzer.analyze_coverage()
    return report.to_dict()
