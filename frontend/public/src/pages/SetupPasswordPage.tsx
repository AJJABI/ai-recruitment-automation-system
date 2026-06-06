import { useState, useEffect } from "react";
import { Lock, Eye, EyeOff, ShieldCheck, ArrowRight } from "lucide-react";
import { useLocation } from "wouter";

export default function SetupPasswordPage() {
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [ready, setReady] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState("");
    const [, navigate] = useLocation();

    // Retrieve token from URL
    const token = new URLSearchParams(window.location.search).get("token") || "";

    useEffect(() => {
        const t = setTimeout(() => setReady(true), 60);
        return () => clearTimeout(t);
    }, []);

    const strength = (() => {
        if (password.length === 0) return 0;
        let s = 0;
        if (password.length >= 8) s++;
        if (/[A-Z]/.test(password)) s++;
        if (/[0-9]/.test(password)) s++;
        if (/[^A-Za-z0-9]/.test(password)) s++;
        return s;
    })();

    const strengthLabel = ["", "Weak", "Fair", "Good", "Strong"][strength];
    const strengthColor = ["", "#ef4444", "#f97316", "#eab308", "#22c55e"][strength];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");

        if (password !== confirm) {
            setError("Passwords do not match.");
            return;
        }
        if (password.length < 8) {
            setError("Password must be at least 8 characters long.");
            return;
        }
        if (!token) {
            setError("Invalid or expired link.");
            return;
        }

        setIsLoading(true);
        try {
            const res = await fetch("http://localhost:8000/auth/setup-password", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token, new_password: password }),
            });

            if (!res.ok) {
                const data = await res.json();
                setError(data.detail || "An error occurred.");
                return;
            }

            setSuccess(true);
            setTimeout(() => navigate("/"), 3000);
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
        @keyframes pulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(124,58,237,0.4); }
          50%       { box-shadow: 0 0 0 12px rgba(124,58,237,0); }
        }

        .panel-left  { animation: panelLeft  0.55s cubic-bezier(.22,.68,0,1.2) both; }
        .panel-right { animation: panelRight 0.55s cubic-bezier(.22,.68,0,1.2) 0.1s both; }

        .fu1 { animation: fadeUp 0.45s ease 0.35s both; }
        .fu2 { animation: fadeUp 0.45s ease 0.45s both; }
        .fu3 { animation: fadeUp 0.45s ease 0.50s both; }
        .fu4 { animation: fadeUp 0.45s ease 0.55s both; }
        .fu5 { animation: fadeUp 0.45s ease 0.60s both; }

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

        .btn-setup {
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
          animation: pulse 2.5s infinite;
        }
        .btn-setup:hover:not(:disabled) {
          background: linear-gradient(135deg, #6d28d9, #5b21b6);
          box-shadow: 0 7px 26px rgba(109,40,217,0.52);
          transform: translateY(-2px);
        }
        .btn-setup:disabled { opacity: .72; cursor: not-allowed; animation: none; }

        .divider {
          position: absolute; top: 0; bottom: 0; left: 0;
          width: 1px;
          background: linear-gradient(to bottom, transparent, rgba(255,255,255,0.12) 30%, rgba(255,255,255,0.12) 70%, transparent);
        }

        .strength-bar {
          height: 4px;
          border-radius: 2px;
          transition: width 0.3s, background 0.3s;
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
                    {/* Geometric backdrop */}
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

                    {/* Decorative glow */}
                    <div style={{
                        position: "absolute", top: "30%", left: "20%",
                        width: 300, height: 300,
                        background: "radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 70%)",
                        pointerEvents: "none",
                    }} />

                    {/* Content */}
                    <div style={{ position: "relative", zIndex: 2, maxWidth: 380 }}>
                        {/* Icon */}
                        <div style={{
                            width: 72, height: 72, borderRadius: 20,
                            background: "linear-gradient(135deg, rgba(124,58,237,0.3), rgba(109,40,217,0.15))",
                            border: "1px solid rgba(124,58,237,0.4)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            marginBottom: 28,
                        }}>
                            <ShieldCheck size={34} color="#a78bfa" />
                        </div>

                        <div style={{ fontSize: 42, fontWeight: 800, color: "#ffffff", lineHeight: 1.1, letterSpacing: "-0.025em", marginBottom: 8 }}>
                            Set up your<br />password
                        </div>

                        <div style={{ marginTop: 20, display: "flex", gap: 10, alignItems: "flex-start" }}>
                            <div style={{
                                width: 3, flexShrink: 0, marginTop: 2, borderRadius: 2, alignSelf: "stretch",
                                background: "linear-gradient(to bottom, #7c3aed, #a78bfa)",
                            }} />
                            <p style={{ fontSize: 14, color: "#94a3b8", lineHeight: 1.7 }}>
                                You have been invited to join the Dynamix Services platform as a <strong style={{ color: "#a78bfa" }}>Manager</strong>. Choose a secure password to activate your account.
                            </p>
                        </div>

                        {/* Tips */}
                        <div style={{ marginTop: 32, display: "flex", flexDirection: "column", gap: 10 }}>
                            {["At least 8 characters", "One uppercase letter recommended", "One number recommended"].map((tip, i) => (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                    <div style={{
                                        width: 6, height: 6, borderRadius: "50%",
                                        background: "#7c3aed", flexShrink: 0,
                                    }} />
                                    <span style={{ fontSize: 13, color: "#64748b" }}>{tip}</span>
                                </div>
                            ))}
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

                        {success ? (
                            /* ── SUCCESS STATE ── */
                            <div style={{ textAlign: "center" }}>
                                <div className="success-icon" style={{
                                    width: 80, height: 80, borderRadius: "50%",
                                    background: "linear-gradient(135deg, #22c55e, #16a34a)",
                                    display: "flex", alignItems: "center", justifyContent: "center",
                                    margin: "0 auto 24px",
                                    boxShadow: "0 8px 32px rgba(34,197,94,0.35)",
                                }}>
                                    <ShieldCheck size={38} color="white" />
                                </div>
                                <h2 style={{ fontSize: 22, fontWeight: 700, color: "#1e1b4b", marginBottom: 10 }}>
                                    Account activated!
                                </h2>
                                <p style={{ fontSize: 14, color: "#64748b", lineHeight: 1.6 }}>
                                    Your password has been set successfully.<br />
                                    Redirecting to the login page…
                                </p>
                            </div>
                        ) : (
                            /* ── FORM ── */
                            <>
                                <div className="fu1" style={{ marginBottom: 32 }}>
                                    <h1 style={{ fontSize: 26, fontWeight: 700, color: "#1e1b4b", letterSpacing: "-0.02em" }}>
                                        Create your password
                                    </h1>
                                    <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 6 }}>
                                        Link valid for 24 hours — single use
                                    </p>
                                </div>

                                <form onSubmit={handleSubmit}>

                                    {/* Password */}
                                    <div className="fu2" style={{ marginBottom: 20 }}>
                                        <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#64748b", marginBottom: 7, letterSpacing: "0.03em" }}>
                                            New password
                                        </label>
                                        <div style={{ position: "relative" }}>
                                            <Lock size={15} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
                                            <input
                                                type={showPassword ? "text" : "password"}
                                                className="inp"
                                                value={password}
                                                onChange={(e) => setPassword(e.target.value)}
                                                placeholder="••••••••"
                                                style={{ paddingRight: 44 }}
                                                required
                                            />
                                            <button type="button" onClick={() => setShowPassword(!showPassword)}
                                                style={{ position: "absolute", right: 13, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 0, color: "#94a3b8", display: "flex", alignItems: "center" }}>
                                                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                                            </button>
                                        </div>

                                        {/* Strength bar */}
                                        {password.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                                                    {[1, 2, 3, 4].map((i) => (
                                                        <div key={i} className="strength-bar" style={{
                                                            flex: 1,
                                                            background: i <= strength ? strengthColor : "#e2e8f0",
                                                        }} />
                                                    ))}
                                                </div>
                                                <span style={{ fontSize: 11, color: strengthColor, fontWeight: 500 }}>
                                                    {strengthLabel}
                                                </span>
                                            </div>
                                        )}
                                    </div>

                                    {/* Confirm */}
                                    <div className="fu3" style={{ marginBottom: 24 }}>
                                        <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "#64748b", marginBottom: 7, letterSpacing: "0.03em" }}>
                                            Confirm password
                                        </label>
                                        <div style={{ position: "relative" }}>
                                            <Lock size={15} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "#94a3b8" }} />
                                            <input
                                                type={showConfirm ? "text" : "password"}
                                                className="inp"
                                                value={confirm}
                                                onChange={(e) => setConfirm(e.target.value)}
                                                placeholder="••••••••"
                                                style={{
                                                    paddingRight: 44,
                                                    borderColor: confirm && confirm !== password ? "#ef4444" : confirm && confirm === password ? "#22c55e" : undefined,
                                                }}
                                                required
                                            />
                                            <button type="button" onClick={() => setShowConfirm(!showConfirm)}
                                                style={{ position: "absolute", right: 13, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", padding: 0, color: "#94a3b8", display: "flex", alignItems: "center" }}>
                                                {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
                                            </button>
                                        </div>
                                        {confirm && confirm !== password && (
                                            <p style={{ fontSize: 11, color: "#ef4444", marginTop: 4 }}>Passwords do not match</p>
                                        )}
                                        {confirm && confirm === password && (
                                            <p style={{ fontSize: 11, color: "#22c55e", marginTop: 4 }}>✓ Passwords match</p>
                                        )}
                                    </div>

                                    {/* Error */}
                                    {error && (
                                        <div className="fu4" style={{
                                            marginBottom: 16, padding: "10px 14px",
                                            background: "#fef2f2", border: "1px solid #fecaca",
                                            borderRadius: 8, fontSize: 13, color: "#dc2626",
                                        }}>
                                            {error}
                                        </div>
                                    )}

                                    {/* Submit */}
                                    <div className="fu5">
                                        <button type="submit" className="btn-setup" disabled={isLoading}>
                                            {isLoading ? (
                                                <svg style={{ animation: "spin 0.75s linear infinite" }} width="18" height="18" viewBox="0 0 24 24" fill="none">
                                                    <circle cx="12" cy="12" r="10" stroke="rgba(255,255,255,0.25)" strokeWidth="3" />
                                                    <path d="M12 2a10 10 0 0 1 10 10" stroke="white" strokeWidth="3" strokeLinecap="round" />
                                                </svg>
                                            ) : (
                                                <><span>Activate my account</span><ArrowRight size={16} /></>
                                            )}
                                        </button>
                                    </div>

                                </form>
                            </>
                        )}

                    </div>
                </div>
            </div>
        </>
    );
}