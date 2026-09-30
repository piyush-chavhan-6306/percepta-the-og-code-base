"""
Unit tests for system metrics, watchdog telemetry, and hardware observability endpoints.
"""
import pytest
from starlette.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_system_status_endpoint_telemetry(client):
    response = client.get("/api/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "device" in data
    assert "gpu_available" in data
    assert "gpu_device_name" in data
    assert "database" in data
    assert "version" in data


def test_system_metrics_watchdog_endpoint(client):
    response = client.get("/api/system/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "uptime_seconds" in data
    assert "hardware" in data
    assert "performance" in data
    assert "telemetry" in data
    assert "cameras" in data
    assert "capture_fps" in data
    assert "ai_processing_fps" in data
    assert "display_fps" in data
    assert "effective_visual_fps" in data
    assert "inference_latency_ms" in data
    assert "tracking_latency_ms" in data
    assert "prediction_latency_ms" in data
    assert "persistence_latency_ms" in data
    assert "encoding_latency_ms" in data
    assert "total_pipeline_latency_ms" in data
    assert "memory_usage_mb" in data
    assert "processed_frames" in data
    assert "dropped_frames" in data
    assert "alerts" in data

    hw = data["hardware"]
    assert "device" in hw
    assert "gpu_available" in hw

    perf = data["performance"]
    assert "target_fps" in perf
    assert "default_frame_stride" in perf
    assert "adaptive_stride_enabled" in perf
