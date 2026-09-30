"""
PERCEPTA SHARED SEVERITY ENGINE
Authoritative Single Source of Truth for Threat Classification.

Strict Classification Rules:
- Threat Score >= 60 -> CRITICAL
- Threat Score >= 25 -> RESTRICTED
- Threat Score < 25  -> NORMAL
"""
from typing import Literal

SeverityLevel = Literal["NORMAL", "RESTRICTED", "CRITICAL"]

CRITICAL_THRESHOLD: float = 60.0
RESTRICTED_THRESHOLD: float = 25.0


def calculate_severity(threat_score: float) -> SeverityLevel:
    """
    Deterministically computes authoritative severity level from a threat score.
    Must be used consistently across all backend modules, databases, and UI sync.
    """
    if threat_score >= CRITICAL_THRESHOLD:
        return "CRITICAL"
    elif threat_score >= RESTRICTED_THRESHOLD:
        return "RESTRICTED"
    return "NORMAL"


def normalize_severity(severity_str: str | None, threat_score: float | None = None) -> SeverityLevel:
    """
    Normalizes a severity string or computes it from threat_score if available.
    """
    if threat_score is not None:
        return calculate_severity(threat_score)
    
    if not severity_str:
        return "NORMAL"
    
    s = str(severity_str).strip().upper()
    if s in ("CRITICAL", "RESTRICTED", "NORMAL"):
        return s  # type: ignore
    return "NORMAL"
