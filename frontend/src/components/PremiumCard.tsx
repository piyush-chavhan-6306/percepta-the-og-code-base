import { useRef, useState, useCallback, type ReactNode } from "react";
import { motion } from "framer-motion";

interface PremiumCardProps {
  children: ReactNode;
  className?: string;
  /** 0 = no tilt, 15 = aggressive */
  tilt?: number;
  /** Lift scale on hover */
  lift?: number;
  /** Show the glare/cursor light effect */
  glare?: boolean;
  /** Glow border color */
  glowColor?: string;
  /** Depth level — affects shadow intensity */
  depth?: 1 | 2 | 3;
  /** Disable animation */
  noMotion?: boolean;
  /** Class name for the inner content container */
  contentClassName?: string;
}

const depthShadows = {
  1: "0 2px 8px rgba(0,0,0,0.2), 0 0 20px rgba(0,229,255,0.02)",
  2: "0 4px 24px rgba(0,0,0,0.3), 0 0 40px rgba(0,229,255,0.04), inset 0 1px 0 rgba(255,255,255,0.04)",
  3: "0 8px 40px rgba(0,0,0,0.4), 0 0 60px rgba(0,229,255,0.06), inset 0 1px 0 rgba(255,255,255,0.06)",
};

const depthShadowsHover = {
  1: "0 8px 32px rgba(0,0,0,0.3), 0 0 30px rgba(0,229,255,0.04)",
  2: "0 12px 48px rgba(0,0,0,0.4), 0 0 60px rgba(0,229,255,0.08), inset 0 1px 0 rgba(255,255,255,0.08)",
  3: "0 20px 64px rgba(0,0,0,0.5), 0 0 80px rgba(0,229,255,0.10), inset 0 1px 0 rgba(255,255,255,0.10)",
};

export function PremiumCard({
  children,
  className = "",
  contentClassName = "",
  tilt = 12,
  lift = 1.02,
  glare = true,
  glowColor = "rgba(0, 229, 255, 0.15)",
  depth = 2,
  noMotion = false,
}: PremiumCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [style, setStyle] = useState<React.CSSProperties>({
    transform: "perspective(1000px) rotateX(0deg) rotateY(0deg) translateZ(0px) scale(1)",
    boxShadow: depthShadows[depth],
  });
  const [glarePos, setGlarePos] = useState({ x: 50, y: 50 });
  const [isHovered, setIsHovered] = useState(false);

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const card = cardRef.current;
      if (!card || !tilt) return;

      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;

      const rotateX = ((y - centerY) / centerY) * -tilt;
      const rotateY = ((x - centerX) / centerX) * tilt;

      setStyle({
        transform: `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateZ(16px) scale(${lift})`,
        boxShadow: depthShadowsHover[depth],
      });

      setGlarePos({
        x: (x / rect.width) * 100,
        y: (y / rect.height) * 100,
      });
    },
    [tilt, lift, depth]
  );

  const handleMouseEnter = useCallback(() => setIsHovered(true), []);
  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
    setStyle({
      transform: "perspective(1000px) rotateX(0deg) rotateY(0deg) translateZ(0px) scale(1)",
      boxShadow: depthShadows[depth],
    });
  }, [depth]);

  const Wrapper = noMotion ? "div" : motion.div;

  return (
    <Wrapper
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={`relative rounded-xl overflow-hidden will-change-transform ${className}`}
      style={{
        ...style,
        transformStyle: "preserve-3d",
        transition: "transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
      {...(!noMotion ? { whileHover: {} } : {})}
    >
      {/* Inner glass background */}
      <div className="absolute inset-0 bg-[oklch(0.14_0.02_260_/_50%)] backdrop-blur-xl z-0" />

      {/* Content */}
      <div className={`relative z-10 ${className.includes("h-full") || className.includes("flex-col") ? "h-full flex flex-col min-h-0 flex-1" : ""} ${contentClassName}`}>
        {children}
      </div>

      {/* Glare overlay — cursor-following light */}
      {glare && (
        <div
          className="absolute inset-0 pointer-events-none z-20 transition-opacity duration-500"
          style={{
            background: `radial-gradient(circle at ${glarePos.x}% ${glarePos.y}%, ${glowColor}, transparent 60%)`,
            opacity: isHovered ? 0.2 : 0,
          }}
        />
      )}

      {/* Top edge highlight */}
      <div
        className="absolute top-0 left-0 right-0 h-px pointer-events-none z-20 transition-opacity duration-500"
        style={{
          background: `linear-gradient(90deg, transparent, ${glowColor}, transparent)`,
          opacity: isHovered ? 0.8 : 0.1,
        }}
      />

      {/* Left edge subtle highlight */}
      <div
        className="absolute top-0 left-0 bottom-0 w-px pointer-events-none z-20 transition-opacity duration-500"
        style={{
          background: `linear-gradient(180deg, transparent, ${glowColor}, transparent)`,
          opacity: isHovered ? 0.4 : 0,
        }}
      />

      {/* Border — glass */}
      <div className="absolute inset-0 rounded-xl pointer-events-none z-20 border border-white/[0.06] transition-colors duration-500"
        style={{
          borderColor: isHovered ? "rgba(255,255,255,0.1)" : "rgba(255,255,255,0.06)",
        }}
      />
    </Wrapper>
  );
}
