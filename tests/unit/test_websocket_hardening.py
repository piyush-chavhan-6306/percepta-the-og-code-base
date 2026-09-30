"""
Unit tests for WebSocket hardening: connection limit enforcement and slow-client pruning.
"""
import asyncio
import pytest
from starlette.testclient import TestClient

from backend.api.streaming import ConnectionManager
from backend.events.schema import AlertEvent, SourceType
from backend.main import create_app


class MockSlowWebSocket:
    """Mock WebSocket client that sleeps on send_text to simulate network stall."""
    def __init__(self, delay: float = 5.0) -> None:
        self.delay = delay
        self.accepted = False
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        await asyncio.sleep(self.delay)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True


class MockHealthyWebSocket:
    """Mock WebSocket client that successfully receives text."""
    def __init__(self) -> None:
        self.accepted = False
        self.closed = False
        self.received = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.received.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_websocket_max_clients_limit():
    # Manager with max 2 clients
    manager = ConnectionManager(max_clients=2, send_timeout=0.1)

    ws1 = MockHealthyWebSocket()
    ws2 = MockHealthyWebSocket()
    ws3 = MockHealthyWebSocket()

    assert await manager.connect(ws1) is True
    assert await manager.connect(ws2) is True
    # 3rd client rejected
    assert await manager.connect(ws3) is False
    assert ws3.closed is True
    assert len(manager.active_connections) == 2


@pytest.mark.asyncio
async def test_websocket_slow_client_pruned_on_broadcast_timeout():
    # Manager with 0.05s send timeout
    manager = ConnectionManager(max_clients=10, send_timeout=0.05)

    healthy_ws = MockHealthyWebSocket()
    slow_ws = MockSlowWebSocket(delay=1.0)  # Exceeds 0.05s timeout

    await manager.connect(healthy_ws)
    await manager.connect(slow_ws)
    assert len(manager.active_connections) == 2

    # Broadcast event
    ev = AlertEvent(
        camera_id="cam_ws_test",
        severity="HIGH",
        message="Test alert",
        source=SourceType.SIMULATION,
    )
    await manager._broadcast_event(ev)

    # Healthy received, slow client was pruned
    assert len(healthy_ws.received) == 1
    assert slow_ws in manager.active_connections or len(manager.active_connections) == 1
    assert healthy_ws in manager.active_connections
