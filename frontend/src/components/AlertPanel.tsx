import { useEffect, useRef, useState } from "react";
import type { AlertItem, IncidentCard } from "@/types/surveillance";
import { api } from "@/api/client";
import { useWebSocket, WsMessage } from "@/hooks/useWebSocket";
import {
  AlertTriangle,
  ShieldAlert,
  Check,
  RefreshCw,
  ChevronRight,
  Clock,
  Compass,
  PlayCircle,
  Camera,
  Menu,
  X,
  Radio,
  Archive,
  FileSearch,
  FileQuestion,
  Shield,
  ShieldCheck,
  Flame,
  Activity,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ────────────────────────────────────────────── Types ──────────────────────────────────────────────
interface AlertPanelProps {
  selectedCameraId?: string;
  onSelectAlert?: (alert: AlertItem) => void;
  selectedAlertId?: string;
  onSeekTime?: (timestamp: string | number, cameraId?: string) => void;
}

type PanelView = "ACTIVE" | "ALL" | "RAW" | "RESOLVED" | "ALERTS" | "EVIDENCE";

// ────────────────────────────────────────────── Helpers ──────────────────────────────────────────────
function formatTime(ts: string | number): string {
  try {
    const d = typeof ts === "number" ? new Date(ts) : new Date(ts);
    if (isNaN(d.getTime())) return String(ts);
    return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch { return String(ts); }
}

function formatDwell(secs: number): string {
  if (secs < 60) return `${Math.round(secs)}s`;
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}m ${s}s`;
}

function severityColors(sev: string) {
  const s = sev?.toUpperCase() ?? "NORMAL";
  if (s === "CRITICAL")   return { badge: "bg-red-500/20 text-red-400 border-red-500/40", bar: "bg-red-500", Icon: Flame, label: "CRITICAL" };
  if (s === "RESTRICTED") return { badge: "bg-amber-500/20 text-amber-400 border-amber-500/40", bar: "bg-amber-500", Icon: Shield, label: "RESTRICTED" };
  return { badge: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40", bar: "bg-emerald-500", Icon: ShieldCheck, label: "NORMAL" };
}

function statusDot(status: string) {
  const s = (status ?? "").toUpperCase();
  if (s === "ACTIVE")       return "bg-red-500 animate-pulse";
  if (s === "ACKNOWLEDGED") return "bg-amber-400";
  if (s === "RESOLVED")     return "bg-emerald-500";
  return "bg-slate-500";
}

function ruleLabel(rule: string): string {
  if (rule === "boundary_crossed" || rule?.includes("tripwire")) return "TRIPWIRE";
  if (rule === "loitering" || rule?.includes("dwell"))        return "LOITERING";
  return "INTRUSION";
}

// Convert an IncidentCard into a rich AlertItem for AlertInspector
function incidentToAlertItem(inc: IncidentCard): AlertItem {
  return {
    event_id: inc.alert_id,
    alert_id: inc.alert_id,
    timestamp: inc.last_updated,
    camera_id: inc.camera_id,
    track_id: inc.primary_track_id,
    incident_id: inc.incident_id,
    severity: inc.severity,
    message: inc.description || `${ruleLabel(inc.rule_type)}: ${inc.object_class.toUpperCase()} #${inc.primary_track_id}${inc.zone_name ? ` — ${inc.zone_name}` : ""}`,
    threat_score: inc.threat_score,
    threat_level: inc.threat_level,
    threat_reasons: inc.threat_reasons,
    causal_chain: inc.causal_chain,
    is_acknowledged: inc.status === "ACKNOWLEDGED" || inc.status === "RESOLVED",
    evidence_snapshot_uri: inc.evidence_snapshot_uri,
    target_crop_uri: inc.target_crop_uri,
    face_snapshot_uri: inc.face_snapshot_uri,
    anpr_snapshot_uri: inc.anpr_snapshot_uri,
    best_frame_number: inc.best_frame_number,
    timeline_offset_sec: inc.timeline_offset_sec,
    description: inc.description,
    alert_description: inc.alert_description,
    rule_type: inc.rule_type,
    dwell_seconds: inc.dwell_seconds,
    replay_url: inc.replay_url,
    replayUrl: inc.replay_url,
    replay_available: inc.replay_available,
    replayAvailable: inc.replay_available,
  };
}

// ────────────────────────────────────────────── Component ──────────────────────────────────────────────
export function AlertPanel({ selectedCameraId, onSelectAlert, selectedAlertId, onSeekTime }: AlertPanelProps) {
  const [incidents, setIncidents] = useState<IncidentCard[]>([]);
  const [incidentCapacity, setIncidentCapacity] = useState<number>(40);
  const [rawAlerts, setRawAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<PanelView>("ACTIVE");
  const [filterSeverity, setFilterSeverity] = useState<string>("ALL");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [sevDropdownOpen, setSevDropdownOpen] = useState(false);
  const sevDropdownRef = useRef<HTMLDivElement>(null);

  // Close menus on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
      if (sevDropdownRef.current && !sevDropdownRef.current.contains(e.target as Node)) setSevDropdownOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      if (view === "ALERTS") {
        const res = await api.getAlerts({ camera_id: selectedCameraId, limit: 100 });
        setRawAlerts(res.alerts || []);
      } else if (view === "ACTIVE") {
        const res = await api.getIncidents({ camera_id: selectedCameraId, status: "ACTIVE", limit: 100 });
        setIncidents(res.incidents || []);
        if (res.capacity) setIncidentCapacity(res.capacity);
      } else if (view === "RESOLVED") {
        const res = await api.getIncidents({ camera_id: selectedCameraId, status: "RESOLVED", limit: 100 });
        setIncidents(res.incidents || []);
        if (res.capacity) setIncidentCapacity(res.capacity);
      } else if (view === "RAW") {
        // Cross-camera audit historical view (including deleted cameras)
        const res = await api.getRawIncidents({ limit: 100 });
        setIncidents(res.incidents || []);
        if (res.capacity) setIncidentCapacity(res.capacity);
      } else {
        // ALL incidents for current camera
        const res = await api.getIncidents({ camera_id: selectedCameraId, status: "ALL", limit: 100 });
        setIncidents(res.incidents || []);
        if (res.capacity) setIncidentCapacity(res.capacity);
      }
    } catch (err) {
      console.error("Failed to load incident data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [view, selectedCameraId]);

  // Live WebSocket — INCIDENT, ALERT & ACKNOWLEDGEMENT events update the feed
  useWebSocket((msg: WsMessage) => {
    const et = (msg.event_type || (msg as any).type) as string;
    if (
      et === "INCIDENT" ||
      et === "INCIDENT_ACKNOWLEDGED" ||
      et === "ALERT_ACKNOWLEDGED" ||
      et === "ALERT" ||
      et === "alert"
    ) {
      fetchData();
    }

    if (et === "ALERT" || et === "alert") {
      if (selectedCameraId && msg.camera_id && msg.camera_id !== selectedCameraId) {
        return;
      }
      const sUpper = (msg.severity || "NORMAL").toUpperCase();
      const normSev = sUpper === "CRITICAL" ? "CRITICAL" : sUpper === "RESTRICTED" ? "RESTRICTED" : "NORMAL";
      const rawScore = (msg as any).threat_score;
      const normScore = rawScore != null ? Math.min(100, Math.max(0, Math.round(Number(rawScore)))) : null;

      const newAlert: AlertItem = {
        event_id: msg.event_id || `alert-${Date.now()}`,
        alert_id: msg.alert_id || msg.event_id,
        timestamp: msg.timestamp || new Date().toISOString(),
        camera_id: msg.camera_id || selectedCameraId || "CAM-01",
        track_id: msg.track_id,
        incident_id: msg.incident_id,
        severity: normSev,
        message: msg.message || "Security violation detected",
        confidence: msg.confidence,
        is_acknowledged: false,
        threat_score: normScore,
        threat_level: (msg as any).threat_level,
        threat_reasons: (msg as any).threat_reasons,
        causal_chain: (msg as any).causal_chain,
        evidence_snapshot_uri: (msg as any).evidence_snapshot_uri,
        face_snapshot_uri: (msg as any).face_snapshot_uri,
        anpr_snapshot_uri: (msg as any).anpr_snapshot_uri,
      };
      setRawAlerts(prev => {
        if (prev.some(a => a.event_id === newAlert.event_id)) return prev;
        return [newAlert, ...prev].slice(0, 100);
      });
    }
  });

  const handleAcknowledgeIncident = async (e: React.MouseEvent, incidentId: string) => {
    e.stopPropagation();
    try {
      await fetch(`/api/incidents/${incidentId}/acknowledge`, { method: "POST" });
      setIncidents(prev => prev.map(i => i.incident_id === incidentId ? { ...i, status: "ACKNOWLEDGED" } : i));
    } catch (err) { console.error("Acknowledge failed:", err); }
  };

  const handleAcknowledgeAlert = async (e: React.MouseEvent, alertId: string) => {
    e.stopPropagation();
    try {
      await api.acknowledgeAlert(alertId);
      setRawAlerts(prev => prev.map(a => (a.event_id === alertId || a.alert_id === alertId) ? { ...a, is_acknowledged: true } : a));
    } catch (err) { console.error("Acknowledge failed:", err); }
  };

  // Filtering using centralized normalized severity
  const visibleIncidents = incidents.filter(inc => {
    if (view !== "RAW" && selectedCameraId && inc.camera_id !== selectedCameraId) return false;
    const norm = (inc.severity || "NORMAL").toUpperCase();
    if (filterSeverity !== "ALL" && norm !== filterSeverity) return false;
    return true;
  });
  const visibleAlerts = rawAlerts.filter(a => {
    if (selectedCameraId && a.camera_id !== selectedCameraId) return false;
    const norm = (a.severity || "NORMAL").toUpperCase();
    if (filterSeverity !== "ALL" && norm !== filterSeverity) return false;
    return true;
  });

  const activeCount = incidents.filter(i => i.status === "ACTIVE" && (!selectedCameraId || i.camera_id === selectedCameraId)).length;
  const unackedAlerts = rawAlerts.filter(a => !a.is_acknowledged).length;

  const menuItems: { icon: React.ReactNode; label: string; view: PanelView }[] = [
    { icon: <Radio className="w-3.5 h-3.5" />, label: "Active Incidents", view: "ACTIVE" },
    { icon: <Archive className="w-3.5 h-3.5" />, label: "All Incidents", view: "ALL" },
    { icon: <Check className="w-3.5 h-3.5" />, label: "Resolved", view: "RESOLVED" },
    { icon: <FileSearch className="w-3.5 h-3.5" />, label: "Raw Incidents", view: "RAW" },
    { icon: <AlertTriangle className="w-3.5 h-3.5" />, label: "Raw Alerts", view: "ALERTS" },
  ];

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="shrink-0 p-3.5 border-b border-white/10 flex items-center justify-between bg-black/40">
        <div className="flex items-center gap-2">
          <div className="relative">
            <ShieldAlert className="w-4 h-4 text-red-400" />
            {activeCount > 0 && (
              <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-red-500 animate-ping" />
            )}
          </div>
          <h2 className="text-xs font-bold text-foreground font-mono uppercase tracking-wider">
            TACTICAL INCIDENT FEED
          </h2>
          {view === "ACTIVE" && (
            <span className="px-1.5 py-0.5 text-[10px] font-mono bg-red-500/20 text-red-400 border border-red-500/30 rounded-md font-bold">
              {activeCount} / {incidentCapacity} ACTIVE
            </span>
          )}
          {view === "ALERTS" && unackedAlerts > 0 && (
            <span className="px-1.5 py-0.5 text-[10px] font-mono bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-md">
              {unackedAlerts} UNACKED
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {/* Tactical C2 Severity Filter Dropdown */}
          <div className="relative" ref={sevDropdownRef}>
            <button
              type="button"
              onClick={() => setSevDropdownOpen(prev => !prev)}
              className={`h-7 px-2.5 rounded-md border text-[10px] font-mono flex items-center gap-1.5 transition-all cursor-pointer ${
                filterSeverity === "CRITICAL"
                  ? "bg-red-500/15 border-red-500/50 text-red-300 shadow-[0_0_8px_rgba(239,68,68,0.25)]"
                  : filterSeverity === "RESTRICTED"
                  ? "bg-amber-500/15 border-amber-500/50 text-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.25)]"
                  : filterSeverity === "NORMAL"
                  ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-[0_0_8px_rgba(16,185,129,0.25)]"
                  : "bg-black/60 border-white/10 text-gray-300 hover:border-[#00e5ff]/50"
              }`}
              aria-haspopup="listbox"
              aria-expanded={sevDropdownOpen}
              data-testid="severity-filter-dropdown-btn"
            >
              <span className={`w-1.5 h-1.5 rounded-full ${
                filterSeverity === "CRITICAL" ? "bg-red-500" :
                filterSeverity === "RESTRICTED" ? "bg-amber-400" :
                filterSeverity === "NORMAL" ? "bg-emerald-400" : "bg-[#00e5ff]"
              }`} />
              <span className="font-bold">{filterSeverity}</span>
              <ChevronDown className="w-3 h-3 opacity-60 ml-0.5" />
            </button>

            {sevDropdownOpen && (
              <div
                role="listbox"
                className="absolute right-0 top-8 z-50 w-44 bg-[#090d14]/95 border border-[#00e5ff]/30 rounded-lg shadow-2xl backdrop-blur-xl p-1 font-mono text-[11px] animate-in fade-in zoom-in-95 duration-100"
              >
                {[
                  { value: "ALL", label: "ALL INCIDENTS", dot: "bg-[#00e5ff]" },
                  { value: "CRITICAL", label: "CRITICAL", dot: "bg-red-500" },
                  { value: "RESTRICTED", label: "RESTRICTED", dot: "bg-amber-400" },
                  { value: "NORMAL", label: "NORMAL", dot: "bg-emerald-400" },
                ].map((item) => (
                  <button
                    key={item.value}
                    role="option"
                    aria-selected={filterSeverity === item.value}
                    onClick={() => {
                      setFilterSeverity(item.value);
                      setSevDropdownOpen(false);
                    }}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-left transition-colors cursor-pointer ${
                      filterSeverity === item.value
                        ? "bg-[#00e5ff]/20 text-[#00e5ff] font-bold"
                        : "text-gray-300 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${item.dot}`} />
                      {item.label}
                    </span>
                    {filterSeverity === item.value && <Check className="w-3.5 h-3.5 text-[#00e5ff]" />}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Refresh */}
          <Button variant="ghost" size="icon" onClick={fetchData}
            className="h-7 w-7 text-muted-foreground hover:text-foreground" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </Button>

          {/* Hamburger menu */}
          <div className="relative" ref={menuRef}>
            <Button variant="ghost" size="icon" onClick={() => setMenuOpen(v => !v)}
              className="h-7 w-7 text-muted-foreground hover:text-foreground" title="View options">
              {menuOpen ? <X className="w-3.5 h-3.5" /> : <Menu className="w-3.5 h-3.5" />}
            </Button>

            {menuOpen && (
              <div className="absolute right-0 top-9 z-50 w-52 bg-black/90 border border-white/15 rounded-lg shadow-2xl backdrop-blur-xl overflow-hidden">
                <div className="px-3 py-2 border-b border-white/10">
                  <p className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">INCIDENT VIEWS</p>
                </div>
                {menuItems.map(item => (
                  <button
                    key={item.view}
                    onClick={() => { setView(item.view); setMenuOpen(false); }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 text-xs font-mono transition-colors ${
                      view === item.view
                        ? "bg-primary/20 text-primary"
                        : "text-muted-foreground hover:bg-white/[0.06] hover:text-foreground"
                    }`}
                  >
                    {item.icon}
                    {item.label}
                    {item.view === "ACTIVE" && (
                      <span className="ml-auto text-[9px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded-full font-mono font-bold">
                        {activeCount} / {incidentCapacity}
                      </span>
                    )}
                  </button>
                ))}
                <div className="px-3 py-2 border-t border-white/10">
                  <p className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest mb-1.5">SEVERITY FILTER</p>
                  {["ALL", "CRITICAL", "RESTRICTED", "NORMAL"].map(sev => (
                    <button key={sev} onClick={() => { setFilterSeverity(sev); setMenuOpen(false); }}
                      className={`w-full text-left text-[10px] font-mono px-2 py-1 rounded transition-colors mb-0.5 ${
                        filterSeverity === sev ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground hover:bg-white/[0.04]"
                      }`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── View label ────────────────────────────────────────── */}
      <div className="shrink-0 px-3.5 py-1.5 border-b border-white/5 bg-black/20 flex items-center gap-2">
        <Activity className="w-3 h-3 text-muted-foreground" />
        <span className="text-[9px] font-mono text-muted-foreground uppercase tracking-widest">
          {view === "ACTIVE"   && (selectedCameraId ? `Active Incidents [${selectedCameraId}]` : "Active Incidents")}
          {view === "ALL"      && (selectedCameraId ? `All Camera Incidents [${selectedCameraId}]` : "All Camera Incidents")}
          {view === "RAW"      && "Raw Incident Audit Layer (System Historical)"}
          {view === "ALERTS"   && (selectedCameraId ? `Alert Stream [${selectedCameraId}]` : "Alert Stream")}
          {view === "RESOLVED" && (selectedCameraId ? `Resolved Incidents [${selectedCameraId}]` : "Resolved Incidents")}
          {view === "EVIDENCE" && (selectedCameraId ? `Evidence Records [${selectedCameraId}]` : "Evidence Records")}
        </span>
      </div>

      {/* â”€â”€ List â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div className="flex-1 min-h-0 overflow-y-auto divide-y divide-white/5 scrollbar-thin scrollbar-thumb-white/15 hover:scrollbar-thumb-white/25 overscroll-contain">

        {/* â”€â”€ INCIDENT CARDS (all non-ALERTS views) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        {view !== "ALERTS" && (
          visibleIncidents.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-center p-4">
              <Shield className="w-8 h-8 text-muted-foreground/40 mb-2" />
              <p className="text-xs text-muted-foreground font-mono">
                {loading ? "LOADING..." : "NO INCIDENTS IN THIS VIEW"}
              </p>
              <p className="text-[10px] text-muted-foreground/60 mt-1">Perimeter status nominal</p>
            </div>
          ) : (
            visibleIncidents.map((inc) => {
              const colors = severityColors(inc.severity);
              const isSelected = selectedAlertId === inc.alert_id || selectedAlertId === inc.incident_id;
              const alertItem = incidentToAlertItem(inc);

              return (
                <div
                  key={inc.incident_id}
                  onClick={() => onSelectAlert?.(alertItem)}
                  className={`p-3 transition-all cursor-pointer relative group border-l-2 ${
                    isSelected
                      ? "bg-primary/10 border-l-primary"
                      : inc.status === "ACTIVE"
                      ? "border-l-red-500/60 hover:bg-white/[0.04]"
                      : inc.status === "ACKNOWLEDGED"
                      ? "border-l-amber-500/40 hover:bg-white/[0.03]"
                      : "border-l-transparent opacity-70 hover:opacity-100 hover:bg-white/[0.02]"
                  }`}
                >
                  {/* Row 1: status + severity + rule + camera */}
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {/* Status dot */}
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusDot(inc.status)}`} />

                      {/* Severity badge */}
                      <span className={`text-[9px] font-mono px-1.5 py-0.5 uppercase rounded-full border font-bold flex items-center gap-1 ${colors.badge}`}>
                        <colors.Icon className="w-2.5 h-2.5" />
                        {colors.label}
                      </span>

                      {/* Rule type */}
                      <span className="text-[9px] font-mono px-1.5 py-0.5 bg-white/5 text-slate-400 border border-white/10 rounded-full">
                        {ruleLabel(inc.rule_type)}
                      </span>

                      {/* Camera */}
                      <span className="text-[10px] font-mono text-cyan-400 flex items-center gap-0.5">
                        <Camera className="w-2.5 h-2.5" />
                        {inc.camera_id}
                      </span>
                    </div>

                    {/* Timestamp */}
                    <button
                      onClick={(e) => { e.stopPropagation(); onSeekTime?.(inc.last_updated, inc.camera_id); onSelectAlert?.(alertItem); }}
                      className="flex items-center gap-1 text-[10px] font-mono text-cyan-300 hover:text-cyan-100 bg-cyan-950/50 hover:bg-cyan-900/70 border border-cyan-800/50 px-1.5 py-0.5 rounded transition-colors"
                      title="Seek to event time"
                    >
                      <PlayCircle className="w-3 h-3" />
                      {formatTime(inc.last_updated)}
                    </button>
                  </div>

                  {/* Row 2: Human-readable Incident description */}
                  <p className="text-xs text-foreground font-semibold leading-tight mb-1">
                    {inc.description || `${inc.object_class.toUpperCase()} #${inc.primary_track_id}${inc.zone_name ? ` — ${inc.zone_name}` : ""}`}
                  </p>

                  {/* Target metadata */}
                  <div className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground mb-2">
                    <span className="text-slate-300 font-medium">
                      Target #{inc.primary_track_id || "1"} ({inc.object_class || "person"})
                    </span>
                    {inc.zone_name && <span className="text-slate-400">• {inc.zone_name}</span>}
                    {inc.associated_track_ids && inc.associated_track_ids.length > 1 && (
                      <span className="ml-1 text-[9px] text-slate-500">(+{inc.associated_track_ids.length - 1} tracks)</span>
                    )}
                  </div>

                  {/* Evidence Display & Thumbnail */}
                  <div className="mb-2">
                    {inc.target_crop_uri || inc.evidence_snapshot_uri ? (
                      <div className="flex items-center gap-2 p-1.5 rounded-lg bg-black/40 border border-white/10 group-hover:border-primary/30 transition-colors">
                        <img
                          src={inc.target_crop_uri || inc.evidence_snapshot_uri || ""}
                          alt="Incident Evidence"
                          className="w-12 h-10 object-cover rounded bg-black/60 border border-white/10 flex-shrink-0"
                          onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1 text-[9px] font-mono text-cyan-300 uppercase font-semibold">
                            <Camera className="w-2.5 h-2.5" />
                            <span>{inc.target_crop_uri ? "TARGET CROP" : "EVIDENCE FRAME"}</span>
                          </div>
                          <p className="text-[8px] font-mono text-muted-foreground truncate">
                            {formatTime(inc.last_updated)} • {inc.camera_id}
                          </p>
                        </div>
                        <span className="text-[8px] font-mono text-primary border border-primary/30 px-1 py-0.5 rounded bg-primary/10">
                          VIEW
                        </span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-black/20 border border-white/5 text-[9px] font-mono text-muted-foreground/60">
                        <FileQuestion className="w-3 h-3 text-slate-500" />
                        <span>No evidence captured</span>
                      </div>
                    )}
                  </div>

                  {/* Row 3: Metrics bar */}
                  <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground mb-1.5">
                    {/* Threat score */}
                    {(() => {
                      const clampedScore = Math.min(100, Math.max(0, Math.round(inc.threat_score ?? 0)));
                      return (
                        <span className={`flex items-center gap-0.5 font-semibold ${
                          clampedScore >= 60 ? "text-red-400" :
                          clampedScore >= 25 ? "text-amber-400" : "text-emerald-400"
                        }`}>
                          <Shield className="w-2.5 h-2.5" />
                          {clampedScore}/100
                        </span>
                      );
                    })()}

                    {/* Dwell */}
                    {inc.dwell_seconds > 0 && (
                      <span className="flex items-center gap-0.5 text-blue-400">
                        <Clock className="w-2.5 h-2.5" />
                        {formatDwell(inc.dwell_seconds)}
                      </span>
                    )}

                    {/* Evidence */}
                    {inc.evidence_count > 0 && (
                      <span className="flex items-center gap-0.5 text-purple-400">
                        <FileSearch className="w-2.5 h-2.5" />
                        {inc.evidence_count} EV
                      </span>
                    )}

                    {/* Incident ID */}
                    <span className="ml-auto text-slate-600 text-[8px]">{inc.incident_id}</span>
                  </div>

                  {/* Threat score bar */}
                  <div className="w-full h-0.5 bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${colors.bar} opacity-60`}
                      style={{ width: `${Math.min(100, Math.max(0, Math.round(inc.threat_score ?? 0)))}%` }}
                    />
                  </div>

                  {/* Row 4: Actions */}
                  <div className="mt-1.5 flex items-center justify-between">
                    <span className={`text-[9px] font-mono ${
                      inc.status === "ACTIVE" ? "text-red-400" :
                      inc.status === "ACKNOWLEDGED" ? "text-amber-400" : "text-emerald-400"
                    }`}>
                      {inc.status}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {inc.status === "ACTIVE" && (
                        <button
                          onClick={(e) => handleAcknowledgeIncident(e, inc.incident_id)}
                          className="text-[9px] text-emerald-400 hover:text-emerald-300 flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20"
                        >
                          <Check className="w-2.5 h-2.5" /> ACK
                        </button>
                      )}
                      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </div>
              );
            })
          )
        )}

        {/* â”€â”€ RAW ALERTS VIEW â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        {view === "ALERTS" && (
          visibleAlerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-center p-4">
              <AlertTriangle className="w-8 h-8 text-muted-foreground/40 mb-2" />
              <p className="text-xs text-muted-foreground font-mono">{loading ? "LOADING..." : "NO RAW ALERTS"}</p>
            </div>
          ) : (
            visibleAlerts.map((alert) => {
              const isSelected = selectedAlertId === alert.event_id || selectedAlertId === alert.alert_id;
              const sevUpper = (alert.severity || "NORMAL").toUpperCase();
              const colors = severityColors(sevUpper);
              const threatScore = alert.threat_score ?? 0;

              return (
                <div
                  key={alert.event_id || alert.alert_id}
                  onClick={() => onSelectAlert?.(alert)}
                  className={`p-3 transition-all cursor-pointer relative group ${
                    isSelected ? "bg-primary/10 border-l-4 border-l-primary" :
                    alert.is_acknowledged ? "opacity-60 hover:opacity-100 hover:bg-white/[0.03]" :
                    "hover:bg-white/[0.04] border-l-2 border-l-transparent"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className={`text-[9px] font-mono px-1.5 py-0.5 uppercase rounded-full border font-bold flex items-center gap-1 ${colors.badge}`}>
                        <colors.Icon className="w-2.5 h-2.5" />
                        {colors.label}
                      </span>
                      {(() => {
                        const clampedAlertScore = Math.min(100, Math.max(0, Math.round(alert.threat_score ?? 0)));
                        return (
                          <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border font-semibold ${
                            clampedAlertScore >= 60 ? "bg-red-950/80 text-red-300 border-red-700/60" :
                            clampedAlertScore >= 25 ? "bg-amber-950/80 text-amber-300 border-amber-700/60" :
                            "bg-emerald-950/80 text-emerald-300 border-emerald-700/60"
                          }`}>
                            {clampedAlertScore}/100
                          </span>
                        );
                      })()}
                      <span className="text-[10px] font-mono text-cyan-400 flex items-center gap-0.5">
                        <Camera className="w-2.5 h-2.5" />{alert.camera_id}
                      </span>
                      {alert.track_id && (
                        <span className="text-[10px] font-mono text-muted-foreground">TRACK #{alert.track_id}</span>
                      )}
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); onSeekTime?.(alert.timestamp, alert.camera_id); onSelectAlert?.(alert); }}
                      className="flex items-center gap-1 text-[10px] font-mono text-cyan-300 hover:text-cyan-100 bg-cyan-950/50 hover:bg-cyan-900/70 border border-cyan-800/50 px-1.5 py-0.5 rounded transition-colors"
                    >
                      <PlayCircle className="w-3 h-3" />
                      {formatTime(alert.timestamp)}
                    </button>
                  </div>
                  <p className="text-xs text-foreground font-medium line-clamp-2 leading-tight">
                    {alert.message || "Perimeter anomaly detected"}
                  </p>
                  <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-muted-foreground">
                    <div className="flex items-center gap-2">
                      {alert.heading && <span className="flex items-center gap-0.5 text-blue-400"><Compass className="w-2.5 h-2.5" />{alert.heading}</span>}
                      {alert.speed_description && <span>{alert.speed_description}</span>}
                    </div>
                    <div className="flex items-center gap-1.5">
                      {!alert.is_acknowledged ? (
                        <button
                          onClick={(e) => handleAcknowledgeAlert(e, alert.event_id || alert.alert_id || "")}
                          className="text-[9px] text-emerald-400 hover:text-emerald-300 flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20"
                        >
                          <Check className="w-2.5 h-2.5" /> ACK
                        </button>
                      ) : (
                        <span className="text-[9px] text-muted-foreground flex items-center gap-0.5">
                          <Check className="w-2.5 h-2.5" /> ACKED
                        </span>
                      )}
                      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </div>
              );
            })
          )
        )}
      </div>
    </div>
  );
}

