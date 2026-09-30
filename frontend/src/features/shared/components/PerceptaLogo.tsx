import React from "react";

export interface PerceptaLogoProps {
  className?: string;
  size?: number;
  showText?: boolean;
  subtitle?: string;
}

export const PerceptaLogo: React.FC<PerceptaLogoProps> = ({
  className = "",
  size = 28,
  showText = true,
  subtitle = "DEFENSE",
}) => {
  return (
    <div className={`flex items-center gap-3 select-none group ${className}`}>
      {/* Precision Tactical Aperture SVG Emblem */}
      <div
        className="relative flex items-center justify-center shrink-0"
        style={{ width: size, height: size }}
      >
        <svg
          viewBox="0 0 36 36"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="w-full h-full transition-transform duration-500 group-hover:rotate-45"
        >
          {/* Hexagonal Tactical Hull */}
          <polygon
            points="18,2 32,10 32,26 18,34 4,26 4,10"
            stroke="#00e5ff"
            strokeWidth="1.2"
            strokeOpacity="0.55"
            className="transition-all duration-300 group-hover:stroke-opacity-100"
          />

          {/* Corner Notch Accents */}
          <line x1="18" y1="2" x2="18" y2="7" stroke="#00e5ff" strokeWidth="1.5" />
          <line x1="18" y1="29" x2="18" y2="34" stroke="#00e5ff" strokeWidth="1.5" />
          <line x1="4" y1="18" x2="9" y2="18" stroke="#00e5ff" strokeWidth="1.5" />
          <line x1="27" y1="18" x2="32" y2="18" stroke="#00e5ff" strokeWidth="1.5" />

          {/* Concentric Radar Ring */}
          <circle
            cx="18"
            cy="18"
            r="8"
            stroke="#00e5ff"
            strokeWidth="0.9"
            strokeDasharray="2.5 2"
            strokeOpacity="0.7"
          />

          {/* Core Sensor / Signal Dot */}
          <circle
            cx="18"
            cy="18"
            r="2.5"
            fill="#00e5ff"
            className="shadow-[0_0_10px_#00e5ff]"
          />
        </svg>

        {/* Ambient Pulse Glow */}
        <div
          className="absolute inset-0 rounded-full bg-[#00e5ff]/15 blur-sm pointer-events-none group-hover:bg-[#00e5ff]/30 transition-all"
        />
      </div>

      {showText && (
        <div className="flex flex-col leading-none">
          <div className="flex items-center gap-1.5">
            <span className="font-['Orbitron','Barlow_Condensed',sans-serif] font-bold text-base tracking-[0.18em] text-[#e8ebe6] uppercase transition-colors group-hover:text-[#00e5ff]">
              PERCEPTA
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-[#00e5ff] shadow-[0_0_6px_#00e5ff] animate-pulse" />
          </div>
          <span className="font-mono text-[8px] tracking-[0.25em] text-[#00e5ff]/60 uppercase mt-0.5">
            {subtitle}
          </span>
        </div>
      )}
    </div>
  );
};
