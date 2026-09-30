"""
Unit tests for TrackingPipeline performance metrics, telemetry, and frame skipping.
"""
import pytest
from datetime import datetime, timezone
import numpy as np

from backend.events.schema import SourceType
from backend.ingestion.adapter import FrameData
from backend.tracking.pipeline import TrackingPipeline


@pytest.mark.asyncio
async def test_tracking_pipeline_metrics_and_telemetry():
    pipeline = TrackingPipeline(frame_stride=1)
    pipeline.initialize()

    # Initial metrics
    metrics = pipeline.get_metrics()
    assert metrics["frames_processed"] == 0
    assert metrics["frame_stride"] == 1
    assert "inference_latency_ms" in metrics
    assert "tracking_latency_ms" in metrics

    # Process a synthetic frame
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = FrameData(
        camera_id="cam_metric_test",
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        image=img,
        width=640,
        height=480,
        fps=30.0,
        source=SourceType.SIMULATION,
    )

    result = await pipeline.process_frame(frame)
    assert result.frame_number == 1
    assert result.total_latency_ms >= 0.0

    updated_metrics = pipeline.get_metrics()
    assert updated_metrics["frames_processed"] == 1
    assert updated_metrics["processing_fps"] >= 0.0


@pytest.mark.asyncio
async def test_tracking_pipeline_frame_stride_skipping():
    pipeline = TrackingPipeline(frame_stride=2)  # Skip odd frames (process only frame_number % 2 == 0)
    pipeline.initialize()

    img = np.zeros((480, 640, 3), dtype=np.uint8)
    f1 = FrameData(
        camera_id="cam_stride",
        frame_number=1,
        timestamp=datetime.now(timezone.utc),
        image=img,
        width=640,
        height=480,
        fps=30.0,
        source=SourceType.SIMULATION,
    )
    f2 = FrameData(
        camera_id="cam_stride",
        frame_number=2,
        timestamp=datetime.now(timezone.utc),
        image=img,
        width=640,
        height=480,
        fps=30.0,
        source=SourceType.SIMULATION,
    )

    # Frame 1 is the keyframe (processed with detector)
    r1 = await pipeline.process_frame(f1)
    assert r1.frame_number == 1

    # Frame 2 is skipped from heavy detector inference
    r2 = await pipeline.process_frame(f2)
    assert r2.frame_number == 2
    assert r2.inference_latency_ms == 0.0  # Skipped
