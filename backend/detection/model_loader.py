"""
Border Intelligence Model Loader Module.
Handles offline caching and safe initialization of YOLOv8 object detection weights.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ModelLoader:
    """
    Manages local model weight caching to ensure offline-ready surveillance operation.
    """

    def __init__(self, models_dir: str = "./models", default_model: str = "yolov8n.pt") -> None:
        self.models_dir = Path(models_dir)
        self.default_model = default_model
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._cached_model = None

    def get_model_path(self, model_name: Optional[str] = None) -> Path:
        """Return the local path for a specific model weight file."""
        target_name = model_name or self.default_model
        return self.models_dir / target_name

    def is_model_cached(self, model_name: Optional[str] = None) -> bool:
        """Check if the model weight file is already cached locally."""
        return self.get_model_path(model_name).exists()

    def load_model(self, model_name: Optional[str] = None, device: str = "cpu"):
        """
        Load YOLO model from local cache or download once if not present.
        Returns the initialized YOLO model instance.
        """
        from ultralytics import YOLO

        target_name = model_name or self.default_model
        model_path = self.get_model_path(target_name)

        # On CPU, prefer optimized ONNX Runtime model if available
        onnx_path = self.models_dir / "yolov8n.onnx"
        if device == "cpu" and onnx_path.exists() and (model_name is None or "onnx" in model_name or "pt" in model_name):
            logger.info(f"Loading high-speed ONNX Runtime YOLO model: {onnx_path}")
            try:
                return YOLO(str(onnx_path), task="detect")
            except Exception as ex:
                logger.warning(f"Failed to load ONNX model ({ex}), falling back to PyTorch weights")

        if model_path.exists():
            logger.info(f"Loading cached YOLO model from: {model_path}")
            model = YOLO(str(model_path))
        else:
            logger.info(f"Downloading model {target_name} to local cache: {model_path}")
            # Ultralytics will download to target path if specified
            model = YOLO(target_name)
            # Save a copy directly into models_dir if downloaded elsewhere
            if not model_path.exists() and Path(target_name).exists():
                Path(target_name).rename(model_path)
            elif not model_path.exists():
                # If Ultralytics saved to root, copy to models_dir
                for p in Path(".").glob(f"*{target_name}*"):
                    if p.is_file() and p.name == target_name:
                        p.rename(model_path)
                        break

        # Apply device setting (CPU fallback or CUDA)
        try:
            model.to(device)
        except Exception as e:
            logger.warning(f"Failed to assign model to device '{device}', falling back to 'cpu': {e}")
            model.to("cpu")
        return model


def detect_hardware_device(preference: str = "auto") -> tuple[str, bool, str]:
    """
    Safely auto-detect available hardware (CUDA GPU vs CPU).
    Returns (selected_device, gpu_available, gpu_name).
    Never throws, safely falls back to CPU.
    """
    import torch

    gpu_available = False
    gpu_name = "N/A"

    try:
        gpu_available = bool(torch.cuda.is_available())
        if gpu_available:
            gpu_name = str(torch.cuda.get_device_name(0))
    except Exception as err:
        logger.warning(f"CUDA detection encountered error: {err}. Falling back to CPU.")
        gpu_available = False

    pref_lower = preference.lower().strip()
    if pref_lower == "cpu":
        selected_device = "cpu"
    elif pref_lower == "cuda":
        if gpu_available:
            selected_device = "cuda"
        else:
            logger.warning("CUDA requested but no CUDA device is available. Falling back to CPU.")
            selected_device = "cpu"
    else:  # "auto"
        selected_device = "cuda" if gpu_available else "cpu"

    return selected_device, gpu_available, gpu_name


# Global instance
global_model_loader = ModelLoader()


def get_model_loader() -> ModelLoader:
    return global_model_loader
