"""
Border Intelligence Real-Time Streaming Module.
Provides:
1. WebSocket (/ws/events & /api/ws/events): Live event and alert broadcast from EventBus to web clients with JWT validation.
2. MJPEG Video Stream (/api/stream/video/{camera_id}): HTTP multipart streaming for frontend video display.
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from backend.events.bus import get_event_bus
from backend.events.schema import BaseEvent
from backend.gateway.dependencies import validate_ws_token
from backend.ingestion.camera_manager import get_camera_manager
from backend.tracking.live_worker import get_worker_registry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Streaming"])


class ConnectionManager:
    """Manages active WebSocket client connections and event broadcasting with backpressure isolation."""

    def __init__(self, max_clients: int = 100, send_timeout: float = 2.0) -> None:
        self.active_connections: Set[WebSocket] = set()
        self.max_clients = max_clients
        self.send_timeout = send_timeout
        self._lock = asyncio.Lock()
        self._subscribed = False

    async def connect(self, websocket: WebSocket) -> bool:
        async with self._lock:
            if len(self.active_connections) >= self.max_clients:
                logger.warning(f"Rejecting WebSocket connection: max client limit ({self.max_clients}) reached")
                await websocket.close(code=1008, reason="Max client connection limit reached")
                return False

            await websocket.accept()
            self.active_connections.add(websocket)

        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

        # Ensure EventBus subscription is active
        if not self._subscribed:
            bus = get_event_bus()
            await bus.subscribe(self._broadcast_event)
            self._subscribed = True
        return True

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Remaining: {len(self.active_connections)}")

    async def _broadcast_event(self, event: BaseEvent) -> None:
        """Internal callback invoked by EventBus on new published event with slow-client timeout."""
        if not self.active_connections:
            return

        payload = event.model_dump_json()
        dead_connections = set()

        async with self._lock:
            for ws in list(self.active_connections):
                try:
                    await asyncio.wait_for(ws.send_text(payload), timeout=self.send_timeout)
                except Exception as err:
                    logger.warning(f"Pruning slow or disconnected WebSocket client: {err}")
                    dead_connections.add(ws)

            for dead_ws in dead_connections:
                self.active_connections.discard(dead_ws)

    async def broadcast_json(self, data: Dict[str, Any]) -> None:
        """Broadcast arbitrary JSON dictionary to all connected clients."""
        if not self.active_connections:
            return
        import json
        payload = json.dumps(data)
        dead_connections = set()
        async with self._lock:
            for ws in list(self.active_connections):
                try:
                    await asyncio.wait_for(ws.send_text(payload), timeout=self.send_timeout)
                except Exception:
                    dead_connections.add(ws)
            for dead_ws in dead_connections:
                self.active_connections.discard(dead_ws)


ws_manager = ConnectionManager()


def get_ws_manager() -> ConnectionManager:
    return ws_manager


@router.websocket("/ws/events")
@router.websocket("/api/ws/events")
async def websocket_events_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> None:
    """
    WebSocket endpoint for real-time surveillance events, alerts, and state updates.
    Validates token from ?token=<jwt> or falls back to DEMO_MODE.
    """
    user = await validate_ws_token(websocket, token)
    if not user:
        return

    connected = await ws_manager.connect(websocket)
    if not connected:
        return

    try:
        while True:
            # Keepalive listener / handle ping-pong or client requests
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type": "pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as err:
        logger.warning(f"WebSocket connection terminated: {err}")
        await ws_manager.disconnect(websocket)


_MAX_MJPEG_CLIENTS = 12
_mjpeg_clients = 0
_mjpeg_clients_lock = asyncio.Lock()


async def _mjpeg_generator(camera_id: str, startup_grace: float = 30.0):
    """
    Yield multipart MJPEG frames already annotated by the camera's perception worker.

    This deliberately does NOT read from the camera adapter. The worker owns the
    frame source; a reader here would advance the capture and steal frames from
    the worker, halving both streams. Frames are also encoded once by the worker
    and fanned out here, so a second viewer costs no extra JPEG work.

    `startup_grace` is how long to wait for a worker to publish its first frame
    (model warm-up on the first detection is slow) before giving up on the stream.
    """
    global _mjpeg_clients

    registry = get_worker_registry()
    manager = get_camera_manager()
    last_sequence = 0

    async with _mjpeg_clients_lock:
        if _mjpeg_clients >= _MAX_MJPEG_CLIENTS:
            logger.warning(
                f"Refusing MJPEG viewer for '{camera_id}': {_MAX_MJPEG_CLIENTS} client limit reached"
            )
            return
        _mjpeg_clients += 1

    try:
        loop = asyncio.get_running_loop()
        idle_since = None
        while True:
            worker = registry.get_worker(camera_id)
            if worker is None or not worker.is_running:
                cam = manager.get_camera(camera_id)
                if cam is None:
                    return
                if idle_since is None:
                    idle_since = loop.time()
                elif loop.time() - idle_since > startup_grace:
                    return
                await asyncio.sleep(min(0.05, startup_grace))
                continue

            frame = await worker.wait_for_frame(
                after_sequence=last_sequence,
                timeout=min(5.0, max(0.05, startup_grace)),
            )
            if frame is None:
                if idle_since is None:
                    idle_since = loop.time()
                elif loop.time() - idle_since > startup_grace:
                    logger.info(f"Closing idle MJPEG stream for '{camera_id}'")
                    return
                continue

            idle_since = None
            last_sequence = frame.sequence
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame.jpeg)).encode() + b"\r\n\r\n"
                + frame.jpeg + b"\r\n"
            )
    except asyncio.CancelledError:
        raise
    finally:
        async with _mjpeg_clients_lock:
            _mjpeg_clients = max(0, _mjpeg_clients - 1)


@router.get("/api/streaming/feed/{camera_id}")
@router.get("/api/stream/video/{camera_id}")
async def stream_video(camera_id: str):
    """
    MJPEG video streaming endpoint for real-time browser display.

    Serves the frames the perception worker already annotated, so the boxes the
    operator sees are burned into the exact frame they belong to — there is no
    client-side overlay that can drift out of sync with the video.
    """
    manager = get_camera_manager()
    cam = manager.get_camera(camera_id)
    if not cam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found in registry",
        )

    # A viewer arriving before the loop is up (e.g. after a server restart)
    # transparently brings it back rather than showing a dead tile.
    registry = get_worker_registry()
    worker = registry.get_worker(camera_id)
    if worker is None or not worker.is_running:
        if cam.adapter.is_running:
            await registry.start_worker(camera_id)

    return StreamingResponse(
        _mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Age": "0",
        },
    )


@router.get("/api/streaming/snapshot/{camera_id}")
@router.get("/api/stream/snapshot/{camera_id}")
async def stream_snapshot(camera_id: str):
    """Single annotated JPEG — used for alert thumbnails and quick health checks."""
    worker = get_worker_registry().get_worker(camera_id)
    if worker is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No perception worker running for camera '{camera_id}'",
        )

    frame = worker.get_latest()
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Camera '{camera_id}' has not published a frame yet",
        )

    return Response(
        content=frame.jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


def _get_media_type_for_video(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".mp4":
        return "video/mp4"
    elif ext == ".webm":
        return "video/webm"
    elif ext == ".avi":
        return "video/x-msvideo"
    elif ext == ".mov":
        return "video/quicktime"
    elif ext == ".mkv":
        return "video/x-matroska"
    return "video/mp4"


@router.get("/api/cameras/{camera_id}/replay")
@router.head("/api/cameras/{camera_id}/replay")
async def serve_camera_replay_video(camera_id: str):
    """
    Stream the actual underlying video for a specific camera with HTTP 206 Partial Content range support.
    """
    from backend.api.cameras import resolve_camera_source_video

    video_path = resolve_camera_source_video(camera_id)
    if video_path and video_path.is_file():
        return FileResponse(
            path=str(video_path),
            media_type=_get_media_type_for_video(video_path),
            filename=video_path.name,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
            },
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Replay video for camera '{camera_id}' is not available.",
    )


@router.get("/api/streaming/video/{video_name:path}")
@router.get("/api/videos/{video_name:path}")
async def serve_cctv_video(video_name: str = "virat_cctv.mp4"):
    """
    Serve any local or uploaded surveillance video with HTTP 206 Partial Content range support.
    """
    import os
    from pathlib import Path
    from fastapi.responses import FileResponse
    from backend.api.cameras import resolve_video_path

    # Try resolving through camera video search roots
    resolved = resolve_video_path(video_name)
    if resolved and Path(resolved).is_file():
        p = Path(resolved)
        return FileResponse(
            path=str(p),
            media_type=_get_media_type_for_video(p),
            filename=p.name,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=86400",
            },
        )

    candidates = [
        Path(video_name),
        Path("resources/videos") / video_name,
        Path("resources/videos/virat_cctv.mp4"),
        Path(f"storage/uploads/{video_name}"),
        Path(f"storage/feeds/{video_name}"),
        Path(f"storage/{video_name}"),
        Path(f"videos/{video_name}"),
        Path(f"frontend/public/videos/{video_name}"),
        Path("storage/virat_cctv.mp4"),
        Path("frontend/public/videos/virat_cctv.mp4"),
        Path(f"VIRAT/CCTV 01/{video_name}"),
        Path("VIRAT/CCTV 01/virat_cctv.mp4"),
        Path("VIRAT/CCTV 01/VIRAT_S_000205_02_000409_000566.mp4"),
    ]
    for cand in candidates:
        if cand.is_file():
            return FileResponse(
                path=str(cand),
                media_type=_get_media_type_for_video(cand),
                filename=cand.name,
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "public, max-age=86400",
                },
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Video file '{video_name}' not found",
    )

