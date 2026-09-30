import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PerceptaLogo } from "@/features/shared/components/PerceptaLogo";
import {
  Plus,
  Video,
  Moon,
  Flame,
  ChevronLeft,
  RefreshCw,
  Radio,
  Trash2,
  User,
  Compass,
} from "lucide-react";
import { CameraFeed } from "@/components/CameraFeed";
import { AlertPanel } from "@/components/AlertPanel";
import { AlertInspector } from "@/components/AlertInspector";
import { AIAssistantBar } from "@/components/AIAssistantBar";
import { PremiumCard } from "@/components/PremiumCard";
import { AddCameraModal } from "@/components/AddCameraModal";
import { ThreatGauge } from "@/components/ThreatGauge";
import { PremiumBackground } from "@/components/PremiumBackground";
import { StatusBar } from "@/components/StatusBar";
import { OfficerProfileModal } from "@/components/OfficerProfileModal";
import { OnboardingTour } from "@/components/OnboardingTour";
import { api } from "@/api/client";
import { useWebSocket, type WsMessage } from "@/hooks/useWebSocket";
import type { AlertItem, CameraRecord } from "@/types/surveillance";

export default function Dashboard() {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState<CameraRecord[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>("CAM-01");
  const [gridLayout, setGridLayout] = useState<"1x1" | "2x2" | "3x3">("1x1");
  const [showProfile, setShowProfile] = useState<boolean>(false);
  const [showTour, setShowTour] = useState<boolean>(false);
  const [activeUserId, setActiveUserId] = useState<string>("usr_operator");
  const [activeAlertCount, setActiveAlertCount] = useState<number>(0);
  const [threatData, setThreatData] = useState<{ score: number; level: string }>({
    score: 0,
    level: "NORMAL",
  });
  const [selectedAlert, setSelectedAlert] = useState<AlertItem | null>(null);
  const [selectedAlertTime, setSelectedAlertTime] = useState<string | number | null>(null);
  const [showAddCamera, setShowAddCamera] = useState(false);
  const [loading, setLoading] = useState(true);

  // Per-User Onboarding Tour Verification
  useEffect(() => {
    api
      .getUserProfile()
      .then((res) => {
        if (res?.profile) {
          setActiveUserId(res.profile.id);
          if (res.profile.onboarding_completed === false) {
            setShowTour(true);
          }
        }
      })
      .catch((err) => {
        console.warn("Failed to check onboarding status:", err);
      });
  }, []);

  const fetchCameras = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.getCameras();
      if (res.cameras && res.cameras.length > 0) {
        setCameras(res.cameras);
        if (!res.cameras.some((c) => c.camera_id === selectedCameraId)) {
          setSelectedCameraId(res.cameras[0].camera_id);
        }
      } else {
        setCameras([
          {
            camera_id: "CAM-01",
            name: "Border Post Alpha",
            source_type: "video_file",
            modality: "STANDARD",
            camera_type: "RGB",
            is_running: true,
          },
        ]);
      }
    } catch (err) {
      console.error("Failed to fetch cameras:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedCameraId]);

  const fetchThreatLevel = useCallback(async () => {
    try {
      const res = await api.getThreatLevel(selectedCameraId);
      const rawLevel = String((res as any).threat_level || (res as any).level || "NORMAL").toUpperCase();
      let normLevel = "NORMAL";
      if (rawLevel === "DEFCON_RED" || rawLevel === "CRITICAL" || rawLevel === "RED") normLevel = "CRITICAL";
      else if (rawLevel === "DEFCON_ORANGE" || rawLevel === "RESTRICTED" || rawLevel === "HIGH" || rawLevel === "ORANGE") normLevel = "RESTRICTED";
      else if (rawLevel === "DEFCON_YELLOW" || rawLevel === "ELEVATED" || rawLevel === "MODERATE" || rawLevel === "YELLOW") normLevel = "ELEVATED";
      else normLevel = "NORMAL";

      const score = Math.round(Number((res as any).threat_score ?? (res as any).score ?? 0));
      setThreatData({
        score,
        level: normLevel,
      });

      // Synchronize active incident count for live status bar
      try {
        const incRes = await api.getIncidents({ camera_id: selectedCameraId, status: "ACTIVE", limit: 50 });
        if (incRes?.incidents) {
          setActiveAlertCount(incRes.incidents.length);
        }
      } catch {}
    } catch (err) {
      console.error("Failed to fetch threat level:", err);
    }
  }, [selectedCameraId]);

  // Real-time WebSocket triggers instantaneous threat recalculation
  useWebSocket((msg: WsMessage) => {
    const et = (msg.event_type || (msg as any).type) as string;
    if (
      et === "ALERT" ||
      et === "alert" ||
      et === "INCIDENT" ||
      et === "incident" ||
      et === "ZONE" ||
      et === "zone" ||
      et === "RISK" ||
      et === "SYSTEM"
    ) {
      fetchThreatLevel();
    }
  });

  useEffect(() => {
    fetchCameras();
    fetchThreatLevel();
    const interval = setInterval(fetchThreatLevel, 3000);
    return () => clearInterval(interval);
  }, [fetchCameras, fetchThreatLevel]);

  const activeCamera = cameras.find((c) => c.camera_id === selectedCameraId) || cameras[0];

  const handleDeleteCamera = async (cameraId: string) => {
    try {
      await api.deleteCamera(cameraId);
      const updated = cameras.filter((c) => c.camera_id !== cameraId);
      setCameras(updated);
      if (selectedCameraId === cameraId && updated.length > 0) {
        setSelectedCameraId(updated[0].camera_id);
      }
    } catch (err) {
      console.error("Failed to remove camera:", err);
    }
  };

  const handleToggleRunCamera = async (camId: string) => {
    const target = cameras.find((c) => c.camera_id === camId);
    if (!target) return;
    try {
      if (target.is_running) {
        await api.stopCamera(target.camera_id);
      } else {
        await api.startCamera(target.camera_id);
      }
      await fetchCameras();
    } catch (err) {
      console.error("Failed to toggle camera analysis:", err);
    }
  };

  const handleSeekTime = (timestamp: string | number, cameraId?: string) => {
    if (cameraId && cameraId !== selectedCameraId) {
      setSelectedCameraId(cameraId);
    }
    setSelectedAlertTime(timestamp);
  };

  const handleExitSeek = () => setSelectedAlertTime(null);

  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      await api.acknowledgeAlert(alertId);
      if (selectedAlert?.event_id === alertId || selectedAlert?.alert_id === alertId) {
        setSelectedAlert((prev) => (prev ? { ...prev, is_acknowledged: true } : null));
      }
    } catch (err) {
      console.error("Failed to acknowledge alert:", err);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans selection:bg-primary/30 relative overflow-hidden">
      {/* Animated background permanently visible */}
      <PremiumBackground />

      {/* ═══ HEADER — Premium Glass ═══ */}
      <header className="sticky top-0 z-40 relative">
        {/* Gradient accent line at top */}
        <div className="h-[2px] w-full bg-gradient-to-r from-transparent via-primary/60 to-transparent" />

        <div className="glass-panel border-b border-white/[0.06] px-5 py-3">
          <div className="max-w-[1920px] mx-auto flex items-center justify-between">
            {/* Left: Navigation + Brand */}
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate("/")}
                className="text-muted-foreground hover:text-foreground font-mono text-xs flex items-center gap-1 -ml-2 h-8"
              >
                <ChevronLeft className="w-4 h-4" />
                <span>PORTAL</span>
              </Button>

              <div className="h-5 w-px bg-white/10" />

              <div
                onClick={() => navigate("/")}
                className="cursor-pointer flex items-center transition-opacity hover:opacity-90"
                title="Return to Recon Portal"
              >
                <PerceptaLogo size={30} showText={true} />
              </div>
            </div>

            {/* Center: Threat Gauge */}
            <ThreatGauge score={threatData.score} level={threatData.level} />

            {/* Right: Actions */}
            <div className="flex items-center gap-2.5">
              <Button
                size="sm"
                onClick={() => setShowAddCamera(true)}
                className="h-9 bg-primary hover:bg-primary/90 text-primary-foreground font-mono text-xs flex items-center gap-1.5 shadow-lg shadow-primary/20 border-0"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>ADD CAMERA</span>
              </Button>

              <Button
                variant="outline"
                size="icon"
                onClick={() => {
                  fetchCameras();
                  fetchThreatLevel();
                }}
                className="h-8 w-8 text-muted-foreground hover:text-foreground border-white/10"
                title="Refresh"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
              </Button>

              <div className="h-5 w-px bg-white/10 hidden sm:block" />

              {/* Active Operator Dossier */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowProfile(true)}
                className="text-xs font-mono flex items-center gap-1.5 text-muted-foreground hover:text-primary h-8 px-2.5 bg-white/[0.03] border border-white/5 cursor-pointer relative z-30"
                title="Operator Dossier & Clearance Profile"
              >
                <User className="w-3.5 h-3.5 text-primary" />
                <span className="hidden md:inline text-[11px]">OFFICER DOSSIER</span>
                <Badge variant="outline" className="text-[8px] px-1 py-0 border-primary/40 text-primary font-mono ml-0.5">
                  DEFCON-2
                </Badge>
              </Button>

              {/* System Orientation Tour */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowTour(true)}
                className="text-xs font-mono flex items-center gap-1.5 text-muted-foreground hover:text-emerald-400 h-8 px-2.5 bg-white/[0.03] border border-white/5 cursor-pointer relative z-30"
                title="Take System Orientation Tour"
              >
                <Compass className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden lg:inline text-[11px]">TOUR</span>
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* ═══ MAIN WORKSPACE ═══ */}
      <main className="flex-1 p-4 grid grid-cols-1 xl:grid-cols-12 gap-4 max-w-[1920px] mx-auto w-full relative z-10">
        {/* LEFT: Camera + AI (8 cols) */}
        <div className="xl:col-span-8 flex flex-col gap-4">
          {/* Camera Selector Bar */}
          <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none px-1">
            {cameras.map((cam) => {
              const isSelected = cam.camera_id === selectedCameraId;
              const typeStr = (cam.camera_type || (cam.modality === "IR_NIGHT" ? "IR" : cam.modality === "THERMAL" ? "THERMAL" : "RGB")).toUpperCase();
              const isIR = typeStr === "IR" || cam.modality === "IR_NIGHT";
              const isThermal = typeStr === "THERMAL" || cam.modality === "THERMAL";

              return (
                <div key={cam.camera_id} className="relative flex items-center">
                  <PremiumCard
                    tilt={6}
                    lift={isSelected ? 1.04 : 1.01}
                    glare={isSelected}
                    glowColor={isThermal ? "rgba(244, 63, 94, 0.2)" : isIR ? "rgba(34, 197, 94, 0.2)" : "rgba(0, 229, 255, 0.15)"}
                    depth={isSelected ? 3 : 1}
                  >
                    <div className="flex items-center">
                      <button
                        onClick={() => {
                          setSelectedCameraId(cam.camera_id);
                          setSelectedAlertTime(null);
                        }}
                        className={`px-3.5 py-2 rounded-xl text-xs font-mono border-0 flex items-center gap-2.5 transition-all duration-300 shrink-0 relative ${
                          isSelected
                            ? "bg-primary/15 text-foreground"
                            : "bg-transparent text-muted-foreground hover:text-foreground hover:bg-white/[0.04]"
                        }`}
                      >
                        <span
                          className={`w-2 h-2 rounded-full ${
                            cam.is_running ? "bg-emerald-500" : "bg-gray-500"
                          }`}
                          style={{
                            boxShadow: cam.is_running
                              ? "0 0 8px rgba(34,197,94,0.5)"
                              : "none",
                          }}
                        />

                        {/* Visual indicator by Camera Type */}
                        <div
                          className={`p-1 rounded flex items-center justify-center transition-all ${
                            isThermal
                              ? "border border-dashed border-rose-500/70 bg-rose-500/10 text-rose-400"
                              : isIR
                              ? "border border-dashed border-emerald-500/70 bg-emerald-500/10 text-emerald-400"
                              : "border border-cyan-500/30 bg-cyan-500/10 text-cyan-400"
                          }`}
                          title={`Sensor Modality: ${isThermal ? "Thermal Radiometry" : isIR ? "IR Night Vision" : "Optical RGB"}`}
                        >
                          {isThermal ? (
                            <Flame className="w-3 h-3 text-rose-400" />
                          ) : isIR ? (
                            <Moon className="w-3 h-3 text-emerald-400" />
                          ) : (
                            <Video className="w-3 h-3 text-cyan-400" />
                          )}
                        </div>

                        <div className="text-left">
                          <div className="font-bold flex items-center gap-1.5">
                            <span>{cam.camera_id}</span>
                            <span
                              className={`text-[8px] font-mono px-1 py-0.2 rounded border ${
                                isThermal
                                  ? "border-dashed border-rose-500/60 text-rose-400 bg-rose-500/10"
                                  : isIR
                                  ? "border-dashed border-emerald-500/60 text-emerald-400 bg-emerald-500/10"
                                  : "border-cyan-500/30 text-cyan-400 bg-cyan-500/10"
                              }`}
                            >
                              {isThermal ? "THERMAL" : isIR ? "IR" : "RGB"}
                            </span>
                          </div>
                          <div className="text-[10px] text-muted-foreground/70 truncate max-w-[130px]">
                            {cam.name}
                          </div>
                        </div>

                        {/* Active indicator bar */}
                        {isSelected && (
                          <motion.div
                            layoutId="cameraIndicator"
                            className="absolute bottom-0 left-2 right-2 h-[2px] bg-primary rounded-full"
                            style={{ boxShadow: "0 0 12px rgba(0,229,255,0.5)" }}
                            transition={{ type: "spring", stiffness: 400, damping: 30 }}
                          />
                        )}
                      </button>

                      {cameras.length > 1 && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteCamera(cam.camera_id);
                          }}
                          className="mr-2 p-1 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title={`Remove ${cam.camera_id}`}
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </PremiumCard>
                </div>
              );
            })}
          </div>

          {/* Camera Feed Area — Dynamic Grid Layout (1x1, 2x2, 3x3) */}
          <PremiumCard tilt={gridLayout === "1x1" ? 2 : 0} glare={false} depth={3}>
            {gridLayout === "1x1" ? (
              <div className="h-[530px] w-full relative">
                {/* Corner brackets */}
                <div className="absolute top-2 left-2 w-5 h-5 border-t-2 border-l-2 border-primary/40 rounded-tl-lg z-20 pointer-events-none" />
                <div className="absolute top-2 right-2 w-5 h-5 border-t-2 border-r-2 border-primary/40 rounded-tr-lg z-20 pointer-events-none" />
                <div className="absolute bottom-2 left-2 w-5 h-5 border-b-2 border-l-2 border-primary/40 rounded-bl-lg z-20 pointer-events-none" />
                <div className="absolute bottom-2 right-2 w-5 h-5 border-b-2 border-r-2 border-primary/40 rounded-br-lg z-20 pointer-events-none" />

                {activeCamera ? (
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={selectedCameraId}
                      initial={{ opacity: 0.85, scale: 0.998 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0.85, scale: 0.998 }}
                      transition={{ duration: 0.2 }}
                      className="h-full"
                    >
                      <CameraFeed
                        cameraId={activeCamera.camera_id}
                        cameraName={activeCamera.name}
                        modality={activeCamera.modality || "STANDARD"}
                        selectedAlertTime={selectedAlertTime}
                        isRunning={activeCamera.is_running}
                        gridLayout={gridLayout}
                        onLayoutChange={setGridLayout}
                        onToggleRun={() => handleToggleRunCamera(activeCamera.camera_id)}
                        onExitSeek={handleExitSeek}
                        onZoneCreated={fetchCameras}
                      />
                    </motion.div>
                  </AnimatePresence>
                ) : (
                  <div className="h-full flex items-center justify-center bg-black/40 rounded-xl">
                    <div className="text-center">
                      <Radio className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
                      <p className="text-sm font-mono text-muted-foreground">No active camera stream</p>
                      <p className="text-[10px] font-mono text-muted-foreground/50 mt-1">
                        Add a camera feed to begin surveillance
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ) : gridLayout === "2x2" ? (
              <div className="p-3">
                <div className="grid grid-cols-2 gap-3 min-h-[580px]">
                  {[0, 1, 2, 3].map((slotIdx) => {
                    const cam = cameras[slotIdx];
                    if (cam) {
                      return (
                        <div
                          key={cam.camera_id}
                          className="h-[290px] relative rounded-xl overflow-hidden border border-white/10 bg-black/60 shadow-lg"
                        >
                          <CameraFeed
                            cameraId={cam.camera_id}
                            cameraName={cam.name}
                            modality={cam.modality || "STANDARD"}
                            selectedAlertTime={cam.camera_id === selectedCameraId ? selectedAlertTime : null}
                            isRunning={cam.is_running}
                            gridLayout={gridLayout}
                            onLayoutChange={setGridLayout}
                            onToggleRun={() => handleToggleRunCamera(cam.camera_id)}
                            onExitSeek={handleExitSeek}
                            onZoneCreated={fetchCameras}
                            onFeedClick={() => {
                              setSelectedCameraId(cam.camera_id);
                              setSelectedAlertTime(null);
                              setGridLayout("1x1");
                            }}
                          />
                        </div>
                      );
                    }
                    return (
                      <div
                        key={`standby-2x2-${slotIdx}`}
                        className="h-[290px] relative rounded-xl border border-dashed border-white/10 bg-black/30 flex flex-col items-center justify-center text-center p-4"
                      >
                        <Radio className="w-7 h-7 text-muted-foreground/25 mb-2 animate-pulse" />
                        <p className="text-[11px] font-mono font-bold tracking-wider text-muted-foreground/70 uppercase">
                          SLOT {slotIdx + 1} // SENSOR STANDBY
                        </p>
                        <p className="text-[9px] font-mono text-muted-foreground/40 mt-0.5">
                          Unassigned Sector Channel
                        </p>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setShowAddCamera(true)}
                          className="mt-3 text-[10px] font-mono h-7 border-white/10 hover:border-primary/40 text-muted-foreground hover:text-foreground"
                        >
                          <Plus className="w-3 h-3 mr-1" /> CONNECT FEED
                        </Button>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="p-3">
                <div className="grid grid-cols-3 gap-2.5 min-h-[640px]">
                  {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((slotIdx) => {
                    const cam = cameras[slotIdx];
                    if (cam) {
                      return (
                        <div
                          key={cam.camera_id}
                          className="h-[210px] relative rounded-xl overflow-hidden border border-white/10 bg-black/60 shadow-md"
                        >
                          <CameraFeed
                            cameraId={cam.camera_id}
                            cameraName={cam.name}
                            modality={cam.modality || "STANDARD"}
                            selectedAlertTime={cam.camera_id === selectedCameraId ? selectedAlertTime : null}
                            isRunning={cam.is_running}
                            gridLayout={gridLayout}
                            onLayoutChange={setGridLayout}
                            onToggleRun={() => handleToggleRunCamera(cam.camera_id)}
                            onExitSeek={handleExitSeek}
                            onZoneCreated={fetchCameras}
                            onFeedClick={() => {
                              setSelectedCameraId(cam.camera_id);
                              setSelectedAlertTime(null);
                              setGridLayout("1x1");
                            }}
                          />
                        </div>
                      );
                    }
                    return (
                      <div
                        key={`standby-3x3-${slotIdx}`}
                        className="h-[210px] relative rounded-xl border border-dashed border-white/10 bg-black/30 flex flex-col items-center justify-center text-center p-2"
                      >
                        <Radio className="w-5 h-5 text-muted-foreground/20 mb-1" />
                        <p className="text-[10px] font-mono font-bold text-muted-foreground/60 uppercase">
                          CH-0{slotIdx + 1} STANDBY
                        </p>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setShowAddCamera(true)}
                          className="mt-1 text-[9px] font-mono h-6 px-2 text-muted-foreground hover:text-primary"
                        >
                          <Plus className="w-2.5 h-2.5 mr-0.5" /> ADD
                        </Button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </PremiumCard>

          {/* AI Copilot — Premium Glass */}
          <PremiumCard tilt={2} glare={true} depth={2} glowColor="rgba(139, 92, 246, 0.12)">
            <AIAssistantBar selectedCameraId={selectedCameraId} />
          </PremiumCard>
        </div>

        {/* RIGHT: Alerts (4 cols) */}
        <div className="xl:col-span-4 h-[calc(100vh-100px)] sticky top-20 flex flex-col min-h-0">
          <PremiumCard tilt={2} glare={true} depth={3} className="h-full flex flex-col min-h-0">
            <AlertPanel
              selectedCameraId={selectedCameraId}
              onSelectAlert={(alert) => setSelectedAlert(alert)}
              selectedAlertId={selectedAlert?.event_id || selectedAlert?.alert_id}
              onSeekTime={handleSeekTime}
            />
          </PremiumCard>
        </div>
      </main>

      {/* ═══ STATUS BAR ═══ */}
      <StatusBar
        cameraCount={cameras.length}
        alertCount={activeAlertCount}
        threatLevel={threatData.level}
      />

      {/* ═══ MODALS ═══ */}
      {selectedAlert && (
        <AlertInspector
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
          onAcknowledge={handleAcknowledgeAlert}
          onSeekTime={handleSeekTime}
        />
      )}

      {showAddCamera && (
        <AddCameraModal
          onClose={() => setShowAddCamera(false)}
          onCameraAdded={() => {
            fetchCameras();
            setShowAddCamera(false);
          }}
        />
      )}

      {showProfile && (
        <OfficerProfileModal
          isOpen={showProfile}
          onClose={() => setShowProfile(false)}
          onRetakeTour={() => setShowTour(true)}
        />
      )}

      {/* ═══ ONBOARDING TOUR ═══ */}
      <OnboardingTour
        isOpen={showTour}
        userId={activeUserId}
        onClose={() => setShowTour(false)}
        onComplete={() => setShowTour(false)}
      />
    </div>
  );
}

