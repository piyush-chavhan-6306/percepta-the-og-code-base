# Border Intelligence — Technology Stack

**Status**: Verified Working Baseline + Proposed Architectural Additions  
**Document Owner**: Piyush Chavhan  
**Document Version**: 1.1.0  
**Last Updated**: 2026-08-24  

---

## 1. Current Verified Technology Stack (As-Is)

### Frontend Tier
- **Framework**: React 19.2.8 with TypeScript
- **Build Tool / Bundler**: Vite 8.2.0 (`@vitejs/plugin-react`)
- **3D Spatial Visualization**: Three.js 0.185.1 (`@types/three`)
- **UI Animation**: GSAP 3.15.0 with ScrollTrigger
- **Iconography**: Lucide React 1.33.0
- **Styling**: Tailwind CSS 4 (`@tailwindcss/vite`) + Vanilla CSS Custom Properties (`src/index.css`)
- **Type Checking & Linting**: TypeScript ~6.0.2 + Oxlint 1.75.0

### Backend Tier
- **Runtime**: Python 3.13
- **Web Framework**: FastAPI >= 0.110.0
- **ASGI Server**: Uvicorn [standard] >= 0.28.0
- **Gateway & Authentication**: `python-jose[cryptography]` >= 3.3.0, `passlib[bcrypt]` >= 1.7.4, `slowapi` >= 0.1.9
- **Data Validation & Settings**: Pydantic >= 2.6.0 + Pydantic-Settings >= 2.2.0
- **Asynchronous ORM**: SQLAlchemy 2.0.28 with `aiosqlite` 0.20.0
- **HTTP Client**: HTTPX >= 0.27.0
- **Environment Management**: Python-Dotenv >= 1.0.1

### Computer Vision & AI/ML
- **Video Ingestion & Frame Processing**: OpenCV (headless) >= 4.9.0.80 + NumPy >= 1.26.0
- **Object Detection Model**: Ultralytics YOLOv8n >= 8.1.0
  - Model weights: Local PyTorch weights `models/yolov8n.pt` (6.5 MB)
  - Hardware inference: Automated CUDA detection with seamless CPU fallback
- **Multi-Object Tracking (MOT)**: ByteTrack algorithm with Kalman filter trajectory prediction
- **Natural Language Assistant**: Rule-based grounded NLP query engine directly querying SQLite WAL tables (zero cloud LLM API dependency for edge resilience)

### Persistence & Storage
- **Database Engine**: SQLite 3 in Write-Ahead Logging (`WAL`) mode
  - `PRAGMA journal_mode=WAL;`
  - `PRAGMA synchronous=NORMAL;`
  - `PRAGMA busy_timeout=5000;`
- **File System Storage**: Local filesystem storage for:
  - Evidence snapshots: `./storage/evidence/`
  - Recorded surveillance feeds: `./storage/feeds/`
  - Incident snapshots: `./storage/snapshots/`

### Automated Testing
- **Test Runner**: Pytest >= 8.0.0
- **Async Test Framework**: Pytest-Asyncio >= 0.23.5
- **Test Baseline**: 139 unit and integration test cases across 43 modules (100% pass rate)

---

## 2. API Contract & Endpoint Inventory

### Gateway & Auth Endpoints (`/api/auth`)
- `POST /api/auth/token`: Authenticate user credentials and return JWT bearer token.
- `GET /api/auth/demo-token`: Issue pre-signed operator evaluation token.

### Surveillance Feeds & Ingestion (`/api/cameras`, `/api/stream`)
- `GET /api/cameras`: List all registered CCTV feeds and status.
- `POST /api/cameras`: Register a new CCTV camera (MP4 path or RTSP URL).
- `DELETE /api/cameras/{id}`: Deregister camera feed.
- `GET /api/cameras/{id}/diagnostics`: Optical diagnostics (Laplacian blur, brightness, glare).
- `GET /api/stream/video/{id}`: MJPEG multipart video stream.
- `WS /ws/events` & `WS /api/ws/events`: Real-time WebSocket event stream with token validation.

### Security Incidents & Forensics (`/api/incidents`, `/api/forensics`, `/api/alerts`)
- `GET /api/incidents`: List aggregated security incidents.
- `GET /api/incidents/{id}/timeline`: Retrieve chronological event timeline.
- `GET /api/incidents/{id}/notes`: Retrieve operator escalation annotations.
- `POST /api/incidents/{id}/notes`: Append new duty officer note.
- `GET /api/incidents/{id}/dossier`: Compile tactical SitRep dossier.
- `POST /api/alerts/{id}/acknowledge`: Acknowledge security alert.
- `GET /api/forensics/verify/{event_id}`: Verify event SHA-256 hash.
- `GET /api/forensics/audit`: Execute in-place cryptographic database integrity audit.

### Security Zones & Heatmap (`/api/zones`)
- `GET /api/zones`: List active polygon geofences.
- `POST /api/zones`: Create new polygon security zone.
- `DELETE /api/zones/{id}`: Remove security zone.
- `GET /api/zones/templates`: List tactical perimeter templates.
- `GET /api/zones/heatmap`: Retrieve spatial density heatmap array.

### Intelligence & Threat System (`/api/intelligence`, `/api/threat`, `/api/system`)
- `POST /api/intelligence/query`: Execute grounded natural-language assistant query.
- `GET /api/threat/level`: Calculate sector composite threat score and DEFCON status.
- `GET /api/system/status`: Retrieve system uptime, memory, and telemetry.
- `POST /api/system/demo/reset`: Reset state to clean baseline for evaluation.

---

## 3. Environment Configuration

```bash
# Application Metadata
APP_NAME=Border Intelligence
APP_ENV=development
DEBUG=true
PORT=8000
HOST=0.0.0.0

# Database Configuration (SQLite WAL mode)
DATABASE_URL=sqlite+aiosqlite:///./border_intelligence.db

# Storage Directories
EVIDENCE_DIR=./storage/evidence
DATASETS_DIR=./datasets
CONFIGS_DIR=./configs

# Gateway & Security
JWT_SECRET_KEY=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=480
DEMO_MODE=true
RATE_LIMIT_PER_MINUTE=120
```
