import { useEffect, useRef, useCallback } from "react";

/**
 * Premium animated background — CSS + Canvas hybrid.
 * Subtle perspective grid, floating gradient orbs, and a slow scan line.
 * Reacts to mouse position for parallax depth.
 */
export function PremiumBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouseRef = useRef({ x: 0.5, y: 0.5 });
  const rafRef = useRef<number>(0);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    mouseRef.current = {
      x: e.clientX / window.innerWidth,
      y: e.clientY / window.innerHeight,
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = window.innerWidth;
    let height = window.innerHeight;

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * devicePixelRatio;
      canvas.height = height * devicePixelRatio;
      ctx.scale(devicePixelRatio, devicePixelRatio);
    };
    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", handleMouseMove);

    // Orb particles — floating ambient lights
    const orbs = Array.from({ length: 6 }, (_, i) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.2,
      radius: 80 + Math.random() * 160,
      hue: [210, 190, 220, 180, 260, 200][i],
      phase: Math.random() * Math.PI * 2,
    }));

    let time = 0;

    const draw = () => {
      time += 0.008;
      ctx.clearRect(0, 0, width, height);

      const mx = mouseRef.current.x;
      const my = mouseRef.current.y;

      // Perspective grid
      ctx.save();
      const gridSpacing = 60;
      const gridAlpha = 0.03 + Math.sin(time * 0.5) * 0.01;
      ctx.strokeStyle = `rgba(0, 229, 255, ${gridAlpha})`;
      ctx.lineWidth = 0.5;

      // Horizontal lines with perspective fade
      for (let y = 0; y < height; y += gridSpacing) {
        const distFromCenter = Math.abs(y - height / 2) / (height / 2);
        const alpha = gridAlpha * (1 - distFromCenter * 0.7);
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.moveTo(0, y + (my - 0.5) * 20);
        ctx.lineTo(width, y + (my - 0.5) * 20);
        ctx.stroke();
      }

      // Vertical lines with perspective fade
      for (let x = 0; x < width; x += gridSpacing) {
        const distFromCenter = Math.abs(x - width / 2) / (width / 2);
        const alpha = gridAlpha * (1 - distFromCenter * 0.7);
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.moveTo(x + (mx - 0.5) * 20, 0);
        ctx.lineTo(x + (mx - 0.5) * 20, height);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      ctx.restore();

      // Floating orbs
      for (const orb of orbs) {
        orb.x += orb.vx + (mx - 0.5) * 0.5;
        orb.y += orb.vy + (my - 0.5) * 0.5;

        // Bounce off edges
        if (orb.x < -orb.radius) orb.x = width + orb.radius;
        if (orb.x > width + orb.radius) orb.x = -orb.radius;
        if (orb.y < -orb.radius) orb.y = height + orb.radius;
        if (orb.y > height + orb.radius) orb.y = -orb.radius;

        const pulse = 0.6 + Math.sin(time * 0.8 + orb.phase) * 0.4;
        const gradient = ctx.createRadialGradient(
          orb.x, orb.y, 0,
          orb.x, orb.y, orb.radius * pulse
        );
        gradient.addColorStop(0, `hsla(${orb.hue}, 80%, 50%, 0.06)`);
        gradient.addColorStop(0.5, `hsla(${orb.hue}, 70%, 40%, 0.03)`);
        gradient.addColorStop(1, `hsla(${orb.hue}, 60%, 30%, 0)`);

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(orb.x, orb.y, orb.radius * pulse, 0, Math.PI * 2);
        ctx.fill();
      }

      // Scan line
      const scanY = (time * 40) % height;
      const scanGradient = ctx.createLinearGradient(0, scanY - 2, 0, scanY + 2);
      scanGradient.addColorStop(0, "rgba(0, 229, 255, 0)");
      scanGradient.addColorStop(0.5, "rgba(0, 229, 255, 0.04)");
      scanGradient.addColorStop(1, "rgba(0, 229, 255, 0)");
      ctx.fillStyle = scanGradient;
      ctx.fillRect(0, scanY - 2, width, 4);

      // Vignette
      const vignette = ctx.createRadialGradient(
        width / 2, height / 2, width * 0.3,
        width / 2, height / 2, width * 0.8
      );
      vignette.addColorStop(0, "rgba(0,0,0,0)");
      vignette.addColorStop(1, "rgba(0,0,0,0.4)");
      ctx.fillStyle = vignette;
      ctx.fillRect(0, 0, width, height);

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", handleMouseMove);
    };
  }, [handleMouseMove]);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-0"
      style={{ width: "100vw", height: "100vh" }}
    />
  );
}
