import React, { useEffect, useState, useRef, useCallback } from "react";
import { Volume2, VolumeX } from "lucide-react";
import c2AudioTrack from "@/assets/c2-loader.mp3";

export interface C2LoaderProps {
  onComplete?: () => void;
  minDuration?: number; // ms
}

const SECURITY_PHASES = [
  "INITIALIZING SECURE C2 ENCLAVE...",
  "AUTHENTICATING SENSOR MESH...",
  "VERIFYING BIOMETRIC CLEARANCE...",
  "SYNCHRONIZING APERTURE RECON...",
  "C2 RECON ENVIRONMENT UNLOCKED",
];

export const C2Loader: React.FC<C2LoaderProps> = ({
  onComplete,
  minDuration = 1000,
}) => {
  const [percent, setPercent] = useState(0);
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [isDone, setIsDone] = useState(false);
  const [shouldRender, setShouldRender] = useState(() => {
    return !sessionStorage.getItem("percepta_c2_intro_seen");
  });
  const [muted, setMuted] = useState(false);
  const prevPhaseIndex = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Circle dimensions
  const radius = 135;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percent / 100) * circumference;

  const handleFinish = useCallback(() => {
    setIsDone(true);
    sessionStorage.setItem("percepta_c2_intro_seen", "true");
    setTimeout(() => {
      setShouldRender(false);
      onComplete?.();
    }, 450);
  }, [onComplete]);

  useEffect(() => {
    if (!shouldRender) {
      onComplete?.();
      return;
    }

    // Audio setup with local bundled track priority
    const audioSource = c2AudioTrack || "/c2-loader.mp3";
    const audioEl = new Audio(audioSource);
    audioEl.volume = 0.9;
    audioEl.preload = "auto";
    audioRef.current = audioEl;

    audioEl.play().catch(() => {});

    const handleKeyDismiss = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
        handleFinish();
      }
    };
    window.addEventListener("keydown", handleKeyDismiss);

    const startTime = performance.now();

    const interval = setInterval(() => {
      const elapsed = performance.now() - startTime;
      const progress = Math.min(100, Math.floor((elapsed / minDuration) * 100));
      setPercent(progress);

      const step = Math.min(
        SECURITY_PHASES.length - 1,
        Math.floor((elapsed / minDuration) * SECURITY_PHASES.length)
      );
      if (step !== prevPhaseIndex.current) {
        prevPhaseIndex.current = step;
        setPhaseIndex(step);
      }

      if (progress >= 100) {
        clearInterval(interval);
        handleFinish();
      }
    }, 20);

    return () => {
      clearInterval(interval);
      if (audioRef.current) {
        audioRef.current.pause();
      }
      window.removeEventListener("keydown", handleKeyDismiss);
    };
  }, [minDuration, onComplete, shouldRender, handleFinish]);

  const toggleSound = (e?: React.MouseEvent) => {
    e?.stopPropagation();
    const nextMuted = !muted;
    setMuted(nextMuted);

    if (audioRef.current) {
      audioRef.current.muted = nextMuted;
      if (!nextMuted) {
        audioRef.current.currentTime = 0;
        audioRef.current.play().catch(() => {});
      }
    }
  };

  if (!shouldRender) return null;

  return (
    <div
      className={`fixed inset-0 z-[99999] flex flex-col items-center justify-center bg-[#07090b] transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] select-none overflow-hidden ${
        isDone ? "opacity-0 scale-[1.03] pointer-events-none" : "opacity-100 scale-100"
      }`}
      style={{
        backgroundImage:
          "radial-gradient(circle at 50% 50%, rgba(12, 18, 22, 0.65) 0%, #050709 85%)",
      }}
      data-testid="c2-loader"
    >
      {/* ── Top Security Header & Instant Skip Button ────────────────────────── */}
      <div className="absolute top-8 left-0 right-0 px-6 sm:px-10 flex items-center justify-between pointer-events-none">
        <div className="flex flex-col space-y-1 font-mono">
          <span className="text-[8px] sm:text-[9px] tracking-[0.25em] text-[#6d7f7a] uppercase">
            PERCEPTA DEFENSE // LEVEL-4 CLEARANCE
          </span>
          <span className="text-[7px] sm:text-[8px] tracking-[0.2em] text-[#41534e] uppercase">
            ENCRYPTED SENSOR LINK · SHA-256 VERIFIED
          </span>
        </div>

        {/* Instant Skip Button */}
        <button
          onClick={handleFinish}
          className="pointer-events-auto font-mono text-[9px] sm:text-[10px] tracking-[0.2em] text-[#d6c19b] border border-[#d6c19b]/40 hover:border-[#d6c19b] bg-[#d6c19b]/10 hover:bg-[#d6c19b]/20 px-3.5 py-1.5 rounded-full transition-all cursor-pointer uppercase shadow-[0_0_12px_rgba(214,193,155,0.15)]"
          title="Skip Intro"
        >
          SKIP INTRO →
        </button>
      </div>

      {/* ── Centerpiece: The Luxury Editorial Ring & Number ───────────── */}
      <div className="relative flex flex-col items-center justify-center scale-90 sm:scale-100">
        <div className="relative w-[280px] h-[280px] sm:w-[320px] sm:h-[320px] flex items-center justify-center">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 320 320">
            {/* Outer Faint Compass Ticks */}
            <circle
              cx="160"
              cy="160"
              r="152"
              fill="none"
              stroke="#d6c19b"
              strokeOpacity="0.12"
              strokeWidth="1"
              strokeDasharray="2 18"
              className="animate-[spin_45s_linear_infinite]"
              style={{ transformOrigin: "160px 160px" }}
            />

            {/* Background Track Circle */}
            <circle
              cx="160"
              cy="160"
              r={radius}
              fill="none"
              stroke="#ffffff"
              strokeOpacity="0.07"
              strokeWidth="1.5"
            />

            {/* Animated Luxury Gold Progress Ring */}
            <circle
              cx="160"
              cy="160"
              r={radius}
              fill="none"
              stroke="#f5ecda"
              strokeWidth="1.8"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-[stroke-dashoffset] duration-75 ease-out"
              style={{
                filter: "drop-shadow(0 0 6px rgba(245, 236, 218, 0.45))",
              }}
            />

            {/* Micro Cardinal Ticks on progress track */}
            <line x1="160" y1="20" x2="160" y2="28" stroke="#d6c19b" strokeOpacity="0.3" strokeWidth="1" />
            <line x1="160" y1="292" x2="160" y2="300" stroke="#d6c19b" strokeOpacity="0.3" strokeWidth="1" />
            <line x1="20" y1="160" x2="28" y2="160" stroke="#d6c19b" strokeOpacity="0.3" strokeWidth="1" />
            <line x1="292" y1="160" x2="300" y2="160" stroke="#d6c19b" strokeOpacity="0.3" strokeWidth="1" />
          </svg>

          {/* Central Large Editorial Number */}
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span
              className="font-serif text-[#f5ecda] tracking-tight select-none transition-all duration-75"
              style={{
                fontFamily: "'DM Serif Display', Georgia, serif",
                fontSize: "clamp(64px, 8vw, 98px)",
                lineHeight: 1,
                textShadow: "0 0 24px rgba(245, 236, 218, 0.2)",
              }}
            >
              {percent}
            </span>
          </div>
        </div>

        {/* ── Subtitle Security Telemetry Status ───────────────────────── */}
        <div className="mt-6 sm:mt-8 flex flex-col items-center space-y-2 pointer-events-none px-4 text-center">
          <div className="flex items-center gap-2 text-center font-mono text-[8.5px] sm:text-[9px] tracking-[0.24em] text-[#d6c19b]/90 uppercase">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#f5ecda] shadow-[0_0_8px_#f5ecda] animate-ping" />
            <span>{SECURITY_PHASES[phaseIndex]}</span>
          </div>

          <div className="flex items-center gap-1.5 text-[7px] font-mono tracking-[0.2em] text-[#556964]">
            <span>NODE 0x4B // SYS-ONLINE</span>
            <span>·</span>
            <span>UPLINK 100%</span>
          </div>
        </div>
      </div>

      {/* ── Bottom Left Audio Mute/Unmute Control ─ */}
      <div className="absolute bottom-6 sm:bottom-8 left-6 sm:left-8 flex items-center gap-3">
        <button
          onClick={toggleSound}
          className="flex items-center justify-center w-8 h-8 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 hover:border-[#d6c19b]/40 text-[#d6c19b] transition-all cursor-pointer shadow-md"
          title={muted ? "Unmute Audio" : "Mute Audio"}
          aria-label="Toggle Sound"
        >
          {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
        </button>
        <span className="hidden sm:inline font-mono text-[7px] tracking-[0.2em] text-[#556964] uppercase">
          {muted ? "AUDIO MUTED" : "C2 AUDIO ACTIVE"}
        </span>
      </div>

      {/* ── Bottom Right Security Watermark ──────────────────────────── */}
      <div className="absolute bottom-6 sm:bottom-8 right-6 sm:right-8 font-mono text-[7px] tracking-[0.2em] text-[#556964] uppercase">
        PERCEPTA DEFENSE C2
      </div>
    </div>
  );
};
