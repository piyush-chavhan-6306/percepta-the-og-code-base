import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { authService } from "@/features/auth/authService.adapter";
import { StarsBackground } from "@/features/shared/components/StarsBackground";
import { PerceptaLogo } from "@/features/shared/components/PerceptaLogo";
import {
  Shield,
  Lock,
  ArrowRight,
  Loader2,
  UserCheck,
  KeyRound,
  ShieldAlert,
  CheckCircle2,
  ChevronLeft,
  Eye,
  EyeOff,
  Radio,
  Sparkles,
  Terminal,
} from "lucide-react";
import "@/features/shared/styles/designTokens.css";
import "@/features/auth/styles/Auth.css";

interface AuthProps {
  redirectAfterAuth?: string;
}

export default function Auth({ redirectAfterAuth = "/dashboard" }: AuthProps) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = searchParams.get("redirect") || searchParams.get("returnTo") || redirectAfterAuth;

  const [mode, setMode] = useState<"signin" | "request">("signin");
  const [email, setEmail] = useState("operator");
  const [password, setPassword] = useState("operator123");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState("");
  const [recoverySent, setRecoverySent] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (mode === "request") {
      if (password !== confirmPassword) {
        setErrorMessage("PASSPHRASES DO NOT MATCH // VERIFICATION FAILED");
        return;
      }
      if (password.length < 6) {
        setErrorMessage("PASSPHRASE LENGTH INSUFFICIENT // MINIMUM 6 CHARACTERS");
        return;
      }
    }

    setIsLoading(true);

    try {
      if (mode === "signin") {
        const res = await authService.login({
          emailOrCallsign: email,
          password: password,
        });

        if (res.success) {
          setSuccessMessage("OPERATOR CLEARANCE VERIFIED // ACCESS GRANTED");
          setTimeout(() => {
            navigate(returnTo);
          }, 350);
        } else {
          setErrorMessage(res.error || "ACCESS DENIED // INVALID CLEARANCE CREDENTIALS");
        }
      } else {
        const res = await authService.register({
          emailOrCallsign: email,
          password: password,
        });

        if (res.success) {
          setSuccessMessage("OPERATOR CLEARANCE REGISTERED // LOGGING IN...");
          setTimeout(() => navigate(returnTo), 600);
        } else {
          setErrorMessage(res.error || "CLEARANCE REGISTRATION REJECTED");
        }
      }
    } catch (err: any) {
      setErrorMessage(err?.message || "GATEWAY HANDSHAKE TIMEOUT");
    } finally {
      setIsLoading(false);
    }
  };

  const handleOAuth = async (provider: "google" | "github" | "azure") => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await authService.loginOAuth(provider);
      if (res.success) {
        navigate(returnTo);
      } else {
        setErrorMessage(res.error || `${provider.toUpperCase()} FEDERATION ERROR`);
      }
    } catch (err: any) {
      setErrorMessage(err?.message || "SSO GATEWAY TIMEOUT");
    } finally {
      setIsLoading(false);
    }
  };


  const handleRecoverySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recoveryEmail) return;
    setIsLoading(true);
    await authService.resetPassword(recoveryEmail);
    setIsLoading(false);
    setRecoverySent(true);
  };

  return (
    <div className="min-h-screen w-full bg-background text-foreground flex flex-col justify-between p-4 relative overflow-hidden font-mono selection:bg-primary selection:text-black">
      {/* 3D WebGL Starfield Atmosphere */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <StarsBackground />
        {/* Layered radial glow anchors matching Old Percepta C2 */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[650px] h-[650px] bg-primary/10 rounded-full blur-[160px] pointer-events-none" />
        <div className="absolute top-1/4 left-1/4 w-[350px] h-[350px] bg-[#2979ff]/10 rounded-full blur-[140px] pointer-events-none" />
      </div>

      {/* Top Header Navigation */}
      <header className="relative z-10 w-full max-w-6xl mx-auto flex items-center justify-between py-4 px-2">
        <Link to="/" className="flex items-center gap-3">
          <PerceptaLogo size={30} showText={true} />
        </Link>

        <Link
          to="/"
          className="text-xs font-mono text-muted-foreground hover:text-primary transition-colors flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/5 bg-black/30 backdrop-blur-md"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          <span>RETURN TO RECON</span>
        </Link>
      </header>

      {/* Main Authentication Terminal */}
      <main className="relative z-10 w-full max-w-md mx-auto my-auto py-6">
        <div className="glass-card rounded-2xl border border-white/10 bg-[#0d1322]/85 backdrop-blur-2xl shadow-[0_20px_60px_rgba(0,0,0,0.6)] relative p-6 sm:p-8">
          {/* Tactical Corner Brackets (Old Percepta C2) */}
          <div className="absolute top-2 left-2 w-4 h-4 border-t-2 border-l-2 border-primary/50 rounded-tl-md pointer-events-none" />
          <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-primary/50 rounded-tr-md pointer-events-none" />
          <div className="absolute bottom-2 left-2 w-4 h-4 border-b-2 border-l-2 border-primary/50 rounded-bl-md pointer-events-none" />
          <div className="absolute bottom-2 right-2 w-4 h-4 border-b-2 border-r-2 border-primary/50 rounded-br-md pointer-events-none" />

          {/* Header Shield + Title */}
          <div className="text-center pb-5">
            <div className="relative inline-block mb-3">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/30 flex items-center justify-center mx-auto text-primary shadow-lg shadow-primary/20">
                <Shield className="w-6 h-6" />
              </div>
              <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-emerald-400 border-2 border-[#0d1322] shadow-[0_0_6px_#34d399]" />
            </div>

            <h1 className="text-xl font-bold tracking-wider font-['Orbitron',sans-serif] uppercase text-white">
              COMMAND CLEARANCE AUTH
            </h1>
            <p className="text-[11px] text-muted-foreground font-mono mt-1">
              Autonomous AI Border Surveillance Security Station
            </p>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="grid grid-cols-2 gap-1 p-1 bg-black/40 rounded-lg border border-white/5 mb-5">
            <button
              type="button"
              onClick={() => {
                setMode("signin");
                setErrorMessage(null);
              }}
              className={`py-2 text-[10px] font-mono font-bold tracking-wider uppercase rounded-md transition-all cursor-pointer ${
                mode === "signin"
                  ? "bg-primary text-black shadow-[0_0_12px_rgba(0,229,255,0.4)]"
                  : "text-muted-foreground hover:text-white"
              }`}
            >
              OPERATOR SIGN IN
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("request");
                setErrorMessage(null);
              }}
              className={`py-2 text-[10px] font-mono font-bold tracking-wider uppercase rounded-md transition-all cursor-pointer ${
                mode === "request"
                  ? "bg-primary text-black shadow-[0_0_12px_rgba(0,229,255,0.4)]"
                  : "text-muted-foreground hover:text-white"
              }`}
            >
              REQUEST CLEARANCE
            </button>
          </div>

          {/* Feedback Alerts */}
          {errorMessage && (
            <div className="p-3 mb-4 rounded-lg bg-red-950/40 border border-red-500/40 text-red-300 text-xs font-mono flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {successMessage && (
            <div className="p-3 mb-4 rounded-lg bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs font-mono flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="callsign" className="text-xs font-semibold text-foreground flex items-center justify-between">
                <span>OPERATOR CALLSIGN / USERNAME</span>
                <span className="text-[10px] text-muted-foreground/60 font-mono">SECTOR ALPHA</span>
              </label>
              <div className="relative">
                <input
                  id="callsign"
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-10 bg-black/60 border border-white/10 focus:border-primary rounded-lg text-xs font-mono pl-9 pr-3 text-white transition-all outline-none"
                  placeholder="operator"
                  required
                />
                <UserCheck className="w-4 h-4 text-muted-foreground absolute left-3 top-3" />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label htmlFor="pin" className="text-xs font-semibold text-foreground">
                  SECURITY PASSPHRASE
                </label>
                {mode === "signin" && (
                  <button
                    type="button"
                    onClick={() => setShowForgotModal(true)}
                    className="text-[10px] text-primary/80 hover:text-primary transition-colors bg-transparent border-none cursor-pointer p-0"
                  >
                    RECOVER CIPHER?
                  </button>
                )}
              </div>
              <div className="relative">
                <input
                  id="pin"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-10 bg-black/60 border border-white/10 focus:border-primary rounded-lg text-xs font-mono pl-9 pr-10 text-white transition-all outline-none"
                  placeholder="••••••••"
                  required
                />
                <KeyRound className="w-4 h-4 text-muted-foreground absolute left-3 top-3" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3 text-muted-foreground hover:text-white bg-transparent border-none cursor-pointer p-0"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {mode === "request" && (
              <div className="space-y-1.5">
                <label htmlFor="confirmPin" className="text-xs font-semibold text-foreground">
                  CONFIRM PASSPHRASE
                </label>
                <div className="relative">
                  <input
                    id="confirmPin"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full h-10 bg-black/60 border border-white/10 focus:border-primary rounded-lg text-xs font-mono pl-9 pr-3 text-white transition-all outline-none"
                    placeholder="••••••••"
                    required
                  />
                  <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-3" />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full h-11 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-mono text-xs font-bold shadow-[0_0_20px_rgba(0,229,255,0.35)] flex items-center justify-center gap-2 transition-all cursor-pointer border border-primary/40 disabled:opacity-50 mt-2"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin text-black" />
              ) : (
                <>
                  <Lock className="w-3.5 h-3.5 text-black" />
                  <span className="text-black uppercase tracking-wider">
                    {mode === "signin" ? "AUTHENTICATE & ENTER C2" : "REGISTER OPERATOR"}
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-black" />
                </>
              )}
            </button>
          </form>

          {/* Tactical SSO federation */}
          <div className="mt-6 pt-5 border-t border-white/[0.08]">
            <span className="text-[10px] font-mono text-muted-foreground/60 uppercase block text-center mb-3">
              or sign with
            </span>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                type="button"
                onClick={() => handleOAuth("google")}
                className="py-2.5 px-3 rounded bg-black/40 hover:bg-black/80 border border-white/10 hover:border-primary/40 text-xs font-mono text-muted-foreground hover:text-white transition-all text-center flex items-center justify-center gap-2"
              >
                <span>GOOGLE</span>
              </button>
              <button
                type="button"
                onClick={() => handleOAuth("github")}
                className="py-2.5 px-3 rounded bg-black/40 hover:bg-black/80 border border-white/10 hover:border-primary/40 text-xs font-mono text-muted-foreground hover:text-white transition-all text-center flex items-center justify-center gap-2"
              >
                <span>GITHUB</span>
              </button>
            </div>
          </div>
        </div>

        {/* Security Enclave Hardware Footer */}
        <div className="mt-4 p-3 rounded-xl bg-black/40 border border-white/5 text-[10px] text-muted-foreground/80 leading-relaxed text-center">
          DEFCON Sector 7 Node • Cryptographically signed hardware terminal.
        </div>
      </main>

      {/* Forgot Password Modal */}
      {showForgotModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
          <div className="glass-card rounded-2xl border border-white/15 bg-[#080c13] p-6 max-w-sm w-full relative">
            <h2 className="text-sm font-bold font-['Orbitron',sans-serif] uppercase text-white mb-2">
              DISPATCH RECOVERY CIPHER
            </h2>
            <p className="text-[11px] font-mono text-muted-foreground mb-4">
              Enter registered operator callsign or secure email to dispatch a one-time cryptographic recovery cipher.
            </p>

            {recoverySent ? (
              <div className="p-3 rounded bg-emerald-950/40 border border-emerald-500/40 text-emerald-300 text-xs font-mono mb-4">
                RECOVERY PROTOCOL INITIATED // Check secure terminal dispatch.
              </div>
            ) : (
              <form onSubmit={handleRecoverySubmit} className="space-y-3">
                <input
                  type="text"
                  value={recoveryEmail}
                  onChange={(e) => setRecoveryEmail(e.target.value)}
                  placeholder="operator@defense.percepta.ai"
                  className="w-full h-10 bg-black/60 border border-white/10 focus:border-primary rounded-lg text-xs font-mono px-3 text-white outline-none"
                  required
                />
                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full h-10 rounded bg-primary text-black font-mono font-bold text-xs uppercase"
                >
                  DISPATCH CIPHER
                </button>
              </form>
            )}

            <button
              onClick={() => {
                setShowForgotModal(false);
                setRecoverySent(false);
              }}
              className="mt-3 w-full py-1 text-center text-xs font-mono text-muted-foreground hover:text-white"
            >
              CLOSE
            </button>
          </div>
        </div>
      )}

      {/* Bottom Legal / Defense Info */}
      <footer className="relative z-10 w-full max-w-6xl mx-auto py-3 text-center text-[10px] font-mono text-muted-foreground/50">
        PERCEPTA DEFENSE OPERATING SYSTEM • SIH26187 CONFIDENTIAL
      </footer>
    </div>
  );
}
