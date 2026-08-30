import { useState, useEffect } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  format, startOfMonth, endOfMonth,
  eachDayOfInterval, getDay, isToday, parseISO,
} from "date-fns";
import {
  ChevronLeft, ChevronRight, Plus, Trash2, Clock,
  Copy, Check, BrainCircuit, CalendarDays, ExternalLink,
  LayoutDashboard, Briefcase, Users, MessageSquare, LogOut, Send,
} from "lucide-react";

import logoImg from "../assets/logoo.png";
import bgWave  from "../assets/imagee.png";

// ─── Types ────────────────────────────────────────────────────────────────────

type SlotStatus = "available" | "booked";

interface Slot {
  id: number;
  job_id?: number | null;
  date: string;
  start_time: string;
  end_time: string;
  status: SlotStatus;
  candidate_name?: string | null;
  candidate_email?: string | null;
  meet_link?: string | null;
  job_title?: string | null;
}

interface Job {
  id: number;
  title: string;
  department?: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const API_BASE  = import.meta.env.VITE_API_BASE_URL  ?? "http://localhost:8000";
const N8N_BASE  = import.meta.env.VITE_N8N_BASE_URL  ?? "http://localhost:5678";
const DAY_LABELS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];

function getToken(): string | null {
  return localStorage.getItem("access_token");
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function getBookingUrl(): string {
  return `${window.location.origin}/booking`;
}

// ─── Shimmer Skeleton ─────────────────────────────────────────────────────────

function Skel({ w, h, radius = 8 }: { w: number | string; h: number; radius?: number }) {
  return (
    <div style={{
      width: w, height: h, borderRadius: radius,
      background: "linear-gradient(90deg,#f1f5f9 25%,#e2e8f0 50%,#f1f5f9 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.5s infinite",
    }} />
  );
}

// ─── Sidebar — floating pill (same as Dashboard) ──────────────────────────────

const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

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
          {/* Arrow */}
          <div style={{
            position: "absolute",
            right: "100%",
            top: "50%",
            transform: "translateY(-50%)",
            width: 0, height: 0,
            borderTop: "5px solid transparent",
            borderBottom: "5px solid transparent",
            borderRight: "6px solid #3b0d8e",
          }} />
          <div style={{
            background: "#3b0d8e",
            color: "#fff",
            fontSize: 15,
            fontWeight: 700,
            padding: "6px 14px",
            borderRadius: 10,
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
      top: 140,
      left: 16,
      zIndex: 50,
      borderRadius: 30,
      background: "linear-gradient(180deg, #4a1d96 0%, #3b0d8e 55%, #2c0f70 100%)",
      boxShadow: "0 8px 32px rgba(60,12,120,0.30), 0 2px 8px rgba(0,0,0,0.15)",
      padding: "18px 8px",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
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
                width: 40, height: 40, margin: "0 auto", borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer",
                background: active
                  ? "rgba(255,255,255,0.20)"
                  : hovered ? "rgba(255,255,255,0.11)" : "transparent",
                transition: "background 0.15s",
                position: "relative",
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

      {/* Divider */}
      <div style={{
        width: 32, height: 1,
        background: "rgba(255,255,255,0.14)",
        margin: "6px 0", flexShrink: 0,
      }} />

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

// ─── Card wrapper (glass, same as Dashboard) ──────────────────────────────────

function Card({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
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
      }}
    >
      {children}
    </motion.div>
  );
}

// ─── Page principale ──────────────────────────────────────────────────────────

export default function ManagerScheduler() {
  const [, navigate] = useLocation();

  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [slots, setSlots] = useState<Slot[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [newSlot, setNewSlot] = useState({ date: "", startTime: "09:00", endTime: "10:00" });
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);
  const [sendingInv, setSendingInv] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [rejectedCandidates, setRejectedCandidates] = useState<{
    application_id: number;
    candidate_name: string;
    candidate_email: string;
    expired_at: string | null;
  }[]>([]);

  const [waitingCandidates, setWaitingCandidates] = useState<{
    id: number;
    candidate_name: string;
    candidate_email: string;
    score_final: number;
    score_technique: number;
  }[]>([]);
  const [relancerLoading, setRelancerLoading] = useState(false);
  const [relancerDone,    setRelancerDone]    = useState(false);

  // Auth guard
  useEffect(() => { if (!getToken()) navigate("/"); }, [navigate]);

  // Fetch manager's jobs once
  useEffect(() => {
    fetch(`${API_BASE}/jobs/manager/dashboard`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then((data: Job[]) => {
        setJobs(data);
        if (data.length > 0) setSelectedJobId(data[0]!.id);
      })
      .catch(() => {});
  }, []);

  // Toast auto-dismiss
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 5000);
    return () => clearTimeout(t);
  }, [toast]);

  const monthKey = format(currentMonth, "yyyy-MM");
  const todayStr = format(new Date(), "yyyy-MM-dd");

  // KPI data
  const availableCount = slots.filter(s => s.status === "available").length;
  const bookedCount    = slots.filter(s => s.status === "booked").length;
  const todayBooked    = slots.filter(s => s.date === todayStr && s.status === "booked").length;

  const kpis = [
    { icon: CalendarDays, label: `${availableCount} available`, color: "#0d9488" },
    { icon: Clock,        label: `${bookedCount} booked`,       color: "#7c3aed" },
    { icon: BrainCircuit, label: `${todayBooked} today`,        color: "#f59e0b" },
  ];

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  // Envoyer invitations entretien aux candidats MEET_PENDING
  async function handleSendInvitations() {
    if (!selectedJobId || sendingInv) return;
    setSendingInv(true);
    try {
      const res = await fetch(`http://localhost:5678/webhook/envoyer-invitations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: selectedJobId,
          token: getToken(),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setToast({ msg: err.detail ?? "Error sending invitations.", type: "err" });
      } else {
        const data = await res.json().catch(() => ({}));
        const count = data.tokens?.length ?? data.message ?? "?";
        setToast({ msg: `✅ Invitations sent `, type: "ok" });
      }
    } catch {
      setToast({ msg: "Error contacting n8n.", type: "err" });
    } finally {
      setSendingInv(false);
    }
  }

  // Cycle 2 — Relancer la sélection (WAITING_MEET → MEET_PENDING via n8n)
  async function handleRelancerCycle2() {
    if (!selectedJobId || relancerLoading) return;
    setRelancerLoading(true);
    try {
      const res = await fetch(`${N8N_BASE}/webhook/elargir-selection`, {
        method : "POST",
        headers: { "Content-Type": "application/json" },
        body   : JSON.stringify({ job_id: selectedJobId, cycle: 2 }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.success !== false) {
        setRelancerDone(true);
        setWaitingCandidates([]);
        setToast({ msg: `✅ ${waitingCandidates.length} candidat(s) promu(s) en MEET_PENDING`, type: "ok" });
      } else {
        setToast({ msg: data.message ?? "Erreur lors du relancement.", type: "err" });
      }
    } catch {
      setToast({ msg: "Error contacting n8n.", type: "err" });
    } finally {
      setRelancerLoading(false);
    }
  }

  // Fetch slots — re-run when month or job changes
  async function fetchSlots() {
    if (!selectedJobId) return;
    setLoading(true);
    try {
      const url = `${API_BASE}/interviews/dashboard/slots?month=${monthKey}&job_id=${selectedJobId}`;
      const res = await fetch(url, { headers: authHeaders() });
      if (res.status === 401) { localStorage.removeItem("access_token"); navigate("/"); return; }
      if (res.ok) {
        const data = await res.json();
        const today = format(new Date(), "yyyy-MM-dd");
        const filtered = data.filter((slot: Slot) => slot.date >= today);
        setSlots(filtered);
      }
    } catch { /* silent */ }
    finally { setLoading(false); }
  }

  useEffect(() => { fetchSlots(); }, [monthKey, selectedJobId]);

  // Refresh every 30 s
  useEffect(() => {
    if (!selectedJobId) return;
    const id = setInterval(fetchSlots, 30_000);
    return () => clearInterval(id);
  }, [monthKey, selectedJobId]);

  // Fetch candidats rejetés auto quand le job change
  useEffect(() => {
    if (!selectedJobId) return;
    fetch(`${API_BASE}/interviews/rejected-auto/${selectedJobId}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : { candidates: [] })
      .then(data => setRejectedCandidates(data.candidates ?? []))
      .catch(() => {});
  }, [selectedJobId]);

  // Fetch candidats WAITING_MEET pour cycle 2
  useEffect(() => {
    if (!selectedJobId) return;
    setRelancerDone(false);
    fetch(`${API_BASE}/applications/waiting-candidates/${selectedJobId}`, {
      headers: { "Content-Type": "application/json", "x-n8n-secret": "mon-secret-n8n" },
    })
      .then(r => r.ok ? r.json() : { candidates: [] })
      .then(data => setWaitingCandidates(data.candidates ?? []))
      .catch(() => {});
  }, [selectedJobId]);

  // Create slot
  async function handleCreate() {
    if (!newSlot.date || !newSlot.startTime || !newSlot.endTime) {
      setToast({ msg: "Please fill in all fields.", type: "err" }); return;
    }
    if (newSlot.date < todayStr) {
      setToast({ msg: "Cannot schedule a past date.", type: "err" }); return;
    }
    if (newSlot.endTime <= newSlot.startTime) {
      setToast({ msg: "End time must be after start time.", type: "err" }); return;
    }
    setCreating(true);
    try {
      const res = await fetch(`${API_BASE}/interviews/dashboard/slots`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ date: newSlot.date, start_time: newSlot.startTime, end_time: newSlot.endTime, job_id: selectedJobId }),
      });
      if (!res.ok) {
        let errMsg = "Error while creating slot.";
        try { const e = await res.json(); errMsg = e.detail ?? e.message ?? errMsg; } catch {}
        setToast({ msg: `Erreur ${res.status}: ${errMsg}`, type: "err" });
        return;
      }
      setToast({ msg: "Slot created.", type: "ok" });
      setAddOpen(false);
      setNewSlot({ date: "", startTime: "09:00", endTime: "10:00" });
      fetchSlots();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Network error.";
      setToast({ msg: `Error: ${msg}`, type: "err" });
    } finally { setCreating(false); }
  }

  // Delete slot
  async function handleDelete(slotId: number) {
    setDeleting(slotId);
    try {
      await fetch(`${API_BASE}/interviews/dashboard/slots/${slotId}`, {
        method: "DELETE", headers: authHeaders(),
      });
      setToast({ msg: "Slot deleted.", type: "ok" });
      fetchSlots();
    } catch {
      setToast({ msg: "Error while deleting slot.", type: "err" });
    } finally { setDeleting(null); }
  }

  // Calendar helpers
  const start    = startOfMonth(currentMonth);
  const end      = endOfMonth(currentMonth);
  const days     = eachDayOfInterval({ start, end });
  const startPad = getDay(start);

  const slotsByDate: Record<string, Slot[]> = {};
  for (const slot of slots) {
    if (!slotsByDate[slot.date]) slotsByDate[slot.date] = [];
    slotsByDate[slot.date]!.push(slot);
  }

  return (
    <>
      <style>{`
        @keyframes floatLogo {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-7px); }
        }
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        .scroll-list::-webkit-scrollbar{width:4px}
        .scroll-list::-webkit-scrollbar-track{background:transparent}
        .scroll-list::-webkit-scrollbar-thumb{background:#e2e8f0;border-radius:4px}
        .scroll-list::-webkit-scrollbar-thumb:hover{background:#cbd5e1}
      `}</style>

      <Sidebar />

      {/* ── Main content — wave background (same as Dashboard) ── */}
      <div style={{
        marginLeft: 62,
        minHeight: "100vh",
        position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
      }}>
        {/* Overlay */}
        <div style={{
          position: "absolute", inset: 0,
          background: "rgba(245,243,255,0.35)",
          pointerEvents: "none",
        }} />

        <div style={{
          position: "relative", zIndex: 1,
          padding: "28px 36px 48px",
          maxWidth: 1260, margin: "0 auto",
        }}>

          {/* ── Header (matches Dashboard TopBar style) ── */}
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{ marginBottom: 28 }}
          >
            {/* Top bar: logo + title */}
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: 20,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                
                <h1 style={{ fontSize: 28, fontWeight: 700, color: "#1c2a38", margin: 0, lineHeight: 1.1 }}>
                  Interviews
                </h1>
              </div>

              {/* Boutons top-right */}
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>

                {/* Cycle 2 — Relancer sélection (visible si candidats WAITING_MEET) */}
                {waitingCandidates.length > 0 && !relancerDone && (
                  <button
                    onClick={handleRelancerCycle2}
                    disabled={relancerLoading}
                    style={{
                      display: "flex", alignItems: "center", gap: 7,
                      padding: "10px 20px", borderRadius: 11, border: "none",
                      background: relancerLoading
                        ? "rgba(148,163,184,0.3)"
                        : "linear-gradient(135deg,#f59e0b,#d97706)",
                      color: relancerLoading ? "#94a3b8" : "#fff",
                      fontSize: 13, fontWeight: 700,
                      cursor: relancerLoading ? "not-allowed" : "pointer",
                      backdropFilter: "blur(8px)",
                      boxShadow: relancerLoading ? "none" : "0 4px 14px rgba(245,158,11,0.35)",
                      transition: "all 0.2s",
                    }}
                  >
                    {relancerLoading ? (
                      <><span style={{ width: 14, height: 14, border: "2px solid #fff", borderTop: "2px solid transparent", borderRadius: "50%", display: "inline-block", animation: "spin 0.8s linear infinite" }} /> Relancement...</>
                    ) : (
                      <> Restart selection </>
                    )}
                  </button>
                )}

                {/* Send Invitations */}
                <button
                  onClick={handleSendInvitations}
                  disabled={!selectedJobId || sendingInv}
                  style={{
                    display: "flex", alignItems: "center", gap: 7,
                    padding: "10px 20px", borderRadius: 11, border: "none",
                    background: selectedJobId && !sendingInv
                      ? "linear-gradient(135deg,#16a34a,#0d9488)"
                      : "rgba(148,163,184,0.3)",
                    color: selectedJobId && !sendingInv ? "#fff" : "#94a3b8",
                    fontSize: 13, fontWeight: 700,
                    cursor: selectedJobId && !sendingInv ? "pointer" : "not-allowed",
                    backdropFilter: "blur(8px)",
                    boxShadow: selectedJobId && !sendingInv ? "0 4px 14px rgba(22,163,74,0.3)" : "none",
                    transition: "all 0.2s",
                  }}
                >
                  {sendingInv ? (
                    <><span style={{ width: 14, height: 14, border: "2px solid #fff", borderTop: "2px solid transparent", borderRadius: "50%", display: "inline-block", animation: "spin 0.8s linear infinite" }} /> Sending...</>
                  ) : (
                    <><Send size={14} /> Send Invitations</>
                  )}
                </button>

                {/* Add Slot */}
                <button
                  onClick={() => setAddOpen(true)}
                  disabled={!selectedJobId}
                  style={{
                    display: "flex", alignItems: "center", gap: 7,
                    padding: "10px 20px", borderRadius: 11, border: "none",
                    background: selectedJobId
                      ? "linear-gradient(135deg,#4a1d96,#0d9488)"
                      : "rgba(148,163,184,0.3)",
                    color: selectedJobId ? "#fff" : "#94a3b8",
                    fontSize: 13, fontWeight: 700,
                    cursor: selectedJobId ? "pointer" : "not-allowed",
                    backdropFilter: "blur(8px)",
                    boxShadow: selectedJobId ? "0 4px 14px rgba(60,12,120,0.25)" : "none",
                  }}
                >
                  <Plus size={14} /> Add Slot
                </button>

              </div>
            </div>

            {/* Date label */}
            <p style={{
              fontSize: 11, fontWeight: 700, color: "#94a3b8",
              letterSpacing: "0.14em", marginBottom: 6, textTransform: "uppercase",
            }}>
              {dateLabel}
            </p>

            

            {/* KPI pills — glass style matching Dashboard */}
            {selectedJobId && <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
              {kpis.map(({ icon: Icon, label, color }) => (
                <motion.div
                  key={label}
                  whileHover={{ scale: 1.03, y: -1 }}
                  style={{
                    display: "flex", alignItems: "center", gap: 7,
                    padding: "7px 14px", borderRadius: 999,
                    background: "rgba(255,255,255,0.85)",
                    backdropFilter: "blur(8px)",
                    border: "1px solid rgba(255,255,255,0.9)",
                    fontSize: 12, fontWeight: 500, color: "#475569",
                    boxShadow: "0 1px 4px rgba(90,40,160,0.08)", cursor: "default",
                  }}
                >
                  <Icon size={13} style={{ color }} />
                  {label}
                </motion.div>
              ))}

                          </div>}

            {/* Job selector */}
            {jobs.length > 0 && (
              <div style={{ maxWidth: 440, marginBottom: 16 }}>
                <label style={{
                  display: "block", fontSize: 10, fontWeight: 700,
                  color: "#94a3b8", letterSpacing: "0.12em",
                  textTransform: "uppercase", marginBottom: 6,
                }}>
                  Select Job Position
                </label>
                <div style={{ position: "relative" }}>
                  <select
                    value={selectedJobId ?? ""}
                    onChange={e => { setSelectedJobId(Number(e.target.value)); setSlots([]); }}
                    style={{
                      width: "100%", padding: "10px 40px 10px 14px",
                      borderRadius: 10,
                      border: "1px solid rgba(255,255,255,0.8)",
                      background: "rgba(255,255,255,0.80)",
                      backdropFilter: "blur(8px)",
                      fontSize: 13, fontWeight: 600, color: "#1e293b",
                      cursor: "pointer", appearance: "none", WebkitAppearance: "none",
                      outline: "none",
                      boxShadow: "0 2px 8px rgba(90,40,160,0.08)",
                      fontFamily: "inherit",
                      transition: "border-color 0.15s, box-shadow 0.15s",
                    }}
                    onFocus={e => {
                      e.currentTarget.style.borderColor = "#7c3aed";
                      e.currentTarget.style.boxShadow = "0 0 0 3px rgba(124,58,237,0.14)";
                    }}
                    onBlur={e => {
                      e.currentTarget.style.borderColor = "rgba(255,255,255,0.8)";
                      e.currentTarget.style.boxShadow = "0 2px 8px rgba(90,40,160,0.08)";
                    }}
                  >
                    {jobs.map(job => (
                      <option key={job.id} value={job.id}>
                        {job.title}{job.department ? ` — ${job.department}` : ""}
                      </option>
                    ))}
                  </select>
                  <div style={{
                    position: "absolute", right: 12, top: "50%",
                    transform: "translateY(-50%)", pointerEvents: "none", color: "#7c3aed",
                  }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </div>
                </div>
                {jobs.find(j => j.id === selectedJobId)?.department && (
                  <div style={{
                    display: "inline-flex", alignItems: "center", gap: 5,
                    marginTop: 6, padding: "3px 10px", borderRadius: 999,
                    background: "rgba(124,58,237,0.10)", border: "1px solid rgba(124,58,237,0.22)",
                  }}>
                    <Briefcase size={10} color="#7c3aed" />
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#7c3aed" }}>
                      {jobs.find(j => j.id === selectedJobId)?.department}
                    </span>
                  </div>
                )}
              </div>
            )}

            
          </motion.div>

          {/* ── Grid: Calendar + Slot list ── */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "380px 1fr 1fr",
            gap: 24,
            marginLeft: 55,
          }}>

            {/* ── Card: Calendar ── */}
            <Card delay={0.05}>
              <div style={{ padding: "14px 16px 12px" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                  <h2 style={{ fontSize: 15, fontWeight: 700, color: "#1c2a38", margin: 0 }}>
                    {format(currentMonth, "MMMM yyyy")}
                  </h2>
                  <div style={{ display: "flex", gap: 6 }}>
                    {[
                      { dir: -1, icon: <ChevronLeft size={13} /> },
                      { dir:  1, icon: <ChevronRight size={13} /> },
                    ].map(({ dir, icon }) => (
                      <button
                        key={dir}
                        onClick={() => setCurrentMonth(d => new Date(d.getFullYear(), d.getMonth() + dir, 1))}
                        style={{
                          width: 26, height: 26, borderRadius: 7,
                          border: "1px solid rgba(124,58,237,0.2)",
                          background: "rgba(124,58,237,0.06)",
                          cursor: "pointer", display: "flex",
                          alignItems: "center", justifyContent: "center",
                          color: "#7c3aed",
                        }}
                      >
                        {icon}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Day labels */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, marginBottom: 6 }}>
                  {DAY_LABELS.map(d => (
                    <div key={d} style={{
                      textAlign: "center", fontSize: 9, color: "#94a3b8",
                      fontFamily: "monospace", padding: "3px 0",
                    }}>{d}</div>
                  ))}
                </div>

                {/* Days grid */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
                  {Array.from({ length: startPad }).map((_, i) => <div key={`p${i}`} />)}
                  {days.map(day => {
                    const dateStr  = format(day, "yyyy-MM-dd");
                    const daySlots = slotsByDate[dateStr] ?? [];
                    const hasSlots = daySlots.length > 0;
                    const today    = isToday(day);
                    const isPast   = dateStr < todayStr;
                    const isSelected = selectedDate === dateStr;
                    return (
                      <button
                        key={dateStr}
                        disabled={isPast}
                        onClick={() => { if (!isPast) setSelectedDate(dateStr); }}
                        style={{
                          aspectRatio: "1", borderRadius: 8, border: "none",
                          background: isSelected
                            ? "rgba(124,58,237,0.15)"
                            : today
                              ? "rgba(13,148,136,0.08)"
                              : "transparent",
                          cursor: isPast ? "not-allowed" : "pointer",
                          display: "flex", flexDirection: "column",
                          alignItems: "center", justifyContent: "center",
                          fontSize: 11,
                          fontWeight: today || isSelected ? 700 : 400,
                          color: isPast ? "#cbd5e1" : isSelected ? "#7c3aed" : today ? "#0d9488" : "#334155",
                          outline: isSelected
                            ? "1px solid rgba(124,58,237,0.45)"
                            : today
                              ? "1px solid rgba(13,148,136,0.35)"
                              : "none",
                          position: "relative", transition: "background 0.1s",
                          opacity: isPast ? 0.45 : 1,
                        }}
                        onMouseEnter={e => { if (!isPast) e.currentTarget.style.background = "rgba(124,58,237,0.07)"; }}
                        onMouseLeave={e => {
                          e.currentTarget.style.background = isSelected
                            ? "rgba(124,58,237,0.15)"
                            : today ? "rgba(13,148,136,0.08)" : "transparent";
                        }}
                      >
                        {format(day, "d")}
                        {hasSlots && (
                          <span style={{ position: "absolute", bottom: 3, left: "50%", transform: "translateX(-50%)", display: "flex", gap: 2 }}>
                            {daySlots.slice(0, 3).map((s, i) => (
                              <span key={i} style={{
                                width: 4, height: 4, borderRadius: "50%",
                                background: s.status === "booked" ? "#7c3aed" : "#0d9488",
                              }} />
                            ))}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Legend */}
                <div style={{
                  display: "flex", gap: 12, marginTop: 10, paddingTop: 10,
                  borderTop: "1px solid rgba(240,235,255,0.7)",
                }}>
                  {[
                    { color: "#0d9488", label: "Available" },
                    { color: "#7c3aed", label: "Booked"    },
                  ].map(({ color, label }) => (
                    <div key={label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
                      <span style={{ fontSize: 11, color: "#94a3b8" }}>{label}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Card>

            {/* ── Card: Slot list ── */}
            <Card delay={0.1}>
              <div style={{
                padding: "16px 20px",
                borderBottom: "1px solid rgba(240,235,255,0.7)",
              }}>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>
                  Slots — {format(currentMonth, "MMMM yyyy")}
                </h2>
                <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                  {loading ? "—" : `${slots.length} slot${slots.length !== 1 ? "s" : ""} upcoming`}
                </p>
              </div>

              <div style={{ padding: 16 }}>
                {loading && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {[1, 2, 3, 4].map(i => <Skel key={i} w="100%" h={52} radius={12} />)}
                  </div>
                )}

                {!loading && slots.length === 0 && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 0", gap: 10 }}>
                    <div style={{
                      width: 48, height: 48, borderRadius: 14,
                      background: "rgba(124,58,237,0.08)",
                      border: "1px solid rgba(124,58,237,0.18)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>
                      <CalendarDays size={22} color="#7c3aed" />
                    </div>
                    <p style={{ fontSize: 13, color: "#64748b", textAlign: "center" }}>
                      No slots this month.<br />
                      <span style={{ fontSize: 11, color: "#94a3b8" }}>Click a day or use "Add Slot".</span>
                    </p>
                  </div>
                )}

                {!loading && slots.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 360, overflowY: "auto", paddingRight: 4 }} className="scroll-list">
                    {slots.map((slot, i) => (
                      <motion.div
                        key={slot.id}
                        initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 + i * 0.03 }}
                        style={{
                          display: "flex", alignItems: "center", gap: 12,
                          borderRadius: 12, padding: "11px 14px",
                          background: "#f8fafc", border: "1px solid #f1f5f9",
                          cursor: slot.status === "booked" ? "pointer" : "default",
                        }}
                        onClick={() => slot.status === "booked" && setSelectedSlot(slot)}
                        whileHover={{ backgroundColor: "#f0f4f9" }}
                      >
                        {/* Status dot */}
                        <div style={{
                          width: 9, height: 9, borderRadius: "50%", flexShrink: 0,
                          background: slot.status === "available" ? "#0d9488" : "#7c3aed",
                        }} />

                        {/* Info */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>
                            {format(parseISO(slot.date), "EEE, d MMM")}
                          </div>
                          <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                            <Clock size={10} />
                            {slot.start_time} — {slot.end_time}
                            
                          </div>
                          {slot.meet_link && (
                            <a
                              href={slot.meet_link}
                              target="_blank" rel="noopener noreferrer"
                              onClick={e => e.stopPropagation()}
                              style={{
                                display: "inline-flex", alignItems: "center", gap: 4,
                                marginTop: 4, fontSize: 10, fontWeight: 600,
                                color: "#2563eb", textDecoration: "none",
                              }}
                            >
                              <ExternalLink size={9} /> Join Zoom
                            </a>
                          )}
                        </div>

                        {/* Badge */}
                        <span style={{
                          fontSize: 9, fontWeight: 800, padding: "3px 9px", borderRadius: 999,
                          border: "1px solid", letterSpacing: "0.08em", flexShrink: 0,
                          ...(slot.status === "available"
                            ? { color: "#0d9488", background: "rgba(13,148,136,0.08)", borderColor: "rgba(13,148,136,0.25)" }
                            : { color: "#7c3aed", background: "#f5f3ff", borderColor: "#c4b5fd" }),
                        }}>
                          {slot.status === "available" ? "AVAILABLE" : "BOOKED"}
                        </span>

                        {/* Delete */}
                        <button
                          onClick={e => { e.stopPropagation(); handleDelete(slot.id); }}
                          disabled={deleting === slot.id}
                          style={{
                            border: "none", background: "transparent",
                            cursor: deleting === slot.id ? "not-allowed" : "pointer",
                            color: "#94a3b8", padding: 4, borderRadius: 6,
                            opacity: deleting === slot.id ? 0.4 : 1,
                          }}
                          onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                          onMouseLeave={e => (e.currentTarget.style.color = "#94a3b8")}
                        >
                          <Trash2 size={14} />
                        </button>
                      </motion.div>
                    ))}
                  </div>
                )}
              </div>
            </Card>

            {/* ── Card 3 : Candidates ── */}
            <Card delay={0.15}>
              <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)" }}>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Candidates</h2>
                <p style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                  {slots.filter(s => s.status === "booked").length} booked · {rejectedCandidates.length} expired
                </p>
              </div>
              <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 6, maxHeight: 360, overflowY: "auto" }} className="scroll-list">

                {/* Waiting Meet candidates — Cycle 2 */}
                {waitingCandidates.length > 0 && !relancerDone && (
                  <>
                    <p style={{ fontSize: 9, fontWeight: 800, color: "#f59e0b", letterSpacing: "0.12em", margin: "4px 0 2px" }}>
                      WAITING MEET — CYCLE 2 ({waitingCandidates.length})
                    </p>
                    {waitingCandidates.map(c => (
                      <div key={c.id} style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "9px 12px", borderRadius: 10,
                        background: "rgba(245,158,11,0.04)", border: "1px solid rgba(245,158,11,0.20)",
                      }}>
                        <div style={{
                          width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                          background: "rgba(245,158,11,0.12)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 11, fontWeight: 700, color: "#d97706",
                        }}>
                          {c.candidate_name.charAt(0).toUpperCase()}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#1c2a38", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {c.candidate_name}
                          </div>
                          <div style={{ fontSize: 10, color: "#94a3b8" }}>
                            Score: {c.score_technique > 0 ? `${c.score_technique}/100` : `${c.score_final}/100`}
                          </div>
                        </div>
                        <span style={{
                          fontSize: 9, fontWeight: 800, padding: "3px 8px", borderRadius: 999,
                          color: "#d97706", background: "rgba(245,158,11,0.10)",
                          border: "1px solid rgba(245,158,11,0.30)", letterSpacing: "0.06em",
                        }}>
                          WAITING
                        </span>
                      </div>
                    ))}
                  </>
                )}

                {/* Booked candidates */}
                {slots.filter(s => s.status === "booked").length > 0 && (
                  <>
                    <p style={{ fontSize: 9, fontWeight: 800, color: "#7c3aed", letterSpacing: "0.12em", margin: "4px 0 2px" }}>BOOKED</p>
                    {slots.filter(s => s.status === "booked").map(s => (
                      <div key={s.id} style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "9px 12px", borderRadius: 10,
                        background: "rgba(124,58,237,0.04)", border: "1px solid rgba(124,58,237,0.12)",
                      }}>
                        <div style={{
                          width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                          background: "rgba(124,58,237,0.10)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 11, fontWeight: 700, color: "#7c3aed",
                        }}>
                          {(s.candidate_name ?? "?").charAt(0).toUpperCase()}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#1c2a38", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {s.candidate_name ?? "—"}
                          </div>
                          <div style={{ fontSize: 10, color: "#94a3b8" }}>
                            {s.date} · {s.start_time}
                          </div>
                        </div>
                        
                      </div>
                    ))}
                  </>
                )}

                {/* Expired / NO SHOW candidates */}
                {rejectedCandidates.length > 0 && (
                  <>
                    <p style={{ fontSize: 9, fontWeight: 800, color: "#b45309", letterSpacing: "0.12em", margin: "8px 0 2px" }}>NO SHOW</p>
                    {rejectedCandidates.map(c => (
                      <div key={c.application_id} style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "9px 12px", borderRadius: 10,
                        background: "rgba(245,158,11,0.04)", border: "1px solid rgba(245,158,11,0.15)",
                      }}>
                        <div style={{
                          width: 30, height: 30, borderRadius: "50%", flexShrink: 0,
                          background: "rgba(245,158,11,0.12)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 11, fontWeight: 700, color: "#b45309",
                        }}>
                          {c.candidate_name.charAt(0).toUpperCase()}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: "#1c2a38", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {c.candidate_name}
                          </div>
                          <div style={{ fontSize: 10, color: "#94a3b8" }}>
                            {c.candidate_email}
                            {c.expired_at && <span style={{ color: "#f59e0b", marginLeft: 6 }}>· expired {new Date(c.expired_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>}
                          </div>
                        </div>
                        
                      </div>
                    ))}
                  </>
                )}

                {slots.filter(s => s.status === "booked").length === 0 && rejectedCandidates.length === 0 && waitingCandidates.length === 0 && (
                  <div style={{ textAlign: "center", padding: "32px 0", color: "#94a3b8", fontSize: 12 }}>
                    No candidates yet for this month.
                  </div>
                )}
              </div>
            </Card>

          </div>{/* end grid */}


        </div>
      </div>

      {/* ── Day detail panel (click on calendar day) ── */}
      {selectedDate && (() => {
        const daySlots = slotsByDate[selectedDate] ?? [];
        return (
          <div
            style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(15,23,42,0.55)" }}
            onClick={e => e.target === e.currentTarget && setSelectedDate(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
              style={{
                background: "rgba(255,255,255,0.97)",
                backdropFilter: "blur(20px)",
                borderRadius: 18, padding: 24, width: 380,
                border: "1px solid rgba(200,185,255,0.35)",
                boxShadow: "0 24px 48px rgba(90,40,160,0.18)",
                display: "flex", flexDirection: "column", maxHeight: "80vh",
              }}
            >
              {/* Header */}
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <div style={{
                  width: 38, height: 38, borderRadius: 11,
                  background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.20)",
                  display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}>
                  <CalendarDays size={17} color="#7c3aed" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>
                    {format(parseISO(selectedDate), "EEEE d MMMM yyyy")}
                  </h2>
                  <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, marginTop: 2 }}>
                    {daySlots.length === 0 ? "No slots" : `${daySlots.length} slot${daySlots.length > 1 ? "s" : ""}`}
                  </p>
                </div>
                <button
                  onClick={() => { setSelectedDate(null); setNewSlot(s => ({ ...s, date: selectedDate })); setAddOpen(true); }}
                  style={{
                    display: "flex", alignItems: "center", gap: 5,
                    padding: "7px 12px", borderRadius: 8, border: "none",
                    background: "linear-gradient(135deg,#4a1d96,#0d9488)",
                    color: "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer", flexShrink: 0,
                    boxShadow: "0 2px 8px rgba(60,12,120,0.25)",
                  }}
                >
                  <Plus size={11} /> Add Slot
                </button>
              </div>

              {/* Slot list */}
              <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 8 }} className="scroll-list">
                {daySlots.length === 0 && (
                  <div style={{ padding: "24px 0", textAlign: "center", fontSize: 13, color: "#94a3b8" }}>
                    No slots for this day.<br />
                    <span style={{ fontSize: 11 }}>Use "Add Slot" to create one.</span>
                  </div>
                )}
                {daySlots.map(slot => (
                  <div
                    key={slot.id}
                    style={{
                      display: "flex", alignItems: "center", gap: 10,
                      borderRadius: 10, border: "1px solid #f1f5f9",
                      background: "#f8fafc", padding: "10px 12px",
                      cursor: slot.status === "booked" ? "pointer" : "default",
                    }}
                    onClick={() => { if (slot.status === "booked") { setSelectedDate(null); setSelectedSlot(slot); } }}
                  >
                    <div style={{
                      width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                      background: slot.status === "available" ? "#0d9488" : "#7c3aed",
                    }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>
                        {slot.start_time} — {slot.end_time}
                      </div>
                      {slot.candidate_name && (
                        <div style={{ fontSize: 11, color: "#0d9488", fontWeight: 600, marginTop: 2 }}>
                          {slot.candidate_name}
                        </div>
                      )}
                    </div>
                    <span style={{
                      fontSize: 9, fontWeight: 800, padding: "3px 9px", borderRadius: 999,
                      border: "1px solid", letterSpacing: "0.08em", flexShrink: 0,
                      ...(slot.status === "available"
                        ? { color: "#0d9488", background: "rgba(13,148,136,0.08)", borderColor: "rgba(13,148,136,0.25)" }
                        : { color: "#7c3aed", background: "#f5f3ff", borderColor: "#c4b5fd" }),
                    }}>
                      {slot.status === "available" ? "AVAILABLE" : "BOOKED"}
                    </span>
                    <button
                      onClick={e => { e.stopPropagation(); handleDelete(slot.id); }}
                      disabled={deleting === slot.id}
                      style={{
                        border: "none", background: "transparent",
                        cursor: deleting === slot.id ? "not-allowed" : "pointer",
                        color: "#94a3b8", padding: 4, borderRadius: 6,
                        opacity: deleting === slot.id ? 0.4 : 1,
                      }}
                      onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                      onMouseLeave={e => (e.currentTarget.style.color = "#94a3b8")}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>

              <button
                onClick={() => setSelectedDate(null)}
                style={{
                  marginTop: 16, width: "100%", padding: "9px 0", borderRadius: 10,
                  border: "1px solid rgba(200,185,255,0.4)", background: "rgba(124,58,237,0.04)",
                  fontSize: 12, fontWeight: 700, color: "#7c3aed", cursor: "pointer",
                }}
              >
                Close
              </button>
            </motion.div>
          </div>
        );
      })()}

      {/* ── Modal: Add Slot ── */}
      {addOpen && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(15,23,42,0.55)" }}
          onClick={e => e.target === e.currentTarget && setAddOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            style={{
              background: "rgba(255,255,255,0.97)",
              backdropFilter: "blur(20px)",
              borderRadius: 18, padding: 28, width: 360,
              border: "1px solid rgba(200,185,255,0.35)",
              boxShadow: "0 24px 48px rgba(90,40,160,0.18)",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 11,
                background: "linear-gradient(135deg,#4a1d96,#0d9488)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <Plus size={16} color="#fff" />
              </div>
              <div>
                <h2 style={{ fontSize: 15, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Add Slot</h2>
                {selectedJobId && (
                  <p style={{ fontSize: 11, color: "#7c3aed", fontWeight: 600, margin: "2px 0 0" }}>
                    {jobs.find(j => j.id === selectedJobId)?.title}
                  </p>
                )}
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <ModalField label="Date">
                <input type="date" value={newSlot.date} min={todayStr}
                  onChange={e => setNewSlot(s => ({ ...s, date: e.target.value }))}
                  style={inputStyle} />
              </ModalField>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <ModalField label="Start">
                  <input type="time" value={newSlot.startTime}
                    onChange={e => setNewSlot(s => ({ ...s, startTime: e.target.value }))}
                    style={inputStyle} />
                </ModalField>
                <ModalField label="End">
                  <input type="time" value={newSlot.endTime}
                    onChange={e => setNewSlot(s => ({ ...s, endTime: e.target.value }))}
                    style={inputStyle} />
                </ModalField>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 22 }}>
              <button onClick={() => setAddOpen(false)}
                style={{
                  padding: "9px 18px", borderRadius: 10, border: "1px solid #e2e8f0",
                  background: "#fff", fontSize: 13, color: "#64748b", cursor: "pointer",
                }}>
                Cancel
              </button>
              <button onClick={handleCreate} disabled={creating}
                style={{
                  padding: "9px 22px", borderRadius: 10, border: "none",
                  background: creating
                    ? "rgba(75,29,150,0.5)"
                    : "linear-gradient(135deg,#4a1d96,#0d9488)",
                  color: "#fff", fontSize: 13, fontWeight: 700,
                  cursor: creating ? "not-allowed" : "pointer",
                  boxShadow: creating ? "none" : "0 4px 14px rgba(60,12,120,0.25)",
                }}>
                {creating ? "Creating..." : "Create Slot"}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* ── Modal: Booked slot detail ── */}
      {selectedSlot && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(15,23,42,0.55)" }}
          onClick={e => e.target === e.currentTarget && setSelectedSlot(null)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            style={{
              background: "rgba(255,255,255,0.97)",
              backdropFilter: "blur(20px)",
              borderRadius: 18, padding: 28, width: 380,
              border: "1px solid rgba(200,185,255,0.35)",
              boxShadow: "0 24px 48px rgba(90,40,160,0.18)",
            }}
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
              <div style={{
                width: 38, height: 38, borderRadius: 11,
                background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.18)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <CalendarDays size={17} color="#7c3aed" />
              </div>
              <div>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Booked Slot</h2>
                <p style={{ fontSize: 11, color: "#94a3b8", margin: 0 }}>
                  {format(parseISO(selectedSlot.date), "EEEE d MMMM yyyy")}
                </p>
              </div>
              <span style={{
                marginLeft: "auto", fontSize: 9, fontWeight: 800,
                padding: "3px 10px", borderRadius: 999, letterSpacing: "0.1em",
                color: "#7c3aed", background: "#f5f3ff", border: "1px solid #c4b5fd",
              }}>BOOKED</span>
            </div>

            {/* Info rows */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <InfoRow icon="🕐" label="Schedule" value={`${selectedSlot.start_time} — ${selectedSlot.end_time}`} />
              <InfoRow icon="👤" label="Candidate" value={selectedSlot.candidate_name || "—"} />
              <InfoRow icon="✉️" label="Email"     value={selectedSlot.candidate_email || "—"} />
            </div>

            {/* Meet link */}
            {selectedSlot.meet_link ? (
              <a
                href={selectedSlot.meet_link}
                target="_blank" rel="noopener noreferrer"
                style={{
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
                  marginTop: 14, width: "100%", padding: "10px 0", borderRadius: 10,
                  background: "rgba(37,99,235,0.07)", border: "1px solid rgba(37,99,235,0.2)",
                  fontSize: 13, fontWeight: 700, color: "#2563eb", textDecoration: "none",
                }}
              >
                <ExternalLink size={13} /> Join Zoom
              </a>
            ) : (
              <div style={{
                marginTop: 14, padding: "10px 14px", borderRadius: 10,
                background: "rgba(124,58,237,0.04)", border: "1px solid rgba(124,58,237,0.12)",
                fontSize: 11, color: "#94a3b8", textAlign: "center",
              }}>
                Meet link pending (generated by n8n after confirmation)
              </div>
            )}

            {/* Absent button */}
            {selectedSlot.status === "booked" && (
              <button
                onClick={async () => {
                  try {
                    await fetch(`${API_BASE}/interviews/slots/${selectedSlot.id}/absent`, {
                      method: "PATCH", headers: authHeaders(),
                    });
                    setToast({ msg: "Candidate rejected, slot released.", type: "ok" });
                    setSelectedSlot(null);
                    fetchSlots();
                  } catch {
                    setToast({ msg: "Error while updating.", type: "err" });
                  }
                }}
                style={{
                  marginTop: 10, width: "100%", padding: "9px 0", borderRadius: 10,
                  border: "1px solid #fca5a5", background: "#fef2f2",
                  fontSize: 12, fontWeight: 700, color: "#dc2626", cursor: "pointer",
                }}
              >
                ❌ Candidate absent — Rejeter
              </button>
            )}

            <button
              onClick={() => setSelectedSlot(null)}
              style={{
                marginTop: 10, width: "100%", padding: "9px 0", borderRadius: 10,
                border: "1px solid rgba(200,185,255,0.4)", background: "rgba(124,58,237,0.04)",
                fontSize: 12, fontWeight: 700, color: "#7c3aed", cursor: "pointer",
              }}
            >
              Close
            </button>
          </motion.div>
        </div>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 60,
          padding: "11px 18px", borderRadius: 10,
          background: toast.type === "ok" ? "#f0fdf4" : "#fef2f2",
          border: `1px solid ${toast.type === "ok" ? "#86efac" : "#fca5a5"}`,
          color: toast.type === "ok" ? "#16a34a" : "#dc2626",
          fontSize: 13, fontWeight: 600,
          boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
        }}>
          {toast.msg}
        </div>
      )}
    </>
  );
}

// ─── Helpers UI ───────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {
  width: "100%", fontSize: 13, color: "#1e293b",
  border: "1px solid rgba(200,185,255,0.4)", borderRadius: 8,
  padding: "9px 12px", background: "rgba(245,243,255,0.5)",
  boxSizing: "border-box", outline: "none", fontFamily: "inherit",
};

function ModalField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{
        fontSize: 10, fontWeight: 700, color: "#7c3aed",
        letterSpacing: "0.12em", textTransform: "uppercase",
      }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function InfoRow({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12,
      padding: "11px 14px", borderRadius: 10,
      background: "rgba(245,243,255,0.6)", border: "1px solid rgba(200,185,255,0.25)",
    }}>
      <span style={{ fontSize: 15, flexShrink: 0 }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{
          fontSize: 10, color: "#94a3b8", letterSpacing: "0.1em",
          textTransform: "uppercase", margin: 0,
        }}>{label}</p>
        <p style={{
          fontSize: 13, fontWeight: 600, color: "#1c2a38",
          margin: 0, marginTop: 2, overflow: "hidden",
          textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {value}
        </p>
      </div>
    </div>
  );
}