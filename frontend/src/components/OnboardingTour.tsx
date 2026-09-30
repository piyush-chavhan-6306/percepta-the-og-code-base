import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Shield,
  Compass,
  Grid,
  Video,
  Play,
  Layers,
  Activity,
  AlertTriangle,
  Flame,
  FileCheck,
  Bot,
  Gauge,
  Route,
  EyeOff,
  UserCheck,
  ChevronRight,
  ChevronLeft,
  X,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export interface OnboardingTourProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete: () => void;
  userId?: string;
}

interface TourStep {
  title: string;
  badge: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
  technicalNote: string;
  targetFocus: string;
}

const TOUR_STEPS: TourStep[] = [
  {
    title: "1. Navigation & System Header",
    badge: "COMMAND & CONTROL",
    icon: Compass,
    description: "The top command bar provides instantaneous visibility into system status, active operator identity, threat counters, and rapid switching between tactical views.",
    technicalNote: "Synchronized with local and cloud telemetry via high-frequency health heartbeats.",
    targetFocus: "Header navigation & status indicators",
  },
  {
    title: "2. Tactical Camera Grid",
    badge: "MULTI-FEED MONITORING",
    icon: Grid,
    description: "Switch seamlessly between 1×1 single inspection view, 2×2 tactical quad-view, and 3×3 high-density sector monitoring layouts.",
    technicalNote: "Dynamic CSS Grid with low-latency WebGL hardware acceleration.",
    targetFocus: "Grid layout buttons (1×1, 2×2, 3×3)",
  },
  {
    title: "3. Live Camera Feed",
    badge: "VIDEO INGESTION",
    icon: Video,
    description: "Real-time surveillance streaming with multi-spectral support (Optical RGB, Night Vision IR, and Thermal). Automatically scales to network and hardware conditions.",
    technicalNote: "Delivered via low-latency partial HTTP/206 streaming and MJPEG hardware pipe.",
    targetFocus: "Primary video viewport",
  },
  {
    title: "4. Perception Engine & Analysis",
    badge: "AI INFERENCE",
    icon: Play,
    description: "Activate or halt the local YOLOv8 neural detection engine and ByteTrack tracker at will. When active, objects are detected and tracked across consecutive frames.",
    technicalNote: "Decoupled background worker maintaining 45+ FPS with zero UI blocking.",
    targetFocus: "START / STOP PERCEPTION button",
  },
  {
    title: "5. Security Zones & Geofencing",
    badge: "PERIMETER DEFENCE",
    icon: Layers,
    description: "Draw arbitrary polygonal security perimeters directly on top of camera feeds. Tracks entering unauthorized or restricted zones trigger instant alarms.",
    technicalNote: "Ray-casting point-in-polygon math running directly inside the inference worker.",
    targetFocus: "Polygon zone drawing tools",
  },
  {
    title: "6. Virtual Tripwires",
    badge: "INTRUSION DETECTION",
    icon: Activity,
    description: "Configure directional tripwires across fence lines and border checkpoints. Differentiates between friendly patrols and inbound unauthorized crossings.",
    technicalNote: "Line-intersection trajectory calculations with velocity vector verification.",
    targetFocus: "Tripwire configuration tools",
  },
  {
    title: "7. Real-Time Tactical Alerts",
    badge: "EVENT LOG",
    icon: AlertTriangle,
    description: "Instantaneous stream of categorized alert events: Zone Intrusion, Tripwire Cross, Loitering, Weapon Detection, and Optical Occlusion.",
    technicalNote: "Persisted to WAL SQLite database with nanosecond sequence identifiers.",
    targetFocus: "Tactical Alert Feed panel",
  },
  {
    title: "8. Correlated Active Incidents",
    badge: "INCIDENT LIFECYCLE",
    icon: Flame,
    description: "High-level incidents aggregate multiple correlated alerts over time into a unified tactical response case with automated threat severity classification.",
    technicalNote: "Stateful IncidentEngine manages opened, acknowledged, and resolved lifecycles.",
    targetFocus: "Active Incidents accordion and list",
  },
  {
    title: "9. Authoritative Threat Gauge",
    badge: "THREAT COMPUTATION",
    icon: Flame,
    description: "Authoritative composite threat score calculation. Automatically classifies conditions into CRITICAL (Score ≥ 60), RESTRICTED (Score ≥ 25), and NORMAL (Score < 25).",
    technicalNote: "Continuous threat scoring taking into account track proximity, velocity, and armed status.",
    targetFocus: "Threat Level Gauge meter",
  },
  {
    title: "10. Evidence Inspector & Replay",
    badge: "FORENSIC INTEGRITY",
    icon: FileCheck,
    description: "Review cryptographically hashed video clips and target crops captured during incidents. Click 'PLAY EVIDENCE' for frame-accurate playback.",
    technicalNote: "SHA-256 HMAC cryptographic chain protects chain-of-custody admissibility.",
    targetFocus: "Evidence Inspector drawer & Replay controller",
  },
  {
    title: "11. Grounded AI Defence Copilot",
    badge: "TACTICAL ASSISTANT",
    icon: Bot,
    description: "Ask natural language questions about active incidents, intruder counts, camera uptime, and recommended tactical response protocols.",
    technicalNote: "Grounded strictly in local incident logs and camera telemetry — zero hallucinations.",
    targetFocus: "AI Assistant floating bar",
  },
  {
    title: "12. Camera Trust & Tamper Sensor",
    badge: "HARDWARE AUDIT",
    icon: Gauge,
    description: "Real-time auditing of camera stream integrity. Detects physical lens covering, spray paint tampering, defocusing, and signal degradation.",
    technicalNote: "Laplacian blur variance and histogram difference analysis on raw frames.",
    targetFocus: "Camera Trust Sensor panel",
  },
  {
    title: "13. PathGuard Trajectory Forecast",
    badge: "PREDICTIVE TRACKING",
    icon: Route,
    description: "Projects future movement paths of tracked targets based on historical velocity vectors and terrain constraints, highlighting imminent boundary breaches.",
    technicalNote: "Kalman filter extrapolation with multi-hypothesis heading estimation.",
    targetFocus: "PathGuard prediction overlays",
  },
  {
    title: "14. Predicted Blind Spots",
    badge: "COVERAGE MAPPING",
    icon: EyeOff,
    description: "Identifies dead zones and terrain shadows between camera fields of view, guiding operators to adjust camera angles or deploy ground patrols.",
    technicalNote: "Geometric ray-tracing across sector terrain boundaries.",
    targetFocus: "Blind spot analysis card",
  },
  {
    title: "15. Officer Profile & Clearance",
    badge: "OPERATOR IDENTITY",
    icon: UserCheck,
    description: "Access your personalized duty dossier, military rank, regiment unit, division, and official communication channels. Data is completely isolated per user.",
    technicalNote: "Strict tenant isolation: User A and User B maintain separate databases & settings.",
    targetFocus: "Officer Profile button & settings modal",
  },
];

export const OnboardingTour: React.FC<OnboardingTourProps> = ({
  isOpen,
  onClose,
  onComplete,
  userId = "usr_operator",
}) => {
  const [currentStep, setCurrentStep] = useState(0);

  if (!isOpen) return null;

  const step = TOUR_STEPS[currentStep];
  const StepIcon = step.icon;
  const isFirst = currentStep === 0;
  const isLast = currentStep === TOUR_STEPS.length - 1;

  const handleNext = () => {
    if (isLast) {
      handleFinish();
    } else {
      setCurrentStep((prev) => prev + 1);
    }
  };

  const handlePrev = () => {
    if (!isFirst) {
      setCurrentStep((prev) => prev - 1);
    }
  };

  const handleFinish = async () => {
    try {
      await fetch("/api/user/onboarding/complete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Id": userId,
        },
      });
    } catch (e) {
      console.warn("Failed to persist onboarding completion:", e);
    }
    onComplete();
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 15 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 15 }}
          transition={{ duration: 0.25 }}
          className="relative w-full max-w-2xl bg-zinc-950 border border-emerald-500/40 rounded-xl shadow-2xl overflow-hidden text-zinc-100"
        >
          {/* Header Bar */}
          <div className="flex items-center justify-between px-6 py-4 bg-zinc-900/90 border-b border-zinc-800">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold tracking-wider text-emerald-400 uppercase">
                    PERCEPTA DEFENSE
                  </h3>
                  <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-300">
                    SYSTEM ORIENTATION
                  </Badge>
                </div>
                <p className="text-xs text-zinc-400">
                  Step {currentStep + 1} of {TOUR_STEPS.length}: {step.badge}
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-800 transition"
              title="Close tour"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Progress Bar */}
          <div className="w-full bg-zinc-900 h-1">
            <div
              className="bg-emerald-500 h-1 transition-all duration-300 ease-out"
              style={{ width: `${((currentStep + 1) / TOUR_STEPS.length) * 100}%` }}
            />
          </div>

          {/* Step Body */}
          <div className="p-6 space-y-6">
            <div className="flex items-start gap-4">
              <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shrink-0">
                <StepIcon className="w-8 h-8" />
              </div>
              <div className="space-y-1.5 flex-1">
                <h4 className="text-lg font-bold text-white tracking-wide">
                  {step.title}
                </h4>
                <p className="text-xs font-mono uppercase text-emerald-400/90">
                  Target Component: {step.targetFocus}
                </p>
                <p className="text-sm text-zinc-300 leading-relaxed pt-1">
                  {step.description}
                </p>
              </div>
            </div>

            {/* Tactical Technical Note Callout */}
            <div className="p-3.5 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-400 flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-zinc-300">Operational Architecture: </span>
                {step.technicalNote}
              </div>
            </div>

            {/* Step navigation dots */}
            <div className="flex items-center justify-center gap-1.5 pt-2">
              {TOUR_STEPS.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => setCurrentStep(idx)}
                  className={`h-1.5 rounded-full transition-all ${
                    idx === currentStep
                      ? "w-6 bg-emerald-400"
                      : idx < currentStep
                      ? "w-2 bg-emerald-800 hover:bg-emerald-600"
                      : "w-2 bg-zinc-800 hover:bg-zinc-700"
                  }`}
                  title={`Jump to step ${idx + 1}`}
                />
              ))}
            </div>
          </div>

          {/* Footer Controls */}
          <div className="flex items-center justify-between px-6 py-4 bg-zinc-900/60 border-t border-zinc-800">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrev}
              disabled={isFirst}
              className="border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Previous
            </Button>

            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={handleFinish}
                className="text-xs text-zinc-400 hover:text-white"
              >
                Skip Tour
              </Button>

              <Button
                size="sm"
                onClick={handleNext}
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold shadow-lg shadow-emerald-900/40"
              >
                {isLast ? "Complete Orientation" : "Next Step"}
                {!isLast && <ChevronRight className="w-4 h-4 ml-1" />}
              </Button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
