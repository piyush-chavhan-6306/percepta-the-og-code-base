"""
Border Intelligence Object Detector Module.
Wraps YOLOv8n for fast, explainable surveillance object detection with CPU/CUDA support
and direct integration with the EventStore and EventBus.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set
import numpy as np

from backend.events.schema import DetectionEvent, EventType, SourceType
from backend.events.store import EventStore, get_event_store
from backend.ingestion.adapter import FrameData
from backend.detection.model_loader import ModelLoader, get_model_loader

logger = logging.getLogger(__name__)

# Default surveillance target classes of interest (COCO mappings)
DEFAULT_SURVEILLANCE_CLASSES = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    4: "airplane",  # Drone / aerial surrogate in default COCO
    5: "bus",
    6: "train",
    7: "truck",
    8: "boat",
}


@dataclass
class DetectionResult:
    """Standardized detection result for downstream tracker and zone evaluator."""
    class_id: int
    class_name: str
    confidence: float
    bounding_box: List[float]  # [x1, y1, x2, y2]
    normalized_box: List[float]  # [nx1, ny1, nx2, ny2] (0.0 to 1.0)


class ObjectDetector:
    """
    Synchronous YOLOv8 object detector for surveillance video frames.
    """

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        target_classes: Optional[Dict[int, str]] = None,
        device: str = "cpu",
        imgsz: Optional[int] = None,
        model_loader: Optional[ModelLoader] = None,
        event_store: Optional[EventStore] = None,
    ) -> None:
        self.model_name = model_name
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.target_classes = target_classes or DEFAULT_SURVEILLANCE_CLASSES
        self.target_class_ids = list(self.target_classes.keys())
        self.device = device
        if imgsz is not None:
            self.imgsz = imgsz
        else:
            from backend.config import get_settings
            self.imgsz = get_settings().DEFAULT_INFERENCE_SIZE
        self.loader = model_loader or get_model_loader()
        self.event_store = event_store or get_event_store()

        self._model = None
        self._is_initialized = False

    def initialize(self) -> None:
        """Load and initialize model weights, then warm the inference graph."""
        if not self._is_initialized:
            import torch
            try:
                if hasattr(torch.backends, "mkldnn"):
                    torch.backends.mkldnn.enabled = True
            except Exception:
                pass
            self._model = self.loader.load_model(self.model_name, device=self.device)
            model_str = str(getattr(self._model, "overrides", {}).get("model", "")) or str(getattr(self._model, "ckpt", ""))
            if "onnx" in model_str.lower() or str(getattr(self._model, "model_name", "")).endswith(".onnx"):
                self.imgsz = 320
            self._is_initialized = True
            logger.info(f"ObjectDetector initialized with {self.model_name} on {self.device} (imgsz={self.imgsz})")
            self.warmup()

    def warmup(self, iterations: int = 2) -> float:
        """
        Run throwaway inferences so the first real frame does not pay setup cost.

        Ultralytics builds its predictor lazily on the first call: warmup allocates
        the tensors, resolves the fuse/stride config, and lets the CPU kernels pick
        their algorithms. That work costs several hundred ms to seconds and used to
        land on the operator's first frame as a visible stall right when a demo
        starts. Paying it here moves the pause to boot, where nobody is watching.

        Returns the last warmup inference time in milliseconds (0.0 if it failed).
        """
        if self._model is None:
            return 0.0

        blank = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        elapsed_ms = 0.0
        try:
            for _ in range(max(1, iterations)):
                started = time.perf_counter()
                self.detect(blank)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
        except Exception as err:
            # A failed warmup must never stop the server from booting -- the first
            # real frame will simply pay the cost instead.
            logger.warning(f"Detector warmup failed (non-fatal): {err}")
            return 0.0

        logger.info(f"Detector warmup complete: steady-state inference ~{elapsed_ms:.1f} ms")
        return elapsed_ms

    def detect(self, image: np.ndarray) -> List[DetectionResult]:
        """
        Run inference on a raw BGR image array.
        Returns a list of DetectionResults filtered by target classes and confidence.
        """
        if not self._is_initialized:
            self.initialize()

        if image is None or not isinstance(image, np.ndarray) or image.size == 0:
            return []

        h, w = image.shape[:2]
        if h == 0 or w == 0:
            return []

        # Detect whether we're running ONNX or PyTorch backend
        model_str = str(getattr(self._model, "overrides", {}).get("model", "")) or str(getattr(self._model, "ckpt", ""))
        is_onnx = "onnx" in model_str.lower() or str(getattr(self._model, "model_name", "")).endswith(".onnx")
        run_imgsz = 320 if is_onnx else self.imgsz

        if is_onnx:
            # ONNX Runtime handles its own optimization — no torch context needed
            results = self._model(
                image,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                classes=self.target_class_ids,
                imgsz=run_imgsz,
                verbose=False,
            )
        else:
            import torch
            with torch.inference_mode():
                results = self._model(
                    image,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    classes=self.target_class_ids,
                    imgsz=self.imgsz,
                    verbose=False,
                    device=self.device,
                )

        detections: List[DetectionResult] = []

        for r in results:
            boxes = r.boxes
            if boxes is None or len(boxes) == 0:
                continue

            # Batch extract tensors to numpy on CPU for fast conversion
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            confs = boxes.conf.cpu().numpy()
            xyxy_arr = boxes.xyxy.cpu().numpy()

            for i in range(len(cls_ids)):
                cls_id = int(cls_ids[i])
                conf = float(confs[i])

                if cls_id in self.target_classes and conf >= self.conf_threshold:
                    cls_name = self.target_classes[cls_id]
                    x1, y1, x2, y2 = xyxy_arr[i]

                    # Calculate normalized coordinates
                    nx1 = max(0.0, min(1.0, float(x1) / w))
                    ny1 = max(0.0, min(1.0, float(y1) / h))
                    nx2 = max(0.0, min(1.0, float(x2) / w))
                    ny2 = max(0.0, min(1.0, float(y2) / h))

                    detections.append(
                        DetectionResult(
                            class_id=cls_id,
                            class_name=cls_name,
                            confidence=round(conf, 4),
                            bounding_box=[round(float(x1), 2), round(float(y1), 2), round(float(x2), 2), round(float(y2), 2)],
                            normalized_box=[round(nx1, 4), round(ny1, 4), round(nx2, 4), round(ny2, 4)],
                        )
                    )

        return detections

    async def detect_frame(
        self,
        frame: FrameData,
        emit_events: bool = True,
    ) -> tuple[List[DetectionResult], List[DetectionEvent]]:
        """
        Process a FrameData package, execute detection, and emit typed DetectionEvents.
        Returns (detections, emitted_events).
        """
        raw_detections = self.detect(frame.image)
        emitted_events: List[DetectionEvent] = []

        if not raw_detections:
            return [], []

        for det in raw_detections:
            event = DetectionEvent(
                camera_id=frame.camera_id,
                object_class=det.class_name,
                bounding_box=det.bounding_box,
                frame_number=frame.frame_number,
                confidence=det.confidence,
                source=frame.source,
                timestamp=frame.timestamp,
            )

            if emit_events:
                await self.event_store.record_event(event)

            emitted_events.append(event)

        return raw_detections, emitted_events


global_detector: Optional[ObjectDetector] = None


def get_detector() -> ObjectDetector:
    """
    Return the process-wide detector, configured from settings.

    This used to be a bare ``ObjectDetector()``, which meant the constructor
    defaults won every time: inference always ran on "cpu" at imgsz=640 with
    conf=0.25/iou=0.45, and DEVICE / DEFAULT_INFERENCE_SIZE /
    CONFIDENCE_THRESHOLD / IOU_THRESHOLD in config.py were dead knobs -- tuning
    them changed nothing, while /api/system/metrics separately reported the
    *configured* device and so could claim "cuda" while the detector ran on CPU.
    Resolving them here makes the configuration real and keeps the reported
    device honest.
    """
    global global_detector
    if global_detector is None:
        from backend.config import get_settings
        from backend.detection.model_loader import detect_hardware_device

        settings = get_settings()
        selected_device, _gpu_available, _gpu_name = detect_hardware_device(settings.DEVICE)
        _apply_torch_thread_limit(settings.TORCH_NUM_THREADS)

        global_detector = ObjectDetector(
            model_name=settings.YOLO_MODEL_NAME,
            conf_threshold=settings.CONFIDENCE_THRESHOLD,
            iou_threshold=settings.IOU_THRESHOLD,
            device=selected_device,
            imgsz=settings.DEFAULT_INFERENCE_SIZE,
        )
    return global_detector


def _apply_torch_thread_limit(num_threads: int) -> None:
    """
    Pin torch's intra-op thread count when configured.

    Inference runs inside ``asyncio.to_thread``, so torch's own pool, the asyncio
    executor, and OpenCV's threads all compete for the same cores. Left to
    itself torch grabs every core, which on a busy box shows up as frame-time
    jitter rather than a higher average rate. 0 means "leave torch alone".
    """
    if num_threads <= 0:
        return
    try:
        import torch

        torch.set_num_threads(num_threads)
        logger.info(f"torch intra-op threads pinned to {num_threads}")
    except Exception as err:
        logger.warning(f"Could not set torch thread count to {num_threads}: {err}")
