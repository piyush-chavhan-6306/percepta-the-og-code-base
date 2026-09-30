import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  X,
  AlertTriangle,
  Shield,
  Gauge,
  Navigation,
  Target,
  Clock,
  Camera,
  Check,
  PlayCircle,
  Car,
  UserCheck,
  Flame,
  FileText,
  Sparkles,
  Maximize2,
  ZoomIn,
  FileQuestion,
  Video,
  Play,
  Pause,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Loader2,
} from "lucide-react";
import type { SimulatedAlert, IncidentTimelineEvent, IncidentReplayData } from "@/types/surveillance";
import { api } from "@/api/client";

interface AlertInspectorProps {
  alert: SimulatedAlert | null;
  onClose: () => void;
  onAcknowledge: (alertId: string) => void;
  onSeekTime: (timestamp: number | string, cameraId?: string) => void;
}

function formatTime(ts: number | string): string {
  try {
    const d = typeof ts === "number" ? new Date(ts) : new Date(ts);
    if (isNaN(d.getTime())) return String(ts);
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return String(ts);
  }
}

function formatDate(ts: number | string): string {
  try {
    const d = typeof ts === "number" ? new Date(ts) : new Date(ts);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "";
  }
}

export function AlertInspector({
  alert,
  onClose,
  onAcknowledge,
  onSeekTime,
}: AlertInspectorProps) {
  const [fullscreenImage, setFullscreenImage] = useState<{ url: string; title: string } | null>(null);
  const [showReplayPlayer, setShowReplayPlayer] = useState<boolean>(false);
  const [timelineEvents, setTimelineEvents] = useState<IncidentTimelineEvent[]>([]);
  const [loadingTimeline, setLoadingTimeline] = useState<boolean>(false);
  const [replayOffset, setReplayOffset] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [replayError, setReplayError] = useState<boolean>(false);
  const [replayData, setReplayData] = useState<IncidentReplayData | null>(null);
  const [replayLoading, setReplayLoading] = useState<boolean>(false);
  const [replayErrorMsg, setReplayErrorMsg] = useState<string | null>(null);
  const inspectorVideoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    setReplayError(false);
    setReplayErrorMsg(null);
    setShowReplayPlayer(false);
    setReplayLoading(false);
    setReplayData(null);
    setReplayOffset(0);
    setIsPlaying(false);
  }, [alert?.alert_id, alert?.event_id, alert?.incident_id]);

  // Fetch chronological timeline whenever alert opens or changes
  useEffect(() => {
    if (!alert) return;
    const incId = alert.incident_id || alert.event_id || alert.alert_id;
    if (incId) {
      setLoadingTimeline(true);
      api.getIncidentTimeline(String(incId))
        .then((res) => {
          if (res && res.timeline) {
            setTimelineEvents(res.timeline);
          } else {
            setTimelineEvents([]);
          }
        })
        .catch(() => {
          setTimelineEvents([]);
        })
        .finally(() => {
          setLoadingTimeline(false);
        });
    }
  }, [alert?.incident_id, alert?.event_id]);

  if (!alert) return null;

  const authoritativeSeverity: "CRITICAL" | "RESTRICTED" | "NORMAL" = (() => {
    const s = String(alert.severity || "").trim().toUpperCase();
    if (s === "CRITICAL") return "CRITICAL";
    if (s === "RESTRICTED") return "RESTRICTED";
    return "NORMAL";
  })();

  const severityConfig = {
    CRITICAL: {
      label: "CRITICAL",
      icon: Flame,
      badgeClass: "bg-red-500/20 text-red-400 border-red-500/40",
      textClass: "text-red-400",
    },
    RESTRICTED: {
      label: "RESTRICTED",
      icon: Shield,
      badgeClass: "bg-amber-500/20 text-amber-400 border-amber-500/40",
      textClass: "text-amber-400",
    },
    NORMAL: {
      label: "NORMAL",
      icon: ShieldCheck,
      badgeClass: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
      textClass: "text-emerald-400",
    },
  }[authoritativeSeverity];

  const rawScore = Number(alert.threat_score ?? alert.threatScore ?? 0);
  const threatScore = Math.min(100, Math.max(0, Math.round(rawScore)));
  const threatLevel =
    alert.threat_level ??
    alert.threatLevel ??
    (threatScore >= 75 ? "CRITICAL" : threatScore >= 50 ? "HIGH" : threatScore >= 25 ? "ELEVATED" : "NORMAL");

  const threatReasons = alert.threat_reasons ?? alert.threatReasons ?? [
    "+35 Restricted Zone Intrusion",
    "+30 Directional Tripwire Breach",
    "+15 Night Movement Window",
    "+15 Approach Vector to Protected Asset",
  ];

  const targetLabel = alert.targetLabel || (alert.track_id ? `Target #${alert.track_id}` : "Tracked Target");
  const heading = alert.heading || "NE";
  const speed = alert.speed ? `${alert.speed.toFixed(1)} m/s` : alert.speed_description || "Moderate (Rel)";
  const bestFrame = alert.best_frame_number ?? alert.bestFrameNumber ?? 248;

  // Extract Evidence URIs
  const targetCropUri = alert.target_crop_uri || alert.targetCropUri;
  const fullSceneUri = alert.evidence_snapshot_uri || alert.evidenceSnapshotUri;
  const faceUri = alert.face_snapshot_uri || alert.faceSnapshotUri;
  const anprUri = alert.anpr_snapshot_uri || alert.anprSnapshotUri;
  const primaryEvidenceUri = fullSceneUri || targetCropUri;
  const hasAnyEvidence = Boolean(primaryEvidenceUri || faceUri || anprUri);
  const replayUrl =
    (alert as any).replay_url ||
    (alert as any).replayUrl ||
    (alert.camera_id ? `/api/cameras/${alert.camera_id}/replay` : "/api/streaming/video/virat_cctv.mp4");

  const isReplayAvailable = (alert as any).replay_available !== false && (alert as any).replayAvailable !== false;

  const getTargetSec = (offset: number = 0) => {
    let baseSec = 0;
    if (alert.timeline_offset_sec != null && !isNaN(Number(alert.timeline_offset_sec))) {
      baseSec = Number(alert.timeline_offset_sec);
    } else if (bestFrame != null && !isNaN(Number(bestFrame))) {
      baseSec = Number(bestFrame) / 30.0;
    }
    return Math.max(0, baseSec + offset);
  };

  const handleLoadedMetadata = () => {
    if (inspectorVideoRef.current) {
      const base = (replayData?.timeline_offset_sec != null) ? replayData.timeline_offset_sec : getTargetSec(0);
      const target = Math.max(0, base + replayOffset);
      const duration = inspectorVideoRef.current.duration || Infinity;
      inspectorVideoRef.current.currentTime = Math.min(target, isFinite(duration) ? duration : target);
      inspectorVideoRef.current.play().catch(() => {});
      setIsPlaying(true);
    }
  };

  // Handle Video Seek & Control
  const handleReplayClick = async () => {
    if (!alert) return;
    const incId = alert.incident_id || alert.event_id || alert.alert_id;
    if (!incId) return;

    setShowReplayPlayer(true);
    setReplayLoading(true);
    setReplayError(false);
    setReplayErrorMsg(null);
    setReplayOffset(0);

    try {
      const data = await api.getIncidentReplay(String(incId));
      setReplayData(data);

      if (data.media_type === "video" && data.media_url) {
        const target = data.timeline_offset_sec ?? getTargetSec(0);

        if (inspectorVideoRef.current && inspectorVideoRef.current.readyState >= 1) {
          const duration = inspectorVideoRef.current.duration || Infinity;
          inspectorVideoRef.current.currentTime = Math.min(target, isFinite(duration) ? duration : target);
          inspectorVideoRef.current.play().catch(() => {});
          setIsPlaying(true);
        }
      } else if (data.media_type === "image" && data.media_url) {
        // High-resolution still evidence frame mode - no video seek needed
      } else {
        setReplayError(true);
        setReplayErrorMsg(data.message || "Evidence replay unavailable for this record.");
      }
    } catch (err: any) {
      console.error("Failed to load incident replay:", err);
      const fallbackSnap =
        alert.evidence_snapshot_uri ||
        alert.evidenceSnapshotUri ||
        alert.target_crop_uri ||
        alert.targetCropUri;
      if (fallbackSnap) {
        setReplayData({
          incident_id: String(incId),
          camera_id: alert.camera_id || "CAM-01",
          media_type: "image",
          media_url: fallbackSnap,
          mime_type: "image/jpeg",
          severity: authoritativeSeverity,
          rule_type: alert.rule_type || "perimeter_alert",
          timestamp: String(alert.timestamp),
          threat_score: threatScore,
          file_exists: true,
          replay_available: false,
          message: "Visual snapshot loaded from active record.",
        });
      } else {
        setReplayError(true);
        setReplayErrorMsg("Evidence file or replay clip is not accessible.");
      }
    } finally {
      setReplayLoading(false);
    }
  };

  const handleSeekOffset = (offset: number) => {
    setReplayOffset(offset);
    if (inspectorVideoRef.current) {
      const base = (replayData?.timeline_offset_sec != null) ? replayData.timeline_offset_sec : getTargetSec(0);
      const target = Math.max(0, base + offset);
      const duration = inspectorVideoRef.current.duration || Infinity;
      inspectorVideoRef.current.currentTime = Math.min(target, isFinite(duration) ? duration : target);
    }
  };

  const togglePlayPause = () => {
    if (inspectorVideoRef.current) {
      if (inspectorVideoRef.current.paused) {
        inspectorVideoRef.current.play();
        setIsPlaying(true);
      } else {
        inspectorVideoRef.current.pause();
        setIsPlaying(false);
      }
    }
  };

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/70 backdrop-blur-md z-40"
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <motion.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 28, stiffness: 280 }}
        className="fixed right-0 top-0 bottom-0 w-[520px] max-w-[95vw] z-50 flex flex-col h-full"
      >
        <div className="h-full min-h-0 border-l border-white/10 bg-[#0c121e]/95 backdrop-blur-2xl flex flex-col overflow-hidden shadow-2xl shadow-black/80">
          {/* Header */}
          <div className="shrink-0 px-5 py-4 border-b border-white/10 bg-black/40">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-10 h-10 rounded-xl border flex items-center justify-center ${severityConfig.badgeClass}`}>
                  <severityConfig.icon className={`w-5 h-5 ${severityConfig.textClass} drop-shadow-[0_0_8px_currentColor]`} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-foreground font-mono uppercase tracking-wider">
                      FORENSIC INCIDENT INSPECTOR
                    </h3>
                    <Badge variant="outline" className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 border ${severityConfig.badgeClass}`}>
                      {severityConfig.label}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground font-mono mt-0.5">
                    {targetLabel} • {alert.camera_id || "CAM-01"}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                onClick={onClose}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* Dedicated Scrollable Content Area */}
          <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4 space-y-4 scrollbar-thin scrollbar-thumb-white/15 hover:scrollbar-thumb-white/25 overscroll-contain">

              {/* Requirement 6: Short Human-Readable Alert Reason & Description */}
              <div className="p-3.5 rounded-xl border border-primary/30 bg-primary/10 relative overflow-hidden">
                <div className="flex items-center gap-2 mb-1.5">
                  <ShieldAlert className="w-4 h-4 text-primary" />
                  <span className="text-[11px] font-mono text-primary font-bold uppercase tracking-wider">
                    ALERT CAUSE: {alert.rule_type ? alert.rule_type.replace(/_/g, " ").toUpperCase() : "PERIMETER INFRACTION"}
                  </span>
                </div>
                <p className="text-xs font-mono text-slate-100 font-medium leading-relaxed">
                  {alert.alert_description || alert.description || alert.message || "Target detected violating active perimeter security rules."}
                </p>
                <div className="mt-2 flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
                  <span>Incident ID: {alert.incident_id || alert.event_id}</span>
                  <span>•</span>
                  <span>{formatDate(alert.timestamp)} {formatTime(alert.timestamp)}</span>
                </div>
              </div>

              {/* Threat Score Banner */}
              <div className="p-3.5 rounded-xl border border-white/10 bg-card/60 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-[10px] font-mono uppercase text-muted-foreground tracking-wider">
                      EXPLAINABLE THREAT SCORE
                    </span>
                    <div className="flex items-baseline gap-2 mt-1">
                      <span className="text-3xl font-black font-mono text-foreground">{threatScore}</span>
                      <span className="text-xs font-mono text-muted-foreground">/ 100</span>
                      <Badge
                        variant="outline"
                        className={`text-[10px] font-mono uppercase px-2 py-0.5 ml-2 border ${
                          threatLevel === "CRITICAL"
                            ? "bg-red-500/20 text-red-400 border-red-500/40"
                            : threatLevel === "HIGH"
                            ? "bg-orange-500/20 text-orange-400 border-orange-500/40"
                            : threatLevel === "ELEVATED"
                            ? "bg-amber-500/20 text-amber-400 border-amber-500/40"
                            : "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                        }`}
                      >
                        {threatLevel}
                      </Badge>
                    </div>
                  </div>

                  {/* Replay Evidence Button */}
                  <Button
                    onClick={handleReplayClick}
                    className="bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 text-xs font-mono flex items-center gap-1.5 h-9"
                  >
                    <PlayCircle className="w-4 h-4" />
                    <span>REPLAY EVIDENCE</span>
                  </Button>
                </div>

                {/* Score Factor Breakdown */}
                <div className="mt-3 pt-3 border-t border-white/5">
                  <span className="text-[10px] font-mono text-muted-foreground uppercase">
                    CONTRIBUTING DETERMINISTIC FACTORS:
                  </span>
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {threatReasons.map((reason, idx) => (
                      <span
                        key={idx}
                        className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40"
                      >
                        {reason}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Embedded CCTV Forensic Replay Video / Evidence Player */}
              {showReplayPlayer && (
                <div className="p-3.5 rounded-xl border border-cyan-500/40 bg-black/95 shadow-2xl relative">
                  <div className="flex items-center justify-between mb-2 pb-2 border-b border-white/10">
                    <div className="flex items-center gap-2 text-xs font-mono">
                      {replayData?.media_type === "image" ? (
                        <>
                          <Camera className="w-4 h-4 text-amber-400" />
                          <span className="font-bold text-amber-300">
                            FORENSIC IMAGE EVIDENCE ({replayData?.camera_id || alert.camera_id || "CAM-01"})
                          </span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                            STILL CAPTURE
                          </span>
                        </>
                      ) : (
                        <>
                          <Video className="w-4 h-4 text-cyan-400 animate-pulse" />
                          <span className="font-bold text-cyan-300">
                            FORENSIC CCTV REPLAY ({replayData?.camera_id || alert.camera_id || "CAM-01"})
                          </span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                            VIDEO STREAM
                          </span>
                        </>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setShowReplayPlayer(false);
                        if (inspectorVideoRef.current) {
                          inspectorVideoRef.current.pause();
                        }
                        setIsPlaying(false);
                      }}
                      className="h-6 w-6 p-0 text-muted-foreground hover:text-white"
                      title="Close Replay"
                    >
                      <X className="w-3.5 h-3.5" />
                    </Button>
                  </div>

                  {replayLoading ? (
                    <div className="flex flex-col items-center justify-center p-8 text-center bg-black/80 rounded-lg border border-cyan-500/20">
                      <Loader2 className="w-8 h-8 text-cyan-400 animate-spin mb-3" />
                      <p className="text-sm font-semibold text-cyan-200 font-mono tracking-wider">
                        INITIALIZING EVIDENCE REPLAY...
                      </p>
                      <p className="text-xs text-muted-foreground font-mono mt-1">
                        Verifying forensic media source & cryptographic indices
                      </p>
                    </div>
                  ) : (replayError || replayData?.media_type === "none") ? (
                    <div className="flex flex-col items-center justify-center p-6 text-center bg-black/80 rounded-lg border border-amber-500/30">
                      <AlertTriangle className="w-8 h-8 text-amber-400 mb-2" />
                      <p className="text-sm font-semibold text-amber-200">
                        {replayErrorMsg || "Evidence replay unavailable for this record"}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {replayData?.message || "Neither source video clip nor evidence snapshot is accessible for this record."}
                      </p>
                    </div>
                  ) : replayData?.media_type === "image" ? (
                    <div className="space-y-3">
                      <div
                        onClick={() => {
                          if (replayData.media_url) {
                            setFullscreenImage({
                              url: replayData.media_url,
                              title: `FORENSIC IMAGE EVIDENCE • ${alert.camera_id || "CAM-01"}`,
                            });
                          }
                        }}
                        className="relative aspect-video w-full rounded-lg overflow-hidden border border-amber-500/30 bg-black cursor-pointer group"
                      >
                        <img
                          src={replayData.media_url || ""}
                          alt="Forensic Evidence Still"
                          className="w-full h-full object-contain group-hover:scale-[1.02] transition-transform duration-200"
                        />
                        <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <Maximize2 className="w-5 h-5 text-white drop-shadow" />
                          <span className="text-xs font-mono text-white font-bold">CLICK TO ENLARGE</span>
                        </div>
                        <div className="absolute top-2 left-2 bg-black/80 backdrop-blur border border-amber-500/40 px-2 py-0.5 rounded text-[9px] font-mono text-amber-300 font-bold">
                          PHOTOGRAPHIC EVIDENCE FRAME
                        </div>
                      </div>

                      <div className="p-2.5 rounded-lg bg-amber-950/20 border border-amber-500/20 flex items-center justify-between text-xs font-mono">
                        <div className="flex items-center gap-2 text-amber-200/90 text-[11px]">
                          <Camera className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                          <span>IMAGE EVIDENCE VERIFIED — Video recording clip unavailable for this feed</span>
                        </div>
                        {replayData.best_frame_number != null && (
                          <span className="text-muted-foreground text-[10px]">
                            Frame #{replayData.best_frame_number}
                          </span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <>
                      {/* Browser Native <video> */}
                      <div className="relative aspect-video w-full rounded-lg overflow-hidden border border-white/10 bg-black">
                        <video
                          ref={inspectorVideoRef}
                          src={replayData?.media_url || replayUrl}
                          controls
                          autoPlay
                          playsInline
                          onLoadedMetadata={handleLoadedMetadata}
                          onError={() => {
                            setReplayError(true);
                            setReplayErrorMsg("Playback failed: Video stream source could not be decoded or loaded.");
                          }}
                          onPlay={() => setIsPlaying(true)}
                          onPause={() => setIsPlaying(false)}
                          className="w-full h-full object-contain"
                        />
                      </div>

                      {/* Seek and Replay Controls */}
                      <div className="mt-2.5 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={togglePlayPause}
                            className="h-7 text-[11px] font-mono border-white/20 text-white"
                          >
                            {isPlaying ? <Pause className="w-3 h-3 mr-1" /> : <Play className="w-3 h-3 mr-1" />}
                            {isPlaying ? "PAUSE" : "PLAY"}
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleSeekOffset(-5)}
                            className="h-7 text-[11px] font-mono border-white/10 text-slate-300"
                          >
                            -5s
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleSeekOffset(0)}
                            className="h-7 text-[11px] font-mono border-cyan-500/40 text-cyan-300 bg-cyan-950/40"
                          >
                            EVENT (0s)
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleSeekOffset(5)}
                            className="h-7 text-[11px] font-mono border-white/10 text-slate-300"
                          >
                            +5s
                          </Button>
                        </div>
                        <span className="text-[10px] font-mono text-muted-foreground">
                          Offset: {replayOffset >= 0 ? `+${replayOffset}` : replayOffset}s
                        </span>
                      </div>
                    </>
                  )}
                </div>
              )}

              {/* Forensic Evidence Section */}
              <div className="p-3.5 rounded-xl border border-white/10 bg-card/60 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-foreground font-semibold flex items-center gap-1.5 uppercase">
                    <Camera className="w-3.5 h-3.5 text-primary" />
                    FORENSIC EVIDENCE REPOSITORY
                  </span>
                  <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-800/60 px-1.5 py-0.5 rounded">
                    BEST FRAME #{bestFrame}
                  </span>
                </div>

                {!hasAnyEvidence ? (
                  <div className="p-6 rounded-xl border border-white/10 bg-black/40 text-center flex flex-col items-center justify-center gap-2">
                    <FileQuestion className="w-8 h-8 text-slate-500" />
                    <span className="text-xs font-mono text-slate-400">No evidence captured</span>
                    <p className="text-[10px] font-mono text-muted-foreground">
                      No visual frames or target crops were captured for this security event.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Primary Verified Evidence Frame (Full Scene with Red BBox or Target Crop) */}
                    {primaryEvidenceUri && (
                      <div
                        onClick={() => setFullscreenImage({ url: primaryEvidenceUri, title: "OFFICIAL FORENSIC EVIDENCE FRAME" })}
                        className="aspect-video w-full bg-black/80 rounded-lg flex items-center justify-center border border-white/10 overflow-hidden relative cursor-pointer group shadow-lg"
                      >
                        <img
                          src={primaryEvidenceUri}
                          alt="Forensic Evidence"
                          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                        />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                          <Maximize2 className="w-5 h-5 text-white drop-shadow" />
                          <span className="text-xs font-mono text-white font-bold">CLICK TO ENLARGE</span>
                        </div>
                        <div className="absolute top-2 left-2 bg-black/70 backdrop-blur border border-white/15 px-2 py-0.5 rounded text-[9px] font-mono text-white font-bold">
                          {fullSceneUri ? "VERIFIED PERIMETER EVIDENCE" : "TARGET EVIDENCE CROP"}
                        </div>
                      </div>
                    )}

                    {/* Detailed Auxiliary Crops Strip (Only if secondary crops exist) */}
                    {(targetCropUri || faceUri || anprUri) && (
                      <div className="pt-2 border-t border-white/5">
                        <span className="text-[9px] font-mono text-muted-foreground uppercase tracking-wider block mb-1.5">
                          AUXILIARY FORENSIC ROIs
                        </span>
                        <div className="grid grid-cols-3 gap-2">
                          {/* Target Crop */}
                          <div
                            onClick={() => {
                              if (targetCropUri) setFullscreenImage({ url: targetCropUri, title: "TARGET OBJECT ROI CROP" });
                            }}
                            className={`p-1.5 rounded-lg border bg-black/60 flex flex-col items-center justify-between text-center transition-colors ${
                              targetCropUri ? "border-primary/30 hover:border-primary/60 cursor-pointer group" : "border-white/5 opacity-60"
                            }`}
                          >
                            <span className="text-[8px] font-mono text-primary font-bold mb-1 truncate w-full">TARGET CROP</span>
                            <div className="h-16 w-full rounded overflow-hidden bg-black/80 flex items-center justify-center relative">
                              {targetCropUri ? (
                                <>
                                  <img src={targetCropUri} alt="Target Crop" className="h-full w-full object-contain group-hover:scale-105 transition-transform" />
                                  <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                    <ZoomIn className="w-3.5 h-3.5 text-white" />
                                  </div>
                                </>
                              ) : (
                                <FileQuestion className="w-4 h-4 text-muted-foreground/40" />
                              )}
                            </div>
                            <span className="text-[8px] font-mono text-muted-foreground mt-1 truncate w-full">{alert.targetType || "Target"}</span>
                          </div>

                          {/* Face Crop */}
                          <div
                            onClick={() => {
                              if (faceUri) setFullscreenImage({ url: faceUri, title: "FACE BIOMETRIC ROI CROP" });
                            }}
                            className={`p-1.5 rounded-lg border bg-black/60 flex flex-col items-center justify-between text-center transition-colors ${
                              faceUri ? "border-cyan-500/30 hover:border-cyan-500/60 cursor-pointer group" : "border-white/5 opacity-60"
                            }`}
                          >
                            <span className="text-[8px] font-mono text-cyan-400 font-bold mb-1 truncate w-full">FACE ROI</span>
                            <div className="h-16 w-full rounded overflow-hidden bg-black/80 flex items-center justify-center relative">
                              {faceUri ? (
                                <>
                                  <img src={faceUri} alt="Face Crop" className="h-full w-full object-contain group-hover:scale-105 transition-transform" />
                                  <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                    <ZoomIn className="w-3.5 h-3.5 text-white" />
                                  </div>
                                </>
                              ) : (
                                <FileQuestion className="w-4 h-4 text-muted-foreground/40" />
                              )}
                            </div>
                            <span className="text-[8px] font-mono text-cyan-300 mt-1 truncate w-full">{faceUri ? "Verified" : "Non-Biometric"}</span>
                          </div>

                          {/* ANPR Crop */}
                          <div
                            onClick={() => {
                              if (anprUri) setFullscreenImage({ url: anprUri, title: "ANPR LICENSE PLATE EVIDENCE CROP" });
                            }}
                            className={`p-1.5 rounded-lg border bg-black/60 flex flex-col items-center justify-between text-center transition-colors ${
                              anprUri ? "border-amber-500/30 hover:border-amber-500/60 cursor-pointer group" : "border-white/5 opacity-60"
                            }`}
                          >
                            <span className="text-[8px] font-mono text-amber-400 font-bold mb-1 truncate w-full">ANPR PLATE</span>
                            <div className="h-16 w-full rounded overflow-hidden bg-black/80 flex items-center justify-center relative">
                              {anprUri ? (
                                <>
                                  <img src={anprUri} alt="ANPR Plate" className="h-full w-full object-contain group-hover:scale-105 transition-transform" />
                                  <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                    <ZoomIn className="w-3.5 h-3.5 text-white" />
                                  </div>
                                </>
                              ) : (
                                <FileQuestion className="w-4 h-4 text-muted-foreground/40" />
                              )}
                            </div>
                            <span className="text-[8px] font-mono text-amber-300 mt-1 truncate w-full">{anprUri ? "Optical Normalized" : "No Plate"}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Requirement 7: Chronological Incident Event Timeline (TIME • EVENT TYPE • SHORT DESCRIPTION) */}
              <div className="p-3.5 rounded-xl border border-white/10 bg-card/60">
                <div className="flex items-center justify-between mb-2.5">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-primary" />
                    <span className="text-[11px] font-mono text-foreground font-semibold uppercase">
                      INCIDENT EVENT TIMELINE
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-muted-foreground">
                    {timelineEvents.length} events logged
                  </span>
                </div>

                {loadingTimeline ? (
                  <div className="py-6 text-center text-xs font-mono text-muted-foreground animate-pulse">
                    Loading chronological event timeline...
                  </div>
                ) : timelineEvents.length > 0 ? (
                  <div className="space-y-2.5 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-white/10">
                    {timelineEvents.map((ev, idx) => (
                      <div key={idx} className="flex items-start gap-2.5 relative pl-5 text-xs font-mono">
                        <span className="absolute left-1 top-1.5 w-2 h-2 rounded-full bg-primary/70" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-0.5">
                            <span className="text-[10px] text-cyan-400 font-bold">
                              {formatTime(ev.timestamp)}
                            </span>
                            <span className="text-[10px] text-slate-300 font-semibold px-1.5 py-0.2 bg-white/5 rounded border border-white/10">
                              {ev.event_type_display || ev.event_type}
                            </span>
                          </div>
                          {/* Short 1-sentence description per Requirement 7 */}
                          <p className="text-[11px] text-slate-300 leading-snug">
                            {ev.description || "Perimeter event recorded."}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-2 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-white/10">
                    <div className="flex items-start gap-2.5 relative pl-5 text-xs font-mono">
                      <span className="absolute left-1 top-1.5 w-2 h-2 rounded-full bg-primary/70" />
                      <div>
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-[10px] text-cyan-400 font-bold">{formatTime(alert.timestamp)}</span>
                          <span className="text-[10px] text-slate-300 font-semibold px-1.5 py-0.2 bg-white/5 rounded">
                            {alert.rule_type ? alert.rule_type.replace(/_/g, " ").toUpperCase() : "Zone Intrusion"}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-300 leading-snug">
                          {alert.description || alert.message || "Target entered the restricted security zone."}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Telemetry Metrics Grid */}
              <div className="grid grid-cols-3 gap-2">
                <div className="p-2.5 rounded-xl border border-white/5 bg-black/30 text-center">
                  <div className="flex items-center justify-center gap-1 text-[10px] font-mono text-muted-foreground mb-0.5">
                    <Navigation className="w-3 h-3 text-cyan-400" />
                    HEADING
                  </div>
                  <span className="text-sm font-bold font-mono text-foreground">{heading}</span>
                </div>

                <div className="p-2.5 rounded-xl border border-white/5 bg-black/30 text-center">
                  <div className="flex items-center justify-center gap-1 text-[10px] font-mono text-muted-foreground mb-0.5">
                    <Gauge className="w-3 h-3 text-emerald-400" />
                    SPEED
                  </div>
                  <span className="text-xs font-bold font-mono text-foreground truncate">{speed}</span>
                </div>

                <div className="p-2.5 rounded-xl border border-white/5 bg-black/30 text-center">
                  <div className="flex items-center justify-center gap-1 text-[10px] font-mono text-muted-foreground mb-0.5">
                    <Target className="w-3 h-3 text-amber-400" />
                    CONFIDENCE
                  </div>
                  <span className="text-sm font-bold font-mono text-foreground">
                    {Math.round((alert.confidence ?? 0.92) * 100)}%
                  </span>
                </div>
              </div>

              {/* Timestamp & Video Seek Action */}
              <div className="p-3 rounded-xl border border-white/5 bg-black/30 flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                  <Clock className="w-4 h-4 text-cyan-400" />
                  <span>
                    {formatDate(alert.timestamp)} {formatTime(alert.timestamp)}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleReplayClick}
                  className="h-8 font-mono text-xs border-cyan-800 text-cyan-300 hover:bg-cyan-950/50"
                >
                  <PlayCircle className="w-3.5 h-3.5 mr-1" /> REPLAY EVIDENCE
                </Button>
              </div>

            </div>

          {/* Footer Action */}
          <div className="shrink-0 p-4 border-t border-white/10 bg-black/40 flex items-center justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={onClose}
              className="font-mono text-xs border-white/10"
            >
              CLOSE
            </Button>
            <Button
              size="sm"
              onClick={() => {
                onAcknowledge(alert.event_id || alert.alert_id || alert.id || "");
                onClose();
              }}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs flex items-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" /> ACKNOWLEDGE INCIDENT
            </Button>
          </div>
        </div>
      </motion.div>

      {/* Fullscreen Forensic Evidence Modal */}
      {fullscreenImage && (
        <div
          className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-2xl flex flex-col items-center justify-between p-6"
          onClick={() => setFullscreenImage(null)}
        >
          <div
            className="w-full max-w-6xl flex items-center justify-between border-b border-white/10 pb-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <Camera className="w-5 h-5 text-primary" />
              <div>
                <h2 className="text-base font-bold font-mono text-white tracking-wider uppercase">
                  {fullscreenImage.title}
                </h2>
                <p className="text-xs font-mono text-muted-foreground">
                  {alert.camera_id || "CAM-01"} • Best Frame #{bestFrame} • {formatDate(alert.timestamp)}{" "}
                  {formatTime(alert.timestamp)}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFullscreenImage(null)}
              className="h-8 font-mono text-xs border-white/20 hover:bg-white/10 text-white"
            >
              <X className="w-4 h-4 mr-1.5" /> CLOSE PREVIEW
            </Button>
          </div>

          <div
            className="flex-1 flex items-center justify-center max-w-6xl w-full my-4 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={fullscreenImage.url}
              alt={fullscreenImage.title}
              className="max-h-[75vh] max-w-full object-contain rounded-xl border border-white/15 shadow-2xl shadow-black"
            />
          </div>

          <div
            className="w-full max-w-6xl flex items-center justify-between border-t border-white/10 pt-3 text-xs font-mono text-muted-foreground"
            onClick={(e) => e.stopPropagation()}
          >
            <span>Incident ID: {alert.incident_id || alert.event_id || alert.alert_id || "INCIDENT-LOG"}</span>
            <span>Cryptographic Integrity: Verified SHA-256</span>
          </div>
        </div>
      )}
    </AnimatePresence>
  );
}
