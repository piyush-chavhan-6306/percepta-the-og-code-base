import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Wifi,
  Database,
  Cpu,
  Clock,
  Shield,
  Zap,
} from "lucide-react";

function useUptime() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => setElapsed(Date.now() - start), 1000);
    return () => clearInterval(interval);
  }, []);

  const hrs = Math.floor(elapsed / 3600000);
  const mins = Math.floor((elapsed % 3600000) / 60000);
  const secs = Math.floor((elapsed % 60000) / 1000);
  return `${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

interface StatusBarProps {
  cameraCount?: number;
  alertCount?: number;
  threatLevel?: string;
}

export function StatusBar({ cameraCount = 0, alertCount = 0, threatLevel = "NORMAL" }: StatusBarProps) {
  const uptime = useUptime();
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const utcTime = time.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone: "UTC",
  });

  const utcDate = time.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  });

  return (
    <div className="glass-panel glow-line px-5 py-2 flex items-center justify-between text-[10px] font-mono text-muted-foreground/70 z-40 relative">
      {/* Left: System status */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-1.5">
          <motion.div
            className="w-1.5 h-1.5 rounded-full bg-emerald-500"
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <span className="text-emerald-400/80">SYSTEM ONLINE</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <div className="flex items-center gap-1.5">
          <Wifi className="w-3 h-3 text-cyan-400/60" />
          <span>WS CONNECTED</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <div className="flex items-center gap-1.5">
          <Database className="w-3 h-3 text-blue-400/60" />
          <span>SQLite WAL</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <div className="flex items-center gap-1.5">
          <Cpu className="w-3 h-3 text-purple-400/60" />
          <span>YOLOv8n</span>
        </div>
      </div>

      {/* Center: Metrics */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-1.5">
          <Shield className="w-3 h-3 text-primary/60" />
          <span>{cameraCount} CAMERAS</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <div className="flex items-center gap-1.5">
          <Zap className="w-3 h-3 text-amber-400/60" />
          <span>{alertCount} ALERTS</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <div className="flex items-center gap-1.5">
          <Activity className="w-3 h-3 text-red-400/60" />
          <span>THREAT: {threatLevel}</span>
        </div>
      </div>

      {/* Right: Time */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3 h-3 text-muted-foreground/50" />
          <span>UP {uptime}</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <div className="flex items-center gap-1.5">
          <span className="text-foreground/60 font-semibold">{utcTime}</span>
          <span className="text-muted-foreground/50">UTC</span>
        </div>

        <div className="h-3 w-px bg-white/10" />

        <span className="text-muted-foreground/40">{utcDate}</span>
      </div>
    </div>
  );
}
