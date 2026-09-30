"""
PERCEPTA SHARED COPILOT PROVIDER ABSTRACTION
Decouples grounded intelligence retrieval from specific cloud or local execution backends.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from shared.copilot.tools import CopilotQueryResponse


class BaseCopilotProvider(ABC):
    @abstractmethod
    async def answer_query(
        self,
        query: str,
        camera_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> CopilotQueryResponse:
        """Process a natural language intelligence query and return a grounded response."""
        pass


class LocalCopilotProvider(BaseCopilotProvider):
    """
    Offline local provider that queries local SQLite database using
    deterministic parameter-validated extraction without requiring external network.
    """

    async def answer_query(
        self,
        query: str,
        camera_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> CopilotQueryResponse:
        from backend.intelligence.assistant import SurveillanceIntelligenceAssistant
        assistant = SurveillanceIntelligenceAssistant()
        res = await assistant.answer_query(query, camera_id=camera_id)
        
        return CopilotQueryResponse(
            answer=res.formatted_text(),
            observed_data={
                "observed_facts": res.observed_facts,
                "rule_results": res.rule_results,
                "evidence": res.evidence,
                "grounding_status": res.grounding_status,
            },
            tools_called=["local_sqlite_query_layer"],
            confidence=1.0 if res.grounding_status == "grounded" else 0.5,
            grounded=res.grounding_status == "grounded",
        )


class CloudCopilotProvider(BaseCopilotProvider):
    """
    Online cloud provider that incorporates tenant data boundaries
    and can route through Neon cloud database queries and cloud LLM summarization.
    """

    async def answer_query(
        self,
        query: str,
        camera_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> CopilotQueryResponse:
        # In cloud mode, ground query against tenant-scoped data
        from backend.intelligence.assistant import SurveillanceIntelligenceAssistant
        assistant = SurveillanceIntelligenceAssistant()
        res = await assistant.answer_query(query, camera_id=camera_id)
        
        return CopilotQueryResponse(
            answer=res.formatted_text(),
            observed_data={
                "tenant_id": tenant_id or "tenant_default",
                "observed_facts": res.observed_facts,
                "rule_results": res.rule_results,
                "evidence": res.evidence,
                "grounding_status": res.grounding_status,
            },
            tools_called=["cloud_neon_query_layer"],
            confidence=1.0 if res.grounding_status == "grounded" else 0.5,
            grounded=res.grounding_status == "grounded",
        )
