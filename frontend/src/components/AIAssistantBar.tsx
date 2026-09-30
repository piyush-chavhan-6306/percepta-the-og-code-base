import { useState } from "react";
import { api } from "@/api/client";
import { GroundedIntelligenceResponse } from "@/types/surveillance";
import {
  Bot,
  Send,
  ShieldCheck,
  AlertCircle,
  FileText,
  CheckCircle2,
  XCircle,
  Sparkles,
  Database,
  Terminal,
  Compass,
  Car,
  Moon,
} from "lucide-react";
import { Button } from "@/components/ui/button";

const SUGGESTIONS = [
  { label: "Why was the alert generated?", icon: AlertCircle },
  { label: "Track movement directions & speeds", icon: Compass },
  { label: "Vehicle & license plate detections", icon: Car },
  { label: "Night intrusions in sector", icon: Moon },
];

export function AIAssistantBar({ selectedCameraId }: { selectedCameraId?: string }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<GroundedIntelligenceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent, customQuery?: string) => {
    e?.preventDefault?.();
    const q = customQuery || query;
    if (!q.trim() || loading) return;

    setLoading(true);
    setError(null);

    try {
      const res = await api.queryIntelligence(q, selectedCameraId);
      setResponse(res);
      setQuery(q);
    } catch (err: any) {
      setError(err.message || "Failed to query intelligence engine");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-primary/20 border border-primary/30 flex items-center justify-center text-primary">
            <Bot className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-foreground font-mono uppercase tracking-wider">
              GROUNDED DEFENSE AI COPILOT
            </h3>
            <p className="text-[10px] text-muted-foreground font-mono">
              Factual SQL-verified intelligence • Zero biometric hallucination guardrails
            </p>
          </div>
        </div>

        {response && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-mono bg-primary/10 border border-primary/30 text-primary">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span className="font-semibold uppercase">
              STATUS: {response.grounding_status?.toUpperCase() || "GROUNDED"}
            </span>
          </div>
        )}
      </div>

      {/* Suggestion Chips */}
      <div className="flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((item, idx) => {
          const Icon = item.icon;
          return (
            <button
              key={idx}
              onClick={() => handleSubmit({} as any, item.label)}
              className="px-2.5 py-1 rounded-lg text-[10px] font-mono bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <Icon className="w-3 h-3 text-primary" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Query Input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask sector intelligence (e.g., 'Why was alert generated for CAM-01?' or 'What direction is Track 27 moving?')"
            className="w-full px-3.5 py-2.5 rounded-xl bg-black/60 border border-white/10 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50 focus:ring-1 focus:ring-primary/40 transition"
          />
        </div>
        <Button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-4 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground font-mono text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-primary/20"
        >
          {loading ? (
            <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
          ) : (
            <>
              <span>ASK</span>
              <Send className="w-3.5 h-3.5" />
            </>
          )}
        </Button>
      </form>

      {/* Error Display */}
      {error && (
        <div className="p-3 rounded-xl bg-red-950/40 border border-red-800/40 text-red-300 font-mono text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 3-Tier Grounded Response Display */}
      {response && (
        <div className="mt-1 p-4 rounded-xl bg-black/50 border border-white/10 flex flex-col gap-3 font-mono text-xs">
          {/* 1. Interpretation */}
          <div className="flex items-start gap-2.5 text-gray-200">
            <Sparkles className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
            <div>
              <span className="font-bold text-cyan-400 uppercase tracking-wider">
                [AI INTERPRETATION]:{" "}
              </span>
              <span className="leading-relaxed">{response.interpretation || "No interpretation available."}</span>
            </div>
          </div>

          {/* 2. Observed Facts */}
          {response.observed_facts && response.observed_facts.length > 0 && (
            <div className="border-t border-white/5 pt-2.5">
              <span className="text-[11px] text-emerald-400 font-bold flex items-center gap-1.5 mb-1.5 uppercase">
                <Database className="w-3.5 h-3.5" />
                [OBSERVED DATABASE FACTS]:
              </span>
              <ul className="list-disc list-inside text-[11px] text-gray-300 space-y-1 pl-1">
                {response.observed_facts.map((fact, i) => (
                  <li key={i} className="leading-relaxed">
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 3. Deterministic Rule Results */}
          {response.rule_results && response.rule_results.length > 0 && (
            <div className="border-t border-white/5 pt-2.5">
              <span className="text-[11px] text-amber-400 font-bold flex items-center gap-1.5 mb-1.5 uppercase">
                <ShieldCheck className="w-3.5 h-3.5" />
                [DETERMINISTIC RULE RESULTS]:
              </span>
              <ul className="list-disc list-inside text-[11px] text-amber-200/90 space-y-1 pl-1">
                {response.rule_results.map((rule, i) => (
                  <li key={i} className="leading-relaxed">
                    {rule}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
