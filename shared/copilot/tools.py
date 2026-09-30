"""
PERCEPTA SHARED COPILOT GROUNDED TOOLS
Formal schemas and execution protocol for grounded Defence Intelligence retrieval.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


COPILOT_TOOL_DEFINITIONS = [
    {
        "name": "get_incident",
        "description": "Retrieve comprehensive details for a specific incident by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "The unique incident identifier"}
            },
            "required": ["incident_id"]
        }
    },
    {
        "name": "search_incidents",
        "description": "Query historical or active incidents matching filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Optional camera filter"},
                "severity": {"type": "string", "enum": ["CRITICAL", "RESTRICTED", "NORMAL"]},
                "status": {"type": "string", "enum": ["ACTIVE", "ACKNOWLEDGED", "RESOLVED", "HISTORICAL"]},
                "limit": {"type": "integer", "default": 5}
            }
        }
    },
    {
        "name": "get_camera_trust",
        "description": "Retrieve the Camera Trust Sensor optical health, score, and factors.",
        "parameters": {
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera ID (e.g., CAM-01)"}
            },
            "required": ["camera_id"]
        }
    },
    {
        "name": "get_pathguard_events",
        "description": "Retrieve PathGuard route integrity violation events.",
        "parameters": {
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera ID"}
            }
        }
    },
    {
        "name": "get_blind_spots",
        "description": "Retrieve predicted perimeter blind spots and coverage gaps.",
        "parameters": {
            "type": "object",
            "properties": {
                "camera_id": {"type": "string", "description": "Camera ID"}
            }
        }
    },
    {
        "name": "get_system_status",
        "description": "Retrieve global C2 platform operational telemetry and device metrics.",
        "parameters": {"type": "object", "properties": {}}
    }
]


class CopilotQueryRequest(BaseModel):
    query: str
    camera_id: Optional[str] = None
    session_id: Optional[str] = None
    mode: str = "auto"  # "auto", "local", "cloud"


class CopilotQueryResponse(BaseModel):
    answer: str
    observed_data: Dict[str, Any] = Field(default_factory=dict)
    tools_called: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    grounded: bool = True
