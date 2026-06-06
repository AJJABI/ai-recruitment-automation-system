/**
 * RHCandidateReport.tsx — Rapport complet candidat pour le RH
 * Layout: Hero header sombre + 2 colonnes (gauche: expérience timeline | droite: scores + décision)
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link, useParams } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell, User, ChevronLeft, CheckCircle2, XCircle,
  Calendar, Star, ThumbsUp, ThumbsDown, Award, Target,
  Clock, ChevronLeft as ChevLeft, ChevronRight,
  Mail, Briefcase,
} from "lucide-react";
import RHSidebar from "./RHSidebar";
import logoImg from "../assets/logoo.png";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
function getToken() { return localStorage.getItem("access_token") ?? ""; }
function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" };
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface FullReport {
  informations: {
    candidate_name  : string;
    candidate_email : string;
    job_title       : string;
    job_id          : number;
    applied_at      : string;
    status_v2       : string;
  };
  scores: {
    score_matching  : number;
    score_technique : number;
    score_final     : number;
    score_global    : number;
  };
  manager_review: {
    decision     : string;
    note         : string;
    manager_email: string | null;
    submitted_at : string;
  } | null;
  ia_report: {
    summary      : string;
    priority     : string;
    strengths    : string[];
    weaknesses   : string[];
    justification: Record<string, string>;
    generated_at : string;
  } | null;
  interview?: {
    scheduled_at: string;
    meeting_link: string;
    status      : string;
  } | null;
  presentiel?: {
    scheduled_at: string;
    meeting_link: string;
    status      : string;
  } | null;
  cv_url?: string | null;
  experience?: Array<{
    type: string;
    role: string;
    company: string;
    duration: string;
    details: string;
  }>;
  education?: Array<{
    degree: string;
    school: string;
    duration: string;
    details: string;
  }>;
}

interface Notification {
  id: number; message: string; type: string; read: boolean; link: string | null; created_at: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function scoreColor(s: number) {
  if (s >= 70) return "#10b981";
  if (s >= 50) return "#f59e0b";
  return "#ef4444";
}
function scoreBg(s: number) {
  if (s >= 70) return "rgba(16,185,129,0.12)";
  if (s >= 50) return "rgba(245,158,11,0.12)";
  return "rgba(239,68,68,0.12)";
}
function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { day: "2-digit", month: "long", year: "numeric" });
}
function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const MONTHS_EN = ["January","February","March","April","May","June","July","August","September","October","November","December"];

function translateMgrDecision(decision?: string | null) {
  if (!decision) return "";
  const map: Record<string,string> = {
    "Validé": "Accepted",
    "À approfondir": "Further evaluation",
    "Refusé": "Rejected",
  };
  return map[decision] ?? decision;
}

function getInitials(name: string) {
  return name.split(" ").map(p => p[0]).join("").toUpperCase().slice(0, 2);
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

// ─── ScoreBar ─────────────────────────────────────────────────────────────────

function ScoreBar({ label, score, delay = 0 }: { label: string; score: number; delay?: number }) {
  const color = scoreColor(score);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 13, color: "#475569" }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color, background: scoreBg(score), padding: "2px 10px", borderRadius: 999 }}>
          {score}/100
        </span>
      </div>
      <div style={{ height: 7, background: "#f1f5f9", borderRadius: 999, overflow: "hidden" }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ delay, type: "spring", stiffness: 140, damping: 26 }}
          style={{ height: "100%", background: color, borderRadius: 999 }}
        />
      </div>
    </div>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────

function Card({ children, delay = 0, style = {} }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 280, damping: 26 }}
      style={{
        background: "#ffffff",
        borderRadius: 16,
        border: "1px solid #e8e3f8",
        overflow: "hidden",
        ...style,
      }}
    >
      {children}
    </motion.div>
  );
}

// ─── SectionHeader ────────────────────────────────────────────────────────────

function SectionHeader({ icon, title, accent = "#7c3aed" }: { icon: React.ReactNode; title: string; accent?: string }) {
  return (
    <div style={{
      padding: "14px 20px",
      borderBottom: "1px solid #f0ecfc",
      display: "flex", alignItems: "center", gap: 10,
      background: "#faf9ff",
    }}>
      <div style={{
        width: 30, height: 30, borderRadius: 8,
        background: `${accent}18`,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        <div style={{ color: accent }}>{icon}</div>
      </div>
      <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>{title}</span>
    </div>
  );
}

// ─── MiniCalendar ─────────────────────────────────────────────────────────────

function MiniCalendar({ onSelect, selectedDate }: { onSelect: (d: Date) => void; selectedDate: Date | null }) {
  const today = new Date();
  const [cur, setCur] = useState(new Date(today.getFullYear(), today.getMonth(), 1));

  const firstDay = new Date(cur.getFullYear(), cur.getMonth(), 1).getDay();
  const offset   = firstDay === 0 ? 6 : firstDay - 1;
  const total    = new Date(cur.getFullYear(), cur.getMonth() + 1, 0).getDate();

  const prev = () => setCur(new Date(cur.getFullYear(), cur.getMonth() - 1, 1));
  const next = () => setCur(new Date(cur.getFullYear(), cur.getMonth() + 1, 1));

  const isSel  = (d: number) => selectedDate && selectedDate.getFullYear() === cur.getFullYear() && selectedDate.getMonth() === cur.getMonth() && selectedDate.getDate() === d;
  const isToday = (d: number) => today.getFullYear() === cur.getFullYear() && today.getMonth() === cur.getMonth() && today.getDate() === d;
  const isPast  = (d: number) => { const dd = new Date(cur.getFullYear(), cur.getMonth(), d); dd.setHours(0,0,0,0); const t = new Date(); t.setHours(0,0,0,0); return dd < t; };

  const cells: (number | null)[] = [...Array(offset).fill(null), ...Array.from({ length: total }, (_, i) => i + 1)];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <button onClick={prev} style={{ width: 26, height: 26, borderRadius: 7, border: "1px solid #e8e3f8", background: "#faf9ff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <ChevLeft size={13} color="#64748b" />
        </button>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#1e293b" }}>{MONTHS_EN[cur.getMonth()]} {cur.getFullYear()}</span>
        <button onClick={next} style={{ width: 26, height: 26, borderRadius: 7, border: "1px solid #e8e3f8", background: "#faf9ff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <ChevronRight size={13} color="#64748b" />
        </button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", textAlign: "center", marginBottom: 4 }}>
        {["M","T","W","T","F","S","S"].map((d, i) => (
          <div key={i} style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, padding: "2px 0" }}>{d}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7,1fr)", gap: 2, textAlign: "center" }}>
        {cells.map((d, i) => (
          <div key={i}
            onClick={() => d && !isPast(d) && onSelect(new Date(cur.getFullYear(), cur.getMonth(), d))}
            style={{
              padding: "5px 2px", borderRadius: 7, fontSize: 11,
              cursor: d && !isPast(d) ? "pointer" : "default",
              background: isSel(d ?? 0) ? "#7c3aed" : isToday(d ?? 0) ? "#f0ecfc" : "transparent",
              color: d ? (isSel(d) ? "#fff" : isPast(d) ? "#cbd5e1" : isToday(d) ? "#7c3aed" : "#334155") : "transparent",
              fontWeight: isSel(d ?? 0) || isToday(d ?? 0) ? 700 : 400,
            }}>
            {d ?? ""}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Notification Bell ────────────────────────────────────────────────────────

function NotifBell({ notifs, onMarkRead, onMarkAllRead }: {
  notifs: Notification[];
  onMarkRead: (id: number) => void;
  onMarkAllRead: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const unread = notifs.filter(n => !n.read).length;

  useEffect(() => {
    function h(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: 36, height: 36, borderRadius: 10, background: "#f1f5f9", border: "1px solid #e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", position: "relative" }}>
        <Bell size={15} color="#475569" />
        {unread > 0 && <div style={{ position: "absolute", top: 6, right: 6, width: 7, height: 7, borderRadius: "50%", background: "#f87171", border: "1.5px solid #fff" }} />}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -8, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6, scale: 0.97 }}
            style={{ position: "absolute", top: "calc(100% + 10px)", right: 0, width: 280, background: "#fff", borderRadius: 14, border: "1px solid #e8e3f8", boxShadow: "0 8px 32px rgba(90,40,160,0.14)", zIndex: 999, overflow: "hidden" }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid #f0ecfc", display: "flex", justifyContent: "space-between" }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>Notifications</span>
              {unread > 0 && <button onClick={onMarkAllRead} style={{ fontSize: 11, fontWeight: 600, cursor: "pointer", background: "none", border: "none", color: "#7c3aed" }}>Mark all read</button>}
            </div>
            <div style={{ maxHeight: 240, overflowY: "auto", padding: "8px 10px" }}>
              {notifs.length === 0 && <p style={{ fontSize: 12, color: "#94a3b8", textAlign: "center", padding: "16px 0", margin: 0 }}>No notifications</p>}
              {notifs.slice(0, 6).map(n => (
                <div key={n.id} onClick={() => !n.read && onMarkRead(n.id)}
                  style={{ padding: "8px 10px", borderRadius: 8, marginBottom: 4, cursor: "pointer", background: n.read ? "#f8fafc" : "#f0ecfc", opacity: n.read ? 0.6 : 1 }}>
                  <p style={{ fontSize: 12, fontWeight: n.read ? 500 : 700, color: "#1e293b", margin: 0 }}>{n.message}</p>
                  <p style={{ fontSize: 10, color: "#94a3b8", margin: "2px 0 0" }}>{relTime(n.created_at)}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Decision Modal ───────────────────────────────────────────────────────────

function DecisionModal({ open, decision, candidateName, onConfirm, onCancel, loading }: {
  open: boolean; decision: "HIRED" | "REJECTED_FINAL" | null;
  candidateName: string; onConfirm: (note: string) => void;
  onCancel: () => void; loading: boolean;
}) {
  const [note, setNote] = useState("");
  const isHired = decision === "HIRED";

  return (
    <AnimatePresence>
      {open && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          style={{ position: "fixed", inset: 0, background: "rgba(15,10,40,0.5)", backdropFilter: "blur(4px)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <motion.div initial={{ opacity: 0, scale: 0.92, y: 16 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.95 }} transition={{ type: "spring", stiffness: 400, damping: 28 }}
            style={{ background: "#fff", borderRadius: 20, padding: 28, width: 420, border: "1px solid #e8e3f8", boxShadow: "0 20px 60px rgba(90,40,160,0.18)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center", background: isHired ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)", flexShrink: 0 }}>
                {isHired ? <ThumbsUp size={20} color="#10b981" /> : <ThumbsDown size={20} color="#ef4444" />}
              </div>
              <div>
                <h3 style={{ fontSize: 16, fontWeight: 800, color: "#1e293b", margin: 0 }}>
                  {isHired ? "Confirm Hire" : "Confirm Rejection"}
                </h3>
                <p style={{ fontSize: 12, color: "#64748b", margin: "2px 0 0" }}>{candidateName}</p>
              </div>
            </div>
            {isHired && (
              <div style={{ marginBottom: 14, padding: "10px 14px", background: "rgba(16,185,129,0.06)", borderRadius: 10, border: "1px solid rgba(16,185,129,0.18)" }}>
                <p style={{ fontSize: 12, color: "#065f46", fontWeight: 600, margin: 0 }}>
                  ⚠️ This will close the job and notify other candidates.
                </p>
              </div>
            )}
            <div style={{ marginBottom: 18 }}>
              <label style={{ fontSize: 12, fontWeight: 700, color: "#475569", display: "block", marginBottom: 7 }}>
                {isHired ? "Note (optional)" : "Rejection reason (optional)"}
              </label>
              <textarea
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder={isHired ? "e.g.: In-person interview on 06/15/2026 at 10:00" : "e.g.: Profile does not match requirements"}
                rows={3}
                style={{ width: "100%", padding: "10px 13px", borderRadius: 10, border: "1px solid #e8e3f8", fontSize: 13, fontFamily: "inherit", outline: "none", resize: "none", background: "#f8fafc", boxSizing: "border-box" }}
              />
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={onCancel} style={{ flex: 1, padding: "10px 0", borderRadius: 10, border: "1px solid #e8e3f8", background: "transparent", color: "#64748b", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                Cancel
              </button>
              <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                onClick={() => onConfirm(note)} disabled={loading}
                style={{ flex: 2, padding: "10px 0", borderRadius: 10, border: "none", background: isHired ? "#10b981" : "#ef4444", color: "#fff", fontSize: 13, fontWeight: 700, cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1 }}>
                {loading ? "Processing..." : isHired ? "✅ Confirm Hire" : "❌ Confirm Rejection"}
              </motion.button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function RHCandidateReport() {
  const params        = useParams<{ job_id: string; application_id: string }>();
  const jobId         = params.job_id ?? "";
  const applicationId = params.application_id ?? "";
  const [, navigate]  = useLocation();

  const [report,     setReport]     = useState<FullReport | null>(null);
  const [notifs,     setNotifs]     = useState<Notification[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [modal,      setModal]      = useState<{ open: boolean; decision: "HIRED" | "REJECTED_FINAL" | null }>({ open: false, decision: null });
  const [submitting, setSubmitting] = useState(false);
  const [toast,      setToast]      = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  // Scores visibility
  const [scoresVisible, setScoresVisible] = useState(true);

  // Calendar state
  const [showCalendar,  setShowCalendar]  = useState(false);
  const [selDate,      setSelDate]      = useState<Date | null>(null);
  const [selTime,      setSelTime]      = useState<string | null>(null);
  const [calConfirmed, setCalConfirmed] = useState(false);
  const [calSaving,    setCalSaving]    = useState(false);
  const [calError,     setCalError]     = useState<string | null>(null);

  async function handleConfirmPresentiel() {
    if (!selDate || !selTime) return;
    setCalSaving(true);
    setCalError(null);

    // Construire la date ISO : selDate + selTime
    const [hours, minutes] = selTime.split(":").map(Number);
    const dt = new Date(selDate);
    dt.setHours(hours, minutes, 0, 0);
    // Construire l'ISO en heure locale (pas UTC) pour éviter le décalage timezone
    const pad = (n: number) => String(n).padStart(2, "0");
    const isoDate = `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}:00`;

    try {
      const res = await fetch(`${API_BASE}/applications/${applicationId}/schedule-presentiel`, {
        method  : "POST",
        headers : authHeaders(),
        body    : JSON.stringify({ scheduled_at: isoDate }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Erreur serveur");
      }
      setCalConfirmed(true);
      // Mettre à jour itw localement avec la date qu'on vient d'envoyer (pas de re-fetch, pas de timezone bug)
      setReport(prev => prev ? {
        ...prev,
        presentiel: { scheduled_at: isoDate, meeting_link: "", status: "scheduled" }
      } : prev);
      setToast({ msg: "Interview scheduled ✅", type: "ok" });
      setTimeout(() => setToast(null), 3000);
    } catch (e: any) {
      setCalError(e.message ?? "Error saving the slot");
    } finally {
      setCalSaving(false);
    }
  }

  useEffect(() => {
    if (!applicationId) return;
    fetch(`${API_BASE}/applications/${applicationId}/rh-full-report`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then((data: FullReport | null) => {
        setReport(data);
        // Sync calendar edit state if interview already scheduled
        if (data?.presentiel?.scheduled_at) {
          const saved = new Date(data.presentiel.scheduled_at);
          setSelDate(saved);
          const hh = String(saved.getHours()).padStart(2, "0");
          const mm = String(saved.getMinutes()).padStart(2, "0");
          setSelTime(`${hh}:${mm}`);
          setCalConfirmed(true);
        }
      })
      .catch(() => setReport(null))
      .finally(() => setLoading(false));

    fetch(`${API_BASE}/notifications`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setNotifs).catch(() => {});
  }, [applicationId]);

  async function markRead(id: number) {
    await fetch(`${API_BASE}/notifications/${id}/read`, { method: "PATCH", headers: authHeaders() });
    setNotifs(p => p.map(n => n.id === id ? { ...n, read: true } : n));
  }
  async function markAllRead() {
    await fetch(`${API_BASE}/notifications/read-all`, { method: "PATCH", headers: authHeaders() });
    setNotifs(p => p.map(n => ({ ...n, read: true })));
  }

  async function handleDecision(note: string) {
    if (!modal.decision) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/applications/${applicationId}/rh-decision`, {
        method: "POST", headers: authHeaders(),
        body: JSON.stringify({ decision: modal.decision, note }),
      });
      if (!res.ok) throw new Error();
      setToast({ msg: modal.decision === "HIRED" ? "Candidate hired ✅" : "Candidate rejected", type: modal.decision === "HIRED" ? "ok" : "err" });
      setModal({ open: false, decision: null });
      setTimeout(() => navigate(`/rh/ranking/${jobId}`), 1500);
    } catch {
      setToast({ msg: "Error — please try again", type: "err" });
    } finally {
      setSubmitting(false);
    }
  }

  const info       = report?.informations;
  const scores     = report?.scores;
  const mgr        = report?.manager_review;
  const itw        = report?.presentiel;  // entretien présentiel RH uniquement
  const experience = report?.experience ?? [];
  const education  = report?.education  ?? [];
  const cvUrl      = report?.cv_url;

  const isAlreadyDecided = info?.status_v2 === "HIRED" || info?.status_v2 === "REJECTED_FINAL" || info?.status_v2 === "POSITION_FILLED";

  const TIME_SLOTS = ["09:00","10:00","11:00","14:00","15:00","16:00"];

  const STATUS_MAP: Record<string, { label: string; color: string; bg: string; border: string }> = {
    ACCEPTED        : { label: "Accepted",         color: "#059669", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.3)" },
    TECH_EVALUATED  : { label: "Under review",      color: "#d97706", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.3)" },
    MEET_PENDING    : { label: "Interview scheduled", color: "#2563eb", bg: "rgba(59,130,246,0.10)", border: "rgba(59,130,246,0.25)" },
    WAITING_MEET    : { label: "Waiting",           color: "#7c3aed", bg: "rgba(124,58,237,0.10)", border: "rgba(124,58,237,0.25)" },
    HIRED           : { label: "Hired",             color: "#059669", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.3)" },
    REJECTED_FINAL  : { label: "Rejected",          color: "#dc2626", bg: "rgba(239,68,68,0.10)",  border: "rgba(239,68,68,0.25)" },
    POSITION_FILLED : { label: "Position filled",   color: "#64748b", bg: "rgba(100,116,139,0.10)",border: "rgba(100,116,139,0.2)" },
  };

  const st = info?.status_v2 ? STATUS_MAP[info.status_v2] : null;
  const initials = info?.candidate_name ? getInitials(info.candidate_name) : "—";

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes spin { to { transform: rotate(360deg); } }
        * { box-sizing: border-box; }
      `}</style>

      <RHSidebar />

      {/* Toast */}
      <AnimatePresence>
        {toast && (
          <motion.div initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
            style={{ position: "fixed", bottom: 28, left: "50%", transform: "translateX(-50%)", zIndex: 2000, background: toast.type === "ok" ? "#10b981" : "#ef4444", color: "#fff", padding: "11px 24px", borderRadius: 12, fontWeight: 700, fontSize: 14, boxShadow: "0 8px 24px rgba(0,0,0,0.15)" }}>
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      <DecisionModal
        open={modal.open} decision={modal.decision}
        candidateName={info?.candidate_name ?? ""}
        onConfirm={handleDecision} onCancel={() => setModal({ open: false, decision: null })}
        loading={submitting}
      />

      {/* ── Wrapper global ── */}
      <div style={{ marginLeft: 62, minHeight: "100vh", background: "#f5f3ff", display: "flex", flexDirection: "column" }}>

        {/* ══════════════════════════════════════════════════════════════
            HERO HEADER SOMBRE
        ══════════════════════════════════════════════════════════════ */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4 }}
          style={{
            background: "#ffffff",
            position: "relative",
            overflow: "hidden",
            borderBottom: "1px solid #e8e3f8",
          }}
        >
          {/* Décorations */}
          <div style={{ position: "absolute", top: -60, right: -60, width: 220, height: 220, borderRadius: "50%", background: "rgba(124,58,237,0.12)", pointerEvents: "none" }} />
          <div style={{ position: "absolute", bottom: -40, left: 200, width: 160, height: 160, borderRadius: "50%", background: "rgba(13,148,136,0.08)", pointerEvents: "none" }} />

          {/* Topbar dans le hero */}
          <div style={{ position: "relative", zIndex: 1, padding: "14px 32px", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid #f0ecfc" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <img src={logoImg} alt="logo" style={{ height: 30 }} />
              <div style={{ width: 1, height: 18, background: "#e2e8f0" }} />
              <Link href={`/rh/ranking/${jobId}`} style={{ textDecoration: "none" }}>
                <motion.div whileHover={{ x: -2 }} style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 12px", borderRadius: 8, background: "#f1f5f9", border: "1px solid #e2e8f0", color: "#1e293b", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
                  <ChevronLeft size={13} /> Ranking
                </motion.div>
              </Link>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#1e293b" }}>Candidate Assessment Report</div>
                <div style={{ fontSize: 11, color: "#94a3b8" }}>{loading ? "Loading..." : (info?.candidate_name ?? "")}</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <NotifBell notifs={notifs} onMarkRead={markRead} onMarkAllRead={markAllRead} />
              <Link href="/rh/account" style={{ textDecoration: "none" }}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: "#f1f5f9", border: "1px solid #e2e8f0", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
                  <User size={15} color="#475569" />
                </div>
              </Link>
            </div>
          </div>

          {/* Identité candidat */}
          <div style={{ position: "relative", zIndex: 1, padding: "24px 32px 28px", display: "flex", alignItems: "center", gap: 20 }}>
            {/* Avatar */}
            {loading ? (
              <Skel w={72} h={72} radius={18} />
            ) : (
              <div style={{
                width: 72, height: 72, borderRadius: 18,
                background: "linear-gradient(135deg, #7c3aed 0%, #4c1d95 100%)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 22, fontWeight: 800, color: "#fff", flexShrink: 0,
                border: "2px solid rgba(124,58,237,0.4)",
              }}>
                {initials}
              </div>
            )}

            {/* Infos */}
            <div style={{ flex: 1 }}>
              {loading ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <Skel w={200} h={24} radius={6} />
                  <Skel w={160} h={14} radius={6} />
                </div>
              ) : (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", margin: 0 }}>
                      {info?.candidate_name ?? "—"}
                    </h1>
                    {st && (
                      <span style={{ fontSize: 12, fontWeight: 700, padding: "4px 12px", borderRadius: 999, background: st.bg, color: st.color, border: `1px solid ${st.border}` }}>
                        {st.label}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 14, color: "#64748b", marginTop: 4 }}>
                    {info?.job_title ?? "—"}
                  </div>
                  <div style={{ display: "flex", gap: 20, marginTop: 10, flexWrap: "wrap" }}>
                    {info?.candidate_email && (
                      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#94a3b8" }}>
                        <Mail size={12} color="#94a3b8" />
                        {info.candidate_email}
                      </div>
                    )}
                    {info?.applied_at && (
                          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#94a3b8" }}>
                            <Calendar size={12} color="#94a3b8" />
                            Applied on {fmtDate(info.applied_at)}
                          </div>
                        )}
                  </div>
                </>
              )}
            </div>

            {/* Bouton planifier entretien */}
              {!isAlreadyDecided && (
              <motion.button
                whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                onClick={() => setShowCalendar(c => !c)}
                style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 18px", borderRadius: 11, border: "1px solid rgba(13,148,136,0.4)", background: showCalendar ? "rgba(13,148,136,0.15)" : "#f0fdf9", color: "#0d9488", fontSize: 13, fontWeight: 700, cursor: "pointer", flexShrink: 0 }}>
                <Calendar size={15} />
                Schedule in-person interview
              </motion.button>
            )}
          </div>
        </motion.div>

        {/* ══════════════════════════════════════════════════════════════
            CALENDRIER INLINE (visible si showCalendar)
        ══════════════════════════════════════════════════════════════ */}
        <AnimatePresence>
          {showCalendar && !isAlreadyDecided && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
              style={{ overflow: "hidden", background: "#fff", borderBottom: "1px solid #e8e3f8" }}
            >
              <div style={{ padding: "20px 32px", display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
                {/* Calendrier */}
                <div style={{ minWidth: 220 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 10 }}>Choose a date</div>
                  <MiniCalendar onSelect={d => { setSelDate(d); setSelTime(null); }} selectedDate={selDate} />
                </div>

                {/* Créneaux */}
                {selDate && (
                  <motion.div initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} style={{ minWidth: 200 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 10 }}>Choose a time slot</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
                      {TIME_SLOTS.map(t => (
                        <button key={t} onClick={() => setSelTime(t)}
                          style={{ padding: "7px 16px", borderRadius: 8, border: `1px solid ${selTime === t ? "#0d9488" : "#e8e3f8"}`, background: selTime === t ? "rgba(13,148,136,0.1)" : "#f8fafc", color: selTime === t ? "#0d9488" : "#475569", fontSize: 12, fontWeight: selTime === t ? 700 : 500, cursor: "pointer" }}>
                          {t}
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}

                {/* Confirmation affichée */}
                    {calConfirmed && selDate && selTime ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                    style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 18px", background: "rgba(16,185,129,0.07)", borderRadius: 12, border: "1px solid rgba(16,185,129,0.2)", alignSelf: "flex-end" }}>
                    <CheckCircle2 size={18} color="#10b981" />
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#064e3b" }}>
                        {selDate!.toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric" })} at {selTime}
                      </div>
                      <div style={{ fontSize: 11, color: "#10b981", marginTop: 2 }}>Slot confirmed</div>
                    </div>
                    <button onClick={() => { setCalConfirmed(false); setSelDate(null); setSelTime(null); }}
                      style={{ marginLeft: "auto", fontSize: 11, color: "#64748b", background: "none", border: "none", cursor: "pointer" }}>
                      Change
                    </button>
                  </motion.div>
                ) : selDate && selTime ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, alignSelf: "flex-end" }}>
                    {calError && (
                      <div style={{ fontSize: 12, color: "#ef4444", padding: "6px 12px", background: "rgba(239,68,68,0.07)", borderRadius: 8, border: "1px solid rgba(239,68,68,0.2)" }}>
                        ⚠ {calError}
                      </div>
                    )}
                    <motion.button initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                      onClick={handleConfirmPresentiel}
                      disabled={calSaving}
                      style={{ alignSelf: "flex-end", padding: "11px 24px", borderRadius: 10, border: "none", background: calSaving ? "#94a3b8" : "#0d9488", color: "#fff", fontSize: 13, fontWeight: 700, cursor: calSaving ? "not-allowed" : "pointer", display: "flex", alignItems: "center", gap: 8 }}>
                      {calSaving ? (
                        <><span style={{ display: "inline-block", width: 13, height: 13, border: "2px solid rgba(255,255,255,0.4)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin 0.7s linear infinite" }} /> Saving...</>
                      ) : "Confirm slot"}
                    </motion.button>
                  </div>
                ) : null}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ══════════════════════════════════════════════════════════════
            CORPS : 2 COLONNES
        ══════════════════════════════════════════════════════════════ */}
        <div style={{ flex: 1, padding: "28px 32px 48px", display: "grid", gridTemplateColumns: "1fr 380px", gap: 20, alignItems: "start" }}>

          {/* ── COLONNE GAUCHE : Expérience & Formation + Entretien ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Expérience & Formation */}
            <Card delay={0.05}>
              <SectionHeader icon={<Briefcase size={14} />} title="Experience & Education" accent="#0d9488" />
              <div style={{ padding: "18px 20px" }}>
                {loading ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <Skel w={200} h={24} radius={6} />
                    <Skel w={160} h={14} radius={6} />
                  </div>
                ) : experience.length === 0 && education.length === 0 ? (
                  <p style={{ fontSize: 13, color: "#94a3b8", margin: 0 }}>No data available</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

                    {/* Expérience professionnelle */}
                    {experience.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 14 }}>
                                  Work Experience
                                </div>
                        <div style={{ position: "relative", paddingLeft: 24 }}>
                          {/* Ligne verticale timeline */}
                          <div style={{ position: "absolute", left: 7, top: 8, bottom: 8, width: 2, background: "linear-gradient(to bottom, #0d9488, #7c3aed)", borderRadius: 999 }} />
                          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            {experience.map((exp, i) => (
                              <motion.div
                                key={i}
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.1 + i * 0.06 }}
                                style={{ position: "relative" }}
                              >
                                {/* Dot */}
                                <div style={{ position: "absolute", left: -20, top: 14, width: 10, height: 10, borderRadius: "50%", background: "#0d9488", border: "2px solid #fff", boxShadow: "0 0 0 2px rgba(13,148,136,0.2)" }} />
                                <div style={{ padding: "14px 16px", borderRadius: 12, background: "#f8fafc", border: "1px solid #e2e8f0" }}>
                                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                                    <div>
                                      <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>{exp.role}</div>
                                      {exp.company && <div style={{ fontSize: 12, color: "#0d9488", fontWeight: 600, marginTop: 2 }}>{exp.company}</div>}
                                    </div>
                                    {exp.type && (
                                      <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 9px", borderRadius: 999, background: "rgba(124,58,237,0.08)", color: "#7c3aed", border: "1px solid rgba(124,58,237,0.15)", whiteSpace: "nowrap", flexShrink: 0 }}>
                                        {exp.type}
                                      </span>
                                    )}
                                  </div>
                                  {exp.duration && (
                                    <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8", marginTop: 5 }}>
                                      <Clock size={11} />
                                      {exp.duration}
                                    </div>
                                  )}
                                  {exp.details && (
                                    <p style={{ fontSize: 13, color: "#475569", margin: "10px 0 0", lineHeight: 1.65 }}>{exp.details}</p>
                                  )}
                                </div>
                              </motion.div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Formation */}
                    {education.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 14 }}>
                          Education
                        </div>
                        <div style={{ position: "relative", paddingLeft: 24 }}>
                          <div style={{ position: "absolute", left: 7, top: 8, bottom: 8, width: 2, background: "linear-gradient(to bottom, #7c3aed, #3b82f6)", borderRadius: 999 }} />
                          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                            {education.map((edu, i) => (
                              <motion.div
                                key={i}
                                initial={{ opacity: 0, x: -8 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.15 + i * 0.06 }}
                                style={{ position: "relative" }}
                              >
                                <div style={{ position: "absolute", left: -20, top: 14, width: 10, height: 10, borderRadius: "50%", background: "#7c3aed", border: "2px solid #fff", boxShadow: "0 0 0 2px rgba(124,58,237,0.2)" }} />
                                <div style={{ padding: "14px 16px", borderRadius: 12, background: "#f5f3ff", border: "1px solid #e8e3f8" }}>
                                  <div style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>{edu.degree}</div>
                                  {edu.school && <div style={{ fontSize: 12, color: "#7c3aed", fontWeight: 600, marginTop: 2 }}>{edu.school}</div>}
                                  {edu.duration && (
                                    <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8", marginTop: 5 }}>
                                      <Calendar size={11} />
                                      {edu.duration}
                                    </div>
                                  )}
                                  {edu.details && (
                                    <p style={{ fontSize: 13, color: "#475569", margin: "10px 0 0", lineHeight: 1.65 }}>{edu.details}</p>
                                  )}
                                </div>
                              </motion.div>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Card>

          </div>

          {/* ── COLONNE DROITE : Décision Manager + Scores + Décision RH ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Note entretien planifié — visible si date confirmée (depuis backend ou nouvelle saisie) */}
            {(() => {
              // Source de vérité : d'abord le backend, sinon la saisie locale
              const interviewDate: Date | null = itw?.scheduled_at
                ? new Date(itw.scheduled_at)
                : (calConfirmed && selDate ? selDate : null);
              const interviewTime: string | null = itw?.scheduled_at
                ? (() => { const d = new Date(itw.scheduled_at); return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`; })()
                : selTime;

              return (
                <AnimatePresence>
                  {interviewDate && interviewTime && (
                    <motion.div
                      initial={{ opacity: 0, y: -10, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -8, scale: 0.97 }}
                      transition={{ type: "spring", stiffness: 300, damping: 26 }}
                      style={{
                        borderRadius: 16, border: "1px solid rgba(13,148,136,0.25)",
                        background: "linear-gradient(135deg, rgba(13,148,136,0.06) 0%, rgba(16,185,129,0.04) 100%)",
                        overflow: "hidden",
                      }}
                    >
                      <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(13,148,136,0.12)", display: "flex", alignItems: "center", gap: 10, background: "rgba(13,148,136,0.07)" }}>
                        <div style={{ width: 30, height: 30, borderRadius: 8, background: "rgba(13,148,136,0.15)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                          <Calendar size={14} color="#0d9488" />
                        </div>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>In-person interview scheduled</span>
                        <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999, background: "rgba(13,148,136,0.12)", color: "#0d9488", border: "1px solid rgba(13,148,136,0.2)" }}>
                          ✓ Confirmed
                        </span>
                      </div>
                      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                          {/* Icône date */}
                          <div style={{ width: 44, height: 44, borderRadius: 12, background: "#fff", border: "1px solid rgba(13,148,136,0.2)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 2px 8px rgba(13,148,136,0.08)" }}>
                            <div style={{ fontSize: 8, fontWeight: 800, color: "#0d9488", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                              {interviewDate.toLocaleDateString("en-US", { month: "short" })}
                            </div>
                            <div style={{ fontSize: 18, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
                              {interviewDate.getDate()}
                            </div>
                          </div>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>
                              {interviewDate.toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                            </div>
                            <div style={{ fontSize: 12, color: "#0d9488", fontWeight: 600, marginTop: 3, display: "flex", alignItems: "center", gap: 5 }}>
                              <Clock size={11} /> {interviewTime}
                            </div>
                          </div>
                        </div>
                        <div style={{ padding: "10px 14px", background: "#fff", borderRadius: 10, borderLeft: "3px solid #0d9488" }}>
                          <p style={{ fontSize: 12, color: "#475569", margin: 0, lineHeight: 1.65, fontStyle: "italic" }}>
                            "In-person interview scheduled with {info?.candidate_name ?? "the candidate"} for the position {info?.job_title ?? "—"}."
                          </p>
                        </div>
                        {!isAlreadyDecided && (
                          <button
                            onClick={() => { setCalConfirmed(false); setSelDate(null); setSelTime(null); setShowCalendar(true); setCalError(null); }}
                            style={{ alignSelf: "flex-end", fontSize: 11, color: "#64748b", background: "none", border: "1px solid #e2e8f0", borderRadius: 7, padding: "5px 12px", cursor: "pointer" }}>
                            Change slot
                          </button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              );
            })()}

            {/* Décision Manager */}
            <Card delay={0.07}>
              <SectionHeader icon={<Award size={14} />} title="Manager Decision" accent="#f59e0b" />
              <div style={{ padding: "16px 20px" }}>
                {loading ? <Skel w="100%" h={72} /> : !mgr ? (
                  <p style={{ fontSize: 13, color: "#94a3b8", margin: 0 }}>No manager decision recorded</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      {/* Avatar manager */}
                      <div style={{ width: 34, height: 34, borderRadius: 9, background: "linear-gradient(135deg, #f59e0b, #d97706)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, color: "#fff", flexShrink: 0 }}>
                        {mgr.manager_email ? mgr.manager_email.slice(0, 2).toUpperCase() : "JD"}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>{mgr.manager_email || "Manager"}</div>
                        <div style={{ fontSize: 11, color: "#94a3b8" }}>{fmtDate(mgr.submitted_at)}</div>
                      </div>
                      <span style={{
                        fontSize: 12, fontWeight: 700, padding: "4px 12px", borderRadius: 999,
                        background: mgr.decision === "Validé" ? "rgba(16,185,129,0.1)" : mgr.decision === "À approfondir" ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)",
                        color:      mgr.decision === "Validé" ? "#059669"             : mgr.decision === "À approfondir" ? "#d97706"              : "#dc2626",
                        border:     `1px solid ${mgr.decision === "Validé" ? "rgba(16,185,129,0.25)" : mgr.decision === "À approfondir" ? "rgba(245,158,11,0.25)" : "rgba(239,68,68,0.2)"}`,
                      }}>
                        {mgr.decision === "Validé" ? "✓ " : mgr.decision === "À approfondir" ? "~ " : "✗ "}{translateMgrDecision(mgr.decision)}
                      </span>
                    </div>
                    {mgr.note && (
                      <div style={{ padding: "10px 14px", background: "#faf9ff", borderRadius: 10, borderLeft: "3px solid #7c3aed" }}>
                        <p style={{ fontSize: 12, color: "#475569", margin: 0, lineHeight: 1.65, fontStyle: "italic" }}>"{mgr.note}"</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {/* Scores d'évaluation */}
            <Card delay={0.1}>
              <div style={{
                padding: "14px 20px",
                borderBottom: scoresVisible ? "1px solid #f0ecfc" : "none",
                display: "flex", alignItems: "center", gap: 10,
                background: "#faf9ff",
              }}>
                <div style={{ width: 30, height: 30, borderRadius: 8, background: "#3b82f618", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <div style={{ color: "#3b82f6" }}><Target size={14} /></div>
                </div>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", flex: 1 }}>Evaluation Scores</span>
                <button
                  onClick={() => setScoresVisible(v => !v)}
                  style={{ fontSize: 11, fontWeight: 600, color: "#64748b", background: "#f1f5f9", border: "1px solid #e2e8f0", borderRadius: 7, padding: "4px 11px", cursor: "pointer", display: "flex", alignItems: "center", gap: 5 }}>
                  {scoresVisible ? "Hide" : "Show"}
                </button>
              </div>
              <AnimatePresence initial={false}>
                {scoresVisible && (
                  <motion.div
                    key="scores-body"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    style={{ overflow: "hidden" }}
                  >
                    <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
                      {loading ? [1,2,3,4].map(i => <Skel key={i} w="100%" h={28} />) : (
                        <>
                          <ScoreBar label="Matching Score"  score={scores?.score_matching  ?? 0} delay={0.14} />
                          <ScoreBar label="Technical Score" score={scores?.score_technique ?? 0} delay={0.18} />
                          <ScoreBar label="Final Score"     score={scores?.score_final     ?? 0} delay={0.22} />
                          <div style={{ height: 1, background: "#f1f5f9" }} />
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                            <span style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>Overall Score</span>
                            <span style={{ fontSize: 22, fontWeight: 800, color: scoreColor(scores?.score_global ?? 0) }}>
                              {scores?.score_global ?? 0}<span style={{ fontSize: 13, fontWeight: 500, color: "#94a3b8" }}>/100</span>
                            </span>
                          </div>
                        </>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </Card>

            {/* Décision Finale RH */}
            {!isAlreadyDecided ? (
              <Card delay={0.13}>
                <SectionHeader icon={<Star size={14} />} title="Final HR Decision" accent="#7c3aed" />
                <div style={{ padding: "16px 20px", display: "flex", gap: 10 }}>
                  <motion.button
                    whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                    onClick={() => setModal({ open: true, decision: "HIRED" })}
                    style={{ flex: 1, padding: "13px 0", borderRadius: 11, border: "none", background: "#10b981", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
                    <ThumbsUp size={15} /> Hire
                  </motion.button>
                  <motion.button
                    whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                    onClick={() => setModal({ open: true, decision: "REJECTED_FINAL" })}
                    style={{ flex: 1, padding: "13px 0", borderRadius: 11, border: "none", background: "#ef4444", color: "#fff", fontSize: 13, fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
                    <ThumbsDown size={15} /> Reject
                  </motion.button>
                </div>
              </Card>
            ) : info ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.13 }}
                style={{ padding: "16px 20px", background: "#fff", borderRadius: 16, border: "1px solid #e8e3f8", display: "flex", alignItems: "center", gap: 12 }}>
                {info.status_v2 === "HIRED"
                  ? <CheckCircle2 size={20} color="#10b981" />
                  : <XCircle size={20} color="#ef4444" />
                }
                <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                  {info.status_v2 === "HIRED"
                    ? "Candidate hired — final decision recorded"
                    : info.status_v2 === "POSITION_FILLED"
                    ? "Position filled — candidate not selected"
                    : "Candidate rejected — final decision recorded"}
                </span>
              </motion.div>
            ) : null}

          </div>
        </div>
      </div>
    </>
  );
}