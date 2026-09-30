import { useState, useRef, useEffect, useMemo, MouseEvent } from "react";
import { api, API_BASE_URL } from "@/api/client";
import { SecurityZone, VirtualBoundary } from "@/types/surveillance";
import {
  useDisplayedImageRect,
  clickToFrameCoords,
} from "@/hooks/useDisplayedImageRect";
import {
  Square,
  Crosshair,
  Trash2,
  Check,
  X,
  Camera,
  Shield,
  Zap,
  Undo2,
  Play,
  Pause,
  RotateCcw,
  Radio,
  Eye,
  Flame,
  Moon,
  Video,
  Clock,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface CameraFeedProps {
  cameraId: string;
  cameraName?: string;
  modality?: "STANDARD" | "IR_NIGHT" | "THERMAL" | string;
  selectedAlertTime?: string | number | null;
  isRunning?: boolean;
  gridLayout?: "1x1" | "2x2" | "3x3";
  onLayoutChange?: (layout: "1x1" | "2x2" | "3x3") => void;
  onToggleRun?: () => void;
  onExitSeek?: () => void;
  onZoneCreated?: () => void;
  onFeedClick?: () => void;
}

type DrawMode = "none" | "polygon" | "tripwire";

export function CameraFeed({
  cameraId,
  cameraName = "Border Sector Feed",
  modality = "STANDARD",
  selectedAlertTime = null,
  isRunning = true,
  gridLayout = "1x1",
  onLayoutChange,
  onToggleRun,
  onExitSeek,
  onZoneCreated,
  onFeedClick,
}: CameraFeedProps) {
  const [activeModality, setActiveModality] = useState<string>(modality);
  const [sessionNonce, setSessionNonce] = useState<number>(Date.now());
  const [trustReport, setTrustReport] = useState<{
    trust_score: number;
    trust_level: string;
    is_trusted: boolean;
    summary: string;
    factors: Array<{ factor: string; score: number; metric: string; status: string }>;
  } | null>(null);
  const [showTrustDetails, setShowTrustDetails] = useState(false);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [points, setPoints] = useState<[number, number][]>([]);
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  const [zones, setZones] = useState<SecurityZone[]>([]);
  const [boundaries, setBoundaries] = useState<VirtualBoundary[]>([]);
  const [zoneName, setZoneName] = useState("");
  const [severity, setSeverity] = useState<string>("restricted");
  const [tripwireDirection, setTripwireDirection] = useState<string>("BIDIRECTIONAL");
  const [isSaving, setIsSaving] = useState(false);
  const [frozenAt, setFrozenAt] = useState<number>(0);
  const [selectedTriggerId, setSelectedTriggerId] = useState<string>("");
  const [isDeletingTrigger, setIsDeletingTrigger] = useState(false);
  const [streamError, setStreamError] = useState(false);

  // Timeline Seek State
  const [isReplaying, setIsReplaying] = useState(false);
  const [seekOffsetSec, setSeekOffsetSec] = useState<number>(0); // -5s to +5s
  const isSeekMode = selectedAlertTime !== null;

  const selectedTrigger = useMemo(() => {
    if (!selectedTriggerId) return null;
    const z = zones.find((item) => item.zone_id === selectedTriggerId);
    if (z) {
      return {
        id: z.zone_id,
        name: z.name,
        type: "ZONE" as const,
        severity: (z.severity || "RESTRICTED").toUpperCase(),
        direction: undefined,
      };
    }
    const b = boundaries.find((item) => item.boundary_id === selectedTriggerId);
    if (b) {
      return {
        id: b.boundary_id,
        name: b.name,
        type: "TRIPWIRE" as const,
        severity: (b.severity || "CRITICAL").toUpperCase(),
        direction: b.direction || "BIDIRECTIONAL",
      };
    }
    return null;
  }, [selectedTriggerId, zones, boundaries]);

  const trustRef = useRef<HTMLDivElement>(null);
  const isCompact = gridLayout !== "1x1";

  // Close trust sensor details on click outside
  useEffect(() => {
    if (!showTrustDetails) return;
    const handleOutsideClick = (e: globalThis.MouseEvent) => {
      if (trustRef.current && !trustRef.current.contains(e.target as Node)) {
        setShowTrustDetails(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [showTrustDetails]);

  const imageRef = useRef<HTMLImageElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const { rect, remeasure } = useDisplayedImageRect(imageRef);

  const isDrawing = drawMode !== "none";
  const required = drawMode === "tripwire" ? 2 : 3;
  const canSave = points.length >= required;

  const containerRect = containerRef.current?.getBoundingClientRect();
  const svgLeft = rect.ready && containerRect ? (rect.elementLeft - containerRect.left) + rect.offsetX : rect.offsetX;
  const svgTop = rect.ready && containerRect ? (rect.elementTop - containerRect.top) + rect.offsetY : rect.offsetY;

  useEffect(() => {
    setActiveModality(modality);
  }, [modality]);

  // Restart lifecycle fix: when isRunning becomes true, update sessionNonce and clear any stale error
  useEffect(() => {
    if (isRunning) {
      setSessionNonce(Date.now());
      setStreamError(false);
    }
  }, [isRunning, cameraId]);

  // Fetch explainable Camera Trust telemetry periodically
  useEffect(() => {
    let isMounted = true;
    const fetchTrust = async () => {
      try {
        const rep = await api.getCameraTrust(cameraId);
        if (isMounted) setTrustReport(rep);
      } catch (err) {
        // Fallback silently if offline
      }
    };
    fetchTrust();
    const interval = setInterval(fetchTrust, 8000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [cameraId]);

  useEffect(() => {
    if (selectedAlertTime) {
      setSeekOffsetSec(0);
      setIsReplaying(true);
    }
  }, [selectedAlertTime]);

  // Synchronize CCTV Replay Video Seek
  const getCameraSeekSec = (offset: number = 0) => {
    let baseSec = 0;
    if (typeof selectedAlertTime === "number") {
      baseSec = selectedAlertTime;
    } else if (typeof selectedAlertTime === "string") {
      const num = parseFloat(selectedAlertTime);
      if (!isNaN(num) && String(num) === selectedAlertTime.trim()) {
        baseSec = num;
      }
    }
    return Math.max(0, baseSec + offset);
  };

  const handleReplayLoadedMetadata = () => {
    if (videoRef.current) {
      const targetTime = getCameraSeekSec(seekOffsetSec);
      const duration = videoRef.current.duration || Infinity;
      videoRef.current.currentTime = Math.min(targetTime, isFinite(duration) ? duration : targetTime);
      videoRef.current.play().catch(() => {});
    }
  };

  useEffect(() => {
    if (isSeekMode && videoRef.current && videoRef.current.readyState >= 1) {
      const targetTime = getCameraSeekSec(seekOffsetSec);
      const duration = videoRef.current.duration || Infinity;
      videoRef.current.currentTime = Math.min(targetTime, isFinite(duration) ? duration : targetTime);
      videoRef.current.play().catch(() => {});
    }
  }, [isSeekMode, selectedAlertTime, seekOffsetSec]);

  const fetchZones = async () => {
    try {
      const res = await api.getZones();
      setZones(res.zones?.filter((z: any) => !z.camera_id || z.camera_id === cameraId) || []);
      setBoundaries(res.boundaries?.filter((b: any) => !b.camera_id || b.camera_id === cameraId) || []);
    } catch (err) {
      console.error("Failed to fetch zones:", err);
    }
  };

  useEffect(() => {
    fetchZones();
  }, [cameraId]);

  const beginDraw = (mode: DrawMode) => {
    setDrawMode(mode);
    setPoints([]);
    setCursor(null);
    setZoneName("");
    setSeverity(mode === "tripwire" ? "critical" : "restricted");
    setTripwireDirection("BIDIRECTIONAL");
    setFrozenAt(Date.now());
  };

  const cancelDraw = () => {
    setDrawMode("none");
    setPoints([]);
    setCursor(null);
  };

  const undoPoint = () => setPoints((prev) => prev.slice(0, -1));

  useEffect(() => {
    if (!isDrawing) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelDraw();
      } else if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        undoPoint();
      } else if (e.key === "Enter" && canSave) {
        e.preventDefault();
        void handleSaveZone();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isDrawing, canSave, points, zoneName, severity, drawMode]);

  const handleClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!isDrawing) {
      if (isCompact && onFeedClick) {
        onFeedClick();
      }
      return;
    }
    if (!rect) return;
    const pt = clickToFrameCoords(e.clientX, e.clientY, rect);
    if (!pt) return;

    if (drawMode === "tripwire") {
      if (points.length === 0) setPoints([pt]);
      else if (points.length === 1) setPoints([points[0], pt]);
    } else {
      setPoints((prev) => [...prev, pt]);
    }
  };

  const handleMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!isDrawing || !rect) return;
    const pt = clickToFrameCoords(e.clientX, e.clientY, rect);
    setCursor(pt);
  };

  const handleSaveZone = async () => {
    if (!canSave) return;
    setIsSaving(true);
    try {
      const name = zoneName.trim() || `${drawMode.toUpperCase()} #${Date.now().toString().slice(-4)}`;
      if (drawMode === "polygon") {
        await api.createZone({
          name,
          polygon: points,
          severity,
          camera_id: cameraId,
        });
      } else if (drawMode === "tripwire" && points.length >= 2) {
        await api.createBoundary({
          name,
          pt1: points[0],
          pt2: points[1],
          severity,
          direction: tripwireDirection,
          camera_id: cameraId,
        });
      }
      cancelDraw();
      setZoneName("");
      await fetchZones();
      onZoneCreated?.();
    } catch (err) {
      console.error("Failed to save zone:", err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteTrigger = async () => {
    if (!selectedTriggerId) return;
    setIsDeletingTrigger(true);
    try {
      await api.deleteZone(selectedTriggerId);
      setSelectedTriggerId("");
      await fetchZones();
      onZoneCreated?.();
    } catch (err) {
      console.error("Failed to delete trigger:", err);
    } finally {
      setIsDeletingTrigger(false);
    }
  };

  const feedUrl = useMemo(() => {
    if (isDrawing && frozenAt) {
      return `${API_BASE_URL}/api/streaming/snapshot/${cameraId}?t=${frozenAt}`;
    }
    return `${API_BASE_URL}/api/streaming/feed/${cameraId}?t=${sessionNonce}`;
  }, [cameraId, isDrawing, frozenAt, sessionNonce]);



  useEffect(() => {
    setStreamError(false);
  }, [feedUrl]);

  return (
    <div className="flex flex-col h-full relative">
      {/* Top Telemetry Header — Responsive Layout & High-Z Stacking Context */}
      <div className="relative z-40 px-3 sm:px-4 py-2 border-b border-white/10 flex flex-wrap items-center justify-between gap-x-2.5 sm:gap-x-3 gap-y-2 bg-black/75 backdrop-blur-md min-h-[46px]">
        {/* Left: Camera Identity & Trust Telemetry */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-wrap">
          <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
            <span
              className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                isRunning
                  ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]"
                  : "bg-gray-500"
              } animate-pulse`}
            />
            <h2
              className="text-xs font-bold text-foreground font-mono uppercase tracking-wider whitespace-nowrap truncate max-w-[130px] xs:max-w-[180px] sm:max-w-[240px] md:max-w-[320px]"
              title={`${cameraId} — ${cameraName}`}
            >
              {cameraId} — {cameraName}
            </h2>
          </div>

          {/* Camera Trust Sensor Badge & Explainability Popover */}
          {trustReport && (
            <div ref={trustRef} className="relative z-50 shrink-0">
              <button
                type="button"
                onClick={() => setShowTrustDetails((prev) => !prev)}
                className={`px-2 py-0.5 sm:px-2.5 sm:py-1 rounded-lg border text-[10px] sm:text-[11px] font-mono flex items-center gap-1 sm:gap-1.5 whitespace-nowrap transition-all cursor-pointer ${
                  trustReport.trust_level === "HIGH"
                    ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300 shadow-[0_0_10px_rgba(16,185,129,0.2)] hover:bg-emerald-500/25"
                    : trustReport.trust_level === "MEDIUM"
                    ? "bg-amber-500/15 border-amber-500/50 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.2)] hover:bg-amber-500/25"
                    : "bg-rose-500/15 border-rose-500/50 text-rose-300 shadow-[0_0_10px_rgba(244,63,94,0.2)] hover:bg-rose-500/25"
                }`}
                title="Camera Trust Sensor (Click to inspect optical health & clarity factors)"
                data-testid="camera-trust-badge"
              >
                <Shield className="w-3.5 h-3.5 shrink-0" />
                <span className="font-bold">TRUST: {trustReport.trust_score.toFixed(0)}%</span>
                <span className="text-[9px] font-semibold px-1 py-0.2 rounded bg-black/50 border border-white/10 uppercase hidden xs:inline">
                  {trustReport.trust_level}
                </span>
              </button>

              {showTrustDetails && (
                <div className="absolute left-0 top-full mt-2 z-50 w-72 sm:w-80 max-w-[calc(100vw-32px)] bg-[#090d14]/98 border border-[#00e5ff]/50 rounded-xl shadow-[0_12px_40px_rgba(0,0,0,0.9)] backdrop-blur-2xl p-3 font-mono text-[11px] animate-in fade-in zoom-in-95 duration-100 ring-1 ring-[#00e5ff]/30">
                  <div className="flex items-center justify-between border-b border-white/10 pb-1.5 mb-2">
                    <span className="font-bold text-white uppercase text-[10px] tracking-wider">
                      CAMERA TRUST SENSOR
                    </span>
                    <button
                      onClick={() => setShowTrustDetails(false)}
                      className="text-gray-400 hover:text-white cursor-pointer"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                  <p className="text-[10px] text-gray-400 mb-2 leading-relaxed">{trustReport.summary}</p>
                  <div className="space-y-1.5 max-h-[190px] overflow-y-auto pr-1">
                    {trustReport.factors.map((f, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-[10px] p-1.5 rounded bg-black/50 border border-white/5"
                      >
                        <span className="text-gray-300">{f.factor}</span>
                        <div className="flex items-center gap-1.5">
                          <span className="text-gray-400 text-[9px]">{f.metric}</span>
                          <span
                            className={`font-bold ${
                              f.status === "OPTIMAL" || f.status === "CLEAR" || f.status === "NOMINAL"
                                ? "text-emerald-400"
                                : f.status === "DEGRADED" || f.status === "SUBOPTIMAL"
                                ? "text-amber-400"
                                : "text-red-400"
                            }`}
                          >
                            {f.score.toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {isSeekMode && (
            <Badge
              variant="destructive"
              className="text-[9px] sm:text-[10px] font-mono px-1.5 sm:px-2 py-0.5 sm:py-1 bg-red-600/30 text-red-300 border-red-500/50 flex items-center gap-1 whitespace-nowrap shrink-0 animate-pulse"
            >
              <Clock className="w-3 h-3" /> <span className="hidden xs:inline">FORENSIC </span>REPLAY
            </Badge>
          )}
        </div>

        {/* Right: Actions & Tools with responsive wrapping and density scaling */}
        <div className="flex items-center gap-1.5 sm:gap-2.5 flex-wrap shrink-0">
          {/* Camera Grid Layout Controls (1x1, 2x2, 3x3) */}
          {onLayoutChange && (
            <div className="flex items-center bg-black/70 border border-white/10 rounded-lg p-0.5 text-[10px] sm:text-[11px] font-mono shadow-inner">
              {(["1x1", "2x2", "3x3"] as const).map((l) => (
                <button
                  key={l}
                  type="button"
                  onClick={() => onLayoutChange(l)}
                  className={`px-1.5 sm:px-2.5 py-0.5 sm:py-1 rounded-md transition-all cursor-pointer font-bold ${
                    gridLayout === l
                      ? "bg-[#00e5ff] text-black shadow-[0_0_12px_rgba(0,229,255,0.4)]"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                  title={`Switch to ${l.replace("x", "×")} layout`}
                  data-testid={`grid-layout-${l}`}
                >
                  {l.replace("x", "×")}
                </button>
              ))}
            </div>
          )}

          {/* Start / Stop Analysis Button */}
          {onToggleRun && (
            <Button
              variant="outline"
              size="sm"
              onClick={onToggleRun}
              className={`h-7 sm:h-8 px-2 sm:px-3 text-[11px] sm:text-xs font-mono font-bold flex items-center gap-1 sm:gap-1.5 rounded-lg transition-all ${
                isRunning
                  ? "border-red-500/40 text-red-400 hover:bg-red-500/20 shadow-red-900/30"
                  : "border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/20 shadow-emerald-900/30"
              }`}
              title={isRunning ? "Stop perception analysis" : "Start live perception analysis"}
            >
              {isRunning ? (
                <>
                  <Square className="w-3 h-3 fill-current shrink-0" />
                  <span>STOP<span className="hidden sm:inline"> ANALYSIS</span></span>
                </>
              ) : (
                <>
                  <Play className="w-3 h-3 fill-current shrink-0" />
                  <span>START<span className="hidden sm:inline"> ANALYSIS</span></span>
                </>
              )}
            </Button>
          )}

          {/* Zone / Tripwire & Trigger management — only in focused 1x1 mode */}
          {!isCompact && (
            <>
              <div className="h-4 sm:h-5 w-px bg-white/10 shrink-0 hidden xs:block" />
              {!isDrawing ? (
                <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                  <div className="flex items-center gap-1 sm:gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => beginDraw("polygon")}
                      className="h-7 sm:h-8 px-2 sm:px-2.5 text-[11px] sm:text-xs font-mono border-white/10 hover:border-cyan-500/50 hover:text-cyan-300 rounded-lg shrink-0"
                    >
                      <Square className="w-3 h-3 mr-1 text-cyan-400 shrink-0" />
                      <span>+<span className="hidden md:inline"> </span>ZONE</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => beginDraw("tripwire")}
                      className="h-7 sm:h-8 px-2 sm:px-2.5 text-[11px] sm:text-xs font-mono border-white/10 hover:border-amber-500/50 hover:text-amber-300 rounded-lg shrink-0"
                    >
                      <Crosshair className="w-3 h-3 mr-1 text-amber-400 shrink-0" />
                      <span>+<span className="hidden md:inline"> </span>TRIPWIRE</span>
                    </Button>
                  </div>

                  {(zones.length > 0 || boundaries.length > 0) && (
                    <>
                      <div className="h-4 sm:h-5 w-px bg-white/10 shrink-0 hidden sm:block" />
                      <div className="flex items-center gap-1 sm:gap-1.5 bg-black/50 border border-white/10 rounded-lg px-2 sm:px-2.5 py-0.5 sm:py-1">
                        <span className="text-[9px] sm:text-[10px] font-mono text-muted-foreground uppercase font-semibold hidden md:inline">
                          TRIGGERS:
                        </span>
                        <select
                          value={selectedTriggerId}
                          onChange={(e) => setSelectedTriggerId(e.target.value)}
                          className="bg-transparent text-[10px] sm:text-[11px] font-mono text-foreground focus:outline-none max-w-[100px] sm:max-w-[140px] truncate cursor-pointer"
                        >
                          <option value="" className="bg-black text-muted-foreground">Select trigger...</option>
                          {zones.map((z) => (
                            <option key={z.zone_id} value={z.zone_id} className="bg-black text-white">
                              [Zone] {z.name}
                            </option>
                          ))}
                          {boundaries.map((b) => (
                            <option key={b.boundary_id} value={b.boundary_id} className="bg-black text-white">
                              [Tripwire] {b.name} ({b.direction || "BIDIR"})
                            </option>
                          ))}
                        </select>
                        {selectedTriggerId && (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={handleDeleteTrigger}
                            disabled={isDeletingTrigger}
                            className="h-5 sm:h-6 px-1.5 sm:px-2 text-[9px] sm:text-[10px] font-mono bg-red-600/80 hover:bg-red-600 flex items-center gap-1 ml-0.5 sm:ml-1"
                          >
                            <Trash2 className="w-2.5 h-2.5 sm:w-3 sm:h-3" />
                            <span className="hidden sm:inline">REMOVE</span>
                          </Button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                  <input
                    type="text"
                    placeholder="Zone name..."
                    value={zoneName}
                    onChange={(e) => setZoneName(e.target.value)}
                    className="bg-black/60 border border-white/20 rounded-md px-2 py-0.5 sm:py-1 text-[11px] sm:text-xs font-mono text-foreground focus:outline-none w-24 sm:w-32"
                  />
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    className="bg-black/60 border border-white/20 rounded-md px-1.5 py-0.5 sm:py-1 text-[11px] sm:text-xs font-mono text-foreground focus:outline-none"
                  >
                    <option value="restricted">RESTRICTED</option>
                    <option value="critical">CRITICAL</option>
                    <option value="normal">NORMAL</option>
                  </select>
                  {drawMode === "tripwire" && (
                    <select
                      value={tripwireDirection}
                      onChange={(e) => setTripwireDirection(e.target.value)}
                      className="bg-black/60 border border-amber-500/40 text-amber-300 rounded-md px-1.5 py-0.5 sm:py-1 text-[11px] sm:text-xs font-mono focus:outline-none"
                      title="Select tripwire crossing trigger direction"
                    >
                      <option value="BIDIRECTIONAL">BOTH (BIDIR)</option>
                      <option value="NORTH">NORTH (UP)</option>
                      <option value="SOUTH">SOUTH (DOWN)</option>
                      <option value="EAST">EAST (RIGHT)</option>
                      <option value="WEST">WEST (LEFT)</option>
                    </select>
                  )}
                  <Button
                    size="sm"
                    onClick={handleSaveZone}
                    disabled={!canSave || isSaving}
                    className="h-7 sm:h-8 bg-emerald-600 hover:bg-emerald-500 text-[11px] sm:text-xs font-mono px-2 sm:px-3"
                  >
                    <Check className="w-3 h-3 mr-1" /> SAVE
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={cancelDraw}
                    className="h-7 sm:h-8 text-[11px] sm:text-xs font-mono text-muted-foreground hover:text-foreground px-2 sm:px-2.5"
                  >
                    <X className="w-3 h-3 mr-1" /> CANCEL
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Main Video Viewport */}
      <div
        ref={containerRef}
        onClick={handleClick}
        onMouseMove={handleMouseMove}
        className={`flex-1 relative z-10 bg-black flex items-center justify-center overflow-hidden ${
          isDrawing ? "cursor-crosshair" : isCompact ? "cursor-pointer" : "cursor-default"
        } group`}
      >
        {isCompact && (
          <div className="absolute inset-0 bg-white/0 group-hover:bg-white/5 transition-colors z-30 pointer-events-none" />
        )}
        {isSeekMode ? (
          <video
            ref={videoRef}
            src={cameraId ? `/api/cameras/${cameraId}/replay` : "/api/streaming/video/virat_cctv.mp4"}
            controls
            autoPlay
            playsInline
            onLoadedMetadata={handleReplayLoadedMetadata}
            onError={() => setStreamError(true)}
            className="max-w-full max-h-full object-contain z-10"
          />
        ) : (
          <img
            ref={imageRef}
            src={feedUrl}
            alt={cameraName}
            onLoad={() => {
              setStreamError(false);
              remeasure();
            }}
            onError={() => setStreamError(true)}
            className="max-w-full max-h-full object-contain select-none pointer-events-none"
          />
        )}

        {/* Offline / Signal Error Overlay */}
        {streamError && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/90 backdrop-blur-sm">
            <div className="p-8 max-w-md text-center flex flex-col items-center gap-3 border border-red-500/30 rounded-2xl bg-black/80 shadow-2xl">
              <div className="w-14 h-14 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center">
                <Video className="w-7 h-7 text-red-400" />
              </div>
              <h3 className="text-sm font-bold font-mono tracking-widest text-red-400 uppercase">
                {cameraId} — SIGNAL OFFLINE
              </h3>
              <p className="text-xs text-muted-foreground font-mono leading-relaxed">
                Video perception stream unavailable. Verify that the backend server is running and the camera ingest feed is reachable.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setStreamError(false);
                  if (imageRef.current) {
                    imageRef.current.src = `${feedUrl}?t=${Date.now()}`;
                  }
                }}
                className="mt-2 text-xs font-mono border-white/20 hover:border-red-400 text-white"
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> RETRY CONNECTION
              </Button>
            </div>
          </div>
        )}

        {/* Standby Overlay when camera perception is stopped */}
        {!isRunning && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/85 backdrop-blur-sm">
            <div className="p-8 max-w-md text-center flex flex-col items-center gap-3 border border-white/10 rounded-2xl bg-black/70 shadow-2xl">
              <div className="w-14 h-14 rounded-full bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center">
                <Video className="w-7 h-7 text-cyan-400" />
              </div>
              <h3 className="text-sm font-bold font-mono tracking-widest text-foreground uppercase">
                {cameraId} — STANDBY MODE
              </h3>
              <p className="text-xs text-muted-foreground font-mono leading-relaxed">
                Surveillance perception pipeline is idle. Exactly one camera actively runs real-time neural inference at a time.
              </p>
              {onToggleRun && (
                <Button
                  onClick={onToggleRun}
                  className="mt-3 bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs px-6 py-2.5 rounded-xl shadow-lg shadow-emerald-900/40 flex items-center gap-2 border border-emerald-400/40"
                >
                  <Play className="w-4 h-4 fill-current" /> START ANALYSIS
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Interactive SVG Drawing & Selection Layer */}
        {rect.ready && (
          <svg
            className="absolute z-10 overflow-visible"
            style={{
              left: `${svgLeft}px`,
              top: `${svgTop}px`,
              width: `${rect.displayWidth}px`,
              height: `${rect.displayHeight}px`,
              pointerEvents: isDrawing ? "none" : "auto",
            }}
            viewBox={`0 0 ${rect.frameWidth} ${rect.frameHeight}`}
          >
            {/* Existing Saved Zones (Click to Select / Highlight) */}
            {!isDrawing && zones.map((z) => {
              const isSel = selectedTriggerId === z.zone_id;
              const ptsStr = z.polygon
                .map((p) => {
                  const x = p[0] <= 1.0 ? p[0] * rect.frameWidth : p[0];
                  const y = p[1] <= 1.0 ? p[1] * rect.frameHeight : p[1];
                  return `${x},${y}`;
                })
                .join(" ");
              return (
                <g
                  key={z.zone_id}
                  className="cursor-pointer"
                  style={{ pointerEvents: "all" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedTriggerId(z.zone_id);
                  }}
                >
                  <polygon
                    points={ptsStr}
                    fill={isSel ? "rgba(239, 68, 68, 0.35)" : "rgba(239, 68, 68, 0.08)"}
                    stroke={isSel ? "#EF4444" : "rgba(239, 68, 68, 0.6)"}
                    strokeWidth={isSel ? "5" : "2"}
                    strokeDasharray={isSel ? "8,4" : "none"}
                    style={{ filter: isSel ? "drop-shadow(0 0 10px rgba(239,68,68,0.9))" : "none" }}
                  />
                  {isSel && z.polygon.map((p, pIdx) => {
                    const cx = p[0] <= 1.0 ? p[0] * rect.frameWidth : p[0];
                    const cy = p[1] <= 1.0 ? p[1] * rect.frameHeight : p[1];
                    return (
                      <circle
                        key={pIdx}
                        cx={cx}
                        cy={cy}
                        r="7"
                        fill="#EF4444"
                        stroke="#FFFFFF"
                        strokeWidth="2"
                      />
                    );
                  })}
                </g>
              );
            })}

            {/* Existing Saved Tripwires (Click to Select / Highlight) */}
            {!isDrawing && boundaries.map((b) => {
              const isSel = selectedTriggerId === b.boundary_id;
              const x1 = b.pt1[0] <= 1.0 ? b.pt1[0] * rect.frameWidth : b.pt1[0];
              const y1 = b.pt1[1] <= 1.0 ? b.pt1[1] * rect.frameHeight : b.pt1[1];
              const x2 = b.pt2[0] <= 1.0 ? b.pt2[0] * rect.frameWidth : b.pt2[0];
              const y2 = b.pt2[1] <= 1.0 ? b.pt2[1] * rect.frameHeight : b.pt2[1];
              const midX = (x1 + x2) / 2;
              const midY = (y1 + y2) / 2;
              return (
                <g
                  key={b.boundary_id}
                  className="cursor-pointer"
                  style={{ pointerEvents: "all" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedTriggerId(b.boundary_id);
                  }}
                >
                  <line
                    x1={x1}
                    y1={y1}
                    x2={x2}
                    y2={y2}
                    stroke={isSel ? "#EF4444" : "rgba(239, 68, 68, 0.7)"}
                    strokeWidth={isSel ? "6" : "3"}
                    strokeDasharray={isSel ? "10,5" : "none"}
                    style={{ filter: isSel ? "drop-shadow(0 0 12px rgba(239,68,68,0.95))" : "none" }}
                  />
                  <circle cx={x1} cy={y1} r="7" fill="#EF4444" stroke="#FFFFFF" strokeWidth="2" />
                  <circle cx={x2} cy={y2} r="7" fill="#EF4444" stroke="#FFFFFF" strokeWidth="2" />
                  <rect
                    x={midX - 45}
                    y={midY - 12}
                    width="90"
                    height="20"
                    rx="4"
                    fill="rgba(10, 15, 25, 0.85)"
                    stroke={isSel ? "#EF4444" : "rgba(239, 68, 68, 0.5)"}
                    strokeWidth="1"
                  />
                  <text
                    x={midX}
                    y={midY + 2}
                    textAnchor="middle"
                    fill="#EF4444"
                    fontSize="10"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {b.name || "TRIPWIRE"}
                  </text>
                </g>
              );
            })}

            {/* Draw Polygon in Progress */}
            {drawMode === "polygon" && points.length > 0 && (
              <>
                <polygon
                  points={[...points, ...(cursor ? [cursor] : [])].map((p) => `${p[0]},${p[1]}`).join(" ")}
                  fill="rgba(239, 68, 68, 0.2)"
                  stroke="#EF4444"
                  strokeWidth="3"
                  strokeDasharray="6 3"
                />
                {points.map((p, idx) => (
                  <circle key={idx} cx={p[0]} cy={p[1]} r="6" fill="#EF4444" stroke="#ffffff" strokeWidth="2" />
                ))}
              </>
            )}

            {/* Draw Tripwire in Progress */}
            {drawMode === "tripwire" && (
              <>
                {points.length === 1 && cursor && (
                  <line
                    x1={points[0][0]}
                    y1={points[0][1]}
                    x2={cursor[0]}
                    y2={cursor[1]}
                    stroke="#EF4444"
                    strokeWidth="4"
                    strokeDasharray="8 4"
                  />
                )}
                {points.length === 2 && (
                  <line
                    x1={points[0][0]}
                    y1={points[0][1]}
                    x2={points[1][0]}
                    y2={points[1][1]}
                    stroke="#EF4444"
                    strokeWidth="4"
                  />
                )}
                {points.map((p, idx) => (
                  <circle key={idx} cx={p[0]} cy={p[1]} r="7" fill="#EF4444" stroke="#ffffff" strokeWidth="2" />
                ))}
              </>
            )}

            {/* Real-time Cursor Indicator for Precise Plotting */}
            {isDrawing && cursor && (
              <g style={{ pointerEvents: "none" }}>
                <circle cx={cursor[0]} cy={cursor[1]} r="5" fill="#ffffff" stroke="#EF4444" strokeWidth="2" />
                <line x1={cursor[0] - 10} y1={cursor[1]} x2={cursor[0] + 10} y2={cursor[1]} stroke="#EF4444" strokeWidth="1.5" />
                <line x1={cursor[0]} y1={cursor[1] - 10} x2={cursor[0]} y2={cursor[1] + 10} stroke="#EF4444" strokeWidth="1.5" />
              </g>
            )}
          </svg>
        )}

        {/* Selected Trigger Inspector Card */}
        {selectedTrigger && (
          <div className="absolute bottom-4 left-4 z-30 flex items-center gap-3 bg-black/90 border border-cyan-500/50 rounded-xl px-4 py-2.5 shadow-2xl backdrop-blur-md font-mono text-xs">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              <span className="text-muted-foreground uppercase text-[10px]">SELECTED:</span>
              <span className="font-bold text-foreground">{selectedTrigger.name}</span>
              <Badge variant="outline" className="text-[9px] uppercase px-1.5 py-0 border-cyan-500/40 text-cyan-300">
                {selectedTrigger.type}
              </Badge>
              <Badge
                variant="outline"
                className={`text-[9px] uppercase px-1.5 py-0 ${
                  selectedTrigger.severity.toUpperCase() === "CRITICAL"
                    ? "border-red-500/50 text-red-400"
                    : selectedTrigger.severity.toUpperCase() === "RESTRICTED"
                    ? "border-amber-500/50 text-amber-400"
                    : "border-emerald-500/50 text-emerald-400"
                }`}
              >
                {selectedTrigger.severity}
              </Badge>
              {selectedTrigger.direction && (
                <span className="text-[10px] text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30">
                  DIR: {selectedTrigger.direction}
                </span>
              )}
            </div>
            <div className="h-4 w-px bg-white/20" />
            <div className="flex items-center gap-1.5">
              <Button
                variant="destructive"
                size="sm"
                onClick={handleDeleteTrigger}
                disabled={isDeletingTrigger}
                className="h-7 px-3 text-[11px] font-mono bg-red-600 hover:bg-red-500 flex items-center gap-1 shadow-lg shadow-red-950/50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                DELETE {selectedTrigger.type === "ZONE" ? "ZONE" : "TRIPWIRE"}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSelectedTriggerId("")}
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                title="Deselect"
              >
                <X className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        )}

        {/* Video Timeline Seek Replay Banner & Controls */}
        {isSeekMode && (
          <div className="absolute bottom-4 left-4 right-4 bg-black/85 backdrop-blur-xl border border-white/15 rounded-xl p-3 shadow-2xl z-30">
            <div className="flex items-center justify-between gap-4 mb-2">
              <div className="flex items-center gap-2 text-xs font-mono text-cyan-300">
                <Clock className="w-4 h-4 text-cyan-400" />
                <span>INCIDENT REPLAY: {String(selectedAlertTime)}</span>
                <span className="text-muted-foreground text-[11px]">
                  ({seekOffsetSec >= 0 ? `+${seekOffsetSec}` : seekOffsetSec}s)
                </span>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSeekOffsetSec(-5)}
                  className="h-7 text-[11px] font-mono border-white/10"
                >
                  -5s
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSeekOffsetSec(0)}
                  className="h-7 text-[11px] font-mono border-cyan-500/40 text-cyan-300"
                >
                  EVENT (0s)
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setSeekOffsetSec(5)}
                  className="h-7 text-[11px] font-mono border-white/10"
                >
                  +5s
                </Button>
                <Button
                  size="sm"
                  onClick={onExitSeek}
                  className="h-7 text-[11px] font-mono bg-emerald-600 hover:bg-emerald-500 ml-2"
                >
                  RETURN TO LIVE
                </Button>
              </div>
            </div>

            {/* Seeking Scrubber Range Slider */}
            <input
              type="range"
              min="-10"
              max="10"
              step="0.5"
              value={seekOffsetSec}
              onChange={(e) => setSeekOffsetSec(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-white/20 rounded-lg appearance-none cursor-pointer accent-primary"
            />
          </div>
        )}
      </div>
    </div>
  );
}
