/**
 * RHRanking.tsx — Final Ranking by Job
 * Group 1: Approved | Group 2: To Review
 * Sorted by global score descending
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link, useParams } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell, User,
  ChevronLeft, ChevronRight,
  CheckCircle2, AlertTriangle, UserX, Medal,
  Users, Loader2,
} from "lucide-react";
import bgWave  from "../assets/imagee.png";
import logoImg from "../assets/logoo.png";
import RHSidebar from "./RHSidebar";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
function getToken() { return localStorage.getItem("access_token") ?? ""; }
function authHeaders() { return { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" }; }

// ─── Types ────────────────────────────────────────────────────────────────────

interface Candidat {
  application_id : number;
  candidate_name : string;
  candidate_email: string;
  score_final    : number;
  technical_score: number;
  score_global   : number;
  manager_note   : string;
  status_v2      : string;
}

interface RankingData {
  job_id   : number;
  groupe_1 : { label: string; candidats: Candidat[] };
  groupe_2 : { label: string; candidats: Candidat[] };
}

interface Notification {
  id        : number;
  message   : string;
  type      : "info" | "success" | "warning" | "error";
  read      : boolean;
  link      : string | null;
  created_at: string;
}


// ─── Helpers ──────────────────────────────────────────────────────────────────

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function scoreColor(score: number) {
  if (score >= 70) return "#10b981";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

function scoreBg(score: number) {
  if (score >= 70) return "rgba(16,185,129,0.08)";
  if (score >= 50) return "rgba(245,158,11,0.08)";
  return "rgba(239,68,68,0.08)";
}

function initials(name: string) {
  return name.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2);
}

function avatarColor(name: string) {
  const colors = ["#7c3aed","#2563eb","#0d9488","#d97706","#dc2626","#7c3aed","#059669"];
  const idx = name.charCodeAt(0) % colors.length;
  return colors[idx];
}

function Skel({ w, h, radius = 8 }: { w: number | string; h: number; radius?: number }) {
  return (
    <div style={{
      width: w, height: h, borderRadius: radius,
      background: "linear-gradient(90deg,#f1f5f9 25%,#e2e8f0 50%,#f1f5f9 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.5s infinite",
    }} />
  );
}

// ─── Score Bar ────────────────────────────────────────────────────────────────

function ScoreBar({ score, delay = 0 }: { score: number; delay?: number }) {
  const color = scoreColor(score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ flex: 1, height: 8, background: "rgba(240,235,255,0.8)", borderRadius: 999, overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ delay, type: "spring", stiffness: 180, damping: 28 }}
          style={{ height: "100%", background: color, borderRadius: 999 }}
        />
      </div>
      <span style={{
        fontSize: 14, fontWeight: 800, color,
        minWidth: 36, textAlign: "right",
      }}>
        {score}
      </span>
    </div>
  );
}

// ─── TopBar ───────────────────────────────────────────────────────────────────

function TopBar({ jobId, jobTitle, notifs, onMarkRead, onMarkAllRead, onElargir, elargirDone, loadingElargir, elargirError }: {
  jobId    : string;
  jobTitle : string;
  notifs   : Notification[];
  onMarkRead   : (id: number) => void;
  onMarkAllRead: () => void;
  onElargir    : () => void;
  elargirDone  : boolean;
  loadingElargir: boolean;
  elargirError  : string;
}) {
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const unreadCount = notifs.filter(n => !n.read).length;

  useEffect(() => {
    function h(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false);
    }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: -16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      style={{
        marginLeft: 55, marginBottom: 28,
        background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
        borderRadius: 20, border: "1px solid rgba(200,185,255,0.25)",
        boxShadow: "0 4px 24px rgba(90,40,160,0.08)",
        padding: "16px 24px", display: "flex", alignItems: "center", justifyContent: "space-between",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Back button */}
          <Link href="/rh/ranking" style={{ textDecoration: "none" }}>
            <motion.div
              whileHover={{ scale: 1.08, x: -2 }} whileTap={{ scale: 0.95 }}
              style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "6px 12px", borderRadius: 10,
                background: "rgba(124,58,237,0.08)", color: "#7c3aed",
                fontSize: 12, fontWeight: 700, cursor: "pointer",
              }}
            >
              <ChevronLeft size={14} />
              Jobs
            </motion.div>
          </Link>
          <div style={{ width: 1, height: 24, background: "rgba(200,185,255,0.4)" }} />
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 800, color: "#1c2a38", margin: 0, letterSpacing: "-0.02em" }}>
              Candidate Ranking
            </h1>
            <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, fontWeight: 600 }}>
              {jobTitle || `Job #${jobId}`}
            </p>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>

        {/* ── Expand selection button ── */}
        {elargirDone ? (
          <span style={{
            fontSize: 12, fontWeight: 700, color: "#f59e0b",
            background: "rgba(245,158,11,0.10)", padding: "7px 16px",
            borderRadius: 999, border: "1px solid rgba(245,158,11,0.25)",
          }}>
            ⏳ Waiting for manager
          </span>
        ) : (
          <motion.button
            whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
            onClick={onElargir}
            disabled={loadingElargir}
            style={{
              display: "flex", alignItems: "center", gap: 7,
              padding: "8px 18px", borderRadius: 12, fontSize: 12, fontWeight: 700,
              border: "none", cursor: loadingElargir ? "not-allowed" : "pointer",
              background: loadingElargir
                ? "#e2e8f0"
                : "linear-gradient(135deg,#6366f1,#4f46e5)",
              color: loadingElargir ? "#94a3b8" : "#fff",
              boxShadow: loadingElargir ? "none" : "0 4px 12px rgba(99,102,241,0.3)",
              opacity: loadingElargir ? 0.65 : 1,
              transition: "all 0.15s",
            }}
          >
            {loadingElargir
              ? <><div style={{ width: 12, height: 12, border: "2px solid #94a3b8", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} /> Sending...</>
              : <><Users size={13} /> Expand selection</>
            }
          </motion.button>
        )}

        <div ref={bellRef} style={{ position: "relative" }}>
          <div onClick={() => setBellOpen(o => !o)} style={{
            width: 38, height: 38, borderRadius: 11,
            background: bellOpen ? "rgba(124,58,237,0.10)" : "rgba(255,255,255,0.8)",
            border: `1px solid ${bellOpen ? "rgba(124,58,237,0.25)" : "rgba(255,255,255,0.9)"}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", position: "relative",
          }}>
            <Bell size={16} color={bellOpen ? "#7c3aed" : "#64748b"} />
            {unreadCount > 0 && (
              <div style={{ position: "absolute", top: 5, right: 5, width: 8, height: 8, borderRadius: "50%", background: "#ef4444", border: "1.5px solid #fff" }} />
            )}
          </div>
          <AnimatePresence>
            {bellOpen && (
              <motion.div
                initial={{ opacity: 0, y: -8, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -6, scale: 0.97 }}
                style={{
                  position: "absolute", top: "calc(100% + 10px)", right: 0, width: 300,
                  background: "rgba(255,255,255,0.97)", backdropFilter: "blur(20px)",
                  borderRadius: 16, border: "1px solid rgba(200,185,255,0.35)",
                  boxShadow: "0 8px 32px rgba(90,40,160,0.15)", zIndex: 999, overflow: "hidden",
                }}
              >
                <div style={{ padding: "14px 16px 12px", borderBottom: "1px solid rgba(240,235,255,0.8)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>Notifications</span>
                  {unreadCount > 0 && (
                    <button onClick={onMarkAllRead} style={{ fontSize: 11, fontWeight: 600, cursor: "pointer", background: "none", border: "none", color: "#0d9488" }}>
                      Mark all read
                    </button>
                  )}
                </div>
                <div style={{ maxHeight: 280, overflowY: "auto", padding: "8px 10px" }}>
                  {notifs.length === 0 ? (
                    <p style={{ textAlign: "center", fontSize: 12, color: "#94a3b8", padding: "20px 0" }}>No notifications</p>
                  ) : notifs.slice(0, 8).map(n => (
                    <div key={n.id} onClick={() => !n.read && onMarkRead(n.id)}
                      style={{ padding: "8px 10px", borderRadius: 8, marginBottom: 4, cursor: "pointer",
                        background: n.read ? "#f8fafc" : "rgba(124,58,237,0.06)", opacity: n.read ? 0.6 : 1 }}>
                      <p style={{ fontSize: 12, fontWeight: n.read ? 500 : 700, color: "#1c2a38", margin: 0 }}>{n.message}</p>
                      <p style={{ fontSize: 10, color: "#94a3b8", margin: "2px 0 0" }}>{relTime(n.created_at)}</p>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <Link href="/rh/account" style={{ textDecoration: "none" }}>
          <div style={{ width: 38, height: 38, borderRadius: 11, background: "rgba(255,255,255,0.8)", border: "1px solid rgba(255,255,255,0.9)", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
            <User size={16} color="#64748b" />
          </div>
        </Link>
      </div>
    </motion.div>
  );
}

// ─── Candidate Row ─────────────────────────────────────────────────────────────

function CandidatRow({ candidat, rank, jobId, delay }: {
  candidat: Candidat;
  rank    : number;
  jobId   : string;
  delay   : number;
}) {
  const color    = scoreColor(candidat.score_global);
  const bg       = scoreBg(candidat.score_global);
  const avatarBg = avatarColor(candidat.candidate_name);

  const medalColors: Record<number, string> = { 1: "#f59e0b", 2: "#94a3b8", 3: "#cd7f32" };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 280, damping: 26 }}
      whileHover={{ scale: 1.01, boxShadow: "0 6px 24px rgba(90,40,160,0.10)" }}
      style={{
        display: "grid",
        gridTemplateColumns: "48px 1fr 180px 80px",
        alignItems: "center",
        gap: 16,
        padding: "16px 20px",
        background: "rgba(255,255,255,0.7)",
        borderRadius: 14,
        border: "1px solid rgba(200,185,255,0.2)",
        cursor: "pointer",
        transition: "box-shadow 0.2s",
      }}
    >
      {/* Rank */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
        {rank <= 3 ? (
          <Medal size={22} color={medalColors[rank]} />
        ) : (
          <span style={{ fontSize: 15, fontWeight: 800, color: "#94a3b8" }}>#{rank}</span>
        )}
      </div>

      {/* Candidate info */}
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 12, flexShrink: 0,
          background: avatarBg, display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, fontWeight: 800, color: "#fff",
        }}>
          {initials(candidat.candidate_name)}
        </div>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38" }}>
              {candidat.candidate_name}
            </span>
            {candidat.status_v2 === "HIRED" && (
              <span style={{
                fontSize: 10, fontWeight: 800, letterSpacing: "0.06em",
                background: "#dcfce7", color: "#16a34a",
                border: "1px solid #bbf7d0",
                padding: "2px 8px", borderRadius: 999,
              }}>✓ HIRED</span>
            )}
            {candidat.status_v2 === "POSITION_FILLED" && (
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: "0.04em",
                background: "#f1f5f9", color: "#64748b",
                border: "1px solid #e2e8f0",
                padding: "2px 8px", borderRadius: 999,
              }}>Position Filled</span>
            )}
          </div>
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
            {candidat.candidate_email}
          </div>
        </div>
      </div>

      {/* Global score */}
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 2 }}>
          <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>Global Score</span>
          <span style={{
            fontSize: 13, fontWeight: 800, color,
            background: bg, padding: "2px 8px", borderRadius: 999,
          }}>
            {candidat.score_global}/100
          </span>
        </div>
        <ScoreBar score={candidat.score_global} delay={delay + 0.1} />
      </div>

      {/* Action */}
      <Link href={`/rh/candidate/${jobId}/${candidat.application_id}`} style={{ textDecoration: "none" }}>
        <motion.div
          whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
            background: "linear-gradient(135deg, #7c3aed, #6d28d9)",
            color: "#fff", borderRadius: 10, padding: "9px 14px",
            fontSize: 12, fontWeight: 700, cursor: "pointer",
            boxShadow: "0 3px 12px rgba(124,58,237,0.25)",
          }}
        >
          Report
          <ChevronRight size={13} />
        </motion.div>
      </Link>
    </motion.div>
  );
}

// ─── Group Section ───────────────────────────────────────────────────────────

function GroupeSection({ title, icon, color, bg, borderColor, candidats, jobId, loading, delay }: {
  title      : string;
  icon       : React.ReactNode;
  color      : string;
  bg         : string;
  borderColor: string;
  candidats  : Candidat[];
  jobId      : string;
  loading    : boolean;
  delay      : number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 280, damping: 26 }}
      style={{
        background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
        borderRadius: 20, border: `1px solid ${borderColor}`,
        boxShadow: "0 4px 20px rgba(90,40,160,0.08)",
        overflow: "hidden", marginBottom: 24,
      }}
    >
      {/* Header */}
      <div style={{
        padding: "18px 24px",
        borderBottom: `1px solid ${borderColor}`,
        display: "flex", alignItems: "center", gap: 12,
        background: bg,
      }}>
        {icon}
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 800, color: "#1c2a38", margin: 0 }}>{title}</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: "2px 0 0" }}>
            {loading ? "..." : `${candidats.length} candidate${candidats.length > 1 ? "s" : ""}`}
          </p>
        </div>
        {!loading && candidats.length > 0 && (
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#64748b", fontWeight: 600 }}>Average score:</span>
            <span style={{
              fontSize: 13, fontWeight: 800, color,
              background: "rgba(255,255,255,0.8)", padding: "3px 10px", borderRadius: 999,
            }}>
              {Math.round(candidats.reduce((a, c) => a + c.score_global, 0) / candidats.length)}/100
            </span>
          </div>
        )}
      </div>

      {/* Content */}
      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 10 }}>
        {loading ? (
          [1, 2].map(i => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "48px 1fr 180px 80px", gap: 16, padding: "16px 20px", background: "#f8fafc", borderRadius: 14 }}>
              <Skel w={24} h={24} radius={999} />
              <div style={{ display: "flex", gap: 12 }}>
                <Skel w={40} h={40} radius={12} />
                <div style={{ display: "flex", flexDirection: "column", gap: 6, justifyContent: "center" }}>
                  <Skel w={120} h={13} />
                  <Skel w={160} h={11} />
                </div>
              </div>
              <Skel w="100%" h={32} radius={8} />
              <Skel w="100%" h={36} radius={10} />
            </div>
          ))
        ) : candidats.length === 0 ? (
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            padding: "36px 0", gap: 10,
          }}>
            <UserX size={36} color="#cbd5e1" />
            <p style={{ fontSize: 14, color: "#94a3b8", fontWeight: 600, margin: 0 }}>
              No candidates in this group
            </p>
          </div>
        ) : (
          /* Table header */
          <>
            <div style={{
              display: "grid", gridTemplateColumns: "48px 1fr 180px 80px",
              gap: 16, padding: "6px 20px",
            }}>
              {["#", "Candidate", "Global Score", ""].map((h, i) => (
                <div key={i} style={{
                  fontSize: 11, fontWeight: 700, color: "#94a3b8",
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  textAlign: i === 2 ? "left" : i === 3 ? "center" : "left",
                }}>{h}</div>
              ))}
            </div>
            {candidats.map((c, i) => (
              <CandidatRow
                key={c.application_id}
                candidat={c}
                rank={i + 1}
                jobId={jobId}
                delay={delay + i * 0.05}
              />
            ))}
          </>
        )}
      </div>
    </motion.div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function RHRanking() {
  const params = useParams<{ job_id: string }>();
  const jobId  = params.job_id ?? "";

  const [ranking,         setRanking]         = useState<RankingData | null>(null);
  const [jobTitle,        setJobTitle]        = useState("");
  const [notifs,          setNotifs]          = useState<Notification[]>([]);
  const [loading,         setLoading]         = useState(true);
  const [loadingElargir,  setLoadingElargir]  = useState(false);
  const [elargirDone,     setElargirDone]     = useState(false);
  const [elargirError,    setElargirError]    = useState("");

  useEffect(() => {
    if (!jobId) return;

    // Fetch ranking
    fetch(`${API_BASE}/applications/rh-final-ranking?job_id=${jobId}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(setRanking)
      .catch(() => setRanking(null))
      .finally(() => setLoading(false));

    // Fetch job title
    fetch(`${API_BASE}/jobs/${jobId}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setJobTitle(d.title))
      .catch(() => {});

    // Fetch notifs
    fetch(`${API_BASE}/notifications`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setNotifs)
      .catch(() => setNotifs([]));


  }, [jobId]);

  async function handleElargir() {
    setLoadingElargir(true);
    setElargirError("");
    try {
      const res = await fetch(`${API_BASE}/applications/request-expand/${jobId}`, {
        method : "POST",
        headers: authHeaders(),
      });
      const data = await res.json();
      if (!res.ok) {
        setElargirError(data.detail ?? "Error while requesting expanded selection");
      } else if (data.success === false) {
        const msg = data.message ?? "No candidate available to expand the selection.";
        setElargirError(msg);
        setTimeout(() => setElargirError(""), 5000);
      } else {
        setElargirDone(true);
      }
    } catch {
      setElargirError("Unable to contact server");
    } finally {
      setLoadingElargir(false);
    }
  }

  async function markRead(id: number) {
    await fetch(`${API_BASE}/notifications/${id}/read`, { method: "PATCH", headers: authHeaders() });
    setNotifs(p => p.map(n => n.id === id ? { ...n, read: true } : n));
  }

  async function markAllRead() {
    await fetch(`${API_BASE}/notifications/read-all`, { method: "PATCH", headers: authHeaders() });
    setNotifs(p => p.map(n => ({ ...n, read: true })));
  }

  return (
    <>
      <style>{`
        @keyframes floatLogo { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
        @keyframes shimmer   { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes spin      { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>

      <RHSidebar />

      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 48px", maxWidth: 1100, margin: "0 auto" }}>

          {/* TopBar */}
          <TopBar
            jobId={jobId} jobTitle={jobTitle}
            notifs={notifs} onMarkRead={markRead} onMarkAllRead={markAllRead}
            onElargir={handleElargir} elargirDone={elargirDone} loadingElargir={loadingElargir} elargirError={elargirError}
          />

          {/* ── Expand selection alert — no candidates available ── */}
          {elargirError && (
            <div style={{
              marginLeft: 55, marginBottom: 16,
              display: "flex", alignItems: "center", gap: 12,
              padding: "14px 20px", borderRadius: 14,
              background: "rgba(239,68,68,0.06)",
              border: "1px solid rgba(239,68,68,0.2)",
              animation: "fadeIn 0.2s ease",
            }}>
              <AlertTriangle size={18} color="#dc2626" style={{ flexShrink: 0 }} />
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: 13, fontWeight: 700, color: "#dc2626", margin: 0 }}>
                  Unable to expand selection
                </p>
                <p style={{ fontSize: 12, color: "#991b1b", margin: "2px 0 0" }}>
                  {elargirError}
                </p>
              </div>
              <button
                onClick={() => setElargirError("")}
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "#dc2626", fontSize: 18, lineHeight: 1, padding: "0 4px",
                  flexShrink: 0,
                }}
              >×</button>
            </div>
          )}

          {/* Group 1 — Approved */}
          <div style={{ marginLeft: 55 }}>
            <GroupeSection
              title="Final Selection"
              icon={<CheckCircle2 size={22} color="#10b981" />}
              color="#10b981"
              bg="rgba(16,185,129,0.05)"
              borderColor="rgba(16,185,129,0.2)"
              candidats={ranking?.groupe_1.candidats ?? []}
              jobId={jobId}
              loading={loading}
              delay={0.1}
            />

          



          </div>

        </div>
      </div>
    </>
  );
}