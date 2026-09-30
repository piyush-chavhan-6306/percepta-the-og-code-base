import { useMemo } from "react";
import { motion } from "framer-motion";
import { ShieldAlert, ShieldCheck, AlertTriangle } from "lucide-react";

interface ThreatGaugeProps {
  score: number;
  level: string;
}

function getLevelConfig(level: string) {
  switch (level.toUpperCase()) {
    case "CRITICAL":
    case "DEFCON_RED":
    case "RED":
      return {
        ring: "#ef4444",
        ring2: "#dc2626",
        bg: "rgba(239,68,68,0.10)",
        border: "rgba(239,68,68,0.30)",
        text: "text-red-400",
        glow: "rgba(239,68,68,0.5)",
        pulse: "rgba(239,68,68,0.08)",
      };
    case "RESTRICTED":
    case "HIGH":
    case "DEFCON_ORANGE":
    case "ORANGE":
      return {
        ring: "#f97316",
        ring2: "#ea580c",
        bg: "rgba(249,115,22,0.10)",
        border: "rgba(249,115,22,0.30)",
        text: "text-orange-400",
        glow: "rgba(249,115,22,0.5)",
        pulse: "rgba(249,115,22,0.08)",
      };
    case "ELEVATED":
    case "MODERATE":
    case "MEDIUM":
    case "DEFCON_YELLOW":
    case "YELLOW":
      return {
        ring: "#eab308",
        ring2: "#ca8a04",
        bg: "rgba(234,179,8,0.10)",
        border: "rgba(234,179,8,0.30)",
        text: "text-yellow-400",
        glow: "rgba(234,179,8,0.5)",
        pulse: "rgba(234,179,8,0.08)",
      };
    default:
      return {
        ring: "#22c55e",
        ring2: "#16a34a",
        bg: "rgba(34,197,94,0.10)",
        border: "rgba(34,197,94,0.30)",
        text: "text-emerald-400",
        glow: "rgba(34,197,94,0.5)",
        pulse: "rgba(34,197,94,0.08)",
      };
  }
}

export function ThreatGauge({ score, level }: ThreatGaugeProps) {
  const config = useMemo(() => getLevelConfig(level), [level]);
  const clampedScore = Math.max(0, Math.min(100, score));

  const radius = 38;
  const radius2 = 42;
  const strokeWidth = 4;
  const strokeWidth2 = 1.5;
  const circumference = 2 * Math.PI * radius;
  const circumference2 = 2 * Math.PI * radius2;
  const arcLength = (270 / 360) * circumference;
  const arcLength2 = (270 / 360) * circumference2;
  const dashOffset = arcLength - (clampedScore / 100) * arcLength;
  const dashOffset2 = arcLength2 - (clampedScore / 100) * arcLength2;

  const Icon = score >= 75 ? ShieldAlert : score >= 50 ? AlertTriangle : ShieldCheck;

  return (
    <div className="flex items-center gap-4">
      {/* Gauge — double ring */}
      <div className="relative w-[96px] h-[96px]">
        {/* Ambient glow behind */}
        <motion.div
          className="absolute inset-[-12px] rounded-full blur-2xl"
          style={{ background: config.pulse }}
          animate={{ opacity: [0.4, 0.7, 0.4] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        />

        <svg viewBox="0 0 96 96" className="w-full h-full -rotate-[135deg] relative z-10">
          {/* Outer decorative ring */}
          <circle
            cx="48"
            cy="48"
            r={radius2}
            fill="none"
            stroke="rgba(255,255,255,0.04)"
            strokeWidth={strokeWidth2}
            strokeDasharray={`${arcLength2} ${circumference2}`}
            strokeLinecap="round"
          />
          <motion.circle
            cx="48"
            cy="48"
            r={radius2}
            fill="none"
            stroke={config.ring2}
            strokeWidth={strokeWidth2}
            strokeDasharray={`${arcLength2} ${circumference2}`}
            strokeLinecap="round"
            initial={{ strokeDashoffset: arcLength2 }}
            animate={{ strokeDashoffset: dashOffset2 }}
            transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
            style={{ opacity: 0.3 }}
          />

          {/* Inner track */}
          <circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={strokeWidth}
            strokeDasharray={`${arcLength} ${circumference}`}
            strokeLinecap="round"
          />

          {/* Active arc */}
          <motion.circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke={config.ring}
            strokeWidth={strokeWidth}
            strokeDasharray={`${arcLength} ${circumference}`}
            strokeLinecap="round"
            initial={{ strokeDashoffset: arcLength }}
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            style={{
              filter: `drop-shadow(0 0 10px ${config.glow}) drop-shadow(0 0 4px ${config.glow})`,
            }}
          />

          {/* Tick marks */}
          {Array.from({ length: 27 }).map((_, i) => {
            const angle = (i / 27) * 270;
            const rad = (angle * Math.PI) / 180;
            const r1 = radius - 6;
            const r2 = radius - 3;
            const x1 = 48 + r1 * Math.cos(rad);
            const y1 = 48 + r1 * Math.sin(rad);
            const x2 = 48 + r2 * Math.cos(rad);
            const y2 = 48 + r2 * Math.sin(rad);
            const isActive = i <= (clampedScore / 100) * 27;
            return (
              <line
                key={i}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={isActive ? config.ring : "rgba(255,255,255,0.1)"}
                strokeWidth={1}
                style={{ opacity: isActive ? 0.8 : 0.3 }}
              />
            );
          })}
        </svg>

        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center z-20">
          <motion.span
            key={clampedScore}
            initial={{ scale: 0.7, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 20 }}
            className="text-[22px] font-black font-mono text-foreground leading-none tracking-tight"
          >
            {clampedScore}
          </motion.span>
          <span className="text-[8px] font-mono text-muted-foreground mt-1 tracking-widest">
            / 100
          </span>
        </div>
      </div>

      {/* Level indicator */}
      <div className="flex flex-col gap-1.5">
        <motion.div
          key={level}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl border backdrop-blur-md"
          style={{
            background: config.bg,
            borderColor: config.border,
            boxShadow: `0 0 20px ${config.pulse}, inset 0 1px 0 rgba(255,255,255,0.05)`,
          }}
        >
          <Icon className={`w-4 h-4 ${config.text}`} />
          <span className={`text-[11px] font-mono font-bold uppercase tracking-widest ${config.text}`}>
            {level}
          </span>
        </motion.div>
        <span className="text-[9px] font-mono text-muted-foreground/60 px-1 tracking-wider">
          THREAT ASSESSMENT
        </span>
      </div>
    </div>
  );
}
