/**
 * JobDetail.tsx — Same theme as Dashboard
 *   • Floating purple sidebar pill (fixed, top:140, left:16)
 *     gradient #4a1d96 → #2c0f70, white icons, framer-motion popup labels
 *   • Wave image background + overlay rgba(245,243,255,0.35)
 *   • Glassmorphism cards: rgba(255,255,255,0.88) + backdrop-filter blur(20px)
 *   • Teal accent #0d9488, text #1c2a38
 *   • NO backend changes
 */

import { useState, useEffect } from "react";
import { useLocation, useParams, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Briefcase, Users, MessageSquare,
  ArrowLeft, RefreshCw, Send, Zap, Clock, CheckCircle2, AlertCircle,
  LogOut,
} from "lucide-react";
import bgWave  from "../assets/imagee.png";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SkillsJson {
  coding?: string[];
  platform?: string[];
  mixed?: string[];
}

interface JobData {
  id: number;
  title: string;
  description: string;
  level: string;
  department: string;
  location: string;
  company: string;
  skills_required: string;
  skills_json: SkillsJson | null;
  bonus_skills: string | string[] | null;
  date_expiration: string | null;
  created_at: string;
  closed_at: string | null;
  test_validated: boolean | null;
  test_id_validated: string | null;
}

interface Question {
  id: string;
  type: string;
  text?: string;
  question?: string;
  options?: string[];
  skill?: string;
  difficulty?: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE  = import.meta.env.VITE_API_BASE_URL  ?? "http://localhost:8000";
const N8N_BASE  = import.meta.env.VITE_N8N_BASE_URL  ?? "http://localhost:5678";
const QUESTIONS_PER_PAGE = 2;

const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

const seniorityOptions = ["Junior", "Mid", "Senior"];

const SKILL_STYLE: Record<string, { bg: string; color: string }> = {
  coding:   { bg: "rgba(37,99,235,0.08)",  color: "#2563eb" },
  platform: { bg: "rgba(124,58,237,0.08)", color: "#7c3aed" },
  mixed:    { bg: "rgba(8,145,178,0.08)",  color: "#0891b2" },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getToken(): string | null { return localStorage.getItem("access_token"); }
function authHeaders(): Record<string, string> {
  const t = getToken();
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}
function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });
}
function normalizeBonusSkills(raw: string | string[] | null | undefined): string[] {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.filter(Boolean);
  return raw.split(",").map(s => s.trim()).filter(Boolean);
}
function buildSkillTags(job: JobData): Array<{ name: string; category: "coding" | "platform" | "mixed" }> {
  if (job.skills_json) {
    const tags: Array<{ name: string; category: "coding" | "platform" | "mixed" }> = [];
    (job.skills_json.coding   ?? []).forEach(s => tags.push({ name: s, category: "coding"   }));
    (job.skills_json.platform ?? []).forEach(s => tags.push({ name: s, category: "platform" }));
    (job.skills_json.mixed    ?? []).forEach(s => tags.push({ name: s, category: "mixed"    }));
    return tags;
  }
  if (typeof job.skills_required === "string") {
    return job.skills_required.split(",").map(s => s.trim()).filter(Boolean)
      .map(name => ({ name, category: "mixed" as const }));
  }
  return [];
}

// ─── Sidebar — floating pill violette (identique Dashboard) ───────────────────

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
            position: "absolute",
            left: "calc(100% + 10px)",
            top: "50%",
            transform: "translateY(-50%)",
            pointerEvents: "none",
            zIndex: 200,
            whiteSpace: "nowrap",
          }}
        >
          <div style={{
            position: "absolute", right: "100%", top: "50%", transform: "translateY(-50%)",
            width: 0, height: 0,
            borderTop: "5px solid transparent",
            borderBottom: "5px solid transparent",
            borderRight: "6px solid #3b0d8e",
          }} />
          <div style={{
            background: "#3b0d8e", color: "#fff",
            fontSize: 15, fontWeight: 700,
            padding: "6px 14px", borderRadius: 10,
            boxShadow: "0 4px 18px rgba(60,12,120,0.30)",
            letterSpacing: "0.01em",
          }}>
            {label}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Sidebar() {
  const [location] = useLocation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  return (
    <nav style={{
      position: "fixed",
      top: 140, left: 16,
      zIndex: 50,
      borderRadius: 30,
      background: "linear-gradient(180deg, #4a1d96 0%, #3b0d8e 55%, #2c0f70 100%)",
      boxShadow: "0 8px 32px rgba(60,12,120,0.30), 0 2px 8px rgba(0,0,0,0.15)",
      padding: "18px 8px",
      display: "flex", flexDirection: "column", alignItems: "center",
      gap: 4,
      overflow: "visible",
      userSelect: "none",
      width: 58,
    }}>
      {NAV.map(({ href, icon: Icon, label }) => {
        const active =
          location === href ||
          location.startsWith(href + "/") ||
          (href === "/dashboard" && location === "/");
        const hovered = hoveredKey === href;

        return (
          <Link key={href} href={href} style={{ textDecoration: "none", position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey(href)}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }}
              whileTap  ={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              style={{
                width: 40, height: 40,
                margin: "0 auto",
                borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer",
                background: active
                  ? "rgba(255,255,255,0.20)"
                  : hovered
                    ? "rgba(255,255,255,0.11)"
                    : "transparent",
                transition: "background 0.15s",
                position: "relative",
              }}
            >
              {active && (
                <motion.div
                  layoutId="activeBar-detail"
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

      {/* Divider */}
      <div style={{ width: 32, height: 1, background: "rgba(255,255,255,0.14)", margin: "6px 0", flexShrink: 0 }} />

      {/* Logout */}
      {(() => {
        const hovered = hoveredKey === "__logout";
        return (
          <div style={{ position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey("__logout")}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }}
              whileTap  ={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              onClick={() => { localStorage.removeItem("access_token"); window.location.href = "/"; }}
              style={{
                width: 40, height: 40,
                margin: "0 auto",
                borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer",
                background: hovered ? "rgba(239,68,68,0.20)" : "transparent",
                transition: "background 0.15s",
                position: "relative",
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

// ─── Card glassmorphism ───────────────────────────────────────────────────────

function Card({ children, delay = 0, style = {} }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      style={{
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(20px)",
        borderRadius: 18,
        border: "1px solid rgba(255,255,255,0.9)",
        overflow: "hidden",
        boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
        display: "flex",
        flexDirection: "column",
        ...style,
      }}
    >
      {children}
    </motion.div>
  );
}

function CardHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div style={{
      padding: "16px 20px",
      borderBottom: "1px solid rgba(240,235,255,0.7)",
    }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>{title}</h2>
      {sub && <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{sub}</p>}
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function JobDetail() {
  const [, navigate] = useLocation();
  const params = useParams<{ id: string }>();
  const jobId  = params.id;

  // Job data
  const [job, setJob]               = useState<JobData | null>(null);
  const [loadingJob, setLoadingJob] = useState(true);
  const [jobError, setJobError]     = useState<string | null>(null);

  // Form
  const [form, setForm]     = useState({ role: "", seniorite: "", skillsCoding: "", skillsPlatform: "", skillsMixed: "" });
  const [sendDate, setSendDate] = useState("");

  // Generation
  const [generating, setGenerating]       = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [generatedTest, setGeneratedTest] = useState<{ test_id: string; questions: Question[] } | null>(null);
  const [questionPage, setQuestionPage]   = useState(0);

  // Validate & Send
  const [validating, setValidating]       = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [validated, setValidated]         = useState(false);
  const [sending, setSending]             = useState(false);
  const [sendError, setSendError]         = useState<string | null>(null);
  const [sent, setSent]                   = useState(false);
  const [sentCount, setSentCount]         = useState(0);

  // Expand selection (cycle 2 / cycle 3)
  const [expandPhase,    setExpandPhase]    = useState<"cycle2" | "cycle3" | null>(null);
  const [expandLoading,  setExpandLoading]  = useState(false);
  const [expandDone,     setExpandDone]     = useState(false);
  const [expandError,    setExpandError]    = useState<string | null>(null);

  useEffect(() => { if (!getToken()) navigate("/"); }, [navigate]);

  useEffect(() => {
    if (!jobId) return;
    setLoadingJob(true); setJobError(null);
    fetch(`${API_BASE}/jobs/${jobId}`, { headers: authHeaders() })
      .then(async res => {
        if (res.status === 401) { localStorage.removeItem("access_token"); navigate("/"); return undefined; }
        if (res.status === 404) throw new Error("Job introuvable.");
        if (!res.ok) throw new Error(`Server error (${res.status})`);
        return res.json() as Promise<JobData>;
      })
      .then(data => {
        if (!data) return;
        setJob(data);
        setForm({
          role: data.title ?? "",
          seniorite: data.level ?? "",
          skillsCoding:   (data.skills_json?.coding   ?? []).join(", "),
          skillsPlatform: (data.skills_json?.platform ?? []).join(", "),
          skillsMixed:    (data.skills_json?.mixed    ?? []).join(", "),
        });
        if (data.test_validated && data.test_id_validated) setValidated(true);
      })
      .catch(err => setJobError(err instanceof Error ? err.message : "Unknown error"))
      .finally(() => setLoadingJob(false));
  }, [jobId, navigate]);

  // Fetch expand phase depuis manager dashboard
  useEffect(() => {
    if (!jobId) return;
    fetch(`${API_BASE}/jobs/manager/dashboard`, { headers: authHeaders() })
      .then(res => res.ok ? res.json() : [])
      .then((jobs: { id: number; expand_phase: string | null; expand_requested: boolean }[]) => {
        const current = jobs.find(j => String(j.id) === String(jobId));
        if (current?.expand_requested && current?.expand_phase) {
          setExpandPhase(current.expand_phase as "cycle2" | "cycle3");
        }
      })
      .catch(() => {/* silencieux — pas bloquant */});
  }, [jobId]);

  async function handleRelancer() {
    if (!jobId || !expandPhase) return;
    setExpandLoading(true); setExpandError(null);
    try {
      const cycle = expandPhase === "cycle2" ? 2 : 3;
      const res = await fetch(`${N8N_BASE}/webhook/elargir-selection`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({ job_id: Number(jobId), cycle, token: getToken() }),
      });
      const data = await res.json();
      if (data.success) {
        setExpandDone(true);
        setExpandPhase(null);
      } else {
        setExpandError(data.message ?? "Error while restarting");
      }
    } catch {
      setExpandError("Unable to reach the server");
    } finally {
      setExpandLoading(false);
    }
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!job) return;
    setGenerating(true); setGenerateError(null); setGeneratedTest(null); setValidated(false); setSent(false);
    try {
      const res = await fetch(`${API_BASE}/tests/generate`, {
        method: "POST", headers: authHeaders(),
        body: JSON.stringify({
          job_id: job.id, role: form.role, seniority: form.seniorite,
          skills: {
            coding:   form.skillsCoding.split(",").map(s => s.trim()).filter(Boolean),
            platform: form.skillsPlatform.split(",").map(s => s.trim()).filter(Boolean),
            mixed:    form.skillsMixed.split(",").map(s => s.trim()).filter(Boolean),
          },
          duration: 60,
        }),
      });
      if (res.status === 401) { localStorage.removeItem("access_token"); navigate("/"); return; }
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail ?? `Error (${res.status})`); }
      const data = await res.json();
      setGeneratedTest({ test_id: data.test_id, questions: data.questions ?? [] });
      setQuestionPage(0);
    } catch (err) { setGenerateError(err instanceof Error ? err.message : "Unknown error"); }
    finally { setGenerating(false); }
  }

  async function handleRegenerate() {
    if (!job) return;
    setGeneratedTest(null); setValidated(false); setSent(false);
    setGenerateError(null); setValidateError(null); setSendError(null); setGenerating(true);
    try {
      const res = await fetch(`${API_BASE}/tests/regenerate`, {
        method: "POST", headers: authHeaders(),
        body: JSON.stringify({
          job_id: job.id, role: form.role, seniority: form.seniorite,
          skills: {
            coding:   form.skillsCoding.split(",").map(s => s.trim()).filter(Boolean),
            platform: form.skillsPlatform.split(",").map(s => s.trim()).filter(Boolean),
            mixed:    form.skillsMixed.split(",").map(s => s.trim()).filter(Boolean),
          },
        }),
      });
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail ?? `Error (${res.status})`); }
      const data = await res.json();
      setGeneratedTest({ test_id: data.test_id, questions: data.questions ?? [] });
      setQuestionPage(0);
    } catch (err) { setGenerateError(err instanceof Error ? err.message : "Regeneration error"); }
    finally { setGenerating(false); }
  }

  async function handleValidateAndSend() {
    if (!job || !generatedTest) return;
    if (!sendDate) { setValidateError("Please choose a send date."); return; }
    setValidating(true); setValidateError(null); setSendError(null);
    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch(`${N8N_BASE}/webhook/valider-test`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ token: getToken(), test_id: generatedTest.test_id, job_id: job.id, send_date: sendDate }),
      });
      clearTimeout(timeoutId);
      if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.error ?? e.detail ?? `Error (${res.status})`); }
      const data = await res.json().catch(() => ({}));
      setValidated(true); setSent(true); setSentCount(data.candidates_count ?? data.sent_count ?? 1);
    } catch (err) {
      clearTimeout(timeoutId);
      if (err instanceof Error && err.name === "AbortError") {
        setValidated(true); setSent(true); setSentCount(1); return;
      }
      setValidateError(err instanceof Error ? err.message : "Validation and sending error");
    } finally { setValidating(false); }
  }

  const skillTags   = job ? buildSkillTags(job) : [];
  const bonusSkills = job ? normalizeBonusSkills(job.bonus_skills) : [];
  const isActive    = job ? !job.closed_at : true;
  const canSend     = !!generatedTest && !sent;
  const sendLoading = validating || sending;
  const totalQPages = generatedTest
    ? Math.ceil(generatedTest.questions.length / QUESTIONS_PER_PAGE)
    : 0;

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  return (
    <>
      <style>{`
        @keyframes shimmer   { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes spin      { to { transform: rotate(360deg); } }
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        input[type="datetime-local"] { color-scheme: light; }
      `}</style>

      <Sidebar />

      {/* Fond wave + overlay identique Dashboard */}
      <div style={{
        marginLeft: 62,
        minHeight: "100vh",
        position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
      }}>
        {/* Overlay doux */}
        <div style={{
          position: "absolute", inset: 0,
          background: "rgba(245,243,255,0.35)",
          pointerEvents: "none",
        }} />

        <div style={{
          position: "relative", zIndex: 1,
          padding: "28px 36px 48px",
          maxWidth: 1260,
          margin: "0 auto",
        }}>

          {/* ── Header ─────────────────────────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{ marginBottom: 28 }}
          >
            {/* Logo + company name (same as Dashboard) */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 44, height: 45, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  
                </div>
                
              </div>
            </div>

            {/* Date + fil d'Ariane */}
            <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.18em", marginBottom: 12, textTransform: "uppercase" }}>
              {dateLabel}
            </p>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button
                  onClick={() => navigate("/mission-registry")}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.9)",
                    background: "rgba(255,255,255,0.80)",
                    backdropFilter: "blur(8px)",
                    color: "#64748b", cursor: "pointer",
                    boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
                  }}
                >
                  <ArrowLeft size={13} /> Back
                </button>
                <h1 style={{ fontSize: 22, fontWeight: 700, color: "#1c2a38", margin: 0 }}>
                  {loadingJob ? "Loading…" : (job?.title ?? "Job Detail")}
                </h1>
                {!loadingJob && job && (
                  <span style={{
                    padding: "4px 12px", borderRadius: 8, fontSize: 10, fontWeight: 700,
                    letterSpacing: "0.08em",
                    background: isActive ? "#f0fdf4" : "#f8fafc",
                    color: isActive ? "#16a34a" : "#94a3b8",
                    border: `1px solid ${isActive ? "#bbf7d0" : "#e2e8f0"}`,
                  }}>
                    {isActive ? "ACTIVE" : "CLOSED"}
                  </span>
                )}
              </div>

              {/* ── Restart button — in the header ── */}
              {expandDone ? (
                <div style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "8px 14px", borderRadius: 10,
                  background: "#f0fdf4", border: "1px solid #bbf7d0",
                }}>
                  <CheckCircle2 size={14} color="#16a34a" />
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#16a34a" }}>
                    Selection relaunched ✓
                  </span>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                  {expandError && (
                    <div style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "6px 12px", borderRadius: 10,
                      background: "#fef2f2", border: "1px solid #fca5a5",
                    }}>
                      <AlertCircle size={13} color="#ef4444" />
                      <span style={{ fontSize: 12, color: "#991b1b" }}>{expandError}</span>
                    </div>
                  )}
                  <button
                    onClick={handleRelancer}
                    disabled={!expandPhase || expandLoading}
                    title={!expandPhase ? "Waiting for HR request" : ""}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "9px 18px", borderRadius: 10, fontSize: 13, fontWeight: 700,
                      border: "none", transition: "all 0.15s",
                      cursor: !expandPhase || expandLoading ? "not-allowed" : "pointer",
                      background: !expandPhase || expandLoading
                        ? "#e2e8f0"
                        : expandPhase === "cycle2"
                          ? "linear-gradient(135deg,#0d9488,#0f766e)"
                          : "linear-gradient(135deg,#7c3aed,#5b21b6)",
                      color: !expandPhase || expandLoading ? "#94a3b8" : "#fff",
                      boxShadow: !expandPhase || expandLoading ? "none" : "0 4px 14px rgba(0,0,0,0.15)",
                      opacity: !expandPhase || expandLoading ? 0.45 : 1,
                    }}
                  >
                    {expandLoading ? (
                      <>
                        <div style={{ width: 14, height: 14, border: "2px solid #94a3b8", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                        Restart in progress…
                      </>
                    ) : !expandPhase ? (
                      <>
                        <Send size={14} />
                        Restart selection
                      </>
                    ) : expandPhase === "cycle2" ? (
                      <>
                        <Send size={14} />
                        Restart — candidates waiting for interview
                      </>
                    ) : (
                      <>
                        <Zap size={14} />
                        Restart — candidates in matching phase
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </motion.div>

          {/* ── Error globale ────────────────────────────────────────────────── */}
          {jobError && (
            <div style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "14px 18px", borderRadius: 14, marginBottom: 20,
              background: "#fef2f2", border: "1px solid #fca5a5",
            }}>
              <AlertCircle size={16} color="#ef4444" />
              <span style={{ fontSize: 13, color: "#991b1b" }}>{jobError}</span>
            </div>
          )}

          {/* ── Grid 2 colonnes ──────────────────────────────────────────────── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>

            {/* ══ Panel gauche — Infos du job ══ */}
            <Card delay={0.05}>
              <CardHeader
                title="Job Information"
                sub={loadingJob ? "Loading…" : `${job?.department ?? ""} · ${job?.location ?? ""}`}
              />

              <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 18, overflowY: "auto", flex: 1 }}>
                {loadingJob ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {[1, 2, 3, 4, 5].map(i => <Skel key={i} w="100%" h={14} />)}
                  </div>
                ) : job ? (
                  <>
                    {/* Infos de base */}
                    {([
                      { label: "Department", value: job.department },
                      { label: "Location",   value: job.location   },
                      { label: "Level",      value: job.level      },
                      { label: "Company",    value: job.company    },
                      { label: "Posted",     value: formatDate(job.created_at)    },
                      { label: "Expires",    value: formatDate(job.date_expiration) },
                    ] as const).map(({ label, value }) => (
                      <div key={label} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", textTransform: "uppercase" }}>
                          {label}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 600, color: "#1c2a38" }}>{value || "—"}</span>
                      </div>
                    ))}

                    {/* Skills */}
                    {skillTags.length > 0 && (
                      <div>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", textTransform: "uppercase", display: "block", marginBottom: 8 }}>
                          Required Skills
                        </span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {skillTags.map(tag => {
                            const s = SKILL_STYLE[tag.category];
                            return (
                              <span key={tag.name} style={{
                                fontSize: 11, padding: "3px 10px", borderRadius: 6, fontWeight: 600,
                                background: s.bg, color: s.color, border: `1px solid ${s.color}28`,
                              }}>{tag.name}</span>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Bonus skills */}
                    {bonusSkills.length > 0 && (
                      <div>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", textTransform: "uppercase", display: "block", marginBottom: 8 }}>
                          Bonus Skills
                        </span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                          {bonusSkills.map(s => (
                            <span key={s} style={{
                              fontSize: 11, padding: "3px 10px", borderRadius: 6, fontWeight: 600,
                              background: "rgba(245,158,11,0.08)", color: "#d97706",
                              border: "1px solid rgba(245,158,11,0.2)",
                            }}>{s}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Description */}
                    {job.description && (
                      <div>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", textTransform: "uppercase", display: "block", marginBottom: 8 }}>
                          Description
                        </span>
                        <p style={{ fontSize: 12, color: "#475569", lineHeight: 1.6, margin: 0 }}>
                          {job.description}
                        </p>
                      </div>
                    )}

                    {/* Test validated */}
                    {job.test_validated && job.test_id_validated && (
                      <div style={{
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "10px 14px", borderRadius: 10,
                        background: "#f0fdf4", border: "1px solid #bbf7d0",
                      }}>
                        <CheckCircle2 size={14} color="#16a34a" />
                        <div>
                          <p style={{ fontSize: 12, fontWeight: 700, color: "#16a34a", margin: 0 }}>Test validated</p>
                          <p style={{ fontSize: 10, color: "#64748b", margin: 0 }}>{job.test_id_validated}</p>
                        </div>
                      </div>
                    )}
                  </>
                ) : null}
              </div>
            </Card>

            {/* ══ Right panel — Test generation ══ */}
            <Card delay={0.10}>
              <CardHeader
                title="Technical Test"
                sub={generatedTest ? `${generatedTest.questions.length} question${generatedTest.questions.length !== 1 ? "s" : ""} generated` : "Generate & dispatch"}
              />

              <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16, overflowY: "auto", flex: 1 }}>

                {/* ── Generated questions ── */}
                {generatedTest && (() => {
                  const start = questionPage * QUESTIONS_PER_PAGE;
                  const pageQ = generatedTest.questions.slice(start, start + QUESTIONS_PER_PAGE);

                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                      {/* Header */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <CheckCircle2 size={15} color="#0d9488" />
                          <span style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>
                            Test ID: {generatedTest.test_id}
                          </span>
                        </div>
                        <button
                          onClick={handleRegenerate}
                          disabled={generating}
                          style={{
                            display: "flex", alignItems: "center", gap: 5,
                            padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                            border: "1px solid rgba(255,255,255,0.7)",
                            background: "rgba(255,255,255,0.7)",
                            backdropFilter: "blur(6px)",
                            color: "#64748b", cursor: generating ? "not-allowed" : "pointer",
                          }}
                        >
                          <RefreshCw size={11} style={{ animation: generating ? "spin 1s linear infinite" : "none" }} />
                          Regenerate
                        </button>
                      </div>

                      {/* Questions */}
                      {pageQ.map((q, qi) => (
                        <div key={q.id} style={{
                          padding: "12px 14px", borderRadius: 12,
                          background: "rgba(255,255,255,0.70)", backdropFilter: "blur(8px)",
                          border: "1px solid rgba(255,255,255,0.85)",
                          display: "flex", flexDirection: "column", gap: 8,
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 10, fontWeight: 800, color: "#94a3b8", letterSpacing: "0.05em" }}>
                              Q{start + qi + 1}
                            </span>
                            {q.skill && (
                              <span style={{
                                fontSize: 10, padding: "1px 8px", borderRadius: 5, fontWeight: 600,
                                background: "rgba(13,148,136,0.10)", color: "#0d9488", border: "1px solid rgba(13,148,136,0.2)",
                              }}>{q.skill}</span>
                            )}
                            {q.difficulty && (
                              <span style={{
                                fontSize: 10, padding: "1px 8px", borderRadius: 5, fontWeight: 600,
                                background: "rgba(245,158,11,0.08)", color: "#d97706", border: "1px solid rgba(245,158,11,0.2)",
                              }}>{q.difficulty}</span>
                            )}
                            <span style={{
                              fontSize: 10, padding: "1px 8px", borderRadius: 5, fontWeight: 600,
                              background: "rgba(124,58,237,0.08)", color: "#7c3aed", border: "1px solid rgba(124,58,237,0.2)",
                              marginLeft: "auto",
                            }}>{q.type}</span>
                          </div>
                          <p style={{ fontSize: 13, fontWeight: 600, color: "#1c2a38", margin: 0, lineHeight: 1.5 }}>
                            {q.text ?? q.question ?? "—"}
                          </p>
                          {q.options && q.options.length > 0 && (
                            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4 }}>
                              {q.options.map((opt, i) => (
                                <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12, color: "#475569" }}>
                                  <span style={{
                                    flexShrink: 0, width: 18, height: 18, borderRadius: "50%",
                                    border: "1px solid #cbd5e1", display: "flex", alignItems: "center", justifyContent: "center",
                                    fontSize: 9, fontWeight: 700, color: "#94a3b8",
                                  }}>{String.fromCharCode(65 + i)}</span>
                                  {opt}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}

                      {/* Pagination questions */}
                      {totalQPages > 1 && (
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          {[
                            { label: "← Previous", disabled: questionPage === 0,              action: () => setQuestionPage(p => Math.max(0, p - 1)) },
                            { label: "Next →",   disabled: questionPage >= totalQPages - 1, action: () => setQuestionPage(p => Math.min(totalQPages - 1, p + 1)) },
                          ].map(({ label, disabled, action }) => (
                            <button key={label} onClick={action} disabled={disabled} style={{
                              padding: "6px 14px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                              border: "1px solid rgba(255,255,255,0.8)",
                              background: "rgba(255,255,255,0.7)", color: "#64748b",
                              cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.35 : 1,
                            }}>{label}</button>
                          ))}
                        </div>
                      )}

                      {/* Scheduled send */}
                      {sent ? (
                        <div style={{
                          padding: "12px 16px", borderRadius: 12,
                          background: "#f0fdf4", border: "1px solid #bbf7d0",
                          display: "flex", flexDirection: "column", gap: 4,
                        }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <CheckCircle2 size={15} color="#16a34a" />
                            <span style={{ fontSize: 12, color: "#16a34a", fontWeight: 700 }}>
                              Scheduled test — send on {new Date(sendDate).toLocaleString("en-US", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}
                            </span>
                          </div>
                          <p style={{ fontSize: 11, color: "#64748b", marginLeft: 23 }}>
                            {sentCount} Candidate(s) automatically notified · n8n manages the sending ⏳
                          </p>
                        </div>
                      ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 4, borderTop: "1px solid rgba(240,235,255,0.7)" }}>
                          {(validateError || sendError) && (
                            <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: 10, background: "#fef2f2", border: "1px solid #fca5a5" }}>
                              <AlertCircle size={14} color="#ef4444" />
                              <span style={{ fontSize: 12, color: "#991b1b" }}>{validateError ?? sendError}</span>
                            </div>
                          )}
                          <div>
                            <label style={{ display: "block", fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", marginBottom: 6, textTransform: "uppercase" }}>
                              Send Date
                            </label>
                            <input
                              type="datetime-local"
                              value={sendDate}
                              onChange={e => setSendDate(e.target.value)}
                              min={new Date(Date.now() + 60000).toISOString().slice(0, 16)}
                              style={{
                                width: "100%", padding: "9px 12px", borderRadius: 10, fontSize: 13,
                                border: "1px solid rgba(255,255,255,0.7)",
                                background: "rgba(255,255,255,0.65)",
                                backdropFilter: "blur(6px)",
                                color: "#1c2a38", outline: "none", boxSizing: "border-box",
                              }}
                            />
                          </div>
                          <button
                            onClick={handleValidateAndSend}
                            disabled={!canSend || sendLoading || !sendDate}
                            style={{
                              width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                              padding: "10px 0", borderRadius: 10, fontSize: 12, fontWeight: 700,
                              border: "none", transition: "all 0.15s",
                              cursor: !canSend || sendLoading || !sendDate ? "not-allowed" : "pointer",
                              background: canSend && !sendLoading && sendDate
                                ? "linear-gradient(135deg,#0d9488,#0f766e)"
                                : "#e2e8f0",
                              color: canSend && !sendLoading && sendDate ? "#fff" : "#94a3b8",
                              boxShadow: canSend && !sendLoading && sendDate ? "0 2px 8px rgba(13,148,136,0.3)" : "none",
                              opacity: !canSend || sendLoading || !sendDate ? 0.6 : 1,
                            }}
                          >
                            <Send size={13} />
                            {sendLoading ? "Validating…" : "Validate & Send"}
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* ── Generation form ── */}
                <form
                  id="generate-form"
                  onSubmit={handleGenerate}
                  style={{ display: generatedTest ? "none" : "flex", flexDirection: "column", gap: 16 }}
                >
                  {/* Generation error */}
                  {generateError && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderRadius: 10, background: "#fef2f2", border: "1px solid #fca5a5" }}>
                      <AlertCircle size={14} color="#ef4444" />
                      <span style={{ fontSize: 12, color: "#991b1b" }}>{generateError}</span>
                    </div>
                  )}

                  {/* Role (readonly) */}
                  <div>
                    <label style={{ display: "block", fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", marginBottom: 6, textTransform: "uppercase" }}>Role</label>
                    <div style={{
                      padding: "9px 12px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                      background: "rgba(255,255,255,0.65)", backdropFilter: "blur(6px)",
                      border: "1px solid rgba(255,255,255,0.75)", color: "#1c2a38",
                    }}>{job?.title ?? "—"}</div>
                  </div>

                  {/* Seniority */}
                  <div>
                    <label style={{ display: "block", fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", marginBottom: 8, textTransform: "uppercase" }}>Seniority</label>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {seniorityOptions.map(s => (
                        <button
                          key={s} type="button"
                          onClick={() => setForm({ ...form, seniorite: s })}
                          style={{
                            padding: "6px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer",
                            border: "1px solid",
                            borderColor: form.seniorite === s ? "#0d9488" : "rgba(255,255,255,0.8)",
                            background: form.seniorite === s ? "rgba(13,148,136,0.10)" : "rgba(255,255,255,0.65)",
                            backdropFilter: "blur(6px)",
                            color: form.seniorite === s ? "#0d9488" : "#64748b",
                            transition: "all 0.15s",
                          }}
                        >{s}</button>
                      ))}
                    </div>
                  </div>

                  {/* Skills inputs */}
                  {[
                    { key: "skillsCoding",   label: "Skills Coding",      placeholder: "React, TypeScript, Node.js…" },
                    { key: "skillsPlatform", label: "Skills Platform",    placeholder: "AWS, Docker, Kubernetes…"     },
                    { key: "skillsMixed",    label: "Skills Mixed", placeholder: "Leadership, Agile…"           },
                  ].map(({ key, label, placeholder }) => (
                    <div key={key}>
                      <label style={{ display: "block", fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.12em", marginBottom: 6, textTransform: "uppercase" }}>{label}</label>
                      <input
                        type="text"
                        placeholder={placeholder}
                        value={(form as Record<string, string>)[key]}
                        onChange={e => setForm({ ...form, [key]: e.target.value })}
                        style={{
                          width: "100%", padding: "9px 12px", borderRadius: 10, fontSize: 13,
                          border: "1px solid rgba(255,255,255,0.75)",
                          background: "rgba(255,255,255,0.65)", backdropFilter: "blur(6px)",
                          color: "#1c2a38", outline: "none", boxSizing: "border-box", transition: "border-color 0.15s",
                        }}
                        onFocus={e => (e.target.style.borderColor = "#0d9488")}
                        onBlur={e => (e.target.style.borderColor = "rgba(255,255,255,0.75)")}
                      />
                    </div>
                  ))}

                  {/* Submit */}
                  <button
                    type="submit"
                    disabled={generating || !form.seniorite}
                    style={{
                      width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                      padding: "11px 0", borderRadius: 10, fontSize: 13, fontWeight: 700,
                      border: "none", cursor: generating || !form.seniorite ? "not-allowed" : "pointer",
                      background: generating || !form.seniorite
                        ? "#e2e8f0"
                        : "linear-gradient(135deg,#4a1d96,#3b0d8e)",
                      color: generating || !form.seniorite ? "#94a3b8" : "#fff",
                      boxShadow: generating || !form.seniorite ? "none" : "0 4px 14px rgba(60,12,120,0.30)",
                      transition: "all 0.15s",
                      opacity: generating || !form.seniorite ? 0.65 : 1,
                    }}
                  >
                    {generating ? (
                      <>
                        <div style={{ width: 14, height: 14, border: "2px solid #94a3b8", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                        Generating…
                      </>
                    ) : (
                      <>
                        <Zap size={14} />
                        Generate Test
                      </>
                    )}
                  </button>
                </form>



              </div>
            </Card>

          </div>{/* end grid */}
        </div>
      </div>
    </>
  );
}