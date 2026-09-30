"""
Unit tests for CameraManager auto-reconnect logic and exponential backoff retry.
"""
import pytest
from backend.ingestion.camera_manager import CameraManager, CameraStatus
from backend.ingestion.simulation_adapter import SimulationAdapter


class FlakySimulationAdapter(SimulationAdapter):
    """Simulation adapter that fails on first N start attempts, then succeeds."""
    def __init__(self, camera_id: str, failures_before_success: int = 1) -> None:
        super().__init__(camera_id=camera_id)
        self.failures_before_success = failures_before_success
        self.attempts = 0

    async def start(self) -> None:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise ConnectionError(f"Temporary connection failure (attempt {self.attempts})")
        await super().start()


@pytest.mark.asyncio
async def test_camera_reconnect_success_after_retry():
    manager = CameraManager()
    # Adapter fails on attempt 1, succeeds on attempt 2
    adapter = FlakySimulationAdapter(camera_id="cam_reconnect_test", failures_before_success=1)
    manager.register_camera("cam_reconnect_test", adapter)

    # Initial start fails
    started = await manager.start_camera("cam_reconnect_test")
    assert started is False
    rec = manager.get_camera("cam_reconnect_test")
    assert rec.status == CameraStatus.ERROR

    # Reconnect succeeds on attempt 2
    reconnected = await manager.reconnect_camera("cam_reconnect_test", max_retries=3, base_delay=0.01)
    assert reconnected is True
    assert rec.status == CameraStatus.ONLINE
    assert rec.last_error is None


@pytest.mark.asyncio
async def test_camera_reconnect_fails_after_max_retries():
    manager = CameraManager()
    # Adapter always fails
    adapter = FlakySimulationAdapter(camera_id="cam_perm_fail", failures_before_success=99)
    manager.register_camera("cam_perm_fail", adapter)

    reconnected = await manager.reconnect_camera("cam_perm_fail", max_retries=2, base_delay=0.01)
    assert reconnected is False
    rec = manager.get_camera("cam_perm_fail")
    assert rec.status == CameraStatus.ERROR
    assert "Temporary connection failure" in str(rec.last_error)


@pytest.mark.asyncio
async def test_camera_reconnect_unknown_camera():
    manager = CameraManager()
    assert await manager.reconnect_camera("non_existent_cam", max_retries=1) is False
