/**
 * Border Intelligence — Unified TypeScript Definitions
 * Aligned with FastAPI OpenAPI Schema (SIH PS SIH26187)
 */

export type BackendEventType =
  | "DETECTION"
  | "TRACKING"
  | "ZONE"
  | "RISK"
  | "EVIDENCE"
  | "ALERT"
  | "INCIDENT"
  | "HANDOFF"
  | "SYSTEM";

export interface CameraRecord {
  camera_id: string;
  name: string;
  source_type: "video_file" | "rtsp" | "webcam" | string;
  source_path?: string;
  source_url?: string;
  device_index?: number;
  location_label?: string;
  is_running: boolean;
  status?: string;
  fps?: number;
  native_fps?: number;
  resolution?: string;
  frames_processed?: number;
  dropped_frames?: number;
  active_tracks?: number;
  uptime_seconds?: number;
  modality?: "RGB" | "IR" | "Thermal" | string;
  camera_type?: "RGB" | "IR" | "Thermal" | string;
}

export interface CameraListResponse {
  count: number;
  cameras: CameraRecord[];
}

export interface SecurityZone {
  zone_id: string;
  name: string;
  polygon: [number, number][];
  severity: "critical" | "restricted" | "warning" | "monitored" | string;
  is_active?: boolean;
  loitering_threshold_seconds?: number;
  loitering_debounce_seconds?: number;
  camera_id?: string;
}

export interface VirtualBoundary {
  boundary_id: string;
  name: string;
  pt1: [number, number];
  pt2: [number, number];
  severity: "critical" | "restricted" | "warning" | "monitored" | string;
  direction?: "NORTH" | "SOUTH" | "EAST" | "WEST" | "BIDIRECTIONAL" | string;
  is_active?: boolean;
  camera_id?: string;
}

export interface ZonesListResponse {
  zones: SecurityZone[];
  boundaries: VirtualBoundary[];
}

export interface AlertItem {
  seq_id?: number;
  event_id: string;
  alert_id?: string;
  id?: string;
  timestamp: string | number;
  camera_id: string;
  cameraId?: string;
  track_id?: string | number | null;
  targetTrackId?: string | number | null;
  targetLabel?: string;
  targetType?: string;
  incident_id?: string | null;
  severity: "CRITICAL" | "RESTRICTED" | "WARNING" | "LOW" | "HIGH" | "INFO" | "critical" | "warning" | string;
  message: string;
  reason?: string;
  summary?: string;
  status?: string;
  confidence?: number | null;
  speed?: number | null;
  speed_description?: string | null;
  speedDescription?: string | null;
  heading?: string | null;
  source?: string;
  payload?: string;
  threat_score?: number | null;
  threatScore?: number | null;
  threat_level?: string | null;
  threatLevel?: string | null;
  threat_reasons?: string[] | null;
  threatReasons?: string[] | null;
  causal_chain?: string[] | null;
  causalChain?: string[] | null;
  evidence_snapshot_uri?: string | null;
  evidenceSnapshotUri?: string | null;
  target_crop_uri?: string | null;
  targetCropUri?: string | null;
  face_snapshot_uri?: string | null;
  faceSnapshotUri?: string | null;
  anpr_snapshot_uri?: string | null;
  anprSnapshotUri?: string | null;
  best_frame_number?: number | null;
  bestFrameNumber?: number | null;
  modality?: "STANDARD" | "IR_NIGHT" | "THERMAL" | string;
  timeline_offset_sec?: number | null;
  timelineOffsetSec?: number | null;
  description?: string | null;
  alert_description?: string | null;
  rule_type?: string | null;
  dwell_seconds?: number | null;
  narrative?: string | null;
  is_acknowledged?: boolean;
  acknowledged_at?: string | null;
  replay_url?: string | null;
  replayUrl?: string | null;
  replay_available?: boolean;
  replayAvailable?: boolean;
}

export type SimulatedAlert = AlertItem;

export interface AlertsResponse {
  count: number;
  alerts: AlertItem[];
}

export interface AvailableSource {
  name: string;
  path: string;
  size_mb: number;
}

export interface AvailableSourcesResponse {
  bundled_clips: AvailableSource[];
  uploaded_clips: AvailableSource[];
  total_count: number;
}

export interface GroundedIntelligenceResponse {
  query: string;
  status: "answered" | "no_records_found" | "unsupported_capability" | "invalid_query" | "error" | string;
  grounding_status: "grounded" | "no_data" | "refusal" | string;
  observed_facts: string[];
  rule_results: string[];
  interpretation: string;
  evidence: Record<string, any>[];
}

export interface AuditLogEntry {
  seq_id: number;
  event_id: string;
  event_type: string;
  timestamp: string;
  camera_id: string;
  track_id?: string;
  incident_id?: string;
  confidence?: number;
  source?: string;
}

export interface CameraDiagnostics {
  camera_id: string;
  fps: number;
  status: string;
  frame_width: number;
  frame_height: number;
  frames_processed?: number;
  dropped_frames?: number;
}

export interface CoverageReport {
  total_cameras: number;
  coverage_percentage: number;
}

export interface DatabaseDiagnostics {
  total_events: number;
  size_bytes: number;
  wal_mode: boolean;
}

export interface ForensicVerificationResult {
  valid: boolean;
  tamper_detected: boolean;
  sha256_hash: string;
}

export interface HeatmapResponse {
  camera_id: string;
  density_matrix?: number[][];
  points?: [number, number, number][];
}

export interface IncidentCard {
  incident_id: string;
  camera_id: string;
  rule_type: string;
  zone_id?: string | null;
  zone_name?: string | null;
  primary_track_id: string;
  object_class: string;
  severity: string;
  status: "ACTIVE" | "ACKNOWLEDGED" | "RESOLVED" | string;
  first_seen: string;
  last_updated: string;
  dwell_seconds: number;
  threat_score: number;
  threat_level: string;
  threat_reasons?: string[];
  causal_chain?: string[];
  evidence_count: number;
  associated_track_ids?: string[];
  alert_id: string;
  description?: string | null;
  alert_description?: string | null;
  evidence_snapshot_uri?: string | null;
  target_crop_uri?: string | null;
  face_snapshot_uri?: string | null;
  anpr_snapshot_uri?: string | null;
  best_frame_number?: number | null;
  timeline_offset_sec?: number | null;
  replay_url?: string | null;
  replay_available?: boolean;
}

export type IncidentSummary = IncidentCard;

export interface IncidentItem {
  incident_id: string;
  camera_id: string;
  start_time: string;
  end_time?: string;
  severity: string;
  summary: string;
  event_count?: number;
  status?: "open" | "investigating" | "closed" | string;
}

export interface IncidentDossier {
  incident_id: string;
  camera_id: string;
  start_time: string;
  end_time?: string;
  severity: string;
  summary: string;
  events: AlertItem[];
}

export interface IncidentTimelineEvent {
  seq_id?: number;
  event_id: string;
  event_type: string;
  event_type_display?: string;
  description?: string;
  timestamp: string;
  camera_id: string;
  track_id?: string | null;
  incident_id?: string | null;
  confidence?: number | null;
  evidence_snapshot_uri?: string | null;
  target_crop_uri?: string | null;
}

export interface IncidentTimelineResponse {
  incident_id: string;
  count: number;
  timeline: IncidentTimelineEvent[];
}

export interface IntegrityAuditReport {
  is_valid: boolean;
  total_checked: number;
  hash_chain_status: string;
}

export interface MultiModalSensorsStatus {
  radar_online: boolean;
  thermal_online: boolean;
  seismic_online: boolean;
}

export interface OperationalProfile {
  profile_id?: string;
  name?: string;
  mode: string;
  threat_level: string;
}

export interface OperatorAnnotation {
  annotation_id: string;
  incident_id: string;
  note: string;
  operator_callsign: string;
  disposition?: string;
  timestamp: string;
}

export interface SnapshotMetadata {
  snapshot_id: string;
  camera_id: string;
  timestamp: string;
  url: string;
}

export interface SystemMetrics {
  device?: string;
  gpu_available?: boolean;
  gpu_device_name?: string;
  memory_usage_mb?: number;
  capture_fps?: number;
  ai_processing_fps?: number;
  display_fps?: number;
  effective_visual_fps?: number;
  inference_latency_ms?: number;
  tracking_latency_ms?: number;
  prediction_latency_ms?: number;
  persistence_latency_ms?: number;
  encoding_latency_ms?: number;
  total_pipeline_latency_ms?: number;
  frame_stride?: number;
  processed_frames?: number;
  skipped_frames?: number;
  predicted_frames?: number;
  dropped_frames?: number;
  active_tracks?: number;
  alerts?: number;
  workers_running?: number;
  [key: string]: any;
}

export interface ThreatAssessment {
  score: number;
  level: "low" | "medium" | "high" | "critical";
  summary: string;
}

export interface ZoneTemplate {
  template_id: string;
  name: string;
  type: string;
}

/** Local UI Drawing Point */
export interface DrawingPoint {
  x: number;
  y: number;
}

/** Local UI Boundary Shape */
export interface BoundaryShape {
  id: string;
  name: string;
  type: "zone" | "tripwire";
  vertices: DrawingPoint[];
  direction?: string;
}

export interface IncidentReplayData {
  incident_id: string;
  camera_id: string;
  media_type: "video" | "image" | "none";
  media_url?: string | null;
  mime_type?: string | null;
  timeline_offset_sec?: number | null;
  best_frame_number?: number | null;
  severity: "CRITICAL" | "RESTRICTED" | "NORMAL";
  rule_type: string;
  timestamp: string;
  threat_score: number;
  evidence_snapshot_uri?: string | null;
  target_crop_uri?: string | null;
  face_snapshot_uri?: string | null;
  anpr_snapshot_uri?: string | null;
  file_exists: boolean;
  replay_available: boolean;
  message?: string | null;
}
