# Border Intelligence — System Design

**Problem Statement**: Smart India Hackathon PS SIH26187  
**Status**: Architecture Redesign Specification  
**Document Owner**: Piyush Chavhan  
**Document Version**: 1.1.0  
**Last Updated**: 2026-08-24  

---

## 1. Architectural Overview & Design Philosophy

Border Intelligence is built as a **Tactical Defense & Aerospace Intelligence Command Post (C2)** platform. It upgrades legacy fixed CCTV and RTSP feeds into an automated perimeter security network without requiring expensive hardware replacements.

### Core Architectural Invariants:
1. **Persist-Before-Publish**: Database writes to SQLite WAL must commit and receive a monotonic `seq_id` and SHA-256 hash before events are published over the EventBus or WebSockets (`backend/events/store.py`).
2. **Camera-Local Track IDs**: Track IDs are camera-local (e.g., `CAM-01:TRK-09`). The system never asserts cross-camera re-identification without explicit optical similarity models.
3. **Zero-Hallucination Grounding**: The AI assistant answers queries grounded exclusively in persisted database records and refuses ungrounded biometrics or weapon assertions.
4. **Offline Resilience**: Perception, tracking, rules, and forensics execute 100% locally on edge hardware with zero reliance on cloud APIs.

```text
  [ CCTV / RTSP Feed / MP4 File / Local Video ]
                       │
                       ▼
          [ Ingestion Layer (OpenCV) ]
                       │
                       ▼
        [ Perception Pipeline (YOLOv8n) ]
                       │
                       ▼
     [ Tracking Layer (ByteTrack + Kalman) ]
                       │
                       ▼
     [ Rules & Geofence Engine (Ray-Casting) ]
                       │
                       ▼
     [ SQLite WAL Persistence Layer ] ◄─── (Persist-Before-Publish Contract)
                       │
        ┌──────────────┴──────────────────┐
        ▼                                 ▼
[ FastAPI EventBus ]         [ Cryptographic SHA-256 Chain ]
        │
        ▼
[ API Gateway & WebSockets ]
        │
        ▼
[ React 19 Tactical Command Post ]
```

---

## 2. Layered Architecture (Target Redesign)

```text
┌────────────────────────────────────────────────────────┐
│  Client Tier — React 19 SPA, Feature Modules           │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  API Gateway — Auth (JWT), Rate Limiter, Telemetry     │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  Domain Services — Perception, Zones, Incidents,       │
│  Intelligence, Sensors, Platform                       │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  Shared Kernel — EventBus, SQLite Store, SHA-256 Chain │
└───────────────────────────┬────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────┐
│  Data & Storage Tier — Repository Pattern over SQLite  │
└────────────────────────────────────────────────────────┘
```

---

### 2.1 Client Tier (Frontend Feature Structure)

The frontend is structured into self-contained feature modules:

```text
frontend/src/
├── app/                     # App.tsx shell, provider wrappers, view router
├── features/
│   ├── dashboard/           # DashboardView + TacticalMap3D
│   ├── surveillance/        # SurveillanceView, CameraCard, RegisterCameraModal
│   ├── incidents/           # IncidentsView, DossierModal, VideoEvidencePlayer
│   ├── zones/               # ZonesView, ZoneDesignerCanvas
│   ├── threat/              # ThreatView, ThreatMatrixCards
│   ├── forensics/           # ForensicsView, IntegrityAuditCard
│   ├── intelligence/        # IntelligenceView, GroundedChatConsole
│   └── sensors/             # SensorsSystemView, TelemetryCharts
└── shared/                  # Shared UI components used across 2+ features
    ├── components/          # Header, Navigation, AlertTicker, ThreatBadge, ThreatGauge
    ├── hooks/               # useWebSocket.ts
    ├── api/                 # client.ts (Typed REST API client)
    ├── store/               # surveillanceContext.tsx (Reactive store)
    └── types/               # surveillance.ts (Central data contracts)
```

**Rule of Shared Ownership**: A component or utility lives in `shared/` if and only if two or more feature folders import it.

---

### 2.2 UI Design System & Tactical Visual Tokens

#### Color Palette (Semantic Defense Hierarchy)
```css
/* Surface & Background */
--bg-darkest: #05070a;          /* Deep void canvas */
--bg-primary: #080c13;          /* Main workspace foundation */
--bg-surface: #0e141f;          /* Elevated tactical card background */
--bg-surface-raised: #141c2b;   /* Active module highlight */
--bg-glass: rgba(14, 20, 31, 0.82); /* 16px blurred translucent glass panel */

/* Semantic Accents */
--c2-cyan: #00e5ff;             /* Live telemetry readouts, radar sweep, 3D camera cones */
--c2-emerald: #00e676;          /* DEFCON 4 / Nominal, online feeds, verified authentic */
--c2-amber: #ffab00;            /* DEFCON 3 / Elevated dwell timers, warning boundaries */
--c2-orange: #ff6d00;           /* DEFCON 2 / High threat, perimeter boundary proximity */
--c2-crimson: #ff1744;          /* DEFCON 1 / Critical breach, tripwire crossing, QRF dispatch */
--c2-blue: #2979ff;             /* Spatial analytics, velocity vectors, persistent track IDs */
```

#### Typography Hierarchy
- **Mission & DEFCON Titles**: `Orbitron`, sans-serif (Weight: 800–900, Tracking: `0.06em`)
- **Sector & Card Headers**: `Rajdhani` / `Space Grotesk`, sans-serif (Weight: 700)
- **Telemetry & Hashes**: `JetBrains Mono`, monospace (Weight: 600–700)
- **Body & Intelligence**: `Inter`, sans-serif (Weight: 400–500)

#### Spatial UI Components:
1. **`.hud-card`**: Corner brackets on top-left and bottom-right in electric cyan with 1px border.
2. **`.glass-panel`**: `rgba(14, 20, 31, 0.82)` with `backdrop-filter: blur(16px)` and inset top highlight.
3. **`.tactical-grid-bg`**: 32px × 32px grid overlay providing depth.

---

### 2.3 API Gateway & Security (`backend/gateway/`)

```text
backend/gateway/
├── auth.py                  # JWT issuance, verification, password hashing (passlib/jose)
├── dependencies.py          # get_current_user(), require_role(), validate_ws_token()
├── middleware.py            # Security headers, process time, telemetry logging
└── rate_limit.py            # Token-bucket rate limiting (slowapi)
```

#### Authentication & Authorization Flow:
1. **HTTP Requests**: `Authorization: Bearer <jwt_token>` header evaluated by `get_current_user`.
2. **Role Enforcement**: `require_role([UserRole.COMMANDER, ...])` restricts sensitive routes.
3. **WebSocket Handshake**: Validates token via `?token=<jwt>` query parameter.
4. **Demo Mode (`DEMO_MODE=true`)**: Provides zero-friction evaluation bypass for judges with console notices.

---

### 2.4 Domain Services & Shared Kernel

```text
backend/
├── core/                    # database.py, config.py, config_profiles.py
├── gateway/                 # auth.py, dependencies.py, middleware.py, rate_limit.py
├── shared_kernel/           # Cross-cutting primitives
│   └── events/              # bus.py, store.py, schema.py, snapshots.py, audit_logger.py
│                            # + forensics.py (SHA-256 hash chaining engine)
├── domains/
│   ├── perception/          # cameras.py + streaming.py routers
│   │   ├── ingestion/       # adapter, camera_manager, frame_buffer, video/rtsp/simulation adapters
│   │   ├── detection/       # detector.py, model_loader.py (YOLOv8n)
│   │   └── tracking/        # tracker.py, bytetrack_wrapper.py, pipeline.py, movement.py
│   ├── zones/               # zones.py router + security_zone.py, templates.py, heatmap.py
│   ├── incidents/           # incidents.py, alerts.py, export.py, verification endpoints
│   │                        # + models.py, annotations.py, dossier.py
│   ├── intelligence/        # intelligence.py, threat.py routers + assistant.py, threat_engine.py
│   ├── sensors/             # sensors.py router + multi_modal.py
│   └── platform/            # health.py, system.py
└── main.py                  # Mounts gateway and domain routers
```

---

## 3. Database Schema Reference

| Table Name | Primary Key | Key Columns | Purpose |
|---|---|---|---|
| `events` | `event_id` | `seq_id`, `event_type`, `camera_id`, `track_id`, `timestamp`, `payload`, `sha256_hash`, `prev_hash` | Monotonic, hash-chained master event ledger |
| `cameras` | `camera_id` | `name`, `source_type`, `source_url`, `location_label`, `status`, `fps`, `resolution` | Registered camera fleet registry |
| `security_zones` | `zone_id` | `name`, `camera_id`, `polygon_coords`, `severity`, `loitering_threshold_seconds`, `is_active` | Polygon geofences and spatial rules |
| `virtual_boundaries` | `boundary_id` | `name`, `camera_id`, `p1_x`, `p1_y`, `p2_x`, `p2_y`, `crossing_direction` | Directional virtual tripwires |
| `alerts` | `alert_id` | `event_id`, `camera_id`, `rule_name`, `severity`, `timestamp`, `status` | Operator alarm notifications |
| `incidents` | `incident_id`| `camera_id`, `status`, `severity`, `first_seen`, `last_seen`, `total_events` | Aggregated security incidents |
| `incident_annotations`| `annotation_id`| `incident_id`, `operator_callsign`, `note`, `disposition`, `timestamp` | Duty officer escalation logs |
| `evidence_snapshots`| `snapshot_id`| `incident_id`, `file_path`, `sha256_hash`, `captured_at` | Forensic JPEG evidence records |
| `system_audit_log` | `log_id` | `timestamp`, `action`, `operator`, `details` | System operational audit trails |

---

## 4. End-to-End System Data Flow

1. **Ingestion**: Video frames are captured at 30 FPS into a thread-safe ring buffer.
2. **Perception**: YOLOv8n detects objects (`person`, `vehicle`) and yields bounding boxes.
3. **Tracking**: ByteTrack assigns consistent track IDs (`TRK-01`, `TRK-02`) and calculates velocity vectors.
4. **Geofencing**: Spatial ray-casting evaluates point-in-polygon containment and dwell thresholds.
5. **Persistence**: The event is assigned a monotonic `seq_id`, hashed with SHA-256, and committed to SQLite WAL.
6. **Publishing**: The event passes through the gateway and is broadcast via WebSocket/REST to connected operator dashboards.
