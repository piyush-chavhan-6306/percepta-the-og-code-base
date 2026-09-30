"""
Border Intelligence Configuration Module.
Loads environment variables using Pydantic Settings.
"""
import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "PERCEPTA"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    API_VERSION: str = "0.1.0"
    # Explicit dev origins: the Vite dev server needs credentialed CORS, and
    # "*" is rejected by browsers when allow_credentials is on.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Gateway & Authentication (Phase 1)
    JWT_SECRET_KEY: str = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 480
    DEMO_MODE: bool = True  # True bypasses strict token checks for judge/demo walkthroughs
    RATE_LIMIT_PER_MINUTE: int = 120

    # Hardware & Model Performance Configuration
    DEVICE: str = "auto"  # "auto", "cpu", "cuda"
    DEFAULT_INFERENCE_SIZE: int = 480
    CONFIDENCE_THRESHOLD: float = 0.25
    IOU_THRESHOLD: float = 0.45
    TORCH_NUM_THREADS: int = 4
    TARGET_FPS: float = 25.0
    MIN_FRAME_STRIDE: int = 1
    MAX_FRAME_STRIDE: int = 4
    DEFAULT_FRAME_STRIDE: int = 2
    ADAPTIVE_STRIDE_ENABLED: bool = True
    PERFORMANCE_SAMPLE_WINDOW: int = 15
    STRIDE_COOLDOWN_FRAMES: int = 30

    # Live perception
    AUTOSTART_DEMO_CAMERA: bool = False
    MJPEG_JPEG_QUALITY: int = 40
    MAX_MJPEG_CLIENTS: int = 16

    # Dynamic Application Directories (Safe for Windows Installed Apps)
    PERCEPTA_INSTALL_DIR: str = os.environ.get("PERCEPTA_INSTALL_DIR", str(Path(__file__).resolve().parent.parent))
    PERCEPTA_USER_DATA_DIR: str = os.environ.get(
        "PERCEPTA_USER_DATA_DIR",
        str(Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "PERCEPTA Defence")
    )

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./percepta.db"

    # Storage paths
    STORAGE_DIR: str = "./storage"
    EVIDENCE_DIR: str = "./storage/evidence"
    SNAPSHOTS_DIR: str = "./storage/snapshots"
    DATASETS_DIR: str = "./datasets"
    CONFIGS_DIR: str = "./configs"
    MODELS_DIR: str = "./models"
    YOLO_MODEL_NAME: str = "yolov8n.pt"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_user_workspace(self, user_id: str) -> dict[str, Path]:
        """
        Derives an isolated user workspace containing dedicated database,
        forensic evidence, temporary recordings, user settings, and logs.
        Guarantees that User A and User B cannot access each other's data.
        """
        clean_user = "".join(c for c in str(user_id) if c.isalnum() or c in ("-", "_")).lower()
        if not clean_user:
            clean_user = "default_operator"

        base = Path(self.PERCEPTA_USER_DATA_DIR) / "users" / clean_user
        workspace = {
            "root": base,
            "database_dir": base / "database",
            "evidence_dir": base / "evidence",
            "recordings_dir": base / "recordings",
            "config_dir": base / "config",
            "logs_dir": base / "logs",
        }
        for d in workspace.values():
            d.mkdir(parents=True, exist_ok=True)

        workspace["database_file"] = workspace["database_dir"] / "percepta.db"
        workspace["settings_file"] = workspace["config_dir"] / "user_settings.json"
        workspace["log_file"] = workspace["logs_dir"] / "percepta.log"
        return workspace

    def ensure_directories(self) -> None:
        """Ensure necessary storage directories exist."""
        Path(self.STORAGE_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.EVIDENCE_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.SNAPSHOTS_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.DATASETS_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.CONFIGS_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.MODELS_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.PERCEPTA_USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
        (Path(self.PERCEPTA_USER_DATA_DIR) / "logs").mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
