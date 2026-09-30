"""
Border Intelligence Natural-Language Surveillance Intelligence Layer.
Provides grounded operator query understanding, parameter-validated EventStore retrieval,
and strict anti-hallucination guardrails.
"""
from backend.intelligence.assistant import SurveillanceAssistant, get_surveillance_assistant

__all__ = ["SurveillanceAssistant", "get_surveillance_assistant"]
