"""
Border Intelligence Camera Manager Module.
Centralized registry and lifecycle manager for multi-camera video streams,
supporting video files, RTSP streams, webcams, and simulation adapters with
health tracking, dropped-frame accounting, and automatic reconnection backoff.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional
import numpy as np

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData, SensorAdapter
from backend.ingestion.video_adapter import VideoFileAdapter

logger = logging.getLogger(__name__)


class CameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class CameraRecord:
    """Metadata and operational telemetry for a registered camera stream."""
    camera_id: str
    name: str
    source_type: SourceType
    adapter: SensorAdapter
    modality: str = "STANDARD"  # "STANDARD", "IR_NIGHT", "THERMAL"
    location_label: str = "Sector Border Post"
    status: CameraStatus = CameraStatus.OFFLINE
    last_seen: Optional[datetime] = None
    frames_processed: int = 0
    dropped_frames: int = 0
    reconnect_attempts: int = 0
    last_error: Optional[str] = None
    latest_frame: Optional[FrameData] = None

    def to_dict(self) -> Dict[str, Any]:
        info = self.adapter.get_stream_info() if hasattr(self.adapter, "get_stream_info") else {}
        cam_type = "RGB"
        if str(self.modality).upper() in ("IR_NIGHT", "IR"):
            cam_type = "IR"
        elif str(self.modality).upper() in ("THERMAL",):
            cam_type = "THERMAL"
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            "source_type": self.source_type.value if hasattr(self.source_type, "value") else str(self.source_type),
            "modality": self.modality,
            "camera_type": cam_type,
            "location_label": self.location_label,
            "status": self.status.value,
            "resolution": info.get("resolution", f"{info.get('width', 1280)}x{info.get('height', 720)}"),
            "native_fps": info.get("native_fps", 30.0),
            "fps": info.get("fps", 30.0),
            "frames_processed": self.frames_processed,
            "dropped_frames": self.dropped_frames,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "is_running": self.adapter.is_running if hasattr(self.adapter, "is_running") else False,
            "video_path": str(getattr(self.adapter, "video_path", "")) if getattr(self.adapter, "video_path", None) else None,
            "replay_url": f"/api/cameras/{self.camera_id}/replay" if getattr(self.adapter, "video_path", None) else None,
        }


class CameraManager:
    """Central registry managing all active camera feeds and adapters."""

    def __init__(self) -> None:
        self._cameras: Dict[str, CameraRecord] = {}
        self._lock = asyncio.Lock()

    def register_camera(
        self,
        camera_id: str,
        adapter: SensorAdapter,
        name: Optional[str] = None,
        location_label: str = "Sector Border Post",
        modality: str = "STANDARD",
        source_type: Optional[SourceType] = None,
        camera_type: Optional[str] = None,
        **kwargs: Any,
    ) -> CameraRecord:
        """Register a new camera adapter and allocate its operational record."""
        clean_id = str(camera_id).strip()
        cam_name = name or f"Camera {clean_id}"
        src = source_type or adapter.source

        if camera_type:
            ct = str(camera_type).upper()
            if ct in ("IR", "IR_NIGHT"):
                mod = "IR_NIGHT"
            elif ct == "THERMAL":
                mod = "THERMAL"
            else:
                mod = modality or getattr(adapter, "modality", "STANDARD")
        else:
            mod = modality or getattr(adapter, "modality", "STANDARD")

        record = CameraRecord(
            camera_id=clean_id,
            name=cam_name,
            source_type=src,
            adapter=adapter,
            modality=mod,
            location_label=location_label,
            status=CameraStatus.ONLINE if adapter.is_running else CameraStatus.OFFLINE,
        )
        self._cameras[clean_id] = record
        logger.info(f"Registered camera '{clean_id}' ({cam_name}) [Modality: {mod}] in CameraManager")
        return record

    async def deregister_camera(self, camera_id: str) -> bool:
        """Stop and remove a camera from the registry."""
        clean_id = str(camera_id).strip()
        record = self._cameras.get(clean_id)
        if not record:
            return False

        if record.adapter.is_running:
            await record.adapter.stop()
        del self._cameras[clean_id]
        logger.info(f"Deregistered camera '{clean_id}' from CameraManager")
        return True

    async def start_camera(self, camera_id: str) -> bool:
        """Start a specific camera stream adapter."""
        clean_id = str(camera_id).strip()
        record = self._cameras.get(clean_id)
        if not record:
            logger.warning(f"Cannot start camera '{clean_id}': not found in registry")
            return False

        try:
            await record.adapter.start()
            record.status = CameraStatus.ONLINE
            record.last_seen = datetime.now(timezone.utc)
            logger.info(f"Camera '{clean_id}' successfully started")
            return True
        except Exception as err:
            record.status = CameraStatus.ERROR
            record.last_error = str(err)
            logger.error(f"Failed to start camera '{clean_id}': {err}")
            return False

    async def stop_camera(self, camera_id: str) -> bool:
        """Stop a specific camera stream adapter."""
        clean_id = str(camera_id).strip()
        record = self._cameras.get(clean_id)
        if not record:
            return False

        try:
            await record.adapter.stop()
            record.status = CameraStatus.OFFLINE
            logger.info(f"Camera '{clean_id}' successfully stopped")
            return True
        except Exception as err:
            logger.error(f"Error stopping camera '{clean_id}': {err}")
            return False

    def get_running_cameras(self) -> List[str]:
        """Return list of camera IDs that are currently running/streaming."""
        return [cid for cid, rec in self._cameras.items() if rec.adapter and rec.adapter.is_running]

    async def reconnect_camera(self, camera_id: str, max_retries: int = 3, base_delay: float = 0.5) -> bool:
        """Attempt to reconnect and re-initialize a degraded or dropped camera stream with exponential backoff."""
        clean_id = str(camera_id).strip()
        record = self._cameras.get(clean_id)
        if not record:
            return False

        record.status = CameraStatus.RECONNECTING
        logger.info(f"Initiating reconnect sequence for camera '{clean_id}' (max {max_retries} attempts)")

        for attempt in range(1, max_retries + 1):
            record.reconnect_attempts += 1
            try:
                if record.adapter.is_running:
                    await record.adapter.stop()
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
                await record.adapter.start()
                record.status = CameraStatus.ONLINE
                record.last_seen = datetime.now(timezone.utc)
                record.last_error = None
                logger.info(f"Camera '{clean_id}' successfully reconnected on attempt {attempt}")
                return True
            except Exception as err:
                record.last_error = str(err)
                logger.warning(f"Reconnect attempt {attempt}/{max_retries} for camera '{clean_id}' failed: {err}")

        record.status = CameraStatus.ERROR
        logger.error(f"Camera '{clean_id}' failed to reconnect after {max_retries} attempts")
        return False

    def get_camera(self, camera_id: str) -> Optional[CameraRecord]:
        """Get camera record by camera_id."""
        return self._cameras.get(str(camera_id).strip())

    def get_adapter(self, camera_id: str) -> Optional[SensorAdapter]:
        """Get camera adapter by camera_id."""
        rec = self.get_camera(camera_id)
        return rec.adapter if rec else None

    def list_cameras(self) -> List[Dict[str, Any]]:
        """List all registered cameras as dictionaries."""
        return [rec.to_dict() for rec in self._cameras.values()]

    async def get_latest_frame(self, camera_id: str) -> Optional[FrameData]:
        """
        Fetch next frame from camera and update telemetry.

        Adapters backed by `cv2.VideoCapture` expose `read_frame_blocking()`; that
        call is dispatched to a worker thread so a slow disk or stalled RTSP socket
        cannot freeze the event loop (and with it every MJPEG client and WebSocket).

        NOTE: this advances the source by one frame, so exactly one component per
        camera may call it. The per-camera perception worker owns that role; other
        consumers should read the worker's published annotated frame instead.
        """
        record = self.get_camera(camera_id)
        if not record or not record.adapter.is_running:
            return None

        try:
            blocking_reader = getattr(record.adapter, "read_frame_blocking", None)
            if blocking_reader is not None:
                frame = await asyncio.to_thread(blocking_reader)
            else:
                frame = await record.adapter.get_next_frame()

            if frame is not None:
                record.frames_processed += 1
                record.last_seen = frame.timestamp
                record.latest_frame = frame
                record.status = CameraStatus.ONLINE
                return frame
            else:
                record.dropped_frames += 1
                return None
        except Exception as err:
            record.status = CameraStatus.DEGRADED
            record.last_error = str(err)
            logger.warning(f"Error reading frame from camera '{camera_id}': {err}")
            return None

    async def stop_all(self) -> None:
        """Gracefully stop all running camera streams."""
        for cid in list(self._cameras.keys()):
            await self.stop_camera(cid)


global_camera_manager = CameraManager()


def get_camera_manager() -> CameraManager:
    return global_camera_manager
