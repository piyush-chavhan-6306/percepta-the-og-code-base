import React, { useEffect, useState, useRef } from "react";

export const TacticalCursor: React.FC = () => {
  const [pos, setPos] = useState({ x: -100, y: -100 });
  const [hovered, setHovered] = useState(false);
  const [clicking, setClicking] = useState(false);
  const [visible, setVisible] = useState(false);

  const trailRef = useRef({ x: -100, y: -100 });
  const reqRef = useRef<number>(0);
  const [trailPos, setTrailPos] = useState({ x: -100, y: -100 });

  useEffect(() => {
    // Only enable on desktop pointer devices
    if (window.matchMedia("(pointer: coarse)").matches) return;

    const handleMouseMove = (e: MouseEvent) => {
      setPos({ x: e.clientX, y: e.clientY });
      if (!visible) setVisible(true);

      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "BUTTON" ||
          target.tagName === "A" ||
          target.closest("button") ||
          target.closest("a") ||
          target.classList.contains("button") ||
          target.classList.contains("tactical-box") ||
          target.classList.contains("command-mini"))
      ) {
        setHovered(true);
      } else {
        setHovered(false);
      }
    };

    const handleMouseDown = () => setClicking(true);
    const handleMouseUp = () => setClicking(false);
    const handleMouseLeave = () => setVisible(false);
    const handleMouseEnter = () => setVisible(true);

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("mousedown", handleMouseDown);
    window.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("mouseleave", handleMouseLeave);
    document.addEventListener("mouseenter", handleMouseEnter);

    // Smooth spring trailing ring
    const animateTrail = () => {
      trailRef.current.x += (pos.x - trailRef.current.x) * 0.22;
      trailRef.current.y += (pos.y - trailRef.current.y) * 0.22;
      setTrailPos({ x: trailRef.current.x, y: trailRef.current.y });
      reqRef.current = requestAnimationFrame(animateTrail);
    };
    reqRef.current = requestAnimationFrame(animateTrail);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mousedown", handleMouseDown);
      window.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("mouseleave", handleMouseLeave);
      document.removeEventListener("mouseenter", handleMouseEnter);
      cancelAnimationFrame(reqRef.current);
    };
  }, [pos.x, pos.y, visible]);

  if (!visible) return null;

  return (
    <>
      {/* 1. Precise Inner Reticle Dot */}
      <div
        className="fixed pointer-events-none z-[9999] rounded-full transition-transform duration-75"
        style={{
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          transform: "translate(-50%, -50%)",
          width: hovered ? "6px" : "4px",
          height: hovered ? "6px" : "4px",
          backgroundColor: hovered ? "#d6c19b" : "#9ee7df",
          boxShadow: hovered
            ? "0 0 10px #d6c19b, 0 0 20px #d6c19b"
            : "0 0 8px #9ee7df, 0 0 16px rgba(158, 231, 223, 0.4)",
        }}
      />

      {/* 2. Damped Trailing Tactical Ring */}
      <div
        className="fixed pointer-events-none z-[9998] transition-all duration-200 ease-out"
        style={{
          left: `${trailPos.x}px`,
          top: `${trailPos.y}px`,
          transform: `translate(-50%, -50%) scale(${clicking ? 0.85 : hovered ? 1.4 : 1})`,
          width: "28px",
          height: "28px",
        }}
      >
        <div
          className={`w-full h-full rounded-full border transition-colors duration-150 ${
            hovered
              ? "border-[#d6c19b]/80 bg-[#d6c19b]/10"
              : "border-[#9ee7df]/40 bg-[#9ee7df]/5"
          }`}
          style={{
            boxShadow: hovered
              ? "0 0 14px rgba(214, 193, 155, 0.25)"
              : "0 0 10px rgba(158, 231, 223, 0.15)",
          }}
        />

        {/* Tactical Crosshair Corner Accents */}
        {hovered && (
          <>
            <span className="absolute -top-1 -left-1 w-2 h-2 border-t border-l border-[#d6c19b]" />
            <span className="absolute -top-1 -right-1 w-2 h-2 border-t border-r border-[#d6c19b]" />
            <span className="absolute -bottom-1 -left-1 w-2 h-2 border-b border-l border-[#d6c19b]" />
            <span className="absolute -bottom-1 -right-1 w-2 h-2 border-b border-r border-[#d6c19b]" />
          </>
        )}
      </div>
    </>
  );
};
