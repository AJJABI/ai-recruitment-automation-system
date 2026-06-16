/**
 * CandidateList.tsx — /candidates/:jobId
 * Thème Dashboard : sidebar pill violette flottante + background wave
 * ⚠️ Aucune modification backend — uniquement le rendu visuel.
 */

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useParams, useLocation, Link } from "wouter";
import {
  LayoutDashboard, Briefcase, Users, MessageSquare,
  ArrowLeft, CheckCircle2, Clock, FileText,
  AlertCircle, User, LogOut,
} from "lucide-react";
import bgWave  from "../assets/imagee.png";

import { API_BASE, authHeaders, getToken } from "./managerShared";

// ─── Design tokens ─────────────────────────────────────────────────────────────
const TEAL        = "#0d9488";
const TEAL_BG     = "rgba(13,148,136,0.08)";
const TEAL_BORDER = "rgba(13,148,136,0.2)";
const TEXT_MAIN   = "#1c2a38";
const TEXT_SUB    = "#64748b";
const TEXT_MUTED  = "#94a3b8";
const BORDER_CARD = "#e8ecf0";

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
function Card({ children, delay = 0, style }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
      style={{
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(20px)",
        borderRadius: 18,
        border: "1px solid rgba(255,255,255,0.9)",
        overflow: "hidden",
        boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
        ...style,
      }}
    >
      {children}
    </motion.div>
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

// ─── Types ────────────────────────────────────────────────────────────────────
interface Candidate {
  application_id: number;
  full_name: string;
  email: string;
  status_v2: string;
  score_final: number | null;
  group: "PRESELECTED" | "PENDING" | "IN_PROGRESS" | "OTHER";
}

interface Job {
  id: number;
  title: string;
  department: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const AVATAR_PALETTE = ["#0d9488", "#0e7490", "#0369a1", "#7c3aed", "#065f46", "#9a3412"];

function initials(name: string) {
  return name ? name.split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase() : "?";
}

function isDone(status: string): boolean {
  return ["INTERVIEW_SCHEDULED", "INTERVIEW_DONE", 
           "MANAGER_REJECTED", "ACCEPTED"].includes(status);
}

function statusLabel(status: string): { label: string; color: string; bg: string; border: string } {
  const map: Record<string, { label: string; color: string; bg: string; border: string }> = {
    MANAGER_REJECTED:    { label: "Rejected",   color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
    INTERVIEW_DONE:      { label: "Done",        color: "#16a34a", bg: "#f0fdf4", border: "#bbf7d0" },
    INTERVIEW_SCHEDULED: { label: "Scheduled",  color: "#2563eb", bg: "#eff6ff", border: "#bfdbfe" },
    ACCEPTED:            { label: "Accepted",   color: "#7c3aed", bg: "#f5f3ff", border: "#c4b5fd" },
  };
  return map[status] ?? { label: "Pending", color: "#d97706", bg: "#fffbeb", border: "#fde68a" };
}

// ─── CandidateRow ─────────────────────────────────────────────────────────────
function CandidateRow({ candidate, i, jobId, navigate }: {
  candidate: Candidate; i: number; jobId: string; navigate: (path: string) => void;
}) {
  const st = statusLabel(candidate.status_v2);
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: i * 0.04 }}
      className="cand-row"
      style={{
        display: "grid", gridTemplateColumns: "2.5fr 1.5fr 1fr",
        padding: "13px 16px", borderRadius: 12,
        background: "rgba(248,250,252,0.9)", border: "1px solid rgba(241,245,249,0.8)",
        alignItems: "center", gap: 12,
        transition: "background 0.15s",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
        <div style={{
          width: 36, height: 36, borderRadius: "50%", flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 700, color: "#fff",
          background: AVATAR_PALETTE[i % AVATAR_PALETTE.length],
        }}>
          {candidate.full_name ? initials(candidate.full_name) : <User size={14} />}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: TEXT_MAIN, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {candidate.full_name || "N/A"}
          </div>
          {candidate.score_final != null && (
            <div style={{ fontSize: 10, color: TEXT_MUTED, marginTop: 2 }}>
              Score: <span style={{ fontWeight: 700, color: candidate.score_final >= 85 ? "#16a34a" : candidate.score_final >= 70 ? "#d97706" : "#dc2626" }}>
                {Math.round(candidate.score_final)}%
              </span>
            </div>
          )}
        </div>
      </div>
      <div>
        <span style={{
          display: "inline-flex", alignItems: "center", gap: 5,
          fontSize: 10, fontWeight: 700, letterSpacing: "0.06em",
          padding: "4px 10px", borderRadius: 99,
          background: st.bg, color: st.color, border: `1px solid ${st.border}`,
        }}>
          {isDone(candidate.status_v2) ? <CheckCircle2 size={11} /> : <Clock size={11} />}
          {st.label}
        </span>
      </div>
      <div style={{ textAlign: "right" }}>
        <button
          onClick={() => navigate(`/candidates/${jobId}/${candidate.application_id}`)}
          style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            padding: "7px 12px", borderRadius: 8,
            border: `1px solid ${TEAL_BORDER}`, background: TEAL_BG,
            cursor: "pointer", fontSize: 11, fontWeight: 700,
            color: TEAL, letterSpacing: "0.04em", transition: "background 0.15s",
          }}
          onMouseEnter={e => { e.currentTarget.style.background = "rgba(13,148,136,0.14)"; }}
          onMouseLeave={e => { e.currentTarget.style.background = TEAL_BG; }}
        >
          <FileText size={12} />
          View Report
        </button>
      </div>
    </motion.div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function CandidateList() {
  const { jobId }    = useParams<{ jobId: string }>();
  const [, navigate] = useLocation();

  const [candidates,    setCandidates]    = useState<Candidate[]>([]);
  const [job,           setJob]           = useState<Job | null>(null);
  const [rejectedCount, setRejectedCount] = useState(0);
  const [loading,       setLoading]       = useState(true);
  const [error,         setError]         = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }
    if (!jobId) return;
    setLoading(true); setError(null);

    Promise.all([
      fetch(`${API_BASE}/jobs/${jobId}`,                { headers: authHeaders() }),
      fetch(`${API_BASE}/applications/by-job/${jobId}`, { headers: authHeaders() }),
    ])
      .then(async ([jobRes, canRes]) => {
        if (jobRes.status === 401) { localStorage.removeItem("access_token"); navigate("/login"); return; }
        if (!jobRes.ok) throw new Error(`Job not found (${jobRes.status})`);
        if (!canRes.ok) throw new Error(`Candidates error (${canRes.status})`);
        const [jobData, canData] = await Promise.all([jobRes.json(), canRes.json()]);
        setJob(jobData);
        setCandidates(canData.candidates ?? canData);
        setRejectedCount(canData.rejected_count ?? 0);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Unknown error"))
      .finally(() => setLoading(false));
  }, [jobId]);

  // Rejected : REJECTED_AUTO + REJECTED_TECH (depuis backend) + MANAGER_REJECTED (dans la liste)
  const rejectedTotal  = rejectedCount + candidates.filter(c => c.status_v2 === "MANAGER_REJECTED").length;
  const totalAll       = candidates.length + rejectedCount;

  // Interviews : tous les statuts liés à l'entretien
  const interviewsDone = candidates.filter(c =>
    ["WAITING_MEET", "MEET_PENDING", "INTERVIEW_SCHEDULED", "INTERVIEW_DONE"].includes(c.status_v2)
  ).length;

  // Pending Review : en attente d'action
  const pendingReview  = candidates.filter(c =>
    ["PENDING", "PRESELECTED", "TEST_SENT", "TEST_IN_PROGRESS", "TEST_COMPLETED"].includes(c.status_v2)
  ).length;

  const preselected  = candidates.filter(c => c.group === "PRESELECTED");
  const pendingList  = candidates.filter(c => c.group === "PENDING");
  const inProgress   = candidates.filter(c => (c.group === "IN_PROGRESS" || c.group === "OTHER") && !["WAITING_MEET","MEET_PENDING"].includes(c.status_v2));

  // Groupes post-test — séparés par score
  const meetPending  = candidates.filter(c => c.status_v2 === "MEET_PENDING");       // score ≥ 70 — vert
  const waitingMeet  = candidates.filter(c => c.status_v2 === "WAITING_MEET");       // score 50-69 — orange

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        .cand-row:hover { background: rgba(240,244,248,0.95) !important; }
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
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
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

            {/* Back + title row */}
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button
                onClick={() => navigate("/candidates")}
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
              <div>
                <h1 style={{ fontSize: 26, fontWeight: 800, color: TEXT_MAIN, margin: 0, letterSpacing: "-0.01em" }}>
                  {loading ? "Loading…" : (job?.title ?? `Job #${jobId}`)}
                </h1>
                <p style={{ fontSize: 13, color: TEXT_SUB, marginTop: 4 }}>
                  {job?.department} · {candidates.length} candidate{candidates.length !== 1 ? "s" : ""}
                </p>
              </div>
            </div>

            {/* KPI pills */}
            {!loading && !error && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
                {[
                  { label: "Total",          value: totalAll,       color: TEAL,      bg: TEAL_BG,     border: TEAL_BORDER   },
                  { label: "Rejected",       value: rejectedTotal,  color: "#dc2626", bg: "#fef2f2",   border: "#fca5a5"     },
                  { label: "Interviews",     value: interviewsDone, color: "#16a34a", bg: "#f0fdf4",   border: "#bbf7d0"     },
                  { label: "Pending Review", value: pendingReview,  color: "#d97706", bg: "#fffbeb",   border: "#fde68a"     },
                ].map(({ label, value, color, bg, border }) => (
                  <motion.div
                    key={label}
                    whileHover={{ scale: 1.03, y: -1 }}
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "7px 16px", borderRadius: 999,
                      background: "rgba(255,255,255,0.85)", backdropFilter: "blur(8px)",
                      border: "1px solid rgba(255,255,255,0.9)",
                      boxShadow: "0 1px 4px rgba(90,40,160,0.08)",
                      fontSize: 12, fontWeight: 500, color: TEXT_SUB,
                    }}
                  >
                    <span style={{ fontSize: 16, fontWeight: 800, color }}>{value}</span>
                    <span>{label}</span>
                  </motion.div>
                ))}
              </div>
            )}
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

          {/* ── Main card ── */}
          <Card delay={0.1}>
            {/* Card header */}
            <div style={{
              padding: "16px 20px",
              borderBottom: "1px solid rgba(240,235,255,0.7)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: TEXT_MAIN, margin: 0 }}>Candidate List</h2>
                <p style={{ fontSize: 12, color: TEXT_SUB, marginTop: 2 }}>
                  {loading ? "—" : `${candidates.length} candidate${candidates.length !== 1 ? "s" : ""} in this pipeline`}
                </p>
              </div>
              <div style={{
                width: 32, height: 32, borderRadius: 10,
                background: TEAL_BG, border: `1px solid ${TEAL_BORDER}`,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <Users size={15} color={TEAL} />
              </div>
            </div>

            {/* Column headers */}
            <div style={{
              display: "grid", gridTemplateColumns: "2.5fr 1.5fr 1fr",
              padding: "10px 20px", background: "rgba(248,250,252,0.8)",
              borderBottom: "1px solid rgba(241,245,249,0.8)",
            }}>
              {["Candidate", "Status", "Report"].map((h, i) => (
                <div key={h} style={{
                  fontSize: 9, fontWeight: 700, textTransform: "uppercase" as const,
                  letterSpacing: "0.18em", color: TEXT_MUTED,
                  textAlign: i === 2 ? "right" as const : "left" as const,
                }}>
                  {h}
                </div>
              ))}
            </div>

            <AnimatePresence mode="wait">
              {/* Loading skeleton */}
              {loading && (
                <div key="skeleton" style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} style={{
                      display: "grid", gridTemplateColumns: "2.5fr 1.5fr 1fr",
                      padding: "14px 16px", borderRadius: 12,
                      background: "rgba(248,250,252,0.9)", border: "1px solid rgba(241,245,249,0.8)",
                      alignItems: "center", gap: 12,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <Skel w={36} h={36} radius={99} />
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                          <Skel w={140} h={13} /><Skel w={80} h={10} />
                        </div>
                      </div>
                      <Skel w={90} h={24} radius={99} />
                      <div style={{ display: "flex", justifyContent: "flex-end" }}><Skel w={100} h={32} radius={8} /></div>
                    </div>
                  ))}
                </div>
              )}

              {/* Rows */}
              {!loading && candidates.length > 0 && (
                <div key="rows" style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 20 }}>
                  {rejectedTotal > 0 && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, color: TEXT_MUTED }}>
                        {rejectedTotal} candidat{rejectedTotal > 1 ? "s" : ""} Rejected — non affiché{rejectedTotal > 1 ? "s" : ""}
                      </span>
                    </div>
                  )}

                  {preselected.length > 0 && (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a" }} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
                          Présélectionnés — {preselected.length}
                        </span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {preselected.map((c, i) => <CandidateRow key={c.application_id} candidate={c} i={i} jobId={jobId!} navigate={navigate} />)}
                      </div>
                    </div>
                  )}

                  {meetPending.length > 0 && (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a" }} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#16a34a", letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
                          Interview invitation — {meetPending.length}
                        </span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, borderLeft: "3px solid #16a34a", paddingLeft: 12 }}>
                        {meetPending.map((c, i) => <CandidateRow key={c.application_id} candidate={c} i={i} jobId={jobId!} navigate={navigate} />)}
                      </div>
                    </div>
                  )}

                  {waitingMeet.length > 0 && (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#d97706" }} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#d97706", letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
                          Awaiting review — {waitingMeet.length}
                        </span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, borderLeft: "3px solid #d97706", paddingLeft: 12 }}>
                        {waitingMeet.map((c, i) => <CandidateRow key={c.application_id} candidate={c} i={i} jobId={jobId!} navigate={navigate} />)}
                      </div>
                    </div>
                  )}

                  {inProgress.length > 0 && (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#2563eb" }} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#2563eb", letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
                          En cours — {inProgress.length}
                        </span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {inProgress.map((c, i) => <CandidateRow key={c.application_id} candidate={c} i={i} jobId={jobId!} navigate={navigate} />)}
                      </div>
                    </div>
                  )}

                  {pendingList.length > 0 && (
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#d97706" }} />
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#d97706", letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
                          Pending — {pendingList.length}
                        </span>
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {pendingList.map((c, i) => <CandidateRow key={c.application_id} candidate={c} i={i} jobId={jobId!} navigate={navigate} />)}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Empty */}
              {!loading && candidates.length === 0 && !error && (
                <div key="empty" style={{ textAlign: "center", padding: "56px 0" }}>
                  <div style={{
                    width: 48, height: 48, borderRadius: 14,
                    background: TEAL_BG, border: `1px solid ${TEAL_BORDER}`,
                    display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px",
                  }}>
                    <Users size={20} color={TEAL} />
                  </div>
                  <p style={{ fontSize: 14, fontWeight: 700, color: TEXT_MAIN, margin: "0 0 6px" }}>No candidates for this job</p>
                  <p style={{ fontSize: 12, color: TEXT_SUB, margin: 0 }}>Candidates will appear here once they apply.</p>
                </div>
              )}
            </AnimatePresence>
          </Card>

        </div>
      </div>
    </>
  );
}