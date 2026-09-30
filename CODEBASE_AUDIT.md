# PERCEPTA — Comprehensive Codebase Audit

**Date**: 2026-09-26  
**Branch**: `chore/codebase-cleanup`  
**Baseline Commit**: `87164e8dd85f914f0c4a2e88fcfc1e38344b0ad7`  
**Audit Objective**: Identify, categorize, and clean technical debt, duplicate systems, dead code, unused dependencies, and fake perception while preserving the proven PERCEPTA C2 architecture and 100% test pass rate.

---

## 1. Classification Taxonomy

- **A. KEEP**: Actively used and required in production pipeline.
- **B. KEEP / MODIFY**: Required, but cleaned or adapted (e.g. offline status, type fixes).
- **C. MIGRATION**: Temporary migration staging files (integrated and removed).
- **D. DUPLICATE**: Redundant duplicate implementation.
- **E. LEGACY**: Obsolete earlier implementation.
- **F. DEAD CODE**: Unreferenced code / components / routes.
- **G. DEMO / MOCK**: Fake or simulated functionality.
- **H. UNUSED ASSET**: Unused image, SVG, or media asset.
- **I. UNUSED DEPENDENCY**: Unused npm or Python package.
- **J. UNKNOWN**: Preserved without deletion pending clarification.

---

## 2. Codebase Inventory & Categorization

### 2.1 Top-Level Root Structure

| Path | Category | Status / Action | Description / Rationale |
| :--- | :--- | :--- | :--- |
| `backend/` | **A. KEEP** | Retained | Core FastAPI, YOLOv8n, ByteTrack, event bus, and database layer. |
| `frontend/` | **A. KEEP** | Retained & Cleaned | React 19 + Vite frontend with Landing, Auth, and C2 Dashboard. |
| `models/` | **A. KEEP** | Retained (Git Ignored) | Model weights (`yolov8n.pt`, `yolov8n.onnx`, OpenVINO). |
| `scripts/` | **A. KEEP** | Retained | Benchmarks, QA runners, demo preflight, and pipeline profiling. |
| `tests/` | **A. KEEP** | Retained | Complete 172-test suite across unit, integration, and failure domains. |
| `.agents/` | **A. KEEP** | Retained | Antigravity IDE workspace customization root with skills. |
| `agent/` | **D. DUPLICATE** | **DELETED** | Duplicate copy of `.agents/skills`. |
| `PERCEPTA_MIGRATION/` | **C. MIGRATION** | **DELETED** | Temporary staging directory; all assets & components integrated into `frontend/src`. |
| `node_modules/` (root) | **F. DEAD CODE** | **DELETED** | Orphaned root node_modules without a root `package.json`. |
| `storage/` | **A. KEEP** | Retained (Git Ignored) | Runtime state for evidence, snapshots, and SQLite WAL database. |
| `datasets/`, `VIRAT/`, `moth17/`, `VisDrone2019-MOT-val/` | **A. KEEP** | Retained (Git Ignored) | Large benchmark datasets (~10.5 GB) kept outside Git via `.gitignore`. |
| `graphify-out/` | **A. KEEP** | Retained (Git Ignored) | Graph analysis cache added to `.gitignore`. |
| `.env` | **A. KEEP** | Retained (Local Secrets) | Local developer environment variables (never committed). |
| `.env.example` | **B. KEEP / MODIFY** | **UPDATED** | Sanitized template with placeholders only; documented all variables. |
| `.gitignore` | **B. KEEP / MODIFY** | **UPDATED** | Added `.onnx`, OpenVINO model weights, and `graphify-out/` ignores. |
| `pytest.ini` | **B. KEEP / MODIFY** | **UPDATED** | Added filterwarnings for graceful asyncio thread teardown in pytest 9. |
| `requirements.txt` | **A. KEEP** | Retained | 18 core Python packages; 100% utilized. |
| `ANTIGRAVITY_UI.md` | **A. KEEP** | Retained | Project architecture & design system specification. |
| `BRD.md`, `DESIGN.md`, `TECHSTACK.md`, `README_RUN.md` | **A. KEEP** | Retained | Core requirements, system design, and runbook documentation. |
| `border_intelligence.db`, `percepta.db*`, `test_percepta.db` | **A. KEEP** | Retained (Git Ignored) | Local SQLite runtime databases. |

---

### 2.2 Frontend Files (`frontend/src/`)

| File / Directory | Category | Status / Action | Description / Rationale |
| :--- | :--- | :--- | :--- |
| `src/main.tsx`, `src/index.css` | **A. KEEP** | Retained | Application entrypoint and dark cinematic styling. |
| `src/App.tsx` | **B. KEEP / MODIFY** | **UPDATED** | Streamlined routes to canonical `/`, `/auth`, `/dashboard`. Removed duplicates (`/landing`, `/login`, `/dashboard/*`). |
| `src/pages/Landing.tsx` | **A. KEEP** | Retained | Migrated 3D Earth Globe landing page. |
| `src/pages/Auth.tsx` | **A. KEEP** | Retained | Migrated tactical Authentication portal with callsign login. |
| `src/pages/Dashboard.tsx` | **A. KEEP** | Retained | Proven PERCEPTA C2 operational surveillance dashboard. |
| `src/pages/NotFound.tsx` | **F. DEAD CODE** | **DELETED** | Unreferenced 404 page; wildcard route redirects to `/`. |
| `src/features/landing/` | **A. KEEP** | Retained | C2Loader, EarthGlobe (Three.js), TacticalCursor, WorldOverlays. |
| `src/features/auth/` | **A. KEEP** | Retained | Isolated `authService.adapter.ts` with backend JWT + fallback. |
| `src/features/routing/ProtectedRoute.tsx` | **A. KEEP** | Retained | Operator clearance gate with session auto-provisioning. |
| `src/features/shared/` | **A. KEEP** | Retained | PerceptaLogo, StarsBackground, design tokens. |
| `src/components/AddCameraModal.tsx` | **A. KEEP** | Retained | Camera registration modal (RTSP, video, webcam). |
| `src/components/AIAssistantBar.tsx` | **A. KEEP** | Retained | NLP Query Assistant bar with fact grounding. |
| `src/components/AlertInspector.tsx` | **A. KEEP** | Retained | Forensic alert drawer with snapshot & timeline. |
| `src/components/AlertPanel.tsx` | **A. KEEP** | Retained | Real-time perimeter alerts feed. |
| `src/components/CameraFeed.tsx` | **B. KEEP / MODIFY** | **UPDATED** | Added dedicated offline/error signal overlay (`SIGNAL OFFLINE`). |
| `src/components/PremiumBackground.tsx` | **A. KEEP** | Retained | Tactical canvas ambient background for C2 Dashboard. |
| `src/components/PremiumCard.tsx` | **A. KEEP** | Retained | Glassmorphic card container with border glow. |
| `src/components/StatusBar.tsx` | **A. KEEP** | Retained | Bottom telemetry bar (FPS, latency, system health). |
| `src/components/ThreatGauge.tsx` | **A. KEEP** | Retained | Circular DEFCON threat gauge. |
| `src/components/CursorReactiveBackground.tsx` | **F. DEAD CODE** | **DELETED** | Unreferenced canvas background prototype. |
| `src/components/LaptopScrollTransition.tsx` | **F. DEAD CODE** | **DELETED** | Unreferenced 3D laptop scroll prototype. |
| `src/components/LogoDropdown.tsx` | **F. DEAD CODE** | **DELETED** | Unreferenced header dropdown. |
| `src/components/MagneticButton.tsx` | **F. DEAD CODE** | **DELETED** | Unreferenced button motion prototype. |
| `src/components/TiltCard.tsx` | **F. DEAD CODE** | **DELETED** | Unreferenced card tilt prototype (superseded by `PremiumCard`). |
| `src/hooks/use-auth.ts` | **F. DEAD CODE / G. DEMO** | **DELETED** | Unreferenced dummy hook with hardcoded credentials; replaced by `authService.adapter.ts`. |
| `src/hooks/useDisplayedImageRect.ts` | **A. KEEP** | Retained | Frame-to-viewport coordinate mapping for polygon zones. |
| `src/hooks/useWebSocket.ts` | **A. KEEP** | Retained | Resilient WebSocket client with automatic reconnection. |
| `src/hooks/use-mobile.ts` | **A. KEEP** | Retained | Mobile responsive breakpoint hook. |
| `src/api/client.ts` | **A. KEEP** | Retained | Unified REST API client with relative proxy support. |
| `src/types/surveillance.ts`, `global.d.ts` | **A. KEEP** | Retained | Complete TypeScript definitions. |

---

### 2.3 Frontend UI Components (`frontend/src/components/ui/`)

| Component | Category | Status / Action | Description / Rationale |
| :--- | :--- | :--- | :--- |
| `badge.tsx` | **A. KEEP** | Retained | Used by `AlertInspector`, `AlertPanel`, `CameraFeed`, `Dashboard`. |
| `button.tsx` | **A. KEEP** | Retained | Used across `AddCameraModal`, `AIAssistantBar`, `AlertInspector`, `Dashboard`. |
| `dialog.tsx` | **A. KEEP** | Retained | Used by `AddCameraModal`. |
| `input.tsx` | **A. KEEP** | Retained | Used by `AddCameraModal`. |
| `label.tsx` | **A. KEEP** | Retained | Used by `AddCameraModal`. |
| `progress.tsx` | **A. KEEP** | Retained | Used by `AddCameraModal`. |
| `scroll-area.tsx` | **A. KEEP** | Retained | Used by `AlertInspector`. |
| `tabs.tsx` | **A. KEEP** | Retained | Used by `AddCameraModal`. |
| 45 Unused UI Components (accordion, alert, avatar, card, carousel, chart, drawer, dropdown-menu, form, select, sheet, sidebar, table, tooltip, etc.) | **F. DEAD CODE** | **DELETED** | Unused shadcn component boilerplate; removed to reduce bundle size. |

---

### 2.4 Frontend Assets & Dependencies

| Asset / Package | Category | Status / Action | Description / Rationale |
| :--- | :--- | :--- | :--- |
| `frontend/src/assets/hero.png` | **H. UNUSED ASSET** | **DELETED** | Unused boilerplate image. |
| `frontend/src/assets/react.svg`, `vite.svg` | **H. UNUSED ASSET** | **DELETED** | Unused Vite starter template SVGs. |
| `frontend/src/assets/logo.svg` | **H. UNUSED ASSET** | **DELETED** | Unused SVG only referenced by deleted `LogoDropdown.tsx`. |
| `frontend/public/assets/images/*.jpg` | **H. UNUSED ASSET** | **DELETED** | Unused static images (`percepta_hero_exact.jpg`, `percepta_thermal_walking.jpg`, `veyrox_thermal_hero.jpg`). |
| 32 Unused npm packages in `package.json` | **I. UNUSED DEPENDENCY** | **DELETED** | Removed unused packages (`@radix-ui/*`, `cmdk`, `date-fns`, `embla-carousel-react`, `gsap`, `input-otp`, `next-themes`, `recharts`, `sonner`, `vaul`, etc.). Reduced CSS bundle size by ~35% (185 kB → 121 kB). |

---

### 2.5 Backend Pipeline (`backend/`)

| Module / File | Category | Status / Action | Description / Rationale |
| :--- | :--- | :--- | :--- |
| `backend/main.py` | **A. KEEP** | Retained | Application entrypoint with lifespan context, router wiring, rate limiting, and CORS. |
| `backend/config.py` | **A. KEEP** | Retained | Settings model with directory creation and hardware auto-detection. |
| `backend/config_profiles.py` | **A. KEEP** | Retained | Performance profiles for CPU, CUDA, and low-spec edge compute. |
| `backend/database.py`, `database_diagnostics.py` | **A. KEEP** | Retained | Async SQLite connection manager with WAL mode and health checks. |
| `backend/api/` (13 domain routers) | **A. KEEP** | Retained | alerts, cameras, events, export, forensics, health, incidents, intelligence, sensors, streaming, system, threat, zones. |
| `backend/detection/` (detector, onnx_detector, anpr, thermal, face, loader) | **A. KEEP** | Retained | Real YOLOv8n object detection, ONNX fallback, thermal edge processing, and ANPR. |
| `backend/events/schema.py` | **B. KEEP / MODIFY** | **UPDATED** | Allowed `track_id: Optional[Union[str, int]]` in `BaseEvent` to seamlessly support integer and string track IDs without validation errors. |
| `backend/events/` (bus, store, snapshots, forensics, audit_logger) | **A. KEEP** | Retained | Real-time event bus, SQLite WAL event persistence, SHA-256 Merkle root hashing. |
| `backend/gateway/` (auth, dependencies, middleware, rate_limit) | **A. KEEP** | Retained | JWT authentication, RBAC, SlowAPI rate limiting, and security headers. |
| `backend/incidents/` (models, dossier, annotations) | **A. KEEP** | Retained | Incident lifecycle management, dossier generation, and operator notes. |
| `backend/ingestion/` (camera_manager, frame_buffer, video, webcam, rtsp, image_sequence) | **A. KEEP** | Retained | Real video feed ingestion from MP4 files, RTSP streams, and USB webcams. |
| `backend/ingestion/simulation_adapter.py` | **G. DEMO / MOCK** | **RETAINED AS TEST FIXTURE** | Isolated synthetic stream generator used exclusively in automated test suites; never runs in production dashboard. |
| `backend/intelligence/` (assistant, threat_engine, correlation, query_parsing) | **A. KEEP** | Retained | Grounded natural language query engine, spatial-temporal correlation, and rule-based threat evaluation. |
| `backend/tracking/` (pipeline, tracker, bytetrack_wrapper, live_worker, movement, overlay) | **A. KEEP** | Retained | ByteTrack tracking, trajectory prediction, and server-side MJPEG bounding box rendering. |
| `backend/zones/` (security_zone, templates, heatmap) | **A. KEEP** | Retained | Point-in-polygon and vector cross-product tripwire evaluation. |

---

## 3. Verification & Metrics

- **Backend Pytest Suite**: 172 passed out of 172 tests (100% pass rate, 0 failures, 0 warnings, clean exit code 0).
- **Frontend Vite Build**: `tsc -b && vite build` passed cleanly in 597ms with zero errors.
- **Frontend Bundle Reduction**: CSS bundle size reduced from 185.13 kB to 121.52 kB (~35% reduction).
- **Fake Perception Check**: 0 synthetic overlays, 0 client-side `Math.sin`/`Math.random` tracking hacks. All dashboard telemetry and bounding boxes stream from the backend CV pipeline.
