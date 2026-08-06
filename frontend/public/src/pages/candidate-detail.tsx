/**
 * CandidateDetail.tsx — /candidates/:jobId/:candidateId
 * Thème Dashboard : sidebar pill violette flottante + background wave
 * ⚠️ Aucune modification backend — uniquement le rendu visuel.
 */

import { useState, useEffect } from "react";
import { useParams, useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Briefcase, Users, MessageSquare,
  ArrowLeft, Video, Code, Save,
  CheckCircle2, XCircle, 
  ExternalLink, AlertCircle, LogOut,
} from "lucide-react";
import bgWave  from "../assets/imagee.png";

import { API_BASE, authHeaders, getToken, getRoleFromToken } from "./managerShared";

// ─── Design tokens ─────────────────────────────────────────────────────────────
const TEAL        = "#0d9488";
const TEAL_BG     = "rgba(13,148,136,0.08)";
const TEAL_BORDER = "rgba(13,148,136,0.2)";
const TEXT_MAIN   = "#1c2a38";
const TEXT_SUB    = "#64748b";
const TEXT_MUTED  = "#94a3b8";
const BORDER_CARD = "#e8ecf0";
const NAVY        = "rgb(30,58,110)";
const NAVY_BG     = "rgba(30,58,110,0.05)";
const NAVY_BR     = "rgba(30,58,110,0.15)";
const AVATAR_PALETTE = ["#0d9488", "#0e7490", "#0369a1", "#7c3aed", "#065f46", "#9a3412"];

const DECISIONS = [
  { value: "VALIDÉ",        label: "Validate",     desc: "Move to next stage",             icon: CheckCircle2,  color: "#16a34a", bg: "#f0fdf4", border: "#bbf7d0", activeBg: "#dcfce7" },
  { value: "NON_RETENU",    label: "Not retained", desc: "Not suitable for this position", icon: XCircle,       color: "#dc2626", bg: "#fef2f2", border: "#fca5a5", activeBg: "#fee2e2" },
];

// ─── Nav ──────────────────────────────────────────────────────────────────────
const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

// ─── Floating label ────────────────────────────────────────────────────────────
function NavLabel({ label, visible }: { label: string; visible: boolean }) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, x: -10, scale: 0.88 }}
          animate={{ opacity: 1, x: 0,   scale: 1     }}
          exit   ={{ opacity: 0, x: -8,  scale: 0.92  }}
          transition={{ type: "spring", stiffness: 460, damping: 26, mass: 0.65 }}
          style={{
            position: "absolute", left: "calc(100% + 10px)", top: "50%",
            transform: "translateY(-50%)", pointerEvents: "none", zIndex: 200, whiteSpace: "nowrap",
          }}
        >
          <div style={{
            position: "absolute", right: "100%", top: "50%", transform: "translateY(-50%)",
            width: 0, height: 0, borderTop: "5px solid transparent",
            borderBottom: "5px solid transparent", borderRight: "6px solid #3b0d8e",
          }} />
          <div style={{
            background: "#3b0d8e", color: "#fff", fontSize: 15, fontWeight: 700,
            padding: "6px 14px", borderRadius: 10,
            boxShadow: "0 4px 18px rgba(60,12,120,0.30)", letterSpacing: "0.01em",
          }}>{label}</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ─── Sidebar — pill violette flottante ────────────────────────────────────────
function Sidebar() {
  const [location]   = useLocation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  return (
    <nav style={{
      position: "fixed", top: 140, left: 16, zIndex: 50,
      borderRadius: 30,
      background: "linear-gradient(180deg, #4a1d96 0%, #3b0d8e 55%, #2c0f70 100%)",
      boxShadow: "0 8px 32px rgba(60,12,120,0.30), 0 2px 8px rgba(0,0,0,0.15)",
      padding: "18px 8px",
      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      overflow: "visible", userSelect: "none", width: 58,
    }}>
      {NAV.map(({ href, icon: Icon, label }) => {
        const active  = location === href || location.startsWith(href + "/") || (href === "/dashboard" && location === "/");
        const hovered = hoveredKey === href;
        return (
          <Link key={href} href={href} style={{ textDecoration: "none", position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey(href)}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              style={{
                width: 40, height: 40, margin: "0 auto", borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer",
                background: active ? "rgba(255,255,255,0.20)" : hovered ? "rgba(255,255,255,0.11)" : "transparent",
                transition: "background 0.15s", position: "relative",
              }}
            >
              {active && (
                <motion.div
                  layoutId="activeBar"
                  style={{
                    position: "absolute", left: -7, top: "50%", y: "-50%",
                    width: 3, height: 18, borderRadius: 3, background: "#fff",
                  }}
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                />
              )}
              <Icon size={17} color={active ? "#ffffff" : "rgba(255,255,255,0.60)"} />
              <NavLabel label={label} visible={hovered} />
            </motion.div>
          </Link>
        );
      })}

      <div style={{ width: 32, height: 1, background: "rgba(255,255,255,0.14)", margin: "6px 0", flexShrink: 0 }} />

      {(() => {
        const hovered = hoveredKey === "__logout";
        return (
          <div style={{ position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey("__logout")}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              onClick={() => { localStorage.removeItem("access_token"); window.location.href = "/"; }}
              style={{
                width: 40, height: 40, margin: "0 auto", borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer",
                background: hovered ? "rgba(239,68,68,0.20)" : "transparent",
                transition: "background 0.15s", position: "relative",
              }}
            >
              <LogOut size={17} color={hovered ? "#fca5a5" : "rgba(255,255,255,0.48)"} />
              <NavLabel label="Log out" visible={hovered} />
            </motion.div>
          </div>
        );
      })()}
    </nav>
  );
}

// ─── Card wrapper ──────────────────────────────────────────────────────────────
function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.88)",
      backdropFilter: "blur(20px)",
      borderRadius: 18,
      border: "1px solid rgba(255,255,255,0.9)",
      overflow: "hidden",
      boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
      ...style,
    }}>
      {children}
    </div>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────
function Skel({ w, h, radius = 8 }: { w: number | string; h: number; radius?: number }) {
  return (
    <div style={{
      width: w, height: h, borderRadius: radius,
      background: "linear-gradient(90deg,#f1f5f9 25%,#e2e8f0 50%,#f1f5f9 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.5s infinite",
    }} />
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function Toast({ msg, type, onDone }: { msg: string; type: "ok" | "err"; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3200);
    return () => clearTimeout(t);
  }, [onDone]);
  return (
    <motion.div
      initial={{ opacity: 0, y: 24, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 16 }}
      style={{
        position: "fixed", bottom: 28, left: "50%", transform: "translateX(-50%)",
        zIndex: 200, display: "flex", alignItems: "center", gap: 10,
        padding: "12px 20px", borderRadius: 12,
        background: type === "ok" ? "#f0fdf4" : "#fef2f2",
        border: `1px solid ${type === "ok" ? "#bbf7d0" : "#fca5a5"}`,
        boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
        fontSize: 13, fontWeight: 600,
        color: type === "ok" ? "#15803d" : "#991b1b",
        minWidth: 280, maxWidth: 440,
      }}
    >
      {type === "ok" ? <CheckCircle2 size={16} style={{ flexShrink: 0 }} /> : <AlertCircle size={16} style={{ flexShrink: 0 }} />}
      <span>{msg}</span>
    </motion.div>
  );
}

// ─── Section primitives ───────────────────────────────────────────────────────
function SectionCard({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
      borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)",
      overflow: "hidden", boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
      ...style,
    }}>
      {children}
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)", background: "rgba(248,250,252,0.8)" }}>
      {children}
    </div>
  );
}

function SectionBody({ children }: { children: React.ReactNode }) {
  return <div style={{ padding: "18px 20px" }}>{children}</div>;
}

// ─── ScoreBar ─────────────────────────────────────────────────────────────────
function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color: TEXT_SUB }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color, fontFamily: "monospace" }}>{Math.round(value)}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 99, background: "#f1f5f9", overflow: "hidden" }}>
        <div style={{ height: "100%", borderRadius: 99, background: color, width: `${Math.min(value, 100)}%`, transition: "width 0.7s ease-out" }} />
      </div>
    </div>
  );
}

// ─── TestAnswersSection ───────────────────────────────────────────────────────
const PAGE_SIZE = 5;

function TestAnswersSection({ testResults }: { testResults: any }) {
  const [visible, setVisible] = useState(false);
  const [page, setPage]       = useState(0);
  const results    = testResults.results ?? [];
  const totalPts   = results.reduce((a: number, r: any) => a + (r.points_earned ?? 0), 0);
  const maxPts     = results.reduce((a: number, r: any) => a + (r.points_max ?? 0), 0);
  const totalPages = Math.ceil(results.length / PAGE_SIZE);
  const pageItems  = results.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  return (
    <SectionCard>
      <SectionHeader>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ padding: 6, borderRadius: 8, background: NAVY_BG, border: `1px solid ${NAVY_BR}` }}>
              <Code size={13} style={{ color: NAVY }} />
            </div>
            <span style={{ fontSize: 12, fontWeight: 700, color: NAVY, letterSpacing: "0.08em", textTransform: "uppercase" as const }}>Test Answers</span>
            <span style={{ fontSize: 11, color: TEXT_MUTED }}>{results.length} questions</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {testResults.flags?.map((f: string) => (
              <span key={f} style={{ fontSize: 9, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: "#fef2f2", color: "#dc2626", border: "1px solid #fca5a5" }}>{f}</span>
            ))}
            <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 99, background: NAVY_BG, color: NAVY, border: `1px solid ${NAVY_BR}` }}>
              {totalPts} / {maxPts} pts
            </span>
            <button
              onClick={() => { setVisible(v => !v); setPage(0); }}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "5px 12px", borderRadius: 8, cursor: "pointer",
                fontSize: 11, fontWeight: 700,
                background: NAVY_BG, border: `1px solid ${NAVY_BR}`, color: NAVY, transition: "all 0.15s",
              }}
            >
              {visible ? "▲ Hide" : "▼ Show answers"}
            </button>
          </div>
        </div>
      </SectionHeader>

      {visible && (
        <SectionBody>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {pageItems.map((r: any, i: number) => {
              const globalIdx = page * PAGE_SIZE + i;
              const passed = (r.points_earned ?? 0) > 0;
              return (
                <div key={globalIdx} style={{
                  padding: "12px 14px", borderRadius: 12,
                  background: passed ? "#f0fdf4" : "#fef2f2",
                  border: `1px solid ${passed ? "#bbf7d0" : "#fca5a5"}`,
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: NAVY_BG, color: NAVY, border: `1px solid ${NAVY_BR}` }}>{r.skill}</span>
                      <span style={{ fontSize: 10, color: TEXT_MUTED }}>{r.difficulty} · {r.type}</span>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: passed ? "#16a34a" : "#dc2626" }}>
                      {r.points_earned ?? 0}/{r.points_max ?? 1} pts
                    </span>
                  </div>
                  {r.question && (
                    <p style={{ fontSize: 12, color: TEXT_MAIN, margin: "0 0 10px", lineHeight: 1.5, fontWeight: 600 }}>
                      Q{globalIdx + 1}: {r.question}
                    </p>
                  )}
                  <div style={{ padding: "8px 12px", borderRadius: 8, background: "#fff", border: "1px solid #e2e8f0", marginBottom: 6 }}>
                    <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase" as const, color: TEXT_SUB, margin: "0 0 4px" }}>Candidate Answer</p>
                    <p style={{ fontSize: 12, color: "#374151", margin: 0, fontFamily: "monospace" }}>
                      {r.candidate_answer !== undefined && r.candidate_answer !== null
                        ? String(r.candidate_answer)
                        : <span style={{ color: TEXT_MUTED, fontStyle: "italic" }}>No answer provided</span>}
                    </p>
                  </div>
                  {r.feedback && (
                    <div style={{ padding: "8px 12px", borderRadius: 8, background: passed ? "rgba(22,163,74,0.05)" : "rgba(220,38,38,0.05)", border: `1px solid ${passed ? "#bbf7d0" : "#fca5a5"}` }}>
                      <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase" as const, color: passed ? "#16a34a" : "#dc2626", margin: "0 0 4px" }}>Correction</p>
                      <p style={{ fontSize: 12, color: passed ? "#15803d" : "#b91c1c", margin: 0, lineHeight: 1.5 }}>{r.feedback}</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {totalPages > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 14, paddingTop: 12, borderTop: "1px solid rgba(241,245,249,0.8)" }}>
              <span style={{ fontSize: 11, color: TEXT_MUTED }}>{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, results.length)} of {results.length}</span>
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                  style={{ padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: page === 0 ? "not-allowed" : "pointer", background: page === 0 ? "#f1f5f9" : TEAL_BG, border: `1px solid ${page === 0 ? "#e2e8f0" : TEAL_BORDER}`, color: page === 0 ? TEXT_MUTED : TEAL, opacity: page === 0 ? 0.5 : 1 }}>
                  ← Prev
                </button>
                <button onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page === totalPages - 1}
                  style={{ padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: page === totalPages - 1 ? "not-allowed" : "pointer", background: page === totalPages - 1 ? "#f1f5f9" : TEAL_BG, border: `1px solid ${page === totalPages - 1 ? "#e2e8f0" : TEAL_BORDER}`, color: page === totalPages - 1 ? TEXT_MUTED : TEAL, opacity: page === totalPages - 1 ? 0.5 : 1 }}>
                  Next →
                </button>
              </div>
            </div>
          )}
        </SectionBody>
      )}
    </SectionCard>
  );
}

// ─── Types ────────────────────────────────────────────────────────────────────
interface RHReport {
  status?    : string;
  status_v2? : string;
  score_final?: number;
  score_matching?: number;
  score_motivation?: number;
  technical_score?: number;
  summary?: string;
  strengths?: string[];
  weaknesses?: string[];
  interview_questions?: string[];
  message?: string;
  manager_review?: {          // ← AJOUTER ICI
    decision?: string;
    note?    : string;
  };
  [key: string]: unknown;
}

interface CVProfile {
  full_name: string;
  email: string;
  skills: string[];
  education: string[];
  professional_experience: string[];
  years_experience: number | null;
}

interface Job { id: number; title: string; }

// ─── Component ────────────────────────────────────────────────────────────────
export default function CandidateDetail() {
  const { jobId, candidateId } = useParams<{ jobId: string; candidateId: string }>();
  const [, navigate]           = useLocation();
  const role                   = getRoleFromToken();

  const [report,      setReport]      = useState<RHReport | null>(null);
  const [cv,          setCv]          = useState<CVProfile | null>(null);
  const [job,         setJob]         = useState<Job | null>(null);
  const [meetLink,    setMeetLink]    = useState<string | null>(null);
  const [testResults, setTestResults] = useState<any | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);
  const [feedback,    setFeedback]    = useState("");
  const [recommendation, setRecommendation] = useState("VALIDÉ");
  const [submitting,  setSubmitting]  = useState(false);
  const [submitted,   setSubmitted]   = useState(false);
  const [toast,       setToast]       = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  const activeRec   = DECISIONS.find(d => d.value === recommendation)!;
  const displayName = cv?.full_name ?? report?.full_name as string ?? `Candidate #${candidateId}`;
  const avatarIdx   = parseInt(candidateId ?? "0") % AVATAR_PALETTE.length;

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }
    if (!jobId || !candidateId) return;
    setLoading(true); setError(null);

    Promise.all([
      fetch(`${API_BASE}/applications/${candidateId}/rh-report`, { headers: authHeaders() }),
      fetch(`${API_BASE}/cv-profiles/${candidateId}`,             { headers: authHeaders() }),
      fetch(`${API_BASE}/jobs/${jobId}`,                          { headers: authHeaders() }),
    ])
      .then(async ([rRes, cvRes, jRes]) => {
        if (jRes.status === 401) { localStorage.removeItem("access_token"); navigate("/login"); return; }
        if (!jRes.ok) throw new Error(`Job not found (${jRes.status})`);
        const [rData, cvData, jData] = await Promise.all([
          rRes.ok  ? rRes.json()  : null,
          cvRes.ok ? cvRes.json() : null,
          jRes.json(),
        ]);
        setReport(rData); setCv(cvData); setJob(jData);

        // ── Pré-remplir l'évaluation Manager si déjà soumise ──────────────
        if (rData?.manager_review) {
          const decisionMap: Record<string, string> = {
            "Validated"  : "VALIDÉ",
            "Non retenu" : "NON_RETENU",
            "To review"  : "NON_RETENU",
          };
          const raw = rData.manager_review.decision ?? "";
          setRecommendation(decisionMap[raw] ?? "VALIDÉ");
          setFeedback(rData.manager_review.note ?? "");
          setSubmitted(true); // verrouille le formulaire
        }
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Unknown error"))
      .finally(() => setLoading(false));

    fetch(`${API_BASE}/interviews/candidate-meet-link/${candidateId}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d?.meet_link && setMeetLink(d.meet_link))
      .catch(() => {});

    fetch(`${API_BASE}/applications/${candidateId}/test-results`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setTestResults(d))
      .catch(() => {});
  }, [jobId, candidateId]);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/applications/${candidateId}/manager-decision`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          test_id: null,
          manager_decision: recommendation,
          manager_note: feedback,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error((data?.detail as { message?: string })?.message ?? `Error ${res.status}`);
      setSubmitted(true);
      setToast({ msg: `Evaluation submitted — ${cv?.full_name ?? "Candidate"} marked ${recommendation.replace("_", " ").toLowerCase()}.`, type: "ok" });
    } catch (e: unknown) {
      setToast({ msg: e instanceof Error ? e.message : "Submission error.", type: "err" });
    } finally {
      setSubmitting(false);
    }
  };

  // Verrouiller le formulaire si déjà soumis dans cette session
  // OU si le candidat a déjà une décision enregistrée (manager_review présent ou statut final)
  const alreadyDecided =
    report?.manager_review != null ||
    ["ACCEPTED", "REJECTED_FINAL", "MANAGER_REJECTED", "NO_SHOW"].includes(
      report?.status_v2 ?? ""
    );
  const isLocked       = submitted || alreadyDecided;

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
      `}</style>

      <Sidebar />

      {/* ── Main — wave background ── */}
      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 48px", maxWidth: 1260, margin: "0 auto" }}>

          {/* ── TopBar ── */}
          <motion.div
            initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
            style={{ marginBottom: 28 }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                
              </div>
              <div style={{
                padding: "7px 14px", borderRadius: 999,
                background: "rgba(255,255,255,0.85)", backdropFilter: "blur(8px)",
                border: "1px solid rgba(255,255,255,0.9)",
                fontSize: 10, fontWeight: 700, color: TEXT_MUTED, letterSpacing: "0.18em",
                boxShadow: "0 1px 4px rgba(90,40,160,0.08)",
              }}>
                {dateLabel}
              </div>
            </div>

            {/* Back + candidate header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button
                onClick={() => navigate(`/candidates/${jobId}`)}
                style={{
                  width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                  background: "rgba(255,255,255,0.85)", backdropFilter: "blur(8px)",
                  border: "1px solid rgba(255,255,255,0.9)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer", color: TEXT_SUB,
                  boxShadow: "0 1px 4px rgba(90,40,160,0.08)", transition: "background 0.15s",
                }}
                onMouseEnter={e => (e.currentTarget.style.background = "rgba(255,255,255,0.97)")}
                onMouseLeave={e => (e.currentTarget.style.background = "rgba(255,255,255,0.85)")}
              >
                <ArrowLeft size={15} />
              </button>

              {loading ? (
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <Skel w={44} h={44} radius={99} />
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <Skel w={200} h={18} /><Skel w={130} h={12} />
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{
                    width: 44, height: 44, borderRadius: "50%", flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 14, fontWeight: 700, color: "#fff",
                    background: AVATAR_PALETTE[avatarIdx],
                    boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
                  }}>
                    {displayName.split(" ").map((p: string) => p[0]).join("").slice(0, 2) || "?"}
                  </div>
                  <div>
                    <h1 style={{ fontSize: 22, fontWeight: 700, color: TEXT_MAIN, margin: 0, lineHeight: 1.2 }}>{displayName}</h1>
                    <p style={{ fontSize: 12, color: TEXT_MUTED, margin: "4px 0 0" }}>{job?.title ?? `Job #${jobId}`}</p>
                  </div>
                </div>
              )}
            </div>
          </motion.div>

          {/* ── Error ── */}
          {error && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "12px 16px", borderRadius: 12, marginBottom: 20,
              background: "#fef2f2", border: "1px solid #fca5a5",
            }}>
              <AlertCircle size={15} color="#dc2626" style={{ flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: "#991b1b" }}>{error}</span>
            </div>
          )}

          {/* ── Video interview banner ── */}
          <motion.div
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              marginBottom: 20, gap: 12, padding: "14px 20px", borderRadius: 14,
              background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
              border: "1px solid rgba(255,255,255,0.9)",
              boxShadow: "0 2px 16px rgba(90,40,160,0.07)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ padding: 8, borderRadius: 10, background: "rgba(37,99,235,0.08)", border: "1px solid rgba(37,99,235,0.2)" }}>
                <Video size={16} style={{ color: "#3b82f6" }} />
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: TEXT_MAIN }}>Video Interview</div>
                <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 2 }}>
                  {report?.status === "INTERVIEW_DONE" ? "Interview completed" : meetLink ? "Zoom scheduled — ready to join" : "Session available"}
                  {" · "}
                  <span onClick={() => navigate("/interviews")} style={{ color: "#3b82f6", cursor: "pointer", textDecoration: "underline", textUnderlineOffset: 2 }}>
                    View schedule
                  </span>
                </div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {report?.status === "INTERVIEW_DONE" && (
                <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 10px", borderRadius: 99, background: "#f0fdf4", color: "#16a34a", border: "1px solid #bbf7d0" }}>Completed</span>
              )}
              <button
                onClick={() => meetLink ? window.open(meetLink, "_blank") : navigate("/interviews")}
                style={{
                  display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", borderRadius: 8,
                  background: meetLink ? "rgba(37,99,235,0.08)" : TEAL_BG,
                  border: `1px solid ${meetLink ? "rgba(37,99,235,0.25)" : TEAL_BORDER}`,
                  color: meetLink ? "#3b82f6" : TEAL,
                  cursor: "pointer", fontSize: 11, fontWeight: 700, transition: "opacity 0.15s",
                }}
                onMouseEnter={e => (e.currentTarget.style.opacity = "0.8")}
                onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
              >
                <ExternalLink size={12} />
                {meetLink ? "Join Zoom" : "View schedule"}
              </button>
            </div>
          </motion.div>

          {/* ── Main 2+1 grid ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 20, alignItems: "start" }}>

            {/* ── Left — Technical content ── */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

              {/* RH Summary scores */}
              
              {/* Interview questions */}
              {!loading && report && report.interview_questions && report.interview_questions.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
                  <SectionCard>
                    <SectionHeader>
                      <span style={{ fontSize: 12, fontWeight: 700, color: TEAL, textTransform: "uppercase" as const, letterSpacing: "0.08em" }}>
                        Suggested Interview Questions
                      </span>
                    </SectionHeader>
                    <SectionBody>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {report.interview_questions.map((q, i) => (
                          <div key={i} style={{
                            display: "flex", alignItems: "flex-start", gap: 10,
                            padding: "8px 12px", borderRadius: 8,
                            background: "rgba(248,250,252,0.8)", border: "1px solid rgba(241,245,249,0.8)",
                          }}>
                            <span style={{ fontSize: 10, fontWeight: 700, color: TEAL, flexShrink: 0, paddingTop: 1, fontFamily: "monospace" }}>Q{i + 1}</span>
                            <span style={{ fontSize: 12, color: TEXT_MAIN, lineHeight: 1.5 }}>{q}</span>
                          </div>
                        ))}
                      </div>
                    </SectionBody>
                  </SectionCard>
                </motion.div>
              )}

              {/* Test Answers */}
              {!loading && testResults?.available && testResults.results?.length > 0 && (
                <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }}>
                  <TestAnswersSection testResults={testResults} />
                </motion.div>
              )}

              {/* CV Profile */}
              {!loading && cv && (
                <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}>
                  <SectionCard>
                    <SectionHeader>
                      <h2 style={{ fontSize: 12, fontWeight: 700, color: NAVY, margin: 0, textTransform: "uppercase" as const, letterSpacing: "0.1em" }}>CV Profile</h2>
                    </SectionHeader>
                    <SectionBody>
                      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                        {cv.skills?.length > 0 && (
                          <div>
                            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase" as const, color: TEXT_MUTED, margin: "0 0 8px" }}>Skills</p>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                              {cv.skills.map(s => (
                                <span key={s} style={{ fontSize: 11, padding: "2px 9px", borderRadius: 99, background: NAVY_BG, color: NAVY, border: `1px solid ${NAVY_BR}`, fontWeight: 600 }}>{s}</span>
                              ))}
                            </div>
                          </div>
                        )}

                        {cv.professional_experience?.length > 0 && (
                          <div>
                            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase" as const, color: TEXT_MUTED, margin: "0 0 8px" }}>Experience</p>
                            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                              {cv.professional_experience.map((exp: any, i: number) => {
                                if (typeof exp === "string") return (
                                  <div key={i} style={{ display: "flex", gap: 10, fontSize: 12, color: "#374151" }}>
                                    <span style={{ width: 3, borderRadius: 2, background: NAVY, flexShrink: 0, marginTop: 4 }} />{exp}
                                  </div>
                                );
                                return (
                                  <div key={i} style={{ padding: "10px 12px", borderRadius: 10, background: "rgba(248,250,252,0.8)", border: "1px solid rgba(241,245,249,0.8)" }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 4 }}>
                                      <span style={{ fontSize: 12, fontWeight: 700, color: TEXT_MAIN }}>{exp.role ?? exp.title ?? "—"}</span>
                                      {exp.duration && <span style={{ fontSize: 10, color: TEXT_MUTED, flexShrink: 0, fontFamily: "monospace" }}>{exp.duration}</span>}
                                    </div>
                                    {exp.company && <div style={{ fontSize: 11, color: TEXT_SUB, marginBottom: 4 }}>{exp.company}</div>}
                                    {Array.isArray(exp.achievements) && exp.achievements.length > 0 && (
                                      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
                                        {exp.achievements.map((ach: string, j: number) => (
                                          <div key={j} style={{ fontSize: 11, color: TEXT_SUB, paddingLeft: 8, borderLeft: `2px solid ${NAVY}` }}>{ach}</div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {cv.education?.length > 0 && (
                          <div>
                            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase" as const, color: TEXT_MUTED, margin: "0 0 8px" }}>Education</p>
                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                              {cv.education.map((e: any, i: number) => {
                                if (typeof e === "string") return <div key={i} style={{ fontSize: 12, color: "#374151" }}>{e}</div>;
                                return (
                                  <div key={i} style={{ padding: "8px 12px", borderRadius: 10, background: "rgba(248,250,252,0.8)", border: "1px solid rgba(241,245,249,0.8)" }}>
                                    <div style={{ fontSize: 12, fontWeight: 700, color: TEXT_MAIN }}>{e.degree ?? "—"}</div>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                                      {e.institution && <span style={{ fontSize: 11, color: TEXT_SUB }}>{e.institution}</span>}
                                      {(e.start_year || e.end_year) && (
                                        <span style={{ fontSize: 10, color: TEXT_MUTED, fontFamily: "monospace" }}>
                                          {e.start_year ?? ""}{e.start_year && e.end_year ? " — " : ""}{e.end_year ?? ""}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {cv.years_experience != null && (
                          <div>
                            <p style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase" as const, color: TEXT_MUTED, margin: "0 0 8px" }}>Total Experience</p>
                            <span style={{ fontSize: 22, fontWeight: 800, color: NAVY, fontFamily: "monospace" }}>{cv.years_experience}</span>
                            <span style={{ fontSize: 12, color: TEXT_SUB, marginLeft: 6 }}>years</span>
                          </div>
                        )}
                      </div>
                    </SectionBody>
                  </SectionCard>
                </motion.div>
              )}

              {/* Loading skeleton left */}
              {loading && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {[200, 160, 300].map((h, i) => (
                    <SectionCard key={i}>
                      <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)", background: "rgba(248,250,252,0.8)" }}>
                        <Skel w={160} h={12} />
                      </div>
                      <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
                        <Skel w="100%" h={h} radius={10} />
                      </div>
                    </SectionCard>
                  ))}
                </div>
              )}
            </div>

            {/* ── Right — Manager evaluation ── */}
            <motion.div
              initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }}
              style={{ position: "sticky", top: 20 }}
            >
              <SectionCard style={{ border: `1px solid ${TEAL_BORDER}` }}>
                <SectionHeader>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: TEAL }} />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: TEXT_MAIN }}>Manager Evaluation</div>
                      <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 2 }}>
                        {role === "MANAGER" ? "Finalize your decision" : "Reserved for assigned manager"}
                      </div>
                    </div>
                  </div>
                </SectionHeader>
                <SectionBody>
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {/* Decision buttons */}
                    <div>
                      <label style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase" as const, color: TEXT_MUTED, display: "block", marginBottom: 8 }}>Decision</label>
                      {isLocked && (
                        <div style={{ fontSize: 11, color: "#16a34a", fontWeight: 600, marginBottom: 8, display: "flex", alignItems: "center", gap: 6 }}>
                          <CheckCircle2 size={13} /> Evaluation already submitted
                        </div>
                      )}
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {DECISIONS.map(dec => {
                          const isActive = recommendation === dec.value;
                          return (
                            <button
                              key={dec.value}
                              type="button"
                              onClick={() => role === "MANAGER" && !isLocked && setRecommendation(dec.value)}
                              style={{
                                width: "100%", display: "flex", alignItems: "center", gap: 10,
                                padding: "10px 12px", borderRadius: 10, textAlign: "left",
                                border: `1px solid ${isActive ? dec.border : "#e2e8f0"}`,
                                background: isActive ? dec.activeBg : "rgba(248,250,252,0.9)",
                                cursor: role === "MANAGER" && !isLocked ? "pointer" : "not-allowed",
                                opacity: role !== "MANAGER" || isLocked ? 0.6 : 1,
                                transition: "all 0.15s",
                              }}
                            >
                              <div style={{ padding: 6, borderRadius: 6, flexShrink: 0, background: dec.bg, border: `1px solid ${dec.border}` }}>
                                <dec.icon size={13} style={{ color: dec.color }} />
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: isActive ? dec.color : TEXT_MAIN }}>{dec.label}</div>
                                <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 1 }}>{dec.desc}</div>
                              </div>
                              {isActive && (
                                <div style={{ width: 8, height: 8, borderRadius: "50%", flexShrink: 0, background: dec.color, boxShadow: `0 0 8px ${dec.color}` }} />
                              )}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Notes */}
                    <div>
                      <label style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase" as const, color: TEXT_MUTED, display: "block", marginBottom: 8 }}>Internal Notes</label>
                      <textarea
                        placeholder="Notes for the interview panel…"
                        value={feedback}
                        onChange={e => setFeedback(e.target.value)}
                        disabled={role !== "MANAGER" || isLocked}
                        style={{
                          width: "100%", minHeight: 90, padding: "10px 12px", borderRadius: 10,
                          border: "1px solid #e2e8f0", background: "rgba(248,250,252,0.9)",
                          fontSize: 13, color: TEXT_MAIN, resize: "none", outline: "none",
                          fontFamily: "inherit", boxSizing: "border-box",
                          opacity: role !== "MANAGER" || isLocked ? 0.5 : 1, transition: "border-color 0.15s",
                        }}
                        onFocus={e => (e.currentTarget.style.borderColor = TEAL_BORDER)}
                        onBlur={e => (e.currentTarget.style.borderColor = "#e2e8f0")}
                      />
                    </div>

                    {/* Submit */}
                    {role === "MANAGER" ? (
                      <button
                        onClick={handleSubmit}
                        disabled={submitting || isLocked}
                        style={{
                          width: "100%", padding: "11px 0", borderRadius: 10, border: "none",
                          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                          fontSize: 13, fontWeight: 700, letterSpacing: "0.04em",
                          cursor: submitting || isLocked ? "not-allowed" : "pointer",
                          background: isLocked ? "#94a3b8" : activeRec.color, color: "#fff",
                          opacity: submitting ? 0.7 : 1, transition: "opacity 0.15s",
                          boxShadow: isLocked ? "none" : `0 4px 16px ${activeRec.color}40`,
                        }}
                      >
                        <Save size={14} />
                        {submitting ? "Submitting…" : isLocked ? "Evaluation Submitted" : "Submit Evaluation"}
                      </button>
                    ) : (
                      <div style={{ textAlign: "center", fontSize: 11, color: TEXT_MUTED, padding: "6px 0" }}>
                        Accessible to the assigned manager
                      </div>
                    )}
                  </div>
                </SectionBody>
              </SectionCard>
            </motion.div>
          </div>
        </div>
      </div>

      {/* Toast */}
      <AnimatePresence>
        {toast && <Toast msg={toast.msg} type={toast.type} onDone={() => setToast(null)} />}
      </AnimatePresence>
    </>
  );
}