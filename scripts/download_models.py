"""
Border Intelligence Model Weight Downloader.
Pre-downloads and caches YOLOv8 detection weights into ./models/ for offline deployment.
"""
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.detection.model_loader import ModelLoader


def main():
    print("=== Border Intelligence Model Weight Caching Script ===")
    models_dir = Path("./models")
    loader = ModelLoader(models_dir=str(models_dir))
    
    target_weights = ["yolov8n.pt"]
    for weight in target_weights:
        target_path = loader.get_model_path(weight)
        if target_path.exists():
            print(f"[OK] Model {weight} already cached at: {target_path}")
        else:
            print(f"[DOWNLOADING] Downloading {weight} to local cache...")
            loader.load_model(weight)
            print(f"[OK] Successfully cached {weight} at: {target_path}")

    print("\nAll model weights ready for offline execution.")


if __name__ == "__main__":
    main()
