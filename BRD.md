# Border Intelligence — Business Requirements Document (BRD)

**Problem Statement**: Smart India Hackathon PS SIH26187 — AI-Powered Border Surveillance & Perimeter Defense Infrastructure using existing CCTV cameras  
**Status**: Mature MVP (130/130 backend tests passing, functional end-to-end) → Entering Architecture Redesign Phase  
**Document Owner**: Piyush Chavhan  
**Document Version**: 1.0.0  
**Last Updated**: 2026-08-24  

---

## 1. Executive Summary & Overview

Border Intelligence (internally referred to as the *"Border Watch Command Post"*) is an intelligent edge-ready software platform designed to upgrade legacy fixed CCTV and RTSP surveillance infrastructure into an automated perimeter security network without requiring expensive hardware replacements.

The platform integrates:
- Real-time video ingestion (RTSP streams, local MP4/WebM recordings, and pre-recorded dataset sequences).
- Local, edge-deployable computer vision detection (YOLOv8n) and continuous multi-object tracking (ByteTrack with Kalman filter state estimation).
- Interactive, user-defined polygon geofencing, virtual tripwire breach detection, and dwell/loitering temporal analysis.
- Explainable security incident generation with synchronized video evidence playback and tactical SitRep dossiers.
- Cryptographic chain-of-custody logging with tamper-evident SHA-256 Merkle-style checksums.
- Grounded, anti-hallucinatory AI operator assistant querying live SQLite database state without external cloud LLM dependencies.

---

## 2. Stakeholders & User Roles

| Role | Responsibilities & Needs | MVP Access (Current) | Target V1 RBAC |
|---|---|---|---|
| **Duty Operator** | Monitor live CCTV feeds, acknowledge alerts, inspect incidents with synchronized video, query the grounded AI assistant. | Full local operator persona (`Duty Officer Alpha`). | `ROLE_OPERATOR` — Access to surveillance wall, live alerts, incident workspace, and AI query console. |
| **Commander / Admin** | Configure security zones and virtual tripwires, review forensic audits, approve tactical SitRep dossiers, manage camera registry. | Full access without authentication check. | `ROLE_ADMIN` / `ROLE_COMMANDER` — Full operational control, zone CRUD, system telemetry, and export permissions. |
| **Auditor** | Verify cryptographic chain-of-custody integrity, review historical incident logs, inspect SHA-256 Merkle hashes. | Access to Forensics view. | `ROLE_AUDITOR` — Read-only access to event store, forensic verifier, and audit trails. |

*(Note: Role definitions are provisional — formal RBAC with JWT token enforcement is scheduled for Phase 1 of the redesign; see Open Questions.)*

---

## 3. Business & Functional Goals

- **BR-001 (Cost-Effective Retrofit)**: Utilize existing fixed CCTV and RTSP cameras without requiring specialized hardware or rip-and-replace sensor deployments.
- **BR-002 (Real-Time Ingestion)**: Ingest video files (MP4/WebM via native OS file picker) and live RTSP camera streams at 30+ FPS.
- **BR-003 (Local Edge AI Perception)**: Execute local object detection (YOLOv8n) and continuous tracking (ByteTrack) with zero dependency on external cloud APIs.
- **BR-004 (Geofenced Perimeter Enforcement)**: Allow operators to draw interactive security polygons and tripwires directly on video feeds with automated dwell/loitering detection.
- **BR-005 (Explainable Incident Workspace)**: Automatically generate incidents when spatial rules are breached, providing synchronized video playback and natural-language AI reasoning.
- **BR-006 (Cryptographic Chain of Custody)**: Enforce a *Persist-Before-Publish* contract where every event is SHA-256 hash-chained and verifiable via in-place integrity audits.
- **BR-007 (Grounded AI Operator Assistant)**: Provide a natural-language assistant answering queries grounded exclusively in active SQLite database records to prevent hallucinations.

---

## 4. MVP Scope (Verified & Already Implemented)

The following capabilities are fully built, tested across 130 backend unit tests, and demonstrable in the React command post interface:

1. **CCTV Fleet Ingestion**:
   - RTSP IP stream connection with auto-reconnect.
   - Local MP4/WebM video file selection via native OS file manager picker (`<input type="file">`).
   - Pre-loaded benchmark defense datasets (VIRAT CCTV recordings).
2. **AI Detection & Tracking**:
   - YOLOv8n object detection (classes: Person, Vehicle, Truck, Bus, Motorcycle).
   - ByteTrack Kalman filter tracking maintaining persistent track IDs across frames.
   - Cardinal velocity headings (N, NE, E, SE, S, SW, W, NW) and speed estimation.
3. **Interactive Security Zones & Geofencing**:
   - Click-and-drag polygon boundary designer directly on live video.
   - Directional virtual tripwires.
   - Dwell time & loitering threshold evaluation with debounce timers.
4. **Incidents Command & Explainable Evidence**:
   - Master-detail incident investigation workspace.
   - Synchronized video playback jumping directly to the incident trigger timestamp.
   - Explainable AI reasoning card explaining the specific rule violation.
   - SHA-256 tamper-evident digital fingerprint committed to database.
   - Tactical SitRep dossier generator.
5. **Cryptographic Forensic System & Integrity Audit**:
   - SHA-256 hash chaining on all ingested events.
   - Single-event hash verification against stored database records.
   - In-place database integrity audit with progress reporting (0 crashes / 0 black screens).
   - Chronological chain-of-custody timeline log.
6. **Grounded AI Surveillance Assistant**:
   - Natural-language query interface grounded in live SQLite tables.
   - Anti-hallucination guardrails (refuses ungrounded biometrics, weapon claims, or cross-camera identity tracking).
7. **Command & Control Visualization**:
   - 3D spatial sector elevation map (Three.js).
   - Real-time alert ticker and DEFCON threat index gauge.
   - 8-step guided evaluation demonstration tour modal.
   - Multi-modal sensor telemetry overview (simulated).

---

## 5. Non-Functional Requirements (NFR)

- **NFR-001 (Performance & Throughput)**: Sustained 30–90 FPS inference throughput via adaptive frame striding; zero UI frame lag during simultaneous video playback, 3D rendering, and WebSocket streaming.
- **NFR-002 (Database Concurrency)**: SQLite WAL mode supporting 500+ concurrent event transactions/sec with `PRAGMA synchronous=NORMAL` and `busy_timeout=5000`.
- **NFR-003 (Edge Resilience & Offline Operation)**: 100% offline-capable with local PyTorch weights (`yolov8n.pt`) and local persistence. Zero reliance on internet connectivity or cloud LLM APIs.
- **NFR-004 (Data Integrity & Anti-Tamper)**: Every event is SHA-256 hash-chained; database modifications are detectable via Merkle-style root hash audits.
- **NFR-005 (Auditability)**: Complete chronological audit trail documenting all operator actions, incident acknowledgements, and zone modifications.

---

## 6. Out of Scope for MVP (Future Roadmap)

The following items are explicitly deferred to post-MVP production phases:
- Multi-tenant authentication with enterprise federated OAuth2 / Keycloak identity providers.
- Direct physical IoT hardware drivers for physical radar and seismic sensor arrays (sensors remain simulated via `multi_modal.py`).
- Distributed multi-node database replication (PostgreSQL / TimescaleDB).
- Automated PTZ (Pan-Tilt-Zoom) camera slew-to-cue tracking.
- Drone / UAV autonomous patrol telemetry integration.
- Offline satellite uplink data synchronization.

---

## 7. Known Gaps Driving the Architectural Redesign

1. **Absence of Authentication Layer**: Current MVP operates on an open local network with a static "Duty Officer Alpha" persona.
2. **Flat Backend Structure**: 13 routers and 9 subsystems sit as flat siblings with no explicit domain boundaries or gateway abstraction.
3. **Frontend Structural Debt**: Redundant nested folder (`frontend/src/src/`), flat `views/` + `components/` split, and an unsplit Three.js bundle (~1.04 MB single chunk).
4. **Documentation Sprawl**: 40 root-level markdown files created during iterative sprints, lacking a consolidated single source of truth.
5. **Direct SQLAlchemy Coupling**: Direct session calls inside routes prevent clean swapping from SQLite to PostgreSQL/TimescaleDB.

---

## 8. Open Questions Requiring Confirmation

1. **Authentication Protocol**: Preferred protocol for V1 (Standalone JWT with `python-jose` proposed for hackathon agility vs OAuth2/Keycloak for enterprise).
2. **Target Edge Compute Platform**: NVIDIA Jetson Orin vs Edge x86 Server vs Centralized Server (impacts edge/core split packaging).
3. **Forensic Evidence Retention**: Required retention duration (30 days vs 90 days vs 1 year).
4. **Target RBAC Roles**: Proposed roles: `Operator`, `Commander`, `Auditor` (confirm if additional granularity is required).

---

## 9. Redesign Success Criteria

1. **Zero Regressions**: All 130 backend unit tests continue passing after restructuring.
2. **Clean Frontend Build**: `npm run build` succeeds with 0 TypeScript errors and 0 lint warnings.
3. **Explicit Demo Mode**: Authentication can be toggled via an explicit `DEMO_MODE=true` environment flag rather than being silently absent.
4. **Clear Domain Ownership**: A new engineer can locate any feature's code by folder name alone without tribal knowledge.
