import { useState, useEffect, useRef } from "react";
import { Eye, EyeOff, Mail, Lock, ArrowRight } from "lucide-react";
import { useLocation } from "wouter";
import logoImg from "../assets/logo.png";

// ─── Helpers JWT ──────────────────────────────────────────────────────────────

/** Decodes a JWT payload without signature verification (client-side). */
function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return {};
  }
}

// ─── NetworkCanvas (unchanged) ────────────────────────────────────────────────

function NetworkCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const resize = () => {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    };
    resize();
    window.addEventListener("resize", resize);

    type Node = { x: number; y: number; vx: number; vy: number };
    const nodes: Node[] = Array.from({ length: 42 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.38,
      vy: (Math.random() - 0.5) * 0.38,
    }));

    let id: number;
    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      nodes.forEach((n) => {
        n.x += n.vx;
        n.y += n.vy;
        if (n.x < 0 || n.x > canvas.width) n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
      });

      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 130) {
            const alpha = (1 - dist / 130) * 0.35;
            ctx.globalAlpha = alpha;
            ctx.strokeStyle = "#7c6fff";
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(nodes[i].x, nodes[i].y);
            ctx.lineTo(nodes[j].x, nodes[j].y);
            ctx.stroke();

            if (dist < 70) {
              const k = (i * 7 + j * 13) % nodes.length;
              ctx.globalAlpha = 0.07;
              ctx.fillStyle = "#4f46e5";
              ctx.beginPath();
              ctx.moveTo(nodes[i].x, nodes[i].y);
              ctx.lineTo(nodes[j].x, nodes[j].y);
              ctx.lineTo(nodes[k].x, nodes[k].y);
              ctx.closePath();
              ctx.fill();
            }
          }
        }
      }

      nodes.forEach((n) => {
        ctx.globalAlpha = 0.7;
        ctx.fillStyle = "#a78bfa";
        ctx.beginPath();
        ctx.arc(n.x, n.y, 2, 0, Math.PI * 2);
        ctx.fill();

        ctx.globalAlpha = 0.25;
        ctx.fillStyle = "#c4b5fd";
        ctx.beginPath();
        ctx.arc(n.x, n.y, 5, 0, Math.PI * 2);
        ctx.fill();
      });

      ctx.globalAlpha = 1;
      id = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
    />
  );
}

function TypewriterOnce({ text, speed = 80 }: { text: string; speed?: number }) {
  const [displayed, setDisplayed] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    let i = 0;
    let timer: ReturnType<typeof setTimeout>;
    const step = () => {
      if (i <= text.length) {
        setDisplayed(text.slice(0, i));
        i++;
        if (i > text.length) { setDone(true); return; }
        timer = setTimeout(step, speed);
      }
    };
    timer = setTimeout(step, 1200);
    return () => clearTimeout(timer);
  }, [text, speed]);

  return (
    <>
      {displayed}
      {!done && (
        <span style={{
          display: "inline-block", width: 2, height: "0.85em",
          background: "#a78bfa", borderRadius: 1, marginLeft: 2,
          verticalAlign: "middle",
          animation: "blink 0.85s ease-in-out infinite",
        }} />
      )}
    </>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function LoginPage() {
  const [, navigate] = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  // If already logged in → redirect directly
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) {
      const payload = decodeJwtPayload(token);
      redirectByRole(payload.role as string, navigate);
    }
  }, [navigate]);

  useEffect(() => {
    const t = setTimeout(() => setReady(true), 60);
    return () => clearTimeout(t);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg(null);

    try {
      // FastAPI OAuth2 endpoint expects form-data (username / password)
      const formData = new FormData();
      formData.append("username", email);
      formData.append("password", password);

      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/auth/login`,
        { method: "POST", body: formData }
      );

      if (response.status === 401) {
        setErrorMsg("Incorrect email or password.");
        return;
      }
      if (!response.ok) {
        setErrorMsg(`Server error (${response.status}). Please try again.`);
        return;
      }

      const data = await response.json();
      const token: string = data.access_token;

      // Store under "access_token" (consistent key with MissionRegistry / JobDetail)
      localStorage.setItem("access_token", token);

      // Decode role from JWT and redirect
      const payload = decodeJwtPayload(token);
      redirectByRole(payload.role as string, navigate);

    } catch {
      setErrorMsg("Unable to reach the server. Please check your connection.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
        @keyframes spin   { to { transform: rotate(360deg); } }
        @keyframes panelLeft  { from { opacity:0; transform: translateX(-30px); } to { opacity:1; transform: translateX(0); } }
        @keyframes panelRight { from { opacity:0; transform: translateX(30px);  } to { opacity:1; transform: translateX(0); } }
        @keyframes logoIn     { 0%  { opacity:0; transform: scale(0.8) translateY(20px); filter:blur(6px); }
                                100%{ opacity:1; transform: scale(1) translateY(0);      filter:blur(0); } }
        @keyframes logoFloat  { 0%,100% { transform: translateY(0) rotate(-1deg); } 50% { transform: translateY(-10px) rotate(1deg); } }
        @keyframes shadowBreathe { 0%,100% { transform: scaleX(1); opacity:.35; } 50% { transform: scaleX(.78); opacity:.15; } }
        @keyframes titleSlide { from { opacity:0; transform: translateX(-24px); } to { opacity:1; transform: translateX(0); } }
        @keyframes riseUp     { from { opacity:0; transform: translateY(18px); } to { opacity:1; transform: translateY(0); } }

        .panel-left  { animation: panelLeft  0.7s cubic-bezier(.22,1,.36,1) forwards; }
        .panel-right { animation: panelRight 0.7s cubic-bezier(.22,1,.36,1) 0.1s forwards; }
        .logo-enter  { animation: logoIn 1s cubic-bezier(.22,1,.36,1) 0.4s both, logoFloat 5s ease-in-out 1.5s infinite; }
        .shadow-breathe { animation: shadowBreathe 5s ease-in-out 1.5s infinite; }
        .brand-slide { animation: titleSlide 0.7s cubic-bezier(.22,1,.36,1) 0.5s both; }
        .fu1 { animation: riseUp 0.5s ease 0.3s both; }
        .fu2 { animation: riseUp 0.5s ease 0.45s both; }
        .fu3 { animation: riseUp 0.5s ease 0.6s both; }
        .fu4 { animation: riseUp 0.5s ease 0.75s both; }
        .fu5 { animation: riseUp 0.5s ease 0.9s both; }

        .inp {
          width: 100%; padding: 11px 12px 11px 38px;
          border: 1.5px solid #e2e8f0; border-radius: 10px;
          font-size: 14px; color: #1e1b4b; background: #fafafa;
          outline: none; transition: border-color 0.2s, box-shadow 0.2s;
          font-family: inherit;
        }
        .inp:focus { border-color: #7c3aed; box-shadow: 0 0 0 3px rgba(124,58,237,0.12); background: #fff; }

        .btn-connect {
          width: 100%; padding: 13px 20px;
          background: linear-gradient(135deg, #7c3aed, #6d28d9);
          color: #fff; border: none; border-radius: 10px; cursor: pointer;
          font-size: 15px; font-weight: 600; letter-spacing: 0.01em;
          display: flex; align-items: center; justify-content: center; gap: 8px;
          transition: all 0.2s; font-family: inherit;
        }
        .btn-connect:hover:not(:disabled) {
          background: linear-gradient(135deg, #6d28d9, #5b21b6);
          box-shadow: 0 7px 26px rgba(109,40,217,0.52);
          transform: translateY(-2px);
        }
        .btn-connect:active { transform: translateY(0); }
        .btn-connect:disabled { opacity: .72; cursor: not-allowed; }

        .divider {
          position: absolute; top: 0; bottom: 0; left: 0; width: 1px;
          background: linear-gradient(to bottom, transparent, rgba(255,255,255,0.12) 30%, rgba(255,255,255,0.12) 70%, transparent);
        }
      `}</style>

      <div style={{ display: "flex", minHeight: "100vh", width: "100%", fontFamily: "'Inter','Segoe UI',sans-serif", overflow: "hidden" }}>

        {/* ── LEFT PANEL ── */}
        <div
          className={ready ? "panel-left" : ""}
          style={{
            flex: "0 0 55%", position: "relative",
            background: "linear-gradient(145deg, #0d1b2e 0%, #0f2040 40%, #0a1628 70%, #0d1535 100%)",
            display: "flex", alignItems: "center", justifyContent: "flex-start",
            padding: "60px 64px", overflow: "hidden", opacity: ready ? undefined : 0,
          }}
        >
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", opacity: 0.18 }}
            viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice">
            <polygon points="0,0 240,80 120,220" fill="#1e3a5f" />
            <polygon points="240,80 480,0 360,180" fill="#162d4a" />
            <polygon points="480,0 800,100 620,200" fill="#1a3456" />
            <polygon points="120,220 240,80 360,180 200,340" fill="#0e2235" />
            <polygon points="360,180 480,0 620,200 480,320" fill="#132840" />
            <polygon points="620,200 800,100 800,320 700,380" fill="#1c3a5e" />
          </svg>
          <NetworkCanvas />
          <div style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "linear-gradient(to right, rgba(13,27,46,0.2) 0%, transparent 60%)" }} />

          <div style={{ position: "relative", zIndex: 2 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", marginBottom: 32 }}>
              <div className="logo-enter">
                <img src={logoImg} alt="Dynamix" style={{ width: 100, height: 100, objectFit: "contain" }} />
              </div>
              <div className="shadow-breathe" style={{ width: 70, height: 12, marginTop: -6, borderRadius: "50%", background: "radial-gradient(ellipse, rgba(0,0,0,0.55) 0%, transparent 70%)" }} />
            </div>
            <div className="brand-slide">
              <div style={{ fontSize: 52, fontWeight: 800, color: "#ffffff", lineHeight: 1, letterSpacing: "-0.025em" }}>Dynamix</div>
              <div style={{ fontSize: 22, fontWeight: 600, color: "#f97316", letterSpacing: "0.14em", marginTop: 2 }}>services</div>
              <div style={{ marginTop: 20, display: "flex", gap: 10, alignItems: "flex-start", maxWidth: 320 }}>
                <div style={{ width: 3, height: 38, borderRadius: 2, flexShrink: 0, marginTop: 2, background: "linear-gradient(to bottom, #7c3aed, #a78bfa)" }} />
                <p style={{ fontSize: 14, color: "#a78bfa", lineHeight: 1.65, fontWeight: 400 }}>
                  <TypewriterOnce text="Dynamix Services internal platform — access restricted to employees." speed={55} />
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div
          className={ready ? "panel-right" : ""}
          style={{
            flex: 1, position: "relative", background: "#ffffff",
            display: "flex", alignItems: "center", justifyContent: "center",
            padding: "60px 64px", opacity: ready ? undefined : 0,
          }}
        >
          <div className="divider" />

          <div style={{ width: "100%", maxWidth: 340 }}>
            <div className="fu1" style={{ marginBottom: 36 }}>
              <h1 style={{ fontSize: 26, fontWeight: 700, color: "#1e1b4b", letterSpacing: "-0.02em" }}>Welcome</h1>
              <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 6 }}>Sign in to access your workspace</p>
            </div>

            <form onSubmit={handleSubmit}>
              {/* Email */}
              <div className="fu2" style={{ marginBottom: 20 }}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#64748b", marginBottom: 7, letterSpacing: "0.03em" }}>Email</label>
                <div style={{ position: "relative" }}>
                  <Mail size={15} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
                  <input
                    type="email" className="inp" value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email" autoComplete="email" required
                  />
                </div>
              </div>

              {/* Password */}
              <div className="fu3" style={{ marginBottom: 24 }}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#64748b", marginBottom: 7, letterSpacing: "0.03em" }}>Password</label>
                <div style={{ position: "relative" }}>
                  <Lock size={15} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
                  <input
                    type={showPassword ? "text" : "password"} className="inp" value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••" style={{ paddingRight: 44 }} autoComplete="current-password" required
                  />
                  <button
                    type="button" onClick={() => setShowPassword(!showPassword)}
                    style={{ position: "absolute", right: 13, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 0, color: "#94a3b8", display: "flex", alignItems: "center", transition: "color 0.2s" }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "#7c3aed")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "#94a3b8")}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {/* Error message */}
              {errorMsg && (
                <div style={{
                  marginBottom: 16, padding: "10px 14px", borderRadius: 8,
                  background: "#fef2f2", border: "1px solid #fca5a5",
                  fontSize: 13, color: "#991b1b", display: "flex", alignItems: "center", gap: 8,
                }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                  {errorMsg}
                </div>
              )}

              <div className="fu4">
                <button type="submit" className="btn-connect" disabled={isLoading}>
                  {isLoading ? (
                    <svg style={{ animation: "spin 0.75s linear infinite" }} width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.25)" strokeWidth="3" />
                      <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <><span>Sign in</span><ArrowRight size={16} /></>
                  )}
                </button>
              </div>
            </form>

            <div className="fu5" style={{ marginTop: 20, textAlign: "center" }}>
              <a
                href="/forgot-password"
                onClick={(e) => { e.preventDefault(); navigate("/forgot-password"); }}
                style={{ fontSize: 13, color: "#7c3aed", textDecoration: "none", fontWeight: 500, transition: "color 0.2s" }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#5b21b6")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "#7c3aed")}
              >
                Forgot your password?
              </a>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// ─── Helper ───────────────────────────────────────────────────────────────────

function redirectByRole(role: string, navigate: (path: string) => void) {
  if (role === "RH") {
    navigate("/rh/dashboard");
  } else if (role === "MANAGER") {
    navigate("/dashboard");
  } else {
    // Unknown role → redirect to login page to avoid inconsistent state
    navigate("/");
  }
}