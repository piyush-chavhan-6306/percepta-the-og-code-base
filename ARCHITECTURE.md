# PERCEPTA — System Architecture Documentation

**System Title**: Autonomous AI Video Analytics & Persistent Border Defense Monitoring  
**Target Problem**: PS SIH26187 — Retaining & Retrofitting Legacy Border CCTV Fleet with Sovereign Edge Intelligence  
**Design Paradigm**: Local / Offline-First Sovereign Edge Computing (Zero Cloud LLM / Cloud Storage Dependencies)

---

## 1. End-to-End System Pipeline

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND PRESENTATION TIER                      │
│                                                                        │
│   Landing Page (/)   ──>   Auth Portal (/auth)   ──>   C2 Dashboard    │
│   [3D Earth & Hero]        [Duty Callsign / JWT]       (/dashboard)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                              HTTP / REST & WS
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                          API & GATEWAY LAYER                           │
│                                                                        │
│   FastAPI Router (Port 8000) ──> Gateway Security ──> SlowAPI Limiter   │
│   Token Auth & RBAC (JWT)    ──> Audit Logger     ──> CORS Middleware  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                          CAMERA INGESTION LAYER                        │
│                                                                        │
│   CameraManager (Thread-safe registry, frame buffer, adaptive stride)   │
│   ├── VideoFileAdapter (VIRAT CCTV / MP4 loop)                         │
│   ├── RTSPAdapter (H.264 / IP Network Cameras)                         │
│   ├── WebcamAdapter (USB DirectShow / V4L2)                            │
│   └── ImageSequenceAdapter (Synthetic forensic replay)                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                Raw BGR Frames
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                           PERCEPTION PIPELINE                          │
│                                                                        │
│   1. YOLOv8 Neural Inference (models/yolov8n.onnx / models/yolov8n.pt) │
│      Wrapped by ObjectDetector (backend/detection/detector.py)         │
│      Detects: Person, Vehicle, Drone, Animals with confidence scoring  │
│                                   │                                    │
│   2. ByteTrack Tracking (backend/tracking/bytetrack_wrapper.py)        │
│      Associates detections across frames, Kalman filter state,         │
│      computes velocities, trajectories, and cardinal headings          │
│                                   │                                    │
│   3. Dynamic Threat & Security Zone Engine                             │
│      - Geofencing: backend/zones/security_zone.py                      │
│      - Threat Engine: backend/intelligence/threat_engine.py            │
│      - Point-in-polygon containment & vector tripwires                 │
│      - Loitering detection & multi-target approach vectors             │
│      - Deterministic composite threat score (0-100) & DEFCON level     │
│                                   │                                    │
│   4. Server-Side Annotation Overlay (backend/tracking/overlay.py)      │
│      Burns bounding boxes, track IDs, headings, and alert rings         │
│      directly into the MJPEG video stream (/api/streaming/feed/{cam})  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                          Events & Incidents
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                        PERSISTENCE & EVIDENCE TIER                     │
│                                                                        │
│   1. EventStore (SQLite 3 WAL Mode: percepta.db)                       │
│      - High-throughput asynchronous write engine (aiosqlite)           │
│      - Immutable log: Detections, Tracks, Zones, Alerts, Audits        │
│                                                                        │
│   2. Cryptographic Forensic Evidence Generator                         │
│      - Full-resolution event snapshots saved to storage/snapshots/     │
│      - SHA-256 Merkle root hashing on incident dossiers                │
│      - Tamper-evident chain of custody for military/legal review       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                             WebSocket Broadcast
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│                    REAL-TIME C2 OPERATOR DASHBOARD                     │
│                                                                        │
│   - Live Annotated MJPEG Video Feed with In-Place Polygon Zone Drawer │
│   - Real-Time Perimeter Alert Notifications & Audio Warnings           │
│   - Forensic Timeline Seeking & Multi-Modal Sensor Fusion Drawer       │
│   - Grounded NLP Operator Assistant (Anti-hallucination factual query) │
│   - Circular DEFCON Threat Meter & System Telemetry Watchdog           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure & Key Locations

```
SIH   border cctv/
├── backend/
│   ├── api/                   # 13 REST API domain routers
│   ├── detection/             # YOLOv8n detector, ONNX, ANPR, thermal processor
│   ├── events/                # Event schema, SQLite store, snapshots, audit logger
│   ├── gateway/               # JWT auth, dependencies, rate limit, security middleware
│   ├── incidents/             # Incident models, dossier compiler, operator notes
│   ├── ingestion/             # Camera manager, video, webcam, and RTSP adapters
│   ├── intelligence/          # Grounded AI assistant, rule-based threat engine
│   ├── sensors/               # Multi-modal radar/seismic/thermal sensor state
│   ├── tracking/              # ByteTrack wrapper, live worker, movement, overlay
│   ├── zones/                 # Polygon geofencing, tripwires, templates, heatmap
│   ├── config.py              # Pydantic Settings & environment variables
│   ├── database.py            # SQLite WAL connection lifecycle
│   └── main.py                # FastAPI entrypoint
├── frontend/
│   ├── public/
│   │   ├── assets/            # Static assets & audio tracks
│   │   └── videos/
│   │       └── border-demo.mp4 # Bundled 5.4 MB border surveillance demo clip
│   ├── src/
│   │   ├── api/client.ts      # Unified REST API client (relative proxy support)
│   │   ├── assets/            # Three.js 3D earth texture & loader audio
│   │   ├── components/        # C2 Dashboard components (CameraFeed, AlertPanel, etc.)
│   │   ├── components/ui/     # Pruned Radix UI primitives (badge, button, dialog, etc.)
│   │   ├── features/
│   │   │   ├── auth/          # Auth adapter (JWT endpoint + offline fallback)
│   │   │   ├── landing/       # 3D Earth Globe, C2Loader, and chapter overlays
│   │   │   ├── routing/       # ProtectedRoute clearance guard
│   │   │   └── shared/        # PerceptaLogo, StarsBackground, design tokens
│   │   ├── hooks/             # WebSocket, image coordinate mapping, responsive hooks
│   │   ├── pages/             # Landing.tsx (/), Auth.tsx (/auth), Dashboard.tsx (/dashboard)
│   │   ├── types/             # Surveillance & telemetry TypeScript interfaces
│   │   ├── App.tsx            # Canonical clean application routes
│   │   └── index.css          # Dark cinematic styling & Tailwind CSS 4 theme
│   ├── package.json           # Pruned dependencies (16 production packages)
│   └── vite.config.ts         # Vite server (port 5000, proxies /api and /ws to 8000)
├── models/
│   ├── yolov8n.pt             # PyTorch weights for YOLOv8n (6.5 MB, offline)
│   ├── yolov8n.onnx           # Optional ONNX export for OpenVINO/TensorRT
│   └── yolov8n_openvino_model/# OpenVINO optimized model files
├── storage/                   # Local runtime storage (Git ignored)
│   ├── evidence/              # Exported forensic packages
│   ├── feeds/                 # Camera buffer feeds
│   └── snapshots/             # Event-triggered full-resolution image crops
├── scripts/                   # Performance benchmarks, profiling, demo runners
├── tests/                     # 172-test automated verification suite
├── ARCHITECTURE.md            # This system architecture documentation
├── CODEBASE_AUDIT.md          # Comprehensive file-by-file audit and cleanup log
├── README_RUN.md              # Operator and judge run playbook
├── requirements.txt           # 18 P0 Python backend dependencies
└── pytest.ini                 # Pytest test configuration
```

---

## 3. How the Application Starts

### 3.1 Backend Startup

```powershell
# From project root
.\venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

1. **Lifespan Initialization**:
   - Ensures all required directories exist (`storage/evidence`, `storage/snapshots`, `models`, `datasets`).
   - Opens local SQLite database `percepta.db` with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`.
   - Logs security gateway status banner.
   - Registers default demo camera `CAM-01` in standby mode.
2. **REST API & WebSocket**:
   - Listens on `http://127.0.0.1:8000`
   - WebSocket events endpoint: `ws://127.0.0.1:8000/ws/events`
   - Interactive OpenAPI documentation: `http://127.0.0.1:8000/docs`

### 3.2 Frontend Startup

```powershell
# From frontend/ directory
cd frontend
npm run dev
```

1. **Vite Development Server**:
   - Boots on `http://localhost:5000` (or `http://localhost:5173`).
   - Reverse-proxies all `/api` requests to `http://localhost:8000/api`.
   - Reverse-proxies all `/ws` requests to `ws://localhost:8000/ws`.

---

## 4. Application Flow & Routing

The application follows a strict 3-stage defense operational hierarchy:

1. **`/` — Public Landing Page**:
   - Interactive Three.js 3D Earth Globe with tactical orbital camera transitions.
   - Chapter cards covering Border Analytics, Multi-Modal Fusion, and Cryptographic Evidence.
   - Direct CTA: **ENTER C2 DEFENSE CONSOLE** navigates to `/auth`.

2. **`/auth` — Tactical Authentication Portal**:
   - Operator callsign and security clearance login.
   - Issues JWT bearer token via `POST /api/auth/token`.
   - Built-in offline fallback: Auto-validates test operator credentials when disconnected.
   - On successful clearance, automatically routes to `/dashboard`.

3. **`/dashboard` — C2 Operational Surveillance Dashboard**:
   - Protected by `ProtectedRoute` clearance guard.
   - Live multi-camera surveillance grid with full-screen and thumbnail views.
   - Real-time server-side annotated MJPEG video streams.
   - Interactive in-place SVG drawer for polygon security zones and directional tripwires.
   - Real-time perimeter alerts drawer with audio notifications.
   - Grounded NLP Operator Assistant with factual database queries.
   - Forensic event inspector with timeline seeking and SHA-256 evidence verification.

---

## 5. Perception & Tracking Pipeline

### Real Inference vs. Simulation
- **Production Pipeline**: Every bounding box, track trajectory, confidence score, and alert is computed in real-time by `backend.tracking.pipeline.TrackingPipeline`.
  - Frame ingested via `SensorAdapter` (e.g. `VideoFileAdapter` in `backend/ingestion/video_adapter.py`).
  - Passed to `ObjectDetector` (`backend/detection/detector.py`, loading local `models/yolov8n.onnx` or `models/yolov8n.pt`) with confidence threshold `0.25` and IoU `0.45`.
  - Detections fed to `ByteTrackTracker` (`backend/tracking/bytetrack_wrapper.py`) to assign persistent integer track IDs.
  - Track centroids evaluated against active `SecurityZone` polygon definitions and `VirtualBoundary` tripwire vectors (`backend/zones/security_zone.py`).
  - Result burned into frame via OpenCV (`backend/tracking/overlay.py`).
  - Streamed to frontend as continuous multipart MJPEG (`image/jpeg`).
- **Signal Offline Protection**:
  - The frontend `CameraFeed` includes an automated error detector. If the backend is offline or camera source disconnected, it explicitly displays `SIGNAL OFFLINE // NO LIVE SIGNAL DETECTED` with a reconnect button. It **never** displays fake perception.
- **Simulation Code Isolation**:
  - `SimulationAdapter` exists solely as an isolated test fixture in `backend/ingestion/` for automated integration tests. It is never used in the production C2 dashboard.

---

## 6. Offline / Sovereign Edge Architecture

PERCEPTA operates 100% locally with zero external network connectivity requirements:
- **Local Model Weights**: `models/yolov8n.pt` is stored locally on the edge disk.
- **Local Database**: SQLite 3 with Write-Ahead Logging (`WAL`) provides zero-latency embedded transactions without requiring PostgreSQL, MySQL, Supabase, or cloud storage.
- **Local Evidence Storage**: Captured high-resolution frames are written directly to `./storage/snapshots/`.
- **Local Grounded AI**: The NLP Assistant uses an AST rule engine to translate natural queries directly into structured SQL against the local audit tables.

---

## 7. How Tests Are Executed

```powershell
# Run the complete test suite (172 tests)
.\venv\Scripts\python -m pytest -q

# Run specific domain test suites
.\venv\Scripts\python -m pytest tests/unit/test_tracking.py -q
.\venv\Scripts\python -m pytest tests/unit/test_threat_engine.py -q
.\venv\Scripts\python -m pytest tests/failure/test_multicamera_fault_isolation.py -q
```

All 172 test cases pass cleanly with exit code 0.
