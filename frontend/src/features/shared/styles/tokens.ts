/**
 * PERCEPTA DEFENSE OS — Design Tokens TypeScript Export
 * 
 * Can be imported into Tailwind configuration (tailwind.config.js / tailwind.config.ts)
 * or consumed directly in React/TypeScript styling systems.
 */

export const perceptaTokens = {
  colors: {
    void: "#050709",
    voidAlt: "#080b0e",
    surfaceDark: "#0a0e13",
    surfaceCard: "rgba(13, 18, 23, 0.95)",
    surfaceElevated: "#0f1420",
    
    // Accents
    cyan: "#9ee7df",
    cyanBright: "#00e5ff",
    cyanDim: "rgba(158, 231, 223, 0.45)",
    mint: "#33f0b4",
    mintActive: "#28dfa3",
    gold: "#d6c19b",
    amber: "#f59e0b",
    crimson: "#ef4444",
    
    // Typography
    textPrimary: "#e8ebe6",
    textBright: "#ffffff",
    textSecondary: "#cbd5e1",
    textMuted: "#869099",
    textDim: "#64748b",
    textPlaceholder: "#475569",
    
    // Borders
    borderLine: "rgba(207, 220, 214, 0.16)",
    borderSubtle: "#1b2530",
    borderLight: "#263544",
    borderHighlight: "#33f0b4",
  },
  
  fonts: {
    title: ["Teko", "Barlow Condensed", "sans-serif"],
    display: ["Barlow Condensed", "Anton", "sans-serif"],
    heading: ["Chakra Petch", "sans-serif"],
    mono: ["JetBrains Mono", "DM Mono", "monospace"],
    body: ["Space Grotesk", "Inter", "-apple-system", "sans-serif"],
  },
  
  shadows: {
    tacticalCard: "0 25px 50px -12px rgba(0, 0, 0, 0.6)",
    cyanGlowSm: "0 0 10px rgba(158, 231, 223, 0.3)",
    cyanGlowMd: "0 0 24px rgba(158, 231, 223, 0.25)",
    mintGlowSm: "0 0 10px rgba(51, 240, 180, 0.25)",
    mintGlowMd: "0 0 20px rgba(51, 240, 180, 0.35)",
  },
  
  transitions: {
    tacticalFast: "0.15s ease-in-out",
    tacticalNormal: "0.3s cubic-bezier(0.16, 1, 0.3, 1)",
    tacticalSlow: "0.6s cubic-bezier(0.16, 1, 0.3, 1)",
  },
} as const;

export default perceptaTokens;
