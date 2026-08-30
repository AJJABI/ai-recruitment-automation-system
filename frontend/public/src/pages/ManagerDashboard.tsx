// ═══════════════════════════════════════════════════════════
  // FILE: Dashboard.tsx
  // ═══════════════════════════════════════════════════════════
  /**
 * Dashboard.tsx — Manager Space
 * 4-card layout: Today's Meetings | Pending Decisions | Open Jobs | Notifications
 * Background: wave image | Sidebar: innovative floating-pill animation
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2, AlertCircle, Calendar,
  Briefcase, Users, Clock, CalendarCheck, AlertTriangle,
  ArrowRight, LayoutDashboard, MessageSquare,
  Bell, ChevronRight, LogOut, User,
} from "lucide-react";
import { API_BASE, getToken, authHeaders } from "./managerShared";
import bgWave from "../assets/imagee.png";
import logoImg from "../assets/logoo.png";


// ─── Types ──────────────────────────────────────────────────────────────────
interface Slot {
  id: number;
  date: string;
  start_time: string;
  end_time: string;
  status: "available" | "booked" | "cancelled";
  candidate_name?: string | null;
  candidate_email?: string | null;
  job_title?: string | null;
}

interface PendingCandidate {
  application_id: number;
  full_name: string;
  status_v2: string;
  jobTitle: string;
  jobId: number;
}

interface Job {
  id: number;
  title: string;
  department: string;
  status: string;
  closed_at: string | null;
  candidats_preselectionnes?: PendingCandidate[];
  pipeline?: { total: number };
}

interface Notification {
  id: number;
  message: string;
  type: "info" | "success" | "warning" | "error";
  read: boolean;
  link: string | null;
  created_at: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────
const DECIDED = [ "MANAGER_REJECTED", "ACCEPTED"];

const GRADIENTS = [
  ["#7c3aed", "#6d28d9"],
  ["#0d9488", "#0f766e"],
  ["#059669", "#047857"],
  ["#d97706", "#b45309"],
  ["#db2777", "#be185d"],
];

// ─── Helpers ─────────────────────────────────────────────────────────────────
function todayStr() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
function monthKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function fmtTime(t: string) { return t?.slice(0, 5) ?? ""; }
function initials(name: string) {
  return name ? name.split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase() : "?";
}

/** Calcule le statut visuel d'un meeting selon l'heure actuelle */
function meetStatus(slot: Slot): "live" | "done" | "upcoming" | "cancelled" {
  if (slot.status === "cancelled") return "cancelled";
  const now = new Date();
  const [sh, sm] = slot.start_time.split(":").map(Number);
  const [eh, em] = slot.end_time.split(":").map(Number);
  const base = new Date(slot.date);
  const start = new Date(base); start.setHours(sh, sm, 0, 0);
  const end   = new Date(base); end.setHours(eh, em, 0, 0);
  if (now > end)   return "done";
  if (now >= start) return "live";
  return "upcoming";
}

const MEET_STATUS_STYLE = {
  live:      { bg: "rgba(16,185,129,0.10)", color: "#059669", border: "rgba(16,185,129,0.25)",  dot: "#10b981", label: "LIVE"      },
  done:      { bg: "rgba(100,116,139,0.08)", color: "#64748b", border: "rgba(100,116,139,0.2)", dot: "#94a3b8", label: "DONE"      },
  upcoming:  { bg: "rgba(59,130,246,0.08)",  color: "#3b82f6", border: "rgba(59,130,246,0.2)",  dot: "#3b82f6", label: "UPCOMING"  },
  cancelled: { bg: "rgba(239,68,68,0.08)",   color: "#dc2626", border: "rgba(239,68,68,0.2)",   dot: "#ef4444", label: "CANCELLED" },
};

// ─── Skeleton ────────────────────────────────────────────────────────────────
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

// ─── Sidebar ─────────────────────────────────────────────────────────────────
const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

/** Floating label that pops to the right of the hovered icon */
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
    <nav
      style={{
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
        overflow: "visible",   /* labels extend outside */
        userSelect: "none",
        width: 58,
      }}
    >
      {/* ── Nav items ── */}
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
                width: 40,
                height: 40,
                margin: "0 auto",
                borderRadius: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
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
              {/* Active indicator */}
              {active && (
                <motion.div
                  layoutId="activeBar"
                  style={{
                    position: "absolute",
                    left: -7,
                    top: "50%",
                    y: "-50%",
                    width: 3,
                    height: 18,
                    borderRadius: 3,
                    background: "#fff",
                  }}
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                />
              )}

              <Icon
                size={17}
                color={active ? "#ffffff" : "rgba(255,255,255,0.60)"}
              />

              {/* Only THIS icon's label appears */}
              <NavLabel label={label} visible={hovered} />
            </motion.div>
          </Link>
        );
      })}

      {/* ── Divider ── */}
      <div style={{
        width: 32,
        height: 1,
        background: "rgba(255,255,255,0.14)",
        margin: "6px 0",
        flexShrink: 0,
      }} />

      {/* ── Logout ── */}
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
              onClick={() => {
                localStorage.removeItem("access_token");
                window.location.href = "/";
              }}
              style={{
                width: 40,
                height: 40,
                margin: "0 auto",
                borderRadius: 13,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
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

// ─── Card wrapper ─────────────────────────────────────────────────────────────
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

function CardHeader({ title, sub, icon, iconBg, iconColor, action }: {
  title: string; sub?: string;
  icon?: React.ReactNode; iconBg?: string; iconColor?: string;
  action?: React.ReactNode;
}) {
  return (
    <div style={{
      padding: "16px 20px",
      borderBottom: "1px solid rgba(240,235,255,0.7)",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
    }}>
      <div>
        <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>{title}</h2>
        {sub && <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>{sub}</p>}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {action}
        {icon && (
          <div style={{
            width: 32,
            height: 32,
            borderRadius: 10,
            background: iconBg ?? "#f1f5f9",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}>
            <span style={{ color: iconColor }}>{icon}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Header top bar ───────────────────────────────────────────────────────────
function TopBar({ dateLabel, kpis, notifs, onMarkRead, onMarkAllRead, onNavigate }: {
  dateLabel: string;
  kpis: { icon: React.ElementType; label: string; color: string }[];
  notifs: Notification[];
  onMarkRead: (id: number) => void;
  onMarkAllRead: () => void;
  onNavigate: (link: string) => void;
}) {
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const unreadCount = notifs.filter(n => !n.read).length;

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false);
      }
    }
    if (bellOpen) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [bellOpen]);

  const typeStyle: Record<string, { bg: string; dot: string }> = {
    info:    { bg: "#f0f9ff", dot: "#3b82f6" },
    success: { bg: "#f0fdf4", dot: "#10b981" },
    warning: { bg: "#fffbeb", dot: "#f59e0b" },
    error:   { bg: "#fef2f2", dot: "#ef4444" },
  };

  function relTime(created_at: string) {
    const diff = Date.now() - new Date(created_at).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "Just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      style={{ marginBottom: 24 }}
    >
      {/* Top right icons bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 20,
      }}>
        {/* Company name + animated logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          
          <span style={{ fontSize: 30, fontWeight: 800, color: "#1c2a38", letterSpacing: "-0.02em" }}>
            AI Recruitment System
          </span>
        </div>

        {/* Right icons */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>

          {/* ── Bell with dropdown ── */}
          <div ref={bellRef} style={{ position: "relative" }}>
            <div
              onClick={() => setBellOpen(o => !o)}
              style={{
                width: 38,
                height: 38,
                borderRadius: 11,
                background: bellOpen ? "rgba(124,58,237,0.10)" : "rgba(255,255,255,0.8)",
                backdropFilter: "blur(8px)",
                border: `1px solid ${bellOpen ? "rgba(124,58,237,0.25)" : "rgba(255,255,255,0.9)"}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
                position: "relative",
                transition: "background 0.15s, border 0.15s",
              }}
            >
              <Bell size={16} color={bellOpen ? "#7c3aed" : "#64748b"} />
              {unreadCount > 0 && (
                <div style={{
                  position: "absolute",
                  top: 5,
                  right: 5,
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "#ef4444",
                  border: "1.5px solid #fff",
                  boxShadow: "0 0 0 1px rgba(239,68,68,0.3)",
                }} />
              )}
            </div>

            {/* Dropdown panel */}
            <AnimatePresence>
              {bellOpen && (
                <motion.div
                  initial={{ opacity: 0, y: -8, scale: 0.96 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.97 }}
                  transition={{ type: "spring", stiffness: 400, damping: 28 }}
                  style={{
                    position: "absolute",
                    top: "calc(100% + 10px)",
                    right: 0,
                    width: 320,
                    background: "rgba(255,255,255,0.97)",
                    backdropFilter: "blur(20px)",
                    borderRadius: 16,
                    border: "1px solid rgba(200,185,255,0.35)",
                    boxShadow: "0 8px 32px rgba(90,40,160,0.15), 0 2px 8px rgba(0,0,0,0.06)",
                    zIndex: 999,
                    overflow: "hidden",
                  }}
                >
                  {/* Header */}
                  <div style={{
                    padding: "14px 16px 12px",
                    borderBottom: "1px solid rgba(240,235,255,0.8)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Bell size={14} color="#7c3aed" />
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>Notifications</span>
                      {unreadCount > 0 && (
                        <span style={{
                          fontSize: 10, fontWeight: 800,
                          background: "rgba(124,58,237,0.1)", color: "#7c3aed",
                          borderRadius: 999, padding: "1px 7px",
                        }}>
                          {unreadCount} new
                        </span>
                      )}
                    </div>
                    {unreadCount > 0 && (
                      <button
                        onClick={() => onMarkAllRead()}
                        style={{
                          fontSize: 11, fontWeight: 600, cursor: "pointer",
                          background: "none", border: "none", color: "#0d9488",
                        }}
                      >
                        Mark all read
                      </button>
                    )}
                  </div>

                  {/* List */}
                  <div style={{ maxHeight: 300, overflowY: "auto", padding: "8px 10px" }}>
                    {notifs.length === 0 ? (
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "28px 0", gap: 8 }}>
                        <CheckCircle2 size={22} color="#10b981" />
                        <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>You're all caught up!</p>
                      </div>
                    ) : (
                      notifs.slice(0, 8).map((notif, i) => {
                        const s = typeStyle[notif.type] ?? typeStyle.info;
                        return (
                          <motion.div
                            key={notif.id}
                            initial={{ opacity: 0, x: 6 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: i * 0.03 }}
                            onClick={() => {
                              if (!notif.read) onMarkRead(notif.id);
                              if (notif.link) { onNavigate(notif.link); setBellOpen(false); }
                            }}
                            style={{
                              display: "flex", alignItems: "flex-start", gap: 10,
                              padding: "9px 10px", borderRadius: 10, marginBottom: 4,
                              background: notif.read ? "#f8fafc" : s.bg,
                              border: `1px solid ${notif.read ? "#f1f5f9" : "transparent"}`,
                              cursor: "pointer",
                              opacity: notif.read ? 0.6 : 1,
                              transition: "opacity 0.2s",
                            }}
                          >
                            <div style={{ paddingTop: 5, flexShrink: 0 }}>
                              <div style={{
                                width: 7, height: 7, borderRadius: "50%",
                                background: notif.read ? "#cbd5e1" : s.dot,
                              }} />
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <p style={{ fontSize: 12, fontWeight: notif.read ? 500 : 700, color: "#1c2a38", margin: 0, lineHeight: 1.4 }}>
                                {notif.message}
                              </p>
                              <p style={{ fontSize: 10, color: "#94a3b8", margin: "2px 0 0" }}>
                                {relTime(notif.created_at)}
                              </p>
                            </div>
                            {!notif.read && (
                              <button
                                onClick={e => { e.stopPropagation(); onMarkRead(notif.id); }}
                                style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", fontSize: 11, flexShrink: 0, paddingTop: 2 }}
                                title="Mark as read"
                              >✓</button>
                            )}
                          </motion.div>
                        );
                      })
                    )}
                    {notifs.length > 8 && (
                      <p style={{ fontSize: 11, color: "#94a3b8", textAlign: "center", marginTop: 4 }}>
                        +{notifs.length - 8} older notifications
                      </p>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Account icon → /account */}
          <Link href="/account" style={{ textDecoration: "none" }}>
            <motion.div
              whileHover={{ scale: 1.08, background: "rgba(124,58,237,0.10)", borderColor: "rgba(124,58,237,0.25)" }}
              whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 400, damping: 22 }}
              style={{
                width: 38,
                height: 38,
                borderRadius: 11,
                background: "rgba(255,255,255,0.8)",
                backdropFilter: "blur(8px)",
                border: "1px solid rgba(255,255,255,0.9)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
              }}
              title="My Account"
            >
              <User size={16} color="#64748b" />
            </motion.div>
          </Link>

        </div>
      </div>

      {/* Date */}
      <p style={{
        fontSize: 10,
        fontWeight: 700,
        color: "#94a3b8",
        letterSpacing: "0.18em",
        marginBottom: 12,
        textTransform: "uppercase",
      }}>
        {dateLabel}
      </p>

      {/* KPI pills */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {kpis.map(({ icon: Icon, label, color }) => (
          <motion.div
            key={label}
            whileHover={{ scale: 1.03, y: -1 }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              padding: "7px 14px",
              borderRadius: 999,
              background: "rgba(255,255,255,0.85)",
              backdropFilter: "blur(8px)",
              border: "1px solid rgba(255,255,255,0.9)",
              fontSize: 12,
              fontWeight: 500,
              color: "#475569",
              boxShadow: "0 1px 4px rgba(90,40,160,0.08)",
              cursor: "default",
            }}
          >
            <Icon size={13} style={{ color }} />
            {label}
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

// ─── Dashboard ───────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [, navigate] = useLocation();

  const [slots, setSlots] = useState<Slot[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loadSlots, setLoadSlots] = useState(true);
  const [loadJobs, setLoadJobs] = useState(true);
  const [notifs, setNotifs] = useState<Notification[]>([]);
  const [loadNotifs, setLoadNotifs] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/interviews/dashboard/slots?month=${monthKey()}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setSlots)
      .catch(() => setSlots([]))
      .finally(() => setLoadSlots(false));

    fetch(`${API_BASE}/jobs/manager/dashboard`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setJobs)
      .catch(() => setJobs([]))
      .finally(() => setLoadJobs(false));

    fetch(`${API_BASE}/notifications`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setNotifs)
      .catch(() => setNotifs([]))
      .finally(() => setLoadNotifs(false));
  }, []);

  async function markRead(id: number) {
    await fetch(`${API_BASE}/notifications/${id}/read`, {
      method: "PATCH", headers: authHeaders(),
    });
    setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  }

  async function markAllRead() {
    await fetch(`${API_BASE}/notifications/read-all`, {
      method: "PATCH", headers: authHeaders(),
    });
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
  }

  async function deleteNotif(id: number) {
    await fetch(`${API_BASE}/notifications/${id}`, {
      method: "DELETE", headers: authHeaders(),
    });
    setNotifs(prev => prev.filter(n => n.id !== id));
  }

  // Computed
  const today = todayStr();
  const todaySlots = slots.filter(s => s.date === today && s.status === "booked");
  const activeJobs = jobs.filter(j => !j.closed_at && j.status !== "closed");

  const pendingByJob = jobs
    .map(job => ({
      jobId: job.id,
      jobTitle: job.title,
      candidates: (job.candidats_preselectionnes ?? [])
        .filter(c => c.status_v2 === "PRESELECTED")
        .map(c => ({
          ...c,
          display_name: (!c.full_name || c.full_name.includes("@"))
            ? (c.full_name?.split("@")[0] ?? "Candidate")
            : c.full_name,
          jobTitle: job.title,
          jobId: job.id,
        })),
    }))
    .filter(g => g.candidates.length > 0);

  const totalPending = jobs.reduce((a, j) =>
    a + (j.candidats_preselectionnes ?? []).filter(c => c.status_v2 === "PRESELECTED").length, 0
  );

  const now = new Date();
  const dateLabel = now.toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  const kpis = [
    { icon: Briefcase, label: `${loadJobs ? "—" : activeJobs.length} open job${activeJobs.length !== 1 ? "s" : ""}`, color: "#0d9488" },
    { icon: CalendarCheck, label: `${loadSlots ? "—" : todaySlots.length} meeting${todaySlots.length !== 1 ? "s" : ""} today`, color: "#10b981" },
    { icon: AlertTriangle, label: `${loadJobs ? "—" : totalPending} pending decision${totalPending !== 1 ? "s" : ""}`, color: "#f59e0b" },
  ];

  return (
    <>
      <style>{`
        @keyframes floatLogo {
          0%, 100% { transform: translateY(0px); }
          50%       { transform: translateY(-7px); }
        }
        @keyframes shimmer {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
      <Sidebar />

      {/* Main content with wave background */}
      <div style={{
        marginLeft: 62,
        minHeight: "100vh",
        position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundAttachment: "fixed",
      }}>
        {/* Subtle overlay to soften the bg */}
        <div style={{
          position: "absolute",
          inset: 0,
          background: "rgba(245,243,255,0.35)",
          pointerEvents: "none",
        }} />

        <div style={{
          position: "relative",
          zIndex: 1,
          padding: "28px 36px 48px",
          maxWidth: 1260,
          margin: "0 auto",
        }}>
          <TopBar dateLabel={dateLabel} kpis={kpis} notifs={notifs} onMarkRead={markRead} onMarkAllRead={markAllRead} onNavigate={(link) => navigate(link)} />

          {/* ── Top row: Meetings + Notifications */}
          <div style={{ display: "grid", marginLeft: 55, gridTemplateColumns: "1.4fr 1fr", gap: 35, marginBottom: 18 }}>

            {/* ── Card: Today's Meetings */}
            <Card delay={0.05}>
              <div style={{ padding: "20px 24px 14px" }}>
                <h2 style={{ fontSize: 17, fontWeight: 700, color: "#1c2a38", margin: 0 }}>
                  Today's Meetings
                </h2>
                <p style={{ fontSize: 13, color: "#64748b", marginTop: 3 }}>
                  {loadSlots ? "—" : `${todaySlots.length} interview${todaySlots.length !== 1 ? "s" : ""} scheduled`}
                </p>
              </div>

              <div style={{ padding: "0 24px 22px" }}>
                {loadSlots ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    {[1, 2, 3].map(i => (
                      <div key={i} style={{ display: "flex", gap: 12 }}>
                        <Skel w={40} h={14} />
                        <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
                          <Skel w="60%" h={13} />
                          <Skel w="40%" h={10} />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : todaySlots.length === 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "36px 0", gap: 10 }}>
                    <div style={{ width: 48, height: 48, borderRadius: 14, background: "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Calendar size={22} color="#94a3b8" />
                    </div>
                    <p style={{ fontSize: 13, color: "#94a3b8" }}>No interviews scheduled</p>
                  </div>
                ) : (
                  <div style={{ position: "relative" }}>
                    <div style={{ position: "absolute", left: 46, top: 8, bottom: 8, width: 1, background: "#e2e8f0" }} />
                    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                      {todaySlots.map((slot, i) => {
                          const ms = meetStatus(slot);
                          const mss = MEET_STATUS_STYLE[ms];
                          return (
                        <motion.div
                          key={slot.id}
                          initial={{ opacity: 0, x: -8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.1 + i * 0.06 }}
                          style={{ display: "flex", alignItems: "flex-start", opacity: ms === "done" ? 0.7 : 1 }}
                        >
                          <div style={{ width: 40, flexShrink: 0, paddingTop: 2 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: "#64748b", fontVariantNumeric: "tabular-nums" }}>
                              {fmtTime(slot.start_time)}
                            </span>
                          </div>
                          <div style={{ width: 14, flexShrink: 0, display: "flex", justifyContent: "center", paddingTop: 6 }}>
                            <div style={{
                              width: 10, height: 10, borderRadius: "50%", zIndex: 1,
                              background: mss.dot,
                              border: `2px solid ${mss.dot}`,
                              boxShadow: ms === "live" ? `0 0 0 3px rgba(16,185,129,0.2)` : "none",
                            }} />
                          </div>
                          <div style={{ flex: 1, paddingLeft: 12 }}>
                            <p style={{ fontSize: 13, fontWeight: 700, color: ms === "cancelled" ? "#94a3b8" : "#1c2a38", margin: 0, textDecoration: ms === "cancelled" ? "line-through" : "none" }}>
                              {slot.candidate_name ?? "Candidate"}
                            </p>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4, flexWrap: "wrap" }}>
                              <span style={{ fontSize: 11, color: "#94a3b8", fontVariantNumeric: "tabular-nums" }}>
                                <Clock size={9} style={{ display: "inline", marginRight: 3 }} />
                                {fmtTime(slot.start_time)} — {fmtTime(slot.end_time)}
                              </span>
                            </div>
                            {slot.job_title && (
                              <div style={{
                                display: "inline-flex", alignItems: "center", gap: 5,
                                marginTop: 5, padding: "3px 9px", borderRadius: 999,
                                background: "rgba(124,58,237,0.08)",
                                border: "1px solid rgba(124,58,237,0.18)",
                              }}>
                                <Briefcase size={10} color="#7c3aed" />
                                <span style={{ fontSize: 11, fontWeight: 700, color: "#7c3aed" }}>
                                  {slot.job_title}
                                </span>
                              </div>
                            )}
                          </div>
                          {/* Status badge */}
                          <div style={{
                            display: "inline-flex", alignItems: "center", gap: 4,
                            padding: "3px 9px", borderRadius: 999, flexShrink: 0,
                            background: mss.bg,
                            border: `1px solid ${mss.border}`,
                          }}>
                            {ms === "live" && (
                              <div style={{ width: 5, height: 5, borderRadius: "50%", background: mss.dot, animation: "floatLogo 1s ease-in-out infinite" }} />
                            )}
                            <span style={{ fontSize: 9, fontWeight: 800, color: mss.color, letterSpacing: "0.05em" }}>
                              {mss.label}
                            </span>
                          </div>
                        </motion.div>
                          );
                        })}
                    </div>
                    <button
                      onClick={() => navigate("/interviews/calendar")}
                      style={{
                        width: "100%", display: "flex", alignItems: "center", justifyContent: "center",
                        gap: 6, marginTop: 20, padding: "9px 0", borderRadius: 10,
                        fontSize: 12, fontWeight: 600, cursor: "pointer",
                        border: "1px solid rgba(13,148,136,0.2)", background: "rgba(13,148,136,0.05)",
                        color: "#0d9488",
                      }}
                    >
                      View schedule <ArrowRight size={12} />
                    </button>
                  </div>
                )}
              </div>
            </Card>

            {/* ── Card: Notifications */}
            <Card delay={0.2}>
              <CardHeader
                title="Notifications"
                sub={loadNotifs ? "—" : `${notifs.filter(n => !n.read).length} unread`}
                icon={<Bell size={15} color="#0d9488" />}
                iconBg="rgba(13,148,136,0.08)"
                action={
                  notifs.some(n => !n.read) ? (
                    <button
                      onClick={markAllRead}
                      style={{
                        fontSize: 11, fontWeight: 600, cursor: "pointer",
                        background: "none", border: "none", color: "#0d9488",
                        padding: "2px 6px",
                      }}
                    >
                      Mark all read
                    </button>
                  ) : undefined
                }
              />
              <div style={{ padding: 16 }}>
                {loadNotifs ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {[1, 2, 3].map(i => <Skel key={i} w="100%" h={52} radius={10} />)}
                  </div>
                ) : notifs.length === 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 0", gap: 10 }}>
                    <div style={{ width: 48, height: 48, borderRadius: 14, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <CheckCircle2 size={22} color="#10b981" />
                    </div>
                    <p style={{ fontSize: 13, color: "#64748b", textAlign: "center" }}>You're all caught up!</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 280, overflowY: "auto", paddingRight: 4 }} className="scroll-list">
                    {notifs.slice(0, 5).map((notif, i) => {
                      const typeStyle: Record<string, { bg: string; dot: string }> = {
                        info: { bg: "#f0f9ff", dot: "#3b82f6" },
                        success: { bg: "#f0fdf4", dot: "#10b981" },
                        warning: { bg: "#fffbeb", dot: "#f59e0b" },
                        error: { bg: "#fef2f2", dot: "#ef4444" },
                      };
                      const style = typeStyle[notif.type] ?? typeStyle.info;
                      const relTime = (() => {
                        const diff = Date.now() - new Date(notif.created_at).getTime();
                        const m = Math.floor(diff / 60000);
                        if (m < 1) return "Just now";
                        if (m < 60) return `${m}m ago`;
                        const h = Math.floor(m / 60);
                        if (h < 24) return `${h}h ago`;
                        return `${Math.floor(h / 24)}d ago`;
                      })();
                      return (
                        <motion.div
                          key={notif.id}
                          initial={{ opacity: 0, x: 8 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.22 + i * 0.04 }}
                          onClick={() => {
                            if (!notif.read) markRead(notif.id);
                            if (notif.link) navigate(notif.link);
                          }}
                          style={{
                            display: "flex", alignItems: "flex-start", gap: 10,
                            padding: "10px 12px", borderRadius: 12,
                            background: notif.read ? "#f8fafc" : style.bg,
                            border: `1px solid ${notif.read ? "#f1f5f9" : "transparent"}`,
                            cursor: notif.link ? "pointer" : "default",
                            opacity: notif.read ? 0.65 : 1,
                            transition: "opacity 0.2s",
                          }}
                          whileHover={{ opacity: 1 }}
                        >
                          <div style={{ paddingTop: 5, flexShrink: 0 }}>
                            <div style={{
                              width: 7, height: 7, borderRadius: "50%",
                              background: notif.read ? "#cbd5e1" : style.dot,
                              transition: "background 0.2s",
                            }} />
                          </div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <p style={{ fontSize: 12, fontWeight: notif.read ? 500 : 700, color: "#1c2a38", margin: 0, lineHeight: 1.4 }}>
                              {notif.message}
                            </p>
                            <p style={{ fontSize: 10, color: "#94a3b8", margin: "3px 0 0" }}>{relTime}</p>
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 3, flexShrink: 0 }}>
                            {!notif.read && (
                              <button
                                onClick={e => { e.stopPropagation(); markRead(notif.id); }}
                                style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", padding: "2px 4px", fontSize: 10, lineHeight: 1 }}
                                title="Mark as read"
                              >✓</button>
                            )}
                            <button
                              onClick={e => { e.stopPropagation(); deleteNotif(notif.id); }}
                              style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", padding: "2px 4px", fontSize: 10, lineHeight: 1 }}
                              onMouseEnter={e => (e.currentTarget.style.color = "#dc2626")}
                              onMouseLeave={e => (e.currentTarget.style.color = "#94a3b8")}
                              title="Delete notification"
                            >🗑</button>
                          </div>
                        </motion.div>
                      );
                    })}
                    {notifs.length > 5 && (
                      <p style={{ fontSize: 11, color: "#94a3b8", textAlign: "center", margin: "4px 0 0" }}>
                        +{notifs.length - 5} older notifications
                      </p>
                    )}
                  </div>
                )}
              </div>
            </Card>

          </div>{/* end top grid */}

          {/* ── Bottom row: Pending Decisions + Open Jobs */}
            <div style={{ display: "grid", marginLeft: 55, gridTemplateColumns: "1fr 1fr", gap: 18 }}>
            {/* ── Card: Pending Decisions */}
            <Card delay={0.1}>
              <CardHeader
                title="Pending Decisions"
                sub={loadJobs ? "—" : `${totalPending} candidate${totalPending !== 1 ? "s" : ""} to review`}
                icon={<AlertCircle size={15} color="#f59e0b" />}
                iconBg="#fffbeb"
              />
              <div style={{ padding: 16 }}>
                {loadJobs ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {[1, 2, 3, 4].map(i => <Skel key={i} w="100%" h={48} radius={10} />)}
                  </div>
                ) : pendingByJob.length === 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 0", gap: 10 }}>
                    <div style={{ width: 48, height: 48, borderRadius: 14, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <CheckCircle2 size={22} color="#10b981" />
                    </div>
                    <p style={{ fontSize: 13, color: "#64748b" }}>All decisions have been made ✓</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12, maxHeight: 320, overflowY: "auto", paddingRight: 4 }} className="scroll-list">
                    {pendingByJob.map((group, gi) => (
                      <div key={group.jobId}>
                        <div style={{
                          display: "flex", alignItems: "center", gap: 8, marginBottom: 6,
                          padding: "4px 8px", borderRadius: 8,
                          background: "rgba(13,148,136,0.06)", border: "1px solid rgba(13,148,136,0.12)",
                        }}>
                          <Briefcase size={11} color="#0d9488" />
                          <span style={{ fontSize: 11, fontWeight: 700, color: "#0d9488", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {group.jobTitle}
                          </span>
                          <span style={{
                            marginLeft: "auto", fontSize: 10, fontWeight: 700,
                            background: "rgba(13,148,136,0.15)", color: "#0d9488",
                            borderRadius: 999, padding: "1px 7px", flexShrink: 0,
                          }}>
                            {group.candidates.length}
                          </span>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 5, paddingLeft: 8 }}>
                          {group.candidates.map((c, i) => (
                            <motion.div
                              key={c.application_id}
                              initial={{ opacity: 0, y: 8 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.12 + gi * 0.06 + i * 0.04 }}
                              onClick={() => navigate(`/candidates/${c.jobId}/${c.application_id}`)}
                              style={{
                                display: "flex", alignItems: "center", gap: 10,
                                padding: "9px 12px", borderRadius: 10,
                                background: "#f8fafc", border: "1px solid #f1f5f9",
                                cursor: "pointer",
                              }}
                              whileHover={{ backgroundColor: "#f0f4f9" }}
                            >
                              <div style={{
                                width: 32, height: 32, borderRadius: 9, flexShrink: 0,
                                background: `linear-gradient(135deg,${GRADIENTS[(gi + i) % GRADIENTS.length][0]},${GRADIENTS[(gi + i) % GRADIENTS.length][1]})`,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: 11, fontWeight: 800, color: "#fff",
                              }}>
                                {initials(c.display_name)}
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <p style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {c.display_name}
                                </p>
                                <p style={{ fontSize: 10, color: "#94a3b8", margin: 0 }}>
                                  {c.status_v2?.replace(/_/g, " ")}
                                </p>
                              </div>
                              <ChevronRight size={14} color="#cbd5e1" style={{ flexShrink: 0 }} />
                            </motion.div>
                          ))}
                        </div>
                      </div>
                    ))}
                    {totalPending > 5 && (
                      <button
                        onClick={() => navigate("/candidates")}
                        style={{
                          width: "100%", padding: "8px 0", borderRadius: 10,
                          fontSize: 11, fontWeight: 600, cursor: "pointer",
                          background: "rgba(13,148,136,0.05)", border: "1px solid rgba(13,148,136,0.15)",
                          color: "#0d9488", display: "flex", alignItems: "center", justifyContent: "center", gap: 4,
                        }}
                      >
                        View all {totalPending} candidates <ChevronRight size={11} />
                      </button>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {/* ── Card: Open Jobs */}
            <Card delay={0.15}>
              <CardHeader
                title="Open Jobs"
                sub={loadJobs ? "—" : `${activeJobs.length} active position${activeJobs.length !== 1 ? "s" : ""}`}
                action={
                  <button
                    onClick={() => navigate("/mission-registry")}
                    style={{
                      display: "flex", alignItems: "center", gap: 5,
                      fontSize: 12, fontWeight: 600, cursor: "pointer",
                      background: "none", border: "none", color: "#64748b",
                    }}
                  >
                    View all <ArrowRight size={12} />
                  </button>
                }
              />
              <div style={{ padding: 20 }}>
                {loadJobs ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {[1, 2, 3].map(i => <Skel key={i} w="100%" h={52} radius={12} />)}
                  </div>
                ) : activeJobs.length === 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 0", gap: 10 }}>
                    <div style={{ width: 48, height: 48, borderRadius: 14, background: "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Briefcase size={22} color="#94a3b8" />
                    </div>
                    <p style={{ fontSize: 13, color: "#94a3b8" }}>No active jobs</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 280, overflowY: "auto", paddingRight: 4 }} className="scroll-list">
                    {activeJobs.map((job, i) => (
                      <motion.div
                        key={job.id}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.18 + i * 0.04 }}
                        onClick={() => navigate("/mission-registry")}
                        style={{
                          display: "flex", alignItems: "center", gap: 12,
                          padding: "12px 14px", borderRadius: 12,
                          background: "#f8fafc", border: "1px solid #f1f5f9",
                          cursor: "pointer",
                        }}
                        whileHover={{ backgroundColor: "#f0f4f9" }}
                      >
                        <div style={{
                          width: 36, height: 36, borderRadius: 10, flexShrink: 0,
                          background: "rgba(13,148,136,0.08)", border: "1px solid rgba(13,148,136,0.18)",
                          display: "flex", alignItems: "center", justifyContent: "center",
                        }}>
                          <Briefcase size={16} color="#0d9488" />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {job.title}
                          </p>
                          <p style={{ fontSize: 11, color: "#94a3b8", margin: 0 }}>{job.department}</p>
                        </div>
                        <span style={{
                          fontSize: 9, fontWeight: 800, padding: "2px 8px", borderRadius: 999,
                          background: "rgba(13,148,136,0.08)", color: "#0d9488",
                          border: "1px solid rgba(13,148,136,0.2)", flexShrink: 0,
                        }}>
                          OPEN
                        </span>
                      </motion.div>
                    ))}
                  </div>
                )}
              </div>
            </Card>

          </div>{/* end bottom grid */}

        </div>
      </div>
    </>
  );
}