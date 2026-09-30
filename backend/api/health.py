"""
Border Intelligence Health API Module.
Returns overall system status, database connectivity, and camera status.
"""
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db_session

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """Health check endpoint validating API and database connectivity (Liveness probe)."""
    db_status = "connected"
    try:
        await session.execute(text("SELECT 1;"))
    except Exception as err:
        db_status = f"unhealthy: {str(err)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": "Border Intelligence AI Layer",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "mode": "P0_CORE",
    }


@router.get("/readiness")
async def readiness_check(session: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """Readiness probe checking database, model weights on disk, directories, and subsystems."""
    from pathlib import Path
    from backend.config import get_settings
    from backend.detection.model_loader import ModelLoader
    from backend.ingestion.camera_manager import get_camera_manager

    settings = get_settings()
    checks = {
        "database_connected": False,
        "model_file_present": False,
        "storage_directories": False,
        "camera_subsystem": False,
    }

    try:
        await session.execute(text("SELECT 1;"))
        checks["database_connected"] = True
    except Exception:
        checks["database_connected"] = False

    try:
        loader = ModelLoader(models_dir=settings.MODELS_DIR, default_model=settings.YOLO_MODEL_NAME)
        checks["model_file_present"] = loader.is_model_cached()
    except Exception:
        checks["model_file_present"] = False

    try:
        checks["storage_directories"] = (
            Path(settings.EVIDENCE_DIR).exists() and Path(settings.DATASETS_DIR).exists()
        )
    except Exception:
        checks["storage_directories"] = False

    try:
        mgr = get_camera_manager()
        checks["camera_subsystem"] = mgr is not None
    except Exception:
        checks["camera_subsystem"] = False

    all_ready = all(checks.values())

    return {
        "status": "ready" if all_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
