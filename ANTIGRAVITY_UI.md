# ANTIGRAVITY — UI ↔ Backend Integration Spec

**Project:** Border Intelligence (SIH PS **SIH26187**)
**Repo:** `D:\SIH   border cctv` · branch `feat/mvp-real-tracking`
**Audience:** the agent building the new frontend.
**Scope of this file:** *how the UI connects to the backend.* Data flow, endpoints,
payload shapes, coordinate systems, state ownership. **Nothing about styling,
theming, colours, fonts, or layout aesthetics** — those are your call entirely.

---

## 0. Situation

The previous UI was **deliberately deleted**. `frontend/src/App.tsx` is currently a
14-line placeholder that renders "UI CLEARED". You are building the replacement
from scratch.

**What survived, and is your foundation:**

| File | Status | Use it? |
|---|---|---|
| `frontend/src/api/client.ts` | Complete REST client, **4 broken methods** (§7) | **Yes** — fix, then build on it |
| `frontend/src/hooks/useWebSocket.ts` | Working auto-reconnect WS hook, **wrong `event_type` casing** (§6) | **Yes** — fix the type union |
| `frontend/src/types/surveillance.ts` | TS types, **partly stale/wrong** (§7) | Yes, but verify against `/openapi.json` |
| `frontend/src/hooks/use-auth.ts`, `use-mobile.ts` | Working | Yes |
| `frontend/src/lib/detection-simulator.ts` | **Fake data generator** | **DELETE** |
| `frontend/src/lib/simulation/demoScenario.ts` | **Fake data generator** | **DELETE** |
| `frontend/src/lib/camera-engine.ts` | Client-side perception — backend does this now | **DELETE** |
| `frontend/src/lib/audioSensory.ts` | Synthesised alert sounds, not backend data | Delete unless you want UI-only audio cues |
| `frontend/src/lib/workflow/workflowEngine.ts` | Client-side rule engine — backend owns rules | **DELETE** |
| `frontend/src/lib/events/eventTypes.ts` | Invented event model, does not match backend | **DELETE** — use §6 shapes |

### Division of labour

| You (antigravity) | Me (backend) |
|---|---|
| All UI, all components, all screens | Perception, detection, tracking, alerts |
| Fixing `client.ts` / `surveillance.ts` mismatches | New endpoints in §9 (modality, chatbot time+region) |
| Zone/tripwire **drawing surface** | Zone **evaluation + alert generation** |
| Chatbot **chat surface** | Chatbot **query understanding + grounding** |

Endpoints marked **PLANNED** in §9 do not exist yet. I am building them. Their
contracts below are fixed — build the UI against them and they will line up.

---

## 1. Run it

Backend (from repo root):

```bash
./venv/Scripts/python -m uvicorn backend.main:app --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Tests (must stay green):

```bash
./venv/Scripts/python -m pytest tests/ -q
```

Live API reference — **this is the source of truth, not this file**:

```bash
curl http://127.0.0.1:8000/openapi.json
```

On boot the backend auto-registers and starts camera **`CAM-01`** playing the
bundled VIRAT clip (`AUTOSTART_DEMO_CAMERA=True` in `backend/config.py`). So a
freshly started backend already has one real camera producing real detections —
you do not need to register anything to see video.

---

## 2. Ground rules (non-negotiable)

1. **No fake data on the primary path.** Every box, number, alert, and track ID
   the operator sees comes from the backend. No `Math.random()`, no `Math.sin()`
   animation, no seeded demo arrays, no placeholder counts.
2. **Never draw detection boxes client-side.** The backend burns boxes, labels,
   and track IDs into the JPEG frames. See §3.
3. **Empty state is a real state.** If there are no alerts, render "no alerts" —
   do not invent one. If a camera is offline, say offline.
4. **The backend owns all rules.** Zone entry, tripwire crossing, loitering,
   threat scoring, incident creation. The UI displays outcomes; it never decides
   them.
5. **Don't break the REST/WS contract.** If you need a shape change, tell me —
   don't reshape the backend to fit a component.

---

## 3. The integration model

Three channels, three jobs. Keep them separate in your architecture.

```
                    ┌──────────────────────────────────────┐
                    │            FastAPI :8000             │
                    └──────────────────────────────────────┘
                          │            │             │
        MJPEG (pixels)    │            │ WS (events) │  REST (state)
                          ▼            ▼             ▼
              ┌───────────────┐  ┌──────────┐  ┌──────────────┐
              │ <img src=...> │  │ push     │  │ fetch/poll   │
              │ boxes already │  │ live     │  │ lists, CRUD, │
              │ burned in     │  │ alerts   │  │ metrics      │
              └───────────────┘  └──────────┘  └──────────────┘
```

### Channel 1 — Video: MJPEG, boxes pre-drawn

```
GET /api/stream/video/{camera_id}     → multipart/x-mixed-replace; boundary=frame
```

Consume it with a plain image element. That is the whole integration:

```tsx
<img src={api.getVideoStreamUrl(cameraId)} alt={`Camera ${cameraId}`} />
```

The server-side perception worker (`backend/tracking/live_worker.py`) is the
**single owner of the frame source**. It reads the frame, runs YOLOv8n, runs
ByteTrack, draws boxes + labels + track IDs onto that exact frame, JPEG-encodes
once, and fans it out to all viewers. Boxes therefore **cannot drift out of sync
with the video** — they are the same pixels.

Consequences you must respect:

- **Do not** fetch detections over REST/WS and position `<div>`s over the video.
  That was the old UI's fake-data bug. Boxes are pixels, not DOM.
- Requesting the stream for a stopped camera **auto-restarts its worker** if the
  underlying adapter is alive — a tile that reappears after a backend restart is
  expected behaviour, not a bug.
- Concurrent MJPEG clients are capped at **12** (`MAX_MJPEG_CLIENTS`). Each
  mounted `<img>` is one client. Unmount tiles you are not showing — do not keep
  16 hidden streams alive.
- To stop a stream, remove the element from the DOM or clear `src`. A hidden but
  mounted `<img>` still consumes a slot.

Single still frame (annotated JPEG), for thumbnails and for the zone-drawing
canvas:

```
GET /api/stream/snapshot/{camera_id}   → image/jpeg
                                         404 if no worker · 503 if no frame yet
```

### Channel 2 — Events: WebSocket push

```
ws://127.0.0.1:8000/ws/events          (alias: /api/ws/events)
```

Use the existing `useWebSocket` hook — it already does exponential-backoff
reconnect (capped 10 s) and a 25 s ping keepalive. Payload shapes in §6.

This is how alerts arrive **live**. Do not poll `/api/alerts` on a timer for
liveness; poll only to load history on mount, then let the socket append.

### Channel 3 — State: REST

Lists, CRUD, metrics. Full table in §5.

---

## 4. Coordinate systems — the #1 integration landmine

Read this twice. Getting it wrong makes zones silently misaligned, and the bug
looks like "the backend is wrong" when it isn't.

**Zone polygons and tripwire endpoints are in SOURCE-FRAME PIXEL coordinates.**

Not normalised 0–1. Not CSS pixels. Not viewport coordinates. The pixel grid of
the *decoded video frame* — e.g. `1920 × 1080` for the VIRAT clip.

Your `<img>` is almost certainly displayed at some other size (CSS scaling,
`object-fit`, responsive layout, device pixel ratio). So a raw click coordinate
is **wrong** and must be converted:

```ts
function toFrameCoords(
  e: React.MouseEvent<HTMLImageElement>,
): [number, number] {
  const img = e.currentTarget;
  const rect = img.getBoundingClientRect();

  // Displayed (CSS) position of the click, relative to the element.
  const cssX = e.clientX - rect.left;
  const cssY = e.clientY - rect.top;

  // Scale from displayed size to the real decoded frame size.
  const scaleX = img.naturalWidth / rect.width;
  const scaleY = img.naturalHeight / rect.height;

  return [cssX * scaleX, cssY * scaleY];
}
```

`naturalWidth` / `naturalHeight` give the true frame dimensions — read them from
the image itself, never hardcode `1920×1080`.

**Caveats:**

- If you use `object-fit: contain`, there is letterboxing; `rect` includes the
  bars but the image does not. Either avoid `contain` on the drawing surface, or
  subtract the letterbox offset. `object-fit: fill` on the drawing canvas is the
  simplest correct choice.
- Draw your in-progress polygon in **CSS space** for feedback, but convert to
  frame space on submit. Keep both; don't round-trip.
- Round to sensible precision on submit. The backend accepts floats.

**Related pixel-space fields** (same grid, same rules):

- `DetectionEvent.bounding_box` → `[x1, y1, x2, y2]`
- `TrackingEvent.position` → `[cx, cy]`, `velocity` → `[dx, dy]`
- `TrackingEvent.speed` → **pixels per frame**, not m/s. Label it as such —
  don't render a fake real-world velocity.
- `TrackingEvent.direction` → degrees, 0–360.
- `DetectionResult.normalized_box` exists (0–1) but is **not** what the zone API
  takes. Don't mix them.

**Track IDs are camera-local.** Track 17 on `CAM-01` and Track 17 on `CAM-02` are
unrelated. Never show a cross-camera "same person" claim — the backend explicitly
refuses that question.

---

## 5. Verified endpoint contract

All verified against the routers on this branch. `POST` bodies are JSON unless noted.

### Health / system

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{status, service, database}` |
| GET | `/api/readiness` | `{status, checks}` |
| GET | `/api/system/status` | Broad status blob |
| GET | `/api/system/metrics` | **Real measured perf** — see below |
| GET | `/api/system/coverage-report` | |
| GET | `/api/system/profiles` · POST `/api/system/profiles/apply` | |
| GET | `/api/system/audit-logs?limit=` | |
| GET | `/api/system/db-diagnostics` | |
| POST | `/api/system/demo-reset` | Destructive — confirm in UI first |

`/api/system/metrics` returns measured numbers from the live workers (these were
once hardcoded fakes; they are now real). Useful keys:

```
device, gpu_available, gpu_device_name, memory_usage_mb,
capture_fps, ai_processing_fps, display_fps, effective_visual_fps,
inference_latency_ms, tracking_latency_ms, prediction_latency_ms,
persistence_latency_ms, encoding_latency_ms, total_pipeline_latency_ms,
frame_stride, processed_frames, skipped_frames, predicted_frames,
dropped_frames, active_tracks, alerts, workers_running,
hardware{...}, performance{...}, telemetry{...}, cameras[...]
```

`display_fps` is what the operator actually sees — use that for an FPS readout.
`workers_running == 0` means nothing is being perceived; surface that honestly.

### Cameras

| Method | Path | Notes |
|---|---|---|
| GET | `/api/cameras` | `{total, cameras[]}` |
| GET | `/api/cameras/{id}` | 404 if unknown |
| POST | `/api/cameras/register` | See body below |
| POST | `/api/cameras/upload` | **`multipart/form-data`**, field `file` (+ `name`, `location_label`). Max **2 GB**, chunked |
| GET | `/api/cameras/sources/available` | `{bundled_clips[], uploaded_clips[], total_count}` |
| POST | `/api/cameras/{id}/start` · `/stop` · `/reconnect` | Starts/stops the perception worker |
| DELETE | `/api/cameras/{id}` | Deregisters + stops worker |
| GET | `/api/cameras/{id}/diagnostics` | 404 if unknown |
| GET | `/api/cameras/{id}/heatmap` | `{density_matrix, ...}` — 200 even for unknown id |

Register body:

```json
{
  "camera_id": "CAM-02",
  "name": "North Gate",
  "source_type": "video_file",   // "video_file" | "rtsp" | "webcam"
  "source_path": "VIRAT/CCTV 01/....mp4",   // video_file
  "source_url":  "rtsp://user:pass@host:554/live",  // rtsp
  "device_index": 0,                        // webcam
  "location_label": "Sector Alpha",
  "fps": 25,
  "loop": true,
  "autostart": true
}
```

RTSP credentials are **never echoed back** in responses — don't try to display
them, and don't cache the URL you posted in app state.

### Alerts / incidents

| Method | Path | Notes |
|---|---|---|
| GET | `/api/alerts?camera_id=&severity=&limit=` | `{count, alerts[]}` · limit 1–500, default 50 |
| POST | `/api/alerts/{event_id}/acknowledge` | ⚠️ **not `/ack`** — see §7 |
| GET | `/api/incidents?camera_id=&limit=` | `{count, incidents[]}` |
| GET | `/api/incidents/{id}` | ⚠️ Timeline lives here, **not `/{id}/timeline`** — §7 |
| GET | `/api/incidents/{id}/dossier` | 404 if unknown |
| GET · POST | `/api/incidents/{id}/notes` | POST `{operator_callsign, note, disposition}` |

`AlertItem.severity` is uppercased by the backend (`"CRITICAL"`, `"WARNING"`,
`"RESTRICTED"`, …). Compare case-insensitively.

### Zones & boundaries

| Method | Path | Notes |
|---|---|---|
| GET | `/api/zones` | `{zones[], boundaries[]}` |
| POST | `/api/zones` | Polygon zone — **min 3 points**, source-frame pixels |
| POST | `/api/zones/boundary` | Tripwire line — `pt1`, `pt2` |
| DELETE | `/api/zones/{id}` | Matches zone **or** boundary id · 404 if neither |
| GET | `/api/zones/templates` | Prebuilt tactical shapes |
| POST | `/api/zones/apply-template` | `{template_id, zone_id_suffix, custom_name}` |

```json
// POST /api/zones
{
  "zone_id": "zone_north_01",
  "name": "North Restricted",
  "polygon": [[420, 180], [900, 180], [900, 640], [420, 640]],
  "severity": "restricted",            // info | warning | restricted | critical
  "loitering_threshold_seconds": 2.0,
  "loitering_debounce_seconds": 30.0
}
```

```json
// POST /api/zones/boundary
{
  "boundary_id": "wire_north_01",
  "name": "North Fence",
  "pt1": [200, 500],
  "pt2": [1700, 520],
  "severity": "critical"
}
```

An unrecognised `severity` string is silently coerced (zones → `restricted`,
boundaries → `critical`) rather than rejected. Send valid values; don't rely on a
validation error to catch typos.

> ⚠️ **Zones are currently IN-MEMORY ONLY.** They are lost on backend restart and
> there is no load-on-startup. Design for this: after any zone mutation, re-`GET
> /api/zones` and treat the server as authoritative. Do **not** keep a
> localStorage copy and assume the backend still has it. I am adding persistence
> (§9) — when it lands, this behaviour only gets better, and your code won't change.

### Intelligence / chatbot

| Method | Path | Notes |
|---|---|---|
| POST | `/api/intelligence/query` | `{query, camera_id?}` → grounded answer |

```json
// response
{
  "query": "When did Track 17 enter the restricted zone?",
  "status": "answered",           // answered | no_records_found
                                  // | unsupported_capability | invalid_query
  "grounding_status": "grounded", // grounded | no_data | refusal
  "observed_facts": ["Track 17 was recorded entering ..."],
  "rule_results":  ["... intrusion rule event ..."],
  "interpretation": "Track 17 entered zone ...",
  "evidence": [{ ... }]
}
```

**Render all five fields.** The three-tier structure (raw facts → rule results →
interpretation) is the anti-hallucination design and the thing that makes this
defensible to judges. Collapsing it to just `interpretation` throws away the
grounding audit trail.

Handle every `status`, not just `answered`:

- `no_records_found` → "nothing on record for that", with `grounding_status: "no_data"`
- `unsupported_capability` → a **deliberate refusal** (face ID, weapon detection,
  criminal intent, cross-camera identity). Render the refusal text as the answer.
  It is a feature, not an error — do not retry, do not show an error toast.
- `invalid_query` → SQL injection guard tripped.

### Threat / forensics / export / sensors

| Method | Path | Notes |
|---|---|---|
| GET | `/api/threat/level?camera_id=` | |
| GET | `/api/evidence/verify/{event_id}` | 404 if unknown |
| GET | `/api/evidence/audit-integrity?limit=` | Hash-chain check |
| GET | `/api/evidence/snapshots/{incident_id}` | |
| GET | `/api/evidence/snapshots/file/{filename}` | Raw image — use directly as `src` |
| GET | `/api/events?...` · `/api/events/incident/{id}` | |
| GET | `/api/events/export?format=json\|csv&camera_id=&event_type=` | `format` other than json/csv → **422** |
| GET | `/api/sensors/status` | |
| POST | `/api/sensors/ingest` | Malformed body → **422** |
| GET | `/api/auth/demo-token` · POST `/api/auth/token` | `DEMO_MODE=True` → WS/REST work without a token |

> The multi-modal sensor endpoints (`radar`, `seismic`, `THERMAL_IR`) are
> **simulated telemetry**, not real sensors and not thermal *video*. If you surface
> them, label them as simulated. Do not present them as live hardware — that is
> exactly the overclaiming this rebuild removed. Real thermal/IR **inference** is
> a separate thing, see §9.

---

## 6. WebSocket contract

Connect: `ws://127.0.0.1:8000/ws/events`. Works without a token while
`DEMO_MODE=True`.

Keepalive: client sends `{"type":"ping"}`; server replies `{"type":"pong"}`. The
existing hook does this every 25 s. Filter pong out before rendering.

**Every other message is a raw serialised backend event** (`event.model_dump_json()`).

### ⚠️ Landmine: `event_type` is UPPERCASE

`useWebSocket.ts` currently declares:

```ts
event_type: "alert" | "zone" | "tracking" | "detection" | "incident" | "system" | "pong";
```

That is **wrong**. The backend `EventType` enum serialises uppercase. A
`switch (msg.event_type) { case "alert": ... }` written from that type will
**never match** — and it fails silently, which is the worst kind of bug here.

Fix it to the real values:

```ts
export type BackendEventType =
  | "DETECTION" | "TRACKING" | "ZONE" | "RISK"
  | "EVIDENCE"  | "ALERT"    | "INCIDENT" | "HANDOFF" | "SYSTEM";
```

### Common envelope (all events)

```ts
{
  event_id: string;      // UUID
  event_type: BackendEventType;
  timestamp: string;     // ISO 8601, UTC
  camera_id: string;
  track_id?: string | null;
  incident_id?: string | null;
  confidence?: number | null;
  source: "video_file" | "simulation" | "radar_sim" | "rf_sim"
        | "thermal_sim" | "unavailable";
}
```

### Per-type extra fields

| `event_type` | Extra fields |
|---|---|
| `ALERT` | `alert_id`, `severity` (`"LOW"`\|`"MEDIUM"`\|`"HIGH"`\|`"CRITICAL"`), `message`, `is_acknowledged` |
| `ZONE` | `zone_id`, `zone_name`, `zone_severity`, `transition` (`entered`\|`exited`\|`dwelling`\|`crossed`\|`loitering`), `dwell_duration_seconds?` |
| `TRACKING` | `lifecycle` (`created`\|`updated`\|`lost`\|`recovered`\|`terminated`), `position [cx,cy]`, `velocity [dx,dy]`, `object_class?`, `bounding_box?`, `frame_number?`, `speed?` (px/frame), `direction?` (deg) |
| `DETECTION` | `object_class`, `bounding_box [x1,y1,x2,y2]`, `frame_number` |
| `RISK` | `risk_level` (`low`\|`medium`\|`high`\|`critical`), `reasons: string[]` |
| `EVIDENCE` | `frame_path`, `frame_number`, `trigger_reason`, `frame_type` |
| `INCIDENT` | `lifecycle` (`opened`\|`updated`\|`closed`), `event_ids: string[]` |
| `SYSTEM` | `subtype` (`camera_unavailable`\|`camera_recovered`\|`model_error`\|`pipeline_degraded`\|`pipeline_recovered`\|`evidence_unavailable`\|`database_error`), `details` |
| `HANDOFF` | `from_camera_id`, `to_camera_id`, `association_score`, `association_status` |

### Consumption guidance

- **`ALERT`** → the alert feed, badge counts, toasts. This is the money event.
- **`ZONE`** → zone highlight / transition log. `transition: "crossed"` is a
  tripwire hit.
- **`SYSTEM`** → connection and camera health banners. `camera_unavailable` /
  `pipeline_degraded` are real states worth showing.
- **`TRACKING`** → **high volume.** Use for counts, track lists, and the chatbot's
  context. **Do not** use it to draw boxes (§3). Throttle/batch before touching
  React state, or you will re-render on every frame.
- Events are **persisted before published** — anything you receive on the socket
  is already durable in SQLite. Safe to treat as authoritative immediately.

### On mount

1. `GET /api/alerts?limit=50` for history.
2. Open the socket.
3. Append arriving events; de-duplicate on `event_id`.

Don't reload the full list on every socket message.

---

## 7. Broken client methods — fix these first

Verified mismatches in `frontend/src/api/client.ts`. All four fail at runtime
today. Fix before building anything on top.

| Method | Currently calls | Actual route | Fix |
|---|---|---|---|
| `acknowledgeAlert` | `POST /api/alerts/{id}/ack` | `POST /api/alerts/{id}/acknowledge` | Change path |
| `getIncidentTimeline` | `GET /api/incidents/{id}/timeline` | `GET /api/incidents/{id}` | Drop `/timeline` |
| `exportAuditLog` | `GET /api/forensics/export` | `GET /api/events/export` | Change path (`getExportUrl` already correct) |
| `getRawStreamUrl` | `/api/stream/raw/{id}` | **no such route** | Delete the method |

### `surveillance.ts` is partly stale

Confirmed wrong against the live API:

- **`SystemMetrics`** — declares `cpu_percent`, `memory_mb`, `gpu_utilization`,
  `inference_fps`. The API returns **none** of those names (see §5 for the real
  keys). Rewrite this interface.
- **`AlertsResponse`** — declares `{total, unacknowledged, alerts}`. API returns
  `{count, alerts}`.
- **`IncidentSummary`** — shaped like aggregate stats, but used in `client.ts` as
  the **array element** type for `/api/incidents`. Semantically wrong.
- **`SecurityZone` / `VirtualBoundary`** — API also returns `is_active`.

**Recommended:** generate types from `http://127.0.0.1:8000/openapi.json` and
delete the hand-written duplicates. The `Detection`, `SimulatedAlert`, and
`BoundaryShape` interfaces are leftovers from the fake-data UI — `Detection` and
`SimulatedAlert` should go; `DrawingPoint`/`BoundaryShape` are fine as
**UI-local** draw state, but convert to the API shape (§5) on submit.

---

## 8. What to build

Four capabilities drive this product. Build the UI for each.

### 8.1 Camera inference — visible, multi-modal

One surface showing live annotated video per camera, plus camera management.

- Video tiles: `<img src={api.getVideoStreamUrl(id)}>` — nothing else. (§3)
- Camera list from `GET /api/cameras`; start/stop/reconnect controls.
- Add a camera three ways, all real:
  - **bundled clip** → `GET /api/cameras/sources/available` → `register` with `source_path`
  - **upload** → `POST /api/cameras/upload` (multipart, ≤2 GB) — show progress
  - **live** → `register` with `source_type: "rtsp"` + `source_url`, or `"webcam"` + `device_index`
- Per-camera health from `GET /api/cameras/{id}/diagnostics` and `SYSTEM` events.
- **Modality selector — RGB / IR / Thermal.** The picker is yours to build now;
  the backend field is **PLANNED** (§9.1). Until it lands, sending `modality` is
  harmless (ignored). Show the active modality on the tile so an operator can
  tell a thermal feed from a daylight one.
- Respect the **12-client MJPEG cap** — unmount offscreen tiles.

### 8.2 Zone & boundary plotting

The operator draws restricted areas and tripwire lines directly on the camera
view; crossing them generates real alerts.

**Draw on a still frame, not on live video.** Use
`GET /api/stream/snapshot/{camera_id}` as the canvas backdrop. Drawing on a
moving image is unusable, and the snapshot gives you a stable pixel grid.

- **Polygon zone** — click to add vertices, ≥3 required, close the shape,
  name it, pick severity → `POST /api/zones`.
- **Tripwire line** — two clicks → `POST /api/zones/boundary`.
- Convert every click with `toFrameCoords()` (§4). This is where it goes wrong.
- Render existing zones/boundaries from `GET /api/zones` as an overlay on the
  snapshot — an SVG layer scaled by the same factor. (Overlaying **zones** is
  correct; overlaying **detection boxes** is not. Zones are UI-owned geometry the
  backend never draws; boxes are backend-owned pixels.)
- Delete via `DELETE /api/zones/{id}` — works for both types.
- Offer `GET /api/zones/templates` + `apply-template` as a fast path.
- After every mutation, re-`GET /api/zones`. Server is authoritative (zones are
  in-memory today — §5).
- Live feedback: a `ZONE` event with `transition: "entered"` or `"crossed"` means
  the operator's shape just fired. Highlight that zone.

**Make this fast and forgiving — it is the feature judges will try themselves.**
An operator must be able to draw a working restricted zone in **under ~10 seconds**
without reading instructions:

- **Two obvious modes only:** "Draw Zone" (polygon) and "Draw Tripwire" (line).
  Mode should be visible at all times while drawing.
- **Auto-generate `zone_id` / `boundary_id`.** Never make the operator invent an
  ID — that is an API detail. Auto-name too ("Zone 1", "Tripwire 2"), editable
  after.
- **Sensible default severity** (`restricted` for zones, `critical` for tripwires)
  so a zone can be created without touching a dropdown.
- **Undo the last point**, and cancel the whole shape (Escape). Misclicks are
  constant with polygon drawing.
- **Close the polygon** by clicking the first vertex *or* a double-click/"finish"
  action — don't require exact pixel accuracy on the first point.
- **Show the vertex count** and block submit below 3 with a clear reason (the API
  requires ≥3 and will 422).
- **Rubber-band preview** of the segment in progress, and of the tripwire line
  between the two clicks.
- **One-click delete** on an existing shape, plus the template fast path
  (`GET /api/zones/templates` → `apply-template`).
- After creating a zone, **immediately show it firing** — keep the snapshot view
  open long enough that the operator sees the `ZONE` event arrive.

Zones and tripwires are **modality-independent**: the same drawing surface and the
same API serve RGB, IR, and thermal cameras. Use each camera's own snapshot as the
backdrop so the geometry matches that camera's frame.

### 8.3 Alerts, incidents, evidence

- Live feed driven by `ALERT` events over WS, seeded from `GET /api/alerts`.
- Acknowledge → `POST /api/alerts/{event_id}/acknowledge` (§7).
- Filter by camera / severity / acknowledged.
- Alert → incident drill-down: `GET /api/incidents/{id}` (timeline),
  `/dossier`, `/notes` (read + post).
- Evidence: `GET /api/evidence/snapshots/{incident_id}`, images via
  `/api/evidence/snapshots/file/{filename}`.
- Integrity: `GET /api/evidence/verify/{event_id}` and `/audit-integrity` — the
  hash-chain tamper check is a strong demo beat.
- Export: link `GET /api/events/export?format=csv`.

### 8.4 AI chatbot

A chat surface over `POST /api/intelligence/query`. Grounded, not generative —
it answers only from persisted events and **refuses** what it cannot know.

Works **today**:

- "When did Track 17 enter the restricted zone?" / "When did Track 17 leave?"
- "How long did Track 17 remain inside the zone?"
- "What direction and speed was Track 17 moving?"
- "Why was the alert generated for camera CAM-01?"
- "Show all boundary crossings on this camera"
- "Show evidence for the highest-risk event"
- Relative time: **"in the last 30 minutes"**, "last 2 hours"
- Refusals (by design): face/identity, weapons, criminal intent, cross-camera identity

**PLANNED** (§9.2) — build the UI now, wire when it lands:

- **Absolute time range:** *"show me the alerts from 1 pm to 5 pm"*
- **Spatial region:** *"was there any person here?"* — the operator **marks a
  region on the screen** and asks about it.

UI requirements:

- Render all five response fields (§5) — keep the grounded/refusal distinction visible.
- **Region picker in the chat flow:** a "mark an area" affordance that opens the
  same drawing surface as §8.2 (reuse it), captures a polygon in **frame pixels**,
  and attaches it to the query as `region`. Show the marked shape next to the
  question in the transcript so the answer stays interpretable.
- Time-range picker that emits ISO 8601 UTC.
- Show `camera_id` scope; let the operator change it.
- Suggested-question chips from the working list above — this is how a judge
  discovers the feature.
- A refusal is a **valid answer**. Render it as one.

### 8.5 Alerting UX — sound + panel (required)

An alert the operator can miss is a failed alert. Three things must happen
**every time** an `ALERT` event arrives over the WebSocket:

1. **Audible cue.** Play a sound. Severity-differentiated (`CRITICAL` distinct
   from `WARNING`) so an operator can triage without looking.
2. **Alert panel entry.** The alert appears in a persistent, always-visible alert
   panel — newest first, with camera, time, severity, message, and track ID.
   Not a toast that disappears. A toast *in addition* is fine.
3. **Visual attention.** Unacknowledged count badge, and the originating camera
   tile marked so the operator knows *where* to look.

**Browser autoplay policy:** audio will not play until the user has interacted
with the page. Handle this — a one-time "enable audio" affordance, and never let
a blocked `play()` throw into a broken state. Provide a mute toggle; mute must
not suppress the panel entry.

**Alert triggers you will receive** (all backend-generated, all real):

| Situation | Arrives as | Notes |
|---|---|---|
| Person/vehicle detected | `DETECTION` / `TRACKING` events | High volume — **do not** sound per detection |
| Person **enters restricted zone** | `ZONE` (`transition: "entered"`) + `ALERT` | Sound + panel |
| Person **crosses border tripwire** | `ZONE` (`transition: "crossed"`) + `ALERT` | Sound + panel, highest urgency |
| Person **loitering** in zone | `ZONE` (`transition: "loitering"`) + `ALERT` | Sound + panel |
| Person **approaches** border line | `ALERT` — **PLANNED** (§9.3) | Early warning, before crossing |
| Camera/pipeline failure | `SYSTEM` | Distinct cue from a security alert |

**Sound on plain detection — read this carefully.** A person being detected is
*not* by itself a security event: on a border feed there may be dozens of people
continuously, and sounding on every detection produces a constant tone that
operators immediately mute, which then hides the real alerts. So:

- **Sound on `ALERT` events** — those are backend-adjudicated security events.
- For "a person appeared at all", offer it as an **opt-in toggle**
  ("chime on new person"), keyed on `TRACKING` with `lifecycle: "created"` and
  `object_class: "person"` — that fires once per new track, not once per frame.
  Debounce it (e.g. max one chime per 3 s).

Every one of these behaves **identically for all three camera modalities** (RGB /
IR / thermal). Alerting is modality-independent: the same zone, tripwire, and
loitering rules run on a thermal feed as on a daylight one. Show which modality
raised the alert; don't branch the logic.

### 8.6 System / performance

- `GET /api/system/metrics` → `display_fps`, `inference_latency_ms`,
  `frame_stride`, `active_tracks`, `workers_running`, device.
- Show real numbers even when bad. `workers_running: 0` must look wrong.
- WS connection state from the hook's `status`.
- `POST /api/system/demo-reset` is **destructive** — confirm first.

---

## 9. Backend work in flight (mine)

Contracts are fixed. Build against them; they will land matching this.

### 9.1 PLANNED — camera modality (RGB / IR / thermal)

**Today:** only RGB inference is real. `SourceType.THERMAL_SIM` and
`sensors/multi_modal.py`'s `ThermalIRPayload` are *simulated telemetry* — there is
no thermal or IR **video inference** anywhere in the pipeline.

**Landing:** a `modality` field on camera register/response:

```json
{ "camera_id": "CAM-03", "source_type": "rtsp",
  "source_url": "rtsp://...", "modality": "thermal" }   // "rgb" | "ir" | "thermal"
```

`GET /api/cameras` will echo `modality` per camera. The worker will select a
modality-appropriate preprocessing chain, confidence threshold, and weights.

**Be honest in the UI:** COCO-trained YOLOv8n is an RGB model. On thermal/IR
input, accuracy is genuinely lower until fine-tuned weights exist. Show the
modality on the tile; don't imply IR and RGB are equally reliable.

### 9.2 PLANNED — chatbot time-range + spatial region

`POST /api/intelligence/query` gains two optional fields. Existing behaviour is
unchanged, so today's UI keeps working:

```json
{
  "query": "show me the alerts from 1pm to 5pm",
  "camera_id": "CAM-01",
  "time_range": { "start": "2026-08-27T13:00:00Z", "end": "2026-08-27T17:00:00Z" },
  "region":     { "polygon": [[420,180],[900,180],[900,640],[420,640]] }
}
```

- `time_range` — absolute ISO 8601 UTC. Today only *relative* windows ("last N
  minutes/hours") parse; absolute clock ranges do not.
- `region` — polygon in **source-frame pixels**, same grid as zones (§4).
  Answered by point-in-polygon over persisted `bounding_box` / `position` values,
  so it stays grounded in real recorded data.

Send them as **structured fields**, not prose in `query`. Natural-language
phrasing will also be parsed as a fallback, but structured input is exact.

### 9.3 PLANNED — proximity / "approaching the border line" alerts

**Today:** a tripwire fires only when a track **crosses** it. There is no early
warning as someone *approaches*.

**Landing:** an approach alert raised before the crossing, so the operator gets
warning time. It arrives as a normal `ALERT` event over the same WebSocket — no
new channel, no new endpoint, and **no UI change needed beyond §8.5**.

Distinguishing fields on the alert:

```json
{
  "event_type": "ALERT",
  "severity": "WARNING",
  "message": "Track 17 (person) approaching 'North Fence' — 42 px, closing",
  "camera_id": "CAM-01",
  "track_id": "17"
}
```

Treat it as a lower-urgency cue than a crossing: `WARNING` severity vs the
crossing's `CRITICAL`. Give it a distinct, softer sound so an operator can hear
the difference between "someone is near the line" and "someone crossed it".

This runs for **all three modalities** and for both tripwires and zone edges.

### 9.4 Zone persistence

Zones/boundaries are in-memory today and lost on restart (§5). I am adding
persistence. **No UI change** — keep treating `GET /api/zones` as authoritative
after every mutation and this improves invisibly.

### 9.5 YOLO inference speed and stutter


Being worked on backend-side. Two verified defects:

- `get_detector()` constructs `ObjectDetector()` with **no settings applied** —
  `device="cpu"` and `imgsz=640` are hardcoded defaults, so
  `settings.DEVICE`, `DEFAULT_INFERENCE_SIZE`, `CONFIDENCE_THRESHOLD`, and
  `IOU_THRESHOLD` never reach inference. The config knobs are dead.
- **No model warmup** — the first inference pays lazy graph init, which is a
  visible stall right when a demo starts.

**What this means for your UI:** frame stride is expected and normal. The backend
runs detection every Nth frame (adaptive, 1–5) and **Kalman-predicts boxes on the
skipped frames**, so every displayed frame still has a box. Stride trades
detection frequency, not smoothness.

So: **do not** build UI that assumes a fixed FPS, and **do not** treat
`frame_stride > 1` as an error state. Read `display_fps` for what the operator
sees and `ai_processing_fps` for detection rate — they legitimately differ.

---

## 10. Acceptance checks

Verify by running the app, not by reading docs.

| # | Check |
|---|---|
| 1 | `CAM-01` shows real video with boxes + stable track IDs following real people/vehicles |
| 2 | An RTSP/webcam camera survives unplug → replug (auto-reconnect, no manual action) |
| 3 | Video is smooth; boxes don't stutter or lag the footage |
| 4 | Drawing a zone, then a person entering it, produces a real alert over WS **and** in `GET /api/alerts` after reload |
| 5 | Tripwire crossing produces a `ZONE` event with `transition: "crossed"` |
| 6 | Chatbot answers a working question with grounded facts, and **refuses** "who is this person?" |
| 7 | Zero fake data anywhere — grep the frontend for `Math.random`, `Math.sin`, `mock`, `simulate`, `demoScenario` |
| 8 | `./venv/Scripts/python -m pytest tests/ -q` still green |
| 9 | Backend restart → UI recovers without a hard refresh (WS reconnects, streams resume) |

---

## 11. Gotchas

- **Backend restart wipes zones.** In-memory only (§5). Re-fetch, don't cache.
- **`event_type` is UPPERCASE.** The surviving TS type says lowercase. Silent failure. (§6)
- **Zone coords are source-frame pixels.** Not normalised, not CSS. (§4)
- **12 MJPEG clients max.** Hidden-but-mounted `<img>` still counts.
- **`speed` is px/frame**, not m/s. Label it honestly.
- **Track IDs are camera-local.** Never claim identity across cameras.
- **`unsupported_capability` is success**, not an error. Render the refusal.
- **`/api/cameras/{id}/heatmap` returns 200 for unknown cameras** — check content,
  not just status.
- **`format=` other than json/csv → 422**, not 400.
- **RTSP passwords are never returned.** Don't display or cache them.
- **`/api/system/demo-reset` is destructive.** Confirm first.
- **CORS is an explicit allow-list**: `localhost:5173`, `127.0.0.1:5173`,
  `localhost:4173`, `127.0.0.1:4173`. A different dev port fails CORS — add it to
  `CORS_ORIGINS` in `backend/config.py`.
- **`DEMO_MODE=True`** means no auth needed. Don't build a mandatory login wall;
  `GET /api/auth/demo-token` exists if you want the flow.
- **Timestamps are UTC ISO 8601.** Convert for display; send UTC back.
- **The old `.md` docs overclaimed heavily** and most are now deleted. Trust the
  running app and `/openapi.json` over any document, including this one.
