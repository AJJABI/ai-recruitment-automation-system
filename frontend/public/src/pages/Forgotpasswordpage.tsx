import { useState, useEffect } from "react";
import { Mail, ArrowRight, ArrowLeft, MailCheck } from "lucide-react";
import { useLocation } from "wouter";
import logoImg from "../assets/logo.png";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [ready, setReady] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [, navigate] = useLocation();

  useEffect(() => {
    const t = setTimeout(() => setReady(true), 60);
    return () => clearTimeout(t);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/auth/forgot-password`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email }),
        }
      );

      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "An error occurred.");
        return;
      }

      // Backend always returns a generic success message — no email enumeration
      setSent(true);
    } catch {
      setError("Unable to connect to the server.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }

        @keyframes panelLeft {
          from { opacity:0; transform: translateX(-30px); }
          to   { opacity:1; transform: translateX(0); }
        }
        @keyframes panelRight {
          from { opacity:0; transform: translateX(30px); }
          to   { opacity:1; transform: translateX(0); }
        }
        @keyframes fadeUp {
          from { opacity:0; transform: translateY(16px); }
          to   { opacity:1; transform: translateY(0); }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes successPop {
          0%   { transform: scale(0.5); opacity: 0; }
          70%  { transform: scale(1.1); }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes floatLogo { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }

        .panel-left  { animation: panelLeft  0.55s cubic-bezier(.22,.68,0,1.2) both; }
        .panel-right { animation: panelRight 0.55s cubic-bezier(.22,.68,0,1.2) 0.1s both; }

        .fu1 { animation: fadeUp 0.45s ease 0.35s both; }
        .fu2 { animation: fadeUp 0.45s ease 0.45s both; }
        .fu3 { animation: fadeUp 0.45s ease 0.55s both; }
        .fu4 { animation: fadeUp 0.45s ease 0.60s both; }

        .logo-float { animation: floatLogo 4s ease-in-out infinite; }

        .inp {
          width: 100%;
          padding: 11px 13px 11px 38px;
          border: 1.5px solid #e2e8f0;
          border-radius: 10px;
          font-size: 14px;
          outline: none;
          transition: border-color 0.2s, box-shadow 0.2s;
          font-family: 'Inter', sans-serif;
          color: #1e1b4b;
          background: #fafafa;
        }
        .inp:focus {
          border-color: #7c3aed;
          box-shadow: 0 0 0 3px rgba(124,58,237,0.12);
          background: #fff;
        }
        .inp::placeholder { color: #cbd5e1; }

        .btn-send {
          width: 100%;
          padding: 13px;
          background: linear-gradient(135deg, #7c3aed, #6d28d9);
          color: white;
          border: none;
          border-radius: 10px;
          font-size: 15px;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          transition: all 0.2s;
          font-family: 'Inter', sans-serif;
        }
        .btn-send:hover:not(:disabled) {
          background: linear-gradient(135deg, #6d28d9, #5b21b6);
          box-shadow: 0 7px 26px rgba(109,40,217,0.52);
          transform: translateY(-2px);
        }
        .btn-send:disabled { opacity: .72; cursor: not-allowed; }

        .back-link {
          display: flex; align-items: center; gap: 6px;
          font-size: 13px; color: #64748b; text-decoration: none;
          font-weight: 500; transition: color 0.2s;
          background: none; border: none; cursor: pointer;
          font-family: 'Inter', sans-serif; padding: 0;
        }
        .back-link:hover { color: #7c3aed; }

        .divider {
          position: absolute; top: 0; bottom: 0; left: 0;
          width: 1px;
          background: linear-gradient(to bottom, transparent, rgba(255,255,255,0.12) 30%, rgba(255,255,255,0.12) 70%, transparent);
        }

        .success-icon { animation: successPop 0.5s cubic-bezier(.22,.68,0,1.2) both; }
      `}</style>

      <div style={{ display: "flex", minHeight: "100vh", width: "100%", fontFamily: "'Inter','Segoe UI',sans-serif", overflow: "hidden" }}>

        {/* ── LEFT PANEL ── */}
        <div
          className={ready ? "panel-left" : ""}
          style={{
            flex: "0 0 55%",
            position: "relative",
            background: "linear-gradient(145deg, #0d1b2e 0%, #0f2040 40%, #0a1628 70%, #0d1535 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-start",
            padding: "60px 64px",
            overflow: "hidden",
            opacity: ready ? undefined : 0,
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
            <polygon points="200,340 360,180 480,320 320,460" fill="#112030" />
            <polygon points="480,320 620,200 700,380 560,480" fill="#152a40" />
            <polygon points="700,380 800,320 800,520 680,560" fill="#1e3a5c" />
            <polygon points="120,480 320,460 200,600 0,600" fill="#0a1828" />
          </svg>

          <div style={{
            position: "absolute", top: "30%", left: "20%",
            width: 300, height: 300,
            background: "radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 70%)",
            pointerEvents: "none",
          }} />

          <div style={{ position: "relative", zIndex: 2, maxWidth: 380 }}>
            <div className="logo-float" style={{ marginBottom: 28 }}>
              <img src={logoImg} alt="Dynamix" style={{ width: 72, height: 72, objectFit: "contain" }} />
            </div>

            <div style={{ fontSize: 42, fontWeight: 800, color: "#ffffff", lineHeight: 1.1, letterSpacing: "-0.025em", marginBottom: 8 }}>
              Reset your<br />password
            </div>

            <div style={{ marginTop: 20, display: "flex", gap: 10, alignItems: "flex-start" }}>
              <div style={{
                width: 3, flexShrink: 0, marginTop: 2, borderRadius: 2, alignSelf: "stretch",
                background: "linear-gradient(to bottom, #7c3aed, #a78bfa)",
              }} />
              <p style={{ fontSize: 14, color: "#94a3b8", lineHeight: 1.7 }}>
                Enter the email associated with your <strong style={{ color: "#a78bfa" }}>Dynamix Services</strong> account and we'll send you a link to reset your password.
              </p>
            </div>
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div
          className={ready ? "panel-right" : ""}
          style={{
            flex: 1,
            position: "relative",
            background: "#ffffff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "60px 64px",
            opacity: ready ? undefined : 0,
          }}
        >
          <div className="divider" />

          <div style={{ width: "100%", maxWidth: 340 }}>

            {sent ? (
              /* ── SUCCESS STATE ── */
              <div style={{ textAlign: "center" }}>
                <div className="success-icon" style={{
                  width: 80, height: 80, borderRadius: "50%",
                  background: "linear-gradient(135deg, #22c55e, #16a34a)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  margin: "0 auto 24px",
                  boxShadow: "0 8px 32px rgba(34,197,94,0.35)",
                }}>
                  <MailCheck size={38} color="white" />
                </div>
                <h2 style={{ fontSize: 22, fontWeight: 700, color: "#1e1b4b", marginBottom: 10 }}>
                  Check your inbox
                </h2>
                <p style={{ fontSize: 14, color: "#64748b", lineHeight: 1.6, marginBottom: 28 }}>
                  If an account exists for <strong>{email}</strong>, a reset link has been sent. The link is valid for 1 hour.
                </p>
                <button className="back-link" style={{ justifyContent: "center", width: "100%" }} onClick={() => navigate("/")}>
                  <ArrowLeft size={14} /> Back to login
                </button>
              </div>
            ) : (
              /* ── FORM ── */
              <>
                <div className="fu1" style={{ marginBottom: 32 }}>
                  <h1 style={{ fontSize: 26, fontWeight: 700, color: "#1e1b4b", letterSpacing: "-0.02em" }}>
                    Forgot password?
                  </h1>
                  <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 6 }}>
                    No worries, we'll send you reset instructions
                  </p>
                </div>

                <form onSubmit={handleSubmit}>
                  <div className="fu2" style={{ marginBottom: 24 }}>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#64748b", marginBottom: 7, letterSpacing: "0.03em" }}>
                      Email
                    </label>
                    <div style={{ position: "relative" }}>
                      <Mail size={15} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
                      <input
                        type="email" className="inp" value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="Enter your email" autoComplete="email" required
                      />
                    </div>
                  </div>

                  {error && (
                    <div className="fu3" style={{
                      marginBottom: 16, padding: "10px 14px",
                      background: "#fef2f2", border: "1px solid #fecaca",
                      borderRadius: 8, fontSize: 13, color: "#dc2626",
                    }}>
                      {error}
                    </div>
                  )}

                  <div className="fu3">
                    <button type="submit" className="btn-send" disabled={isLoading}>
                      {isLoading ? (
                        <svg style={{ animation: "spin 0.75s linear infinite" }} width="18" height="18" viewBox="0 0 24 24" fill="none">
                          <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.25)" strokeWidth="3" />
                          <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                        </svg>
                      ) : (
                        <><span>Send reset link</span><ArrowRight size={16} /></>
                      )}
                    </button>
                  </div>
                </form>

                <div className="fu4" style={{ marginTop: 24, textAlign: "center" }}>
                  <button className="back-link" style={{ justifyContent: "center", width: "100%" }} onClick={() => navigate("/")}>
                    <ArrowLeft size={14} /> Back to login
                  </button>
                </div>
              </>
            )}

          </div>
        </div>
      </div>
    </>
  );
}