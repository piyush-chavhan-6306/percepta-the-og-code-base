/**
 * Border Intelligence — Full REST API Client
 * Connects to FastAPI backend at http://127.0.0.1:8000
 */

import type {
  AlertsResponse,
  AuditLogEntry,
  CameraDiagnostics,
  CameraListResponse,
  CameraRecord,
  CoverageReport,
  DatabaseDiagnostics,
  ForensicVerificationResult,
  GroundedIntelligenceResponse,
  HeatmapResponse,
  IncidentDossier,
  IncidentReplayData,
  IncidentSummary,
  IncidentTimelineResponse,
  IntegrityAuditReport,
  MultiModalSensorsStatus,
  OperationalProfile,
  OperatorAnnotation,
  SnapshotMetadata,
  SystemMetrics,
  ThreatAssessment,
  ZoneTemplate,
  ZonesListResponse,
} from "../types/surveillance";

export const API_BASE_URL = import.meta.env.VITE_API_URL || "";
export const WS_BASE_URL =
  import.meta.env.VITE_WS_URL ||
  (typeof window !== "undefined"
    ? `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/events`
    : "ws://127.0.0.1:8000/ws/events");

class ApiClient {
  public baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    let userId = "usr_operator";
    if (typeof window !== "undefined") {
      try {
        const raw = localStorage.getItem("percepta_c2_session");
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed?.user?.id) userId = parsed.user.id;
        }
      } catch (_) {}
    }
    const headers = {
      "Content-Type": "application/json",
      "X-User-Id": userId,
      ...(options.headers || {}),
    };

    try {
      const response = await fetch(url, { ...options, headers });
      if (!response.ok) {
        let errorDetail = `HTTP ${response.status} ${response.statusText}`;
        try {
          const body = await response.json();
          if (body.detail) {
            errorDetail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          }
        } catch {
          // ignore json parse error
        }
        throw new Error(errorDetail);
      }
      return (await response.json()) as T;
    } catch (err: any) {
      console.error(`API Error on [${options.method || "GET"}] ${endpoint}:`, err.message);
      throw err;
    }
  }

  // === System & Health ===
  getHealth() {
    return this.request<{ status: string; service: string; database: string }>("/api/health");
  }

  getReadiness() {
    return this.request<{ status: string; checks: Record<string, boolean> }>("/api/readiness");
  }

  getSystemStatus() {
    return this.request<any>("/api/system/status");
  }

  getSystemMetrics() {
    return this.request<SystemMetrics>("/api/system/metrics");
  }

  getCoverageReport() {
    return this.request<CoverageReport>("/api/system/coverage-report");
  }

  getProfiles() {
    return this.request<{ active_profile: OperationalProfile; available_profiles: OperationalProfile[] }>("/api/system/profiles");
  }

  applyProfile(profile_id: string) {
    return this.request<{ status: string; active_profile: OperationalProfile }>("/api/system/profiles/apply", {
      method: "POST",
      body: JSON.stringify({ profile_id }),
    });
  }

  getAuditLogs(limit: number = 100) {
    return this.request<{ count: number; audit_logs: AuditLogEntry[] }>(`/api/system/audit-logs?limit=${limit}`);
  }

  getDbDiagnostics() {
    return this.request<DatabaseDiagnostics>("/api/system/db-diagnostics");
  }

  resetDemo() {
    return this.request<{ status: string; message: string }>("/api/system/demo-reset", {
      method: "POST",
    });
  }

  // === Cameras ===
  getCameras() {
    return this.request<CameraListResponse>("/api/cameras");
  }

  getCamera(cameraId: string) {
    return this.request<CameraRecord>(`/api/cameras/${cameraId}`);
  }

  registerCamera(data: {
    camera_id: string;
    name?: string;
    source_type: string;
    source_url?: string;
    source_path?: string;
    location_label?: string;
    fps?: number;
    loop?: boolean;
    device_index?: number;
    autostart?: boolean;
  }) {
    return this.request<CameraRecord>("/api/cameras/register", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  uploadCameraVideo(file: File, name?: string, location?: string, modality?: string) {
    const formData = new FormData();
    formData.append("file", file);
    if (name) formData.append("name", name);
    if (location) formData.append("location_label", location);
    if (modality) formData.append("modality", modality);
    const url = `${this.baseUrl}/api/cameras/upload`;
    return fetch(url, {
      method: "POST",
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        let err = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          if (body.detail) err = body.detail;
        } catch {}
        throw new Error(err);
      }
      return res.json() as Promise<CameraRecord>;
    });
  }

  getAvailableSources() {
    return this.request<{
      bundled_clips: Array<{ name: string; path: string; size_mb: number }>;
      uploaded_clips: Array<{ name: string; path: string; size_mb: number }>;
      total_count: number;
    }>("/api/cameras/sources/available");
  }

  startCamera(cameraId: string) {
    return this.request<{ camera_id: string; status: string }>(`/api/cameras/${cameraId}/start`, { method: "POST" });
  }

  stopCamera(cameraId: string) {
    return this.request<{ camera_id: string; status: string }>(`/api/cameras/${cameraId}/stop`, { method: "POST" });
  }

  deleteCamera(cameraId: string) {
    return this.request<{ camera_id: string; status: string; deregistered?: boolean }>(`/api/cameras/${cameraId}`, { method: "DELETE" });
  }

  getCameraDiagnostics(cameraId: string) {
    return this.request<CameraDiagnostics>(`/api/cameras/${cameraId}/diagnostics`);
  }

  getCameraTrust(cameraId: string) {
    return this.request<{
      camera_id: string;
      trust_score: number;
      trust_level: string;
      is_trusted: boolean;
      summary: string;
      factors: Array<{ factor: string; score: number; metric: string; status: string }>;
      timestamp: string;
    }>(`/api/cameras/${cameraId}/trust`);
  }

  getCameraHeatmap(cameraId: string) {
    return this.request<HeatmapResponse>(`/api/cameras/${cameraId}/heatmap`);
  }

  // === Alerts & Incidents ===
  getAlerts(params?: { camera_id?: string; severity?: string; limit?: number }) {
    const q = new URLSearchParams();
    if (params?.camera_id) q.set("camera_id", params.camera_id);
    if (params?.severity) q.set("severity", params.severity);
    if (params?.limit) q.set("limit", params.limit.toString());
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return this.request<AlertsResponse>(`/api/alerts${queryStr}`);
  }

  acknowledgeAlert(alertId: string) {
    return this.request<{ event_id: string; status: string }>(`/api/alerts/${alertId}/acknowledge`, {
      method: "POST",
    });
  }

  getIncidents(params?: { camera_id?: string; limit?: number; status?: string; severity?: string; raw?: boolean }) {
    const q = new URLSearchParams();
    if (params?.camera_id) q.set("camera_id", params.camera_id);
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.status) q.set("status", params.status);
    if (params?.severity) q.set("severity", params.severity);
    if (params?.raw) q.set("raw", "true");
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return this.request<{ count: number; capacity?: number; incidents: IncidentSummary[] }>(`/api/incidents${queryStr}`);
  }

  getRawIncidents(params?: { limit?: number; severity?: string }) {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", params.limit.toString());
    if (params?.severity) q.set("severity", params.severity);
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return this.request<{ count: number; capacity?: number; incidents: IncidentSummary[] }>(`/api/incidents/raw${queryStr}`);
  }

  getIncidentsActive(params?: { camera_id?: string }) {
    const q = new URLSearchParams();
    if (params?.camera_id) q.set("camera_id", params.camera_id);
    const queryStr = q.toString() ? `?${q.toString()}` : "";
    return this.request<{ count: number; capacity?: number; incidents: IncidentSummary[] }>(`/api/incidents/active${queryStr}`);
  }

  getIncidentTimeline(incidentId: string) {
    return this.request<IncidentTimelineResponse>(`/api/incidents/${incidentId}`);
  }

  getIncidentReplay(incidentId: string) {
    return this.request<IncidentReplayData>(`/api/incidents/${incidentId}/replay`);
  }

  getIncidentDossier(incidentId: string) {
    return this.request<IncidentDossier>(`/api/incidents/${incidentId}/dossier`);
  }

  acknowledgeIncident(incidentId: string) {
    return this.request<{ incident_id: string; status: string }>(`/api/incidents/${incidentId}/acknowledge`, {
      method: "POST",
    });
  }

  getIncidentNotes(incidentId: string) {
    return this.request<{ incident_id: string; count: number; annotations: OperatorAnnotation[] }>(
      `/api/incidents/${incidentId}/notes`
    );
  }

  addIncidentNote(incidentId: string, data: { operator_callsign: string; note: string; disposition: string }) {
    return this.request<OperatorAnnotation>(`/api/incidents/${incidentId}/notes`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // === Zones & Boundaries ===
  getZones() {
    return this.request<ZonesListResponse>("/api/zones");
  }

  createCamera(data: {
    camera_id?: string;
    name?: string;
    source_type: string;
    source_url?: string;
    source_path?: string;
    location_label?: string;
    fps?: number;
    loop?: boolean;
    device_index?: number;
    autostart?: boolean;
    modality?: string;
  }) {
    const payload = {
      ...data,
      camera_id: data.camera_id || `CAM-${Date.now().toString().slice(-4)}`,
    };
    return this.registerCamera(payload as any);
  }



  createZone(data: {
    zone_id?: string;
    name: string;
    polygon: [number, number][] | number[][];
    severity: string;
    loitering_threshold_seconds?: number;
    camera_id?: string;
  }) {
    const payload = {
      ...data,
      zone_id: data.zone_id || `zone_${Date.now().toString().slice(-6)}`,
    };
    return this.request<any>("/api/zones", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  createBoundary(data: {
    boundary_id?: string;
    name: string;
    pt1: [number, number];
    pt2: [number, number];
    severity: string;
    direction?: string;
    debounce_seconds?: number;
    camera_id?: string;
  }) {
    const payload = {
      ...data,
      boundary_id: data.boundary_id || `trip_${Date.now().toString().slice(-6)}`,
      direction: data.direction || "BIDIRECTIONAL",
    };
    return this.request<any>("/api/zones/boundary", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  deleteZone(zoneId: string) {
    return this.request<{ zone_id: string; status: string }>(`/api/zones/${zoneId}`, { method: "DELETE" });
  }

  getZoneTemplates() {
    return this.request<{ templates: ZoneTemplate[] }>("/api/zones/templates");
  }

  applyZoneTemplate(template_id: string, zone_id_suffix: string = "01", custom_name?: string) {
    return this.request<any>("/api/zones/apply-template", {
      method: "POST",
      body: JSON.stringify({ template_id, zone_id_suffix, custom_name }),
    });
  }

  // === Threat & Forensics ===
  getThreatLevel(cameraId?: string) {
    const q = cameraId ? `?camera_id=${cameraId}` : "";
    return this.request<ThreatAssessment>(`/api/threat/level${q}`);
  }

  verifyEvent(eventId: string) {
    return this.request<ForensicVerificationResult>(`/api/evidence/verify/${eventId}`);
  }

  auditIntegrity(limit: number = 200) {
    return this.request<IntegrityAuditReport>(`/api/evidence/audit-integrity?limit=${limit}`);
  }

  getSnapshots(incidentId: string) {
    return this.request<{ incident_id: string; count: number; snapshots: SnapshotMetadata[] }>(
      `/api/evidence/snapshots/${incidentId}`
    );
  }

  getSnapshotFileUrl(filename: string) {
    return `${this.baseUrl}/api/evidence/snapshots/file/${filename}`;
  }

  exportAuditLog(format: "json" | "csv" = "json", cameraId?: string) {
    const q = new URLSearchParams({ format });
    if (cameraId) q.set("camera_id", cameraId);
    return this.request<any>(`/api/events/export?${q.toString()}`);
  }

  getExportUrl(format: "json" | "csv", cameraId?: string, eventType?: string) {
    const q = new URLSearchParams({ format });
    if (cameraId) q.set("camera_id", cameraId);
    if (eventType) q.set("event_type", eventType);
    return `${this.baseUrl}/api/events/export?${q.toString()}`;
  }

  // === Multi-Modal Sensors ===
  getSensorsStatus() {
    return this.request<MultiModalSensorsStatus>("/api/sensors/status");
  }

  ingestSensorEvent(data: {
    sensor_id: string;
    sensor_type: string;
    sector_id: string;
    confidence: number;
    data: Record<string, any>;
  }) {
    return this.request<any>("/api/sensors/ingest", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // === Grounded AI Assistant ===
  queryIntelligence(query: string, cameraId?: string) {
    return this.request<GroundedIntelligenceResponse>("/api/intelligence/query", {
      method: "POST",
      body: JSON.stringify({ query, camera_id: cameraId || null }),
    });
  }

  // === User Identity & Onboarding ===
  getUserProfile() {
    return this.request<{ success: boolean; profile: any; workspace_path: string }>("/api/user/profile");
  }

  updateUserProfile(data: Record<string, any>) {
    return this.request<{ success: boolean; profile: any; workspace_path: string }>("/api/user/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  completeOnboarding() {
    return this.request<{ success: boolean; onboarding_completed: boolean }>("/api/user/onboarding/complete", {
      method: "POST",
    });
  }

  resetOnboarding() {
    return this.request<{ success: boolean; onboarding_completed: boolean }>("/api/user/onboarding/reset", {
      method: "POST",
    });
  }

  syncSupabase(data: { supabase_id: string; email: string; name?: string; access_token?: string }) {
    return this.request<any>("/api/user/sync-supabase", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // === Stream URLs ===
  getVideoStreamUrl(cameraId: string) {
    return `${this.baseUrl}/api/stream/video/${cameraId}`;
  }

  getRawStreamUrl(cameraId: string) {
    return `${this.baseUrl}/api/stream/raw/${cameraId}`;
  }
}

export const api = new ApiClient();
