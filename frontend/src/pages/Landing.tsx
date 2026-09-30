import React, { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router";
import {
  ChevronRight,
  ArrowDown,
  Menu,
  X,
} from "lucide-react";
import { EarthGlobe } from "@/features/landing/components/EarthGlobe";
import { WorldOverlays, OverlayTransform } from "@/features/landing/components/WorldOverlays";
import { TacticalCursor } from "@/features/landing/components/TacticalCursor";
import { C2Loader } from "@/features/landing/components/C2Loader";
import { PerceptaLogo } from "@/features/shared/components/PerceptaLogo";
import "@/features/shared/styles/designTokens.css";
import "@/features/landing/styles/WorldOverlays.css";
import "@/features/landing/styles/WorldMotion.css";

export const stages = [
  {
    id: "observe",
    index: "01",
    title: "Observe",
    kicker: "SIH26187 // LEGACY CCTV FLEET RETROFIT",
    body: "Ingest fixed border CCTV cameras, RTSP streams, and local recordings into an automated surveillance post — zero costly sensor replacements required.",
    metric: "RTSP · MP4 / WEBM · 30+ FPS EDGE INGESTION",
    side: "left",
  },
  {
    id: "detect",
    index: "02",
    title: "Detect",
    kicker: "INDIA BORDER THEATRE // LOCAL EDGE PERCEPTION",
    body: "Local YOLOv8 neural detection for border infiltrators, patrol vehicles, convoys, and equipment — operating 100% offline without cloud dependency.",
    metric: "YOLOv8n · PERSON · VEHICLE · 0.94 CONF",
    side: "right",
  },
  {
    id: "track",
    index: "03",
    title: "Track",
    kicker: "CONTINUOUS MULTI-OBJECT TRACKING",
    body: "ByteTrack with Kalman filter state estimation preserves persistent track IDs, velocity vectors, and cardinal headings across camera handoffs.",
    metric: "BYTETRACK · KALMAN FILTER · VELOCITY HEADINGS",
    side: "left",
  },
  {
    id: "understand",
    index: "04",
    title: "Understand",
    kicker: "POLYGON GEOFENCING & VIRTUAL TRIPWIRES",
    body: "Interactive user-drawn boundary polygons, directional tripwires, and temporal dwell thresholds transform raw movement into verified spatial breaches.",
    metric: "RESTRICTED ZONES · TRIPWIRES · DWELL EVALUATION",
    side: "right",
  },
  {
    id: "assess",
    index: "05",
    title: "Assess",
    kicker: "AUTOMATED THREAT WEIGHTING & DEFCON LEVEL",
    body: "Multi-factor threat index separates benign movement from hostile breaches, calculating real-time DEFCON readiness and perimeter risk scores.",
    metric: "DEFCON LEVEL 2 · THREAT INDEX 72/100 · SEVERE",
    side: "left",
  },
  {
    id: "evidence",
    index: "06",
    title: "Evidence",
    kicker: "CRYPTOGRAPHIC CHAIN-OF-CUSTODY",
    body: "Frame-synchronized video playback, target crops, and tamper-evident SHA-256 Merkle hash chaining establish an airtight audit trail.",
    metric: "SHA-256 TAMPER-PROOF · SYNCED VIDEO CLIPS",
    side: "right",
  },
  {
    id: "incidents",
    index: "07",
    title: "Incidents",
    kicker: "EXPLAINABLE INCIDENT DOSSIERS",
    body: "Reduces flood of detections into structured, explainable security incidents with automated SitRep generation and verified operator actions.",
    metric: "SITREP DOSSIER · RULE REASONING · DISPATCH",
    side: "left",
  },
  {
    id: "command",
    index: "08",
    title: "Command",
    kicker: "GROUNDED AI OPERATOR ASSISTANT",
    body: "Natural-language query console strictly grounded in active SQLite records — answering perimeter questions with zero external hallucinations.",
    metric: "GROUNDED SQL ASSISTANT · ZERO HALLUCINATIONS",
    side: "left",
  },
];

interface PublicNavProps {
  onMenu: () => void;
  onNavigate: (sectionId: string) => void;
}

function PublicNav({ onMenu, onNavigate }: PublicNavProps) {
  const navigate = useNavigate();

  return (
    <header className="public-nav" data-testid="public-navigation">
      <Link to="/" className="flex items-center" data-testid="brand-home">
        <PerceptaLogo size={30} showText={true} />
      </Link>

      <nav className="nav-links">
        <button
          onClick={() => onNavigate("observe")}
          className="text-[10px] tracking-[0.15em] uppercase text-[#9da9aa] hover:text-[#00e5ff] transition-colors bg-transparent border-none cursor-pointer p-0 font-mono"
          data-testid="nav-features"
        >
          FEATURES
        </button>
        <button
          onClick={() => onNavigate("track")}
          className="text-[10px] tracking-[0.15em] uppercase text-[#9da9aa] hover:text-[#00e5ff] transition-colors bg-transparent border-none cursor-pointer p-0 font-mono"
          data-testid="nav-technology"
        >
          TECHNOLOGY
        </button>
        <button
          onClick={() => onNavigate("assess")}
          className="text-[10px] tracking-[0.15em] uppercase text-[#9da9aa] hover:text-[#00e5ff] transition-colors bg-transparent border-none cursor-pointer p-0 font-mono"
          data-testid="nav-capabilities"
        >
          CAPABILITIES
        </button>
        <button
          onClick={() => onNavigate("command")}
          className="text-[10px] tracking-[0.15em] uppercase text-[#9da9aa] hover:text-[#00e5ff] transition-colors bg-transparent border-none cursor-pointer p-0 font-mono"
          data-testid="nav-about"
        >
          ABOUT
        </button>
      </nav>

      <div className="nav-actions">
        <button
          onClick={() => navigate("/auth?redirect=/dashboard")}
          className="button button-small"
          data-testid="nav-demo"
        >
          ENTER C2 <ChevronRight size={14} />
        </button>
      </div>

      <button
        className="icon-button mobile-menu"
        onClick={onMenu}
        aria-label="Open menu"
        data-testid="mobile-menu-button"
      >
        <Menu size={20} />
      </button>
    </header>
  );
}

export default function Landing() {
  const navigate = useNavigate();
  const [progress, setProgress] = useState(0);
  const [menu, setMenu] = useState(false);
  const [stageOpacities, setStageOpacities] = useState<Record<string, OverlayTransform>>({
    observe: { opacity: 0, scale: 0.94, translateY: 0 },
    detect: { opacity: 0, scale: 0.94, translateY: 0 },
    track: { opacity: 0, scale: 0.94, translateY: 0 },
    understand: { opacity: 0, scale: 0.94, translateY: 0 },
    assess: { opacity: 0, scale: 0.94, translateY: 0 },
    evidence: { opacity: 0, scale: 0.94, translateY: 0 },
    incidents: { opacity: 0, scale: 0.94, translateY: 0 },
    command: { opacity: 0, scale: 0.94, translateY: 0 },
  });

  const [titleTransforms, setTitleTransforms] = useState<Record<string, { opacity: number; translateY: number }>>({});

  useEffect(() => {
    let ticking = false;

    const updatePositions = () => {
      const viewportCenter = window.innerHeight / 2;
      const nextOpacities: Record<string, OverlayTransform> = {};
      const nextTitles: Record<string, { opacity: number; translateY: number }> = {};
      const NAV_THRESHOLD = 82;

      // 0. Hero Title Exit (purely scroll-driven: 100% visible at scrollY=0, smoothly fades out as you scroll down)
      const heroScrollDist = window.innerHeight * 0.45;
      const heroProgress = Math.min(1, Math.max(0, window.scrollY / Math.max(1, heroScrollDist)));
      const heroOpacity = Math.max(0, 1 - Math.pow(heroProgress, 1.2));
      const heroTranslate = heroProgress * -45;
      nextTitles["hero"] = { opacity: heroOpacity, translateY: heroTranslate };

      // 1–8. Choreographed Chapters
      stages.forEach((stage) => {
        const el = document.getElementById(stage.id);
        if (!el) {
          nextOpacities[stage.id] = { opacity: 0, scale: 0.94, translateY: 0 };
          nextTitles[stage.id] = { opacity: 1, translateY: 0 };
          return;
        }

        const copyEl = (el.querySelector(".stage-copy") as HTMLElement) || el;
        const copyRect = copyEl.getBoundingClientRect();
        const copyTop = copyRect.top;

        if (copyTop <= NAV_THRESHOLD) {
          nextOpacities[stage.id] = { opacity: 0, scale: 0.94, translateY: -15 };
          nextTitles[stage.id] = { opacity: 0, translateY: -45 };
          return;
        }

        const PLATEAU_HALF = 70;
        const plateauTop = viewportCenter - PLATEAU_HALF;
        const plateauBottom = viewportCenter + PLATEAU_HALF;

        if (copyTop < plateauTop) {
          const progressToNav = Math.min(
            1,
            Math.max(0, (plateauTop - copyTop) / (plateauTop - NAV_THRESHOLD))
          );
          const exitFade = Math.max(0, 1 - Math.pow(progressToNav, 1.15));
          const titleTranslate = progressToNav * -45;
          const overlayTranslate = progressToNav * -15;

          nextTitles[stage.id] = {
            opacity: exitFade,
            translateY: titleTranslate,
          };
          nextOpacities[stage.id] = {
            opacity: exitFade,
            scale: 0.95 + 0.05 * exitFade,
            translateY: overlayTranslate,
          };
        } else if (copyTop <= plateauBottom) {
          nextTitles[stage.id] = {
            opacity: 1,
            translateY: 0,
          };
          nextOpacities[stage.id] = {
            opacity: 1,
            scale: 1,
            translateY: 0,
          };
        } else {
          const enterDistance = window.innerHeight * 0.45;
          const progressEnter = Math.min(
            1,
            Math.max(0, (copyTop - plateauBottom) / enterDistance)
          );
          const enterFade = Math.max(0, 1 - Math.pow(progressEnter, 1.2));
          const titleTranslate = progressEnter * 30;
          const overlayTranslate = progressEnter * 15;

          nextTitles[stage.id] = {
            opacity: enterFade,
            translateY: titleTranslate,
          };
          nextOpacities[stage.id] = {
            opacity: enterFade,
            scale: 0.95 + 0.05 * enterFade,
            translateY: overlayTranslate,
          };
        }
      });

      setStageOpacities(nextOpacities);
      setTitleTransforms(nextTitles);

      const maxScroll = document.body.scrollHeight - window.innerHeight;
      setProgress(maxScroll > 0 ? Math.min(1, Math.max(0, window.scrollY / maxScroll)) : 0);
      ticking = false;
    };

    const handleScroll = () => {
      if (!ticking) {
        requestAnimationFrame(updatePositions);
        ticking = true;
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    updatePositions();
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (id: string) => {
    if (id === "hero") {
      window.scrollTo({ top: 0, behavior: "smooth" });
      window.dispatchEvent(
        new CustomEvent("percepta-sync-scroll", { detail: { targetY: 0 } })
      );
      return;
    }

    const el = document.getElementById(id);
    if (el) {
      const copyEl = (el.querySelector(".stage-copy") as HTMLElement) || el;
      const copyRect = copyEl.getBoundingClientRect();
      const targetViewportY = window.innerHeight * 0.46;
      const topOffset = Math.max(0, Math.round(copyRect.top + window.scrollY - targetViewportY));

      window.scrollTo({
        top: topOffset,
        behavior: "smooth",
      });
      window.dispatchEvent(
        new CustomEvent("percepta-sync-scroll", { detail: { targetY: topOffset } })
      );
    }
  };

  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    if (hash) {
      const timer = setTimeout(() => {
        scrollToSection(hash);
      }, 250);
      return () => clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    let targetY = window.scrollY;
    let currentY = window.scrollY;
    let isWheeling = false;
    let animId: number | null = null;

    const originalScrollBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";

    const smoothStep = () => {
      const diff = targetY - currentY;
      if (Math.abs(diff) < 0.35) {
        currentY = targetY;
        window.scrollTo(0, currentY);
        isWheeling = false;
        animId = null;
        return;
      }

      currentY += diff * 0.12;
      window.scrollTo(0, currentY);
      animId = requestAnimationFrame(smoothStep);
    };

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      e.preventDefault();

      const maxScroll = Math.max(
        0,
        document.documentElement.scrollHeight - window.innerHeight
      );

      targetY = Math.max(0, Math.min(maxScroll, targetY + e.deltaY * 0.35));

      if (!isWheeling) {
        isWheeling = true;
        currentY = window.scrollY;
        animId = requestAnimationFrame(smoothStep);
      }
    };

    const handleManualScroll = () => {
      if (!isWheeling) {
        targetY = window.scrollY;
        currentY = window.scrollY;
      }
    };

    const handleSync = (e: any) => {
      if (typeof e.detail?.targetY === "number") {
        targetY = e.detail.targetY;
        currentY = window.scrollY;
        isWheeling = false;
        if (animId) {
          cancelAnimationFrame(animId);
          animId = null;
        }
      }
    };

    window.addEventListener("wheel", handleWheel, { passive: false });
    window.addEventListener("scroll", handleManualScroll, { passive: true });
    window.addEventListener("percepta-sync-scroll", handleSync);

    return () => {
      document.documentElement.style.scrollBehavior = originalScrollBehavior;
      window.removeEventListener("wheel", handleWheel);
      window.removeEventListener("scroll", handleManualScroll);
      window.removeEventListener("percepta-sync-scroll", handleSync);
      if (animId) cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <main className="landing selection:bg-[#00e5ff] selection:text-[#05070a]" data-testid="landing-page">
      <C2Loader />
      <TacticalCursor />
      <PublicNav onMenu={() => setMenu(!menu)} onNavigate={scrollToSection} />

      {/* Mobile Drawer Navigation */}
      {menu && (
        <div className="mobile-nav" data-testid="mobile-navigation">
          <button onClick={() => setMenu(false)} data-testid="mobile-close-button">
            <X size={20} />
          </button>
          <div className="mb-6">
            <PerceptaLogo size={26} showText={true} />
          </div>
          {stages.map((stage) => (
            <button
              key={stage.id}
              onClick={() => {
                setMenu(false);
                scrollToSection(stage.id);
              }}
              className="text-left font-mono tracking-wider py-2 uppercase hover:text-[#00e5ff] transition-colors bg-transparent border-none cursor-pointer text-ink"
              data-testid={`mobile-nav-${stage.id}`}
            >
              {stage.title.toUpperCase()}
            </button>
          ))}
          <button
            onClick={() => {
              setMenu(false);
              navigate("/auth?redirect=/dashboard");
            }}
            className="button mt-6 text-center w-full justify-center"
            data-testid="mobile-enter-c2"
          >
            ENTER C2 →
          </button>
        </div>
      )}

      {/* Telemetry Progress Bar */}
      <div className="landing-progress">
        <span style={{ transform: `scaleX(${progress})` }} />
      </div>

      {/* 3D Photorealistic Earth Scene + Centered Overlays */}
      <div className="earth-layer">
        <EarthGlobe progress={progress} />
        <WorldOverlays opacities={stageOpacities} />
        <div
          className="earth-caption"
          style={{
            opacity: progress > 0.04 && progress < 0.97 ? 1 : 0,
            transition: "opacity 0.4s ease",
            pointerEvents: "none",
          }}
        >
          <span /> GLOBAL INTELLIGENCE / 00
          {Math.min(9, Math.floor(progress * 10) + 1)}
        </div>
      </div>

      {/* ── 00. Hero Section ────────────────────────────────────────────────── */}
      <section className="hero-story" id="hero" data-testid="hero-section">
        <div
          className="hero-copy"
          style={{
            opacity: titleTransforms["hero"]?.opacity ?? 1,
            transform: `translateY(${titleTransforms["hero"]?.translateY ?? 0}px)`,
            pointerEvents: (titleTransforms["hero"]?.opacity ?? 1) > 0.2 ? "auto" : "none",
          }}
        >
          <p className="eyebrow">
            <span className="eyebrow-line" /> SMART INDIA HACKATHON // PS SIH26187
          </p>
          <h1>
            Automated Border Defense.
            <br />
            <em>Without new sensors.</em>
          </h1>
          <p className="hero-description">
            Percepta upgrades existing fixed CCTV cameras into an edge AI surveillance command post — integrating real-time YOLOv8 perception, ByteTrack Kalman tracking, dynamic polygon tripwires, and SHA-256 cryptographic chain-of-custody.
          </p>

          {/* Hero Action Button Group */}
          <div className="flex flex-wrap items-center gap-4 mt-8 mb-6 pt-2">
            <button
              onClick={() => navigate("/dashboard")}
              className="button font-mono text-xs py-3 px-6 flex items-center gap-2 cursor-pointer shadow-[0_0_20px_rgba(0,229,255,0.25)] hover:shadow-[0_0_28px_rgba(0,229,255,0.4)] transition-all active:scale-[0.98]"
            >
              <span>ENTER COMMAND POST</span>
              <ChevronRight size={14} />
            </button>
            <button
              onClick={() => navigate("/auth?redirect=/dashboard")}
              className="button button-ghost font-mono text-xs py-3 px-5 flex items-center gap-2 cursor-pointer hover:border-[#00e5ff]/50 transition-all active:scale-[0.98]"
            >
              <span>OPERATOR AUTH // CLEARANCE</span>
            </button>
          </div>

          <button
            onClick={() => scrollToSection("observe")}
            className="scroll-prompt cursor-pointer bg-transparent border-none text-left p-0 mt-8 hover:text-white transition-colors"
            data-testid="hero-scroll-link"
          >
            <span className="scroll-icon">
              <ArrowDown size={15} />
            </span>
            SCROLL TO EXPLORE MISSION CHAPTERS
          </button>
        </div>
        <div
          className="hero-side-note"
          style={{
            opacity: titleTransforms["hero"]?.opacity ?? 1,
          }}
        >
          <span>01</span>
          <span className="vertical-rule" />
          <span>BORDER DEFENSE INFRASTRUCTURE</span>
        </div>
      </section>

      {/* ── 01–08. The 8 Choreographed Chapters ─────────────────────────────── */}
      <div className="story-track">
        {stages.map((stage) => {
          const tStyle = titleTransforms[stage.id] || { opacity: 1, translateY: 0 };
          return (
            <section
              key={stage.id}
              className={`story-stage stage-${stage.side}`}
              id={stage.id}
              data-testid={`story-stage-${stage.id}`}
            >
              <div
                className="stage-index"
                style={{
                  opacity: tStyle.opacity,
                  pointerEvents: tStyle.opacity > 0.2 ? "auto" : "none",
                }}
              >
                {stage.index}
                <span />
              </div>
              <div
                className="stage-copy"
                style={{
                  opacity: tStyle.opacity,
                  transform: `translateY(${tStyle.translateY}px)`,
                  pointerEvents: tStyle.opacity > 0.2 ? "auto" : "none",
                }}
              >
                <p className="eyebrow">{stage.kicker}</p>
                <h2>
                  {stage.title}
                  <sup>.</sup>
                </h2>
                <p className="stage-body">{stage.body}</p>
                <div className="telemetry-line">
                  <span>{stage.metric}</span>
                  <ChevronRight size={15} />
                </div>
              </div>
            </section>
          );
        })}
      </div>

      {/* ── 09. Grounded Defense AI Section (Clean Final CTA) ────────────────── */}
      <section
        className="final-cta min-h-screen py-28 px-6 md:px-16 lg:px-24 flex flex-col justify-center relative z-10"
        id="final-cta"
        data-testid="final-cta"
      >
        <div className="w-full max-w-5xl text-left space-y-8">
          <p className="eyebrow flex items-center gap-3">
            <span className="eyebrow-line" /> SMART INDIA HACKATHON // PS SIH26187
          </p>

          <h2 className="text-6xl sm:text-7xl lg:text-9xl font-['Barlow_Condensed'] uppercase tracking-tight text-[#e8ebe6] leading-[0.85]">
            Make sense
            <br />
            of what <em className="text-[#00e5ff] not-italic">matters</em>.
          </h2>

          <p className="text-base sm:text-lg text-[#a5b0ae] font-mono leading-relaxed max-w-xl">
            Percepta is an intelligent edge platform transforming legacy border CCTV infrastructure into an automated perimeter defense command post — with local AI perception, tamper-proof audit trails, and zero cloud dependencies.
          </p>

        </div>

        {/* Bottom Footer Signature */}
        <div className="footer-signature w-full max-w-5xl flex flex-col sm:flex-row justify-between items-center gap-4 text-[9px] font-mono text-[#667273] border-t border-[rgba(207,220,214,0.16)] pt-6 mt-20">
          <span>PERCEPTA // BORDER WATCH COMMAND POST (SIH26187)</span>
          <span>EDGE NEURAL PERCEPTION · KALMAN BYTETRACK · SHA-256 CUSTODY</span>
          <span>© 2026 MINISTRY OF HOME AFFAIRS / DEFENSE INFRASTRUCTURE</span>
        </div>
      </section>
    </main>
  );
}
