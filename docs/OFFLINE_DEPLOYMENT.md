# PERCEPTA OFFLINE DEPLOYMENT GUIDE
**Air-Gapped & Native Windows Tactical C2 Station**

This guide provides operational procedures for deploying, packaging, running, and maintaining PERCEPTA Offline as a native Windows desktop C2 workstation without any Internet requirement.

---

## 1. System Requirements

- **Operating System**: Windows 10 / Windows 11 (64-bit)
- **Processor**: Intel Core i5/i7 (8th Gen+) or AMD Ryzen 5/7 (or ARM64 with translation)
- **RAM**: Minimum 8 GB (16 GB recommended for multi-camera 3×3 grid)
- **Storage**: Minimum 20 GB free SSD storage for local recordings and forensic evidence
- **Graphics**: NVIDIA GPU with CUDA 11.8+ (Optional, CPU inference supported via PyTorch auto-stride)
- **Network**: Local Area Network (LAN) only required if connecting to IP RTSP cameras; no Internet required.

---

## 2. Packaging the Standalone Windows Executable (`PERCEPTA.exe`)

1. Open PowerShell in the project root:
   ```powershell
   .\venv\Scripts\activate
   ```
2. Ensure build dependencies are installed:
   ```powershell
   pip install pyinstaller
   ```
3. Run the packaging script:
   ```powershell
   python offline/desktop/build_exe.py
   ```
4. PyInstaller will compile all orchestrator dependencies into:
   ```
   dist/PERCEPTA.exe
   ```
5. The executable packages the local launcher, environment initializers, and Edge WebView2 desktop bridge.

---

## 3. Installation & First Launch

1. Copy the PERCEPTA installation bundle or `PERCEPTA.exe` to the workstation (e.g., `C:\PERCEPTA`).
2. Double-click **`PERCEPTA.exe`** (or execute `offline/desktop/launch_percepta.bat`).
3. The orchestrator executes the following initialization sequence automatically:
   - **Step 1/5**: Verifies and creates local storage directories (`./storage/recordings`, `./storage/evidence`, `./storage/snapshots`).
   - **Step 2/5**: Inspects local SQLite database (`percepta.db`) and verifies AI model files (`models/yolov8n.pt`).
   - **Step 3/5**: Starts the local perception engine in background on loopback `127.0.0.1:8000`.
   - **Step 4/5**: Binds the local web interface on `http://localhost:5000`.
   - **Step 5/5**: Spawns a dedicated native desktop window in standalone application mode (no browser URL bar, no tabs).
4. The operator is immediately greeted with the PERCEPTA Tactical Command Post without typing any terminal commands.

---

## 4. Operational Workflows

### A. Testing with Recorded Video Files
1. Place surveillance video files (`.mp4`, `.avi`, `.mkv`) in `./datasets` or any local folder.
2. In PERCEPTA C2, click **+ ADD CAMERA FEED**.
3. Select **Video File**, enter the local path (e.g., `datasets/virat_cctv.mp4`), assign Sector Modality (**RGB**, **IR**, or **THERMAL**), and click **ADD SENSOR**.
4. Click **START ANALYSIS** to initiate real-time YOLOv8 neural detection and ByteTrack tracking.

### B. Testing Local IP / RTSP Cameras
1. Ensure the camera is connected to the tactical switch / LAN.
2. Click **+ ADD CAMERA FEED**, select **RTSP Stream**, enter `rtsp://192.168.1.100:554/live/ch0`, and click **ADD SENSOR**.
3. The Camera Trust Sensor immediately computes optical clarity, brightness, signal stability, and blur factors.

### C. Drawing Zones & Tripwires
1. Click **+ ZONE** to draw polygon surveillance boundaries directly on the video feed.
2. Click **+ TRIPWIRE** to draw directional boundary tripwires (BIDIRECTIONAL, NORTH, SOUTH, EAST, WEST).
3. Violations automatically transition to **ACTIVE INCIDENTS** with SHA-256 evidence captured to `./storage/evidence/`.

### D. Grounded Defence AI Copilot
1. Open the bottom AI Copilot bar.
2. Type tactical queries:
   - *"What happened at Camera 01?"*
   - *"Show me today's critical incidents."*
   - *"Which camera detected the object first?"*
   - *"Are there any predicted blind spots near this camera?"*
3. The Copilot queries the local SQLite database directly and returns structured, 100% grounded facts without hallucinations.

---

## 5. Maintenance, Backup, & Updates

### Local Database Backup
To backup the incident history and camera configurations:
```powershell
# Copy SQLite database and WAL files
Copy-Item "percepta.db*" "D:\Backups\percepta_backup_$(Get-Date -Format 'yyyyMMdd')\"
```

### Application Updates
1. Stop `PERCEPTA.exe` (close the desktop window).
2. Replace `PERCEPTA.exe` or git pull the updated code into the station folder.
3. Launch `PERCEPTA.exe`. Database migrations run automatically on startup.

### Clean Uninstall
1. Delete the `C:\PERCEPTA` application folder.
2. To retain forensic evidence, preserve the `offline/storage/evidence/` directory before deletion.
