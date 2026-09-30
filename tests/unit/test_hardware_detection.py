"""
Unit tests for safe GPU / CPU hardware auto-detection and offline fallback.
"""
from unittest.mock import patch
import pytest

from backend.detection.model_loader import detect_hardware_device


def test_detect_hardware_device_cpu_explicit():
    device, gpu_available, gpu_name = detect_hardware_device(preference="cpu")
    assert device == "cpu"
    assert isinstance(gpu_available, bool)


def test_detect_hardware_device_cuda_fallback_when_unavailable():
    with patch("torch.cuda.is_available", return_value=False):
        device, gpu_available, gpu_name = detect_hardware_device(preference="cuda")
        assert device == "cpu"
        assert gpu_available is False
        assert gpu_name == "N/A"


def test_detect_hardware_device_cuda_when_available():
    with patch("torch.cuda.is_available", return_value=True), \
         patch("torch.cuda.get_device_name", return_value="NVIDIA RTX 4090"):
        device, gpu_available, gpu_name = detect_hardware_device(preference="auto")
        assert device == "cuda"
        assert gpu_available is True
        assert "NVIDIA" in gpu_name


def test_detect_hardware_device_handles_exception_safely():
    with patch("torch.cuda.is_available", side_effect=RuntimeError("Driver missing")):
        device, gpu_available, gpu_name = detect_hardware_device(preference="auto")
        assert device == "cpu"
        assert gpu_available is False
