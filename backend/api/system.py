"""
Border Intelligence System Health & Observability REST API.
Provides real-time system metrics, latency breakdown, camera counts, and database telemetry.
"""
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

import time

from backend.config import get_settings
from backend.detection.model_loader import detect_hardware_device
from backend.events.store import get_event_store
from backend.ingestion.camera_manager import get_camera_manager
from backend.tracking.live_worker import get_worker_registry

router = APIRouter(prefix="/api/system", tags=["System Observability"])

_START_TIME = time.perf_counter()


@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """Get high-level system operating status and connectivity."""
    settings = get_settings()
    store = get_event_store()
    manager = get_camera_manager()

    db_stats = await store.get_system_stats()
    cameras = manager.list_cameras()
    active_cams = sum(1 for c in cameras if c.get("status") == "online")

    selected_dev, gpu_avail, gpu_name = detect_hardware_device(settings.DEVICE)

    return {
        "status": "online",
        "service": "Border Intelligence AI Platform",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected (SQLite WAL)",
        "mode": "P0_CORE",
        "version": settings.API_VERSION,
        "device": selected_dev,
        "gpu_available": gpu_avail,
        "gpu_device_name": gpu_name,
        "total_cameras": len(cameras),
        "active_cameras": active_cams,
        "total_events_logged": db_stats.get("total_events", 0),
        "total_alerts_logged": db_stats.get("total_alerts", 0),
    }


import psutil

@router.get("/metrics")
async def get_system_metrics() -> Dict[str, Any]:
    """Retrieve detailed telemetry on processing performance, latencies, and event rates."""
    settings = get_settings()
    store = get_event_store()
    manager = get_camera_manager()

    db_stats = await store.get_system_stats()
    cameras = manager.list_cameras()

    total_frames = sum(c.get("frames_processed", 0) for c in cameras)
    total_dropped = sum(c.get("dropped_frames", 0) for c in cameras)
    active_cams = sum(1 for c in cameras if c.get("status") == "online")

    selected_dev, gpu_avail, gpu_name = detect_hardware_device(settings.DEVICE)
    uptime_sec = round(time.perf_counter() - _START_TIME, 1)

    process = psutil.Process()
    mem_mb = round(process.memory_info().rss / (1024 * 1024), 1)

    # Rolling camera aggregate metrics
    cap_fps = round(sum(c.get("fps", 30.0) for c in cameras) / max(len(cameras), 1), 1)

    # Every performance number below is measured by the live perception workers.
    # These were previously hardcoded constants (display_fps 60.0, inference
    # 42.0 ms, ...) that reported healthy figures no matter what the system was
    # actually doing -- including when no camera was running at all.
    perf = get_worker_registry().aggregate_metrics()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime_sec,
        "device": perf.get("device", selected_dev),
        "gpu_available": gpu_avail,
        "gpu_device_name": gpu_name,
        "memory_usage_mb": mem_mb,
        "capture_fps": cap_fps,
        "ai_processing_fps": perf.get("ai_processing_fps", 0.0),
        "display_fps": perf.get("display_fps", 0.0),
        # What the operator actually sees: the annotated MJPEG output rate.
        "effective_visual_fps": perf.get("display_fps", 0.0),
        "inference_latency_ms": perf.get("inference_latency_ms", 0.0),
        "tracking_latency_ms": perf.get("tracking_latency_ms", 0.0),
        "prediction_latency_ms": perf.get("prediction_latency_ms", 0.0),
        "persistence_latency_ms": perf.get("persistence_latency_ms", 0.0),
        "encoding_latency_ms": perf.get("encoding_latency_ms", 0.0),
        "total_pipeline_latency_ms": perf.get("total_pipeline_latency_ms", 0.0),
        "frame_stride": perf.get("frame_stride", settings.DEFAULT_FRAME_STRIDE),
        "processed_frames": total_frames,
        "skipped_frames": perf.get("skipped_frames", 0),
        "predicted_frames": perf.get("predicted_frames", 0),
        "dropped_frames": total_dropped,
        "active_tracks": perf.get("active_tracks", 0),
        "alerts": db_stats.get("total_alerts", 0),
        "workers_running": perf.get("workers_running", 0),
        "hardware": {
            "device": selected_dev,
            "gpu_available": gpu_avail,
            "gpu_device_name": gpu_name,
        },
        "performance": {
            "target_fps": settings.TARGET_FPS,
            "default_frame_stride": settings.DEFAULT_FRAME_STRIDE,
            "adaptive_stride_enabled": settings.ADAPTIVE_STRIDE_ENABLED,
            "min_frame_stride": settings.MIN_FRAME_STRIDE,
            "max_frame_stride": settings.MAX_FRAME_STRIDE,
            "inference_size": settings.DEFAULT_INFERENCE_SIZE,
        },
        "telemetry": {
            "total_frames_processed": total_frames,
            "total_frames_dropped": total_dropped,
            "total_events": db_stats.get("total_events", 0),
            "total_alerts": db_stats.get("total_alerts", 0),
            "distinct_cameras": db_stats.get("distinct_cameras_logged", len(cameras)),
            "active_cameras": active_cams,
        },
        "cameras": cameras,
    }


@router.post("/demo-reset")
async def demo_reset() -> Dict[str, Any]:
    """
    Demo Reset Mechanism:
    Safely resets live camera state, in-memory buffers, and pipeline metrics for a clean judge demo.
    """
    manager = get_camera_manager()
    await manager.stop_all()
    
    # Restart registered demo cameras
    for c in manager.list_cameras():
        cid = c["camera_id"]
        await manager.start_camera(cid)

    return {
        "status": "reset_complete",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_cameras": len(manager.list_cameras()),
        "message": "Demo state reset successfully. Pipeline is primed for demonstration.",
    }


@router.get("/coverage-report")
async def get_coverage_report() -> Dict[str, Any]:
    """
    Generate fleet-wide surveillance coverage, uptime analytics, and readiness grades.
    """
    manager = get_camera_manager()
    store = get_event_store()
    cameras = manager.list_cameras()
    total_cams = len(cameras)
    active_cams = sum(1 for c in cameras if c.get("status") == "online")

    coverage_pct = round((active_cams / max(total_cams, 1)) * 100.0, 1)
    if coverage_pct >= 90.0:
        grade = "GRADE_A_COMBAT_READY"
        assessment = "Full sector coverage operational across all primary and secondary CCTV checkpoints."
    elif coverage_pct >= 70.0:
        grade = "GRADE_B_DEGRADED"
        assessment = "Minor blind spots detected due to offline or degraded sector cameras."
    else:
        grade = "GRADE_C_VULNERABLE"
        assessment = "Critical perimeter surveillance deficit. Multiple camera streams offline."

    stats = await store.get_system_stats()

    return {
        "report_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cameras_registered": total_cams,
        "active_cameras_online": active_cams,
        "sector_coverage_percentage": coverage_pct,
        "surveillance_readiness_grade": grade,
        "strategic_assessment": assessment,
        "total_events_logged": stats.get("total_events", 0),
        "total_alerts_logged": stats.get("total_alerts", 0),
        "camera_fleet_status": [
            {
                "camera_id": c["camera_id"],
                "name": c["name"],
                "status": c["status"],
                "fps": c.get("fps", 30.0),
                "frames_processed": c.get("frames_processed", 0),
                "dropped_frames": c.get("dropped_frames", 0),
            }
            for c in cameras
        ],
    }


@router.get("/profiles")
async def get_surveillance_profiles():
    """Retrieve all available environmental surveillance operation profiles and active status."""
    from backend.config_profiles import get_active_profile, list_operational_profiles
    return {
        "active_profile": get_active_profile(),
        "available_profiles": list_operational_profiles(),
    }


@router.post("/profiles/apply")
async def apply_surveillance_profile(request: dict):
    """Dynamically switch the active surveillance sensitivity profile at runtime."""
    from backend.config_profiles import set_active_profile
    profile_id = request.get("profile_id")
    if not profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'profile_id' is required",
        )
    try:
        active = set_active_profile(profile_id)
        return {"status": "applied", "active_profile": active}
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@router.get("/audit-logs")
async def get_system_audit_logs(limit: int = 100):
    """Retrieve chronological administrative audit logs."""
    from backend.events.audit_logger import get_audit_logger
    logger = get_audit_logger()
    logs = await logger.get_audit_logs(limit=limit)
    return {"count": len(logs), "audit_logs": logs}


@router.get("/db-diagnostics")
async def get_database_diagnostics():
    """Inspect SQLite WAL storage metrics and PostgreSQL migration readiness."""
    from backend.database_diagnostics import inspect_database_diagnostics
    return await inspect_database_diagnostics()
