/**
 * RHJobs.tsx — Jobs list for HR space
 * Grid of cards with general info, status, expiration date
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell, User, Briefcase,
  MapPin, Building2, Calendar, ChevronRight,
  CheckCircle2, Clock, XCircle, Search, Filter,
} from "lucide-react";
import bgWave   from "../assets/imagee.png";
import logoImg  from "../assets/logoo.png";
import RHSidebar from "./RHSidebar";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
function getToken() { return localStorage.getItem("access_token") ?? ""; }
function authHeaders() { return { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" }; }

// ─── Types ────────────────────────────────────────────────────────────────────

interface RHJob {
  id            : number;
  title         : string;
  department    : string | null;
  location      : string | null;
  level         : string | null;
  status        : "open" | "closed";
  date_expiration: string;
  created_at    : string;
  pipeline      : {
    total             : number;
    en_attente        : number;
    preselectionnes   : number;
    test_envoye       : number;
    test_complete     : number;
    entretien_planifie: number;
    acceptes          : number;
    rejetes           : number;
  };
  manager: { id: number; email: string } | null;
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

function daysUntil(iso: string | null | undefined): number {
  if (!iso) return NaN;
  // Normalize: if date-only string (YYYY-MM-DD), append time to avoid UTC midnight parse issues
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso;
  const d = new Date(normalized);
  if (isNaN(d.getTime())) return NaN;
  return Math.ceil((d.getTime() - Date.now()) / 86400000);
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
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

// ─── TopBar ───────────────────────────────────────────────────────────────────

function TopBar({ notifs, onMarkRead, onMarkAllRead }: {
  notifs: Notification[];
  onMarkRead: (id: number) => void;
  onMarkAllRead: () => void;
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
        <img src={logoImg} alt="logo" style={{ height: 36, animation: "floatLogo 3s ease-in-out infinite" }} />
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: "#1c2a38", margin: 0, letterSpacing: "-0.02em" }}>
            Open Positions
          </h1>
          <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            HR Space · All Positions
          </p>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
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
              <div style={{
                position: "absolute", top: 5, right: 5, width: 8, height: 8,
                borderRadius: "50%", background: "#ef4444", border: "1.5px solid #fff",
              }} />
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
                      Mark all as read
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

// ─── Job Card ─────────────────────────────────────────────────────────────────

function JobCard({ job, index }: { job: RHJob; index: number }) {
  const days        = daysUntil(job.date_expiration);
  const validDate   = job.date_expiration && !isNaN(new Date(job.date_expiration).getTime());
  const isExpiring  = !isNaN(days) && days > 0 && days <= 15;
  const isExpired   = !isNaN(days) && days <= 0;
  const isOpen      = job.status === "open";

  const expiryColor = isExpired ? "#ef4444" : isExpiring ? "#f59e0b" : "#10b981";
  const expiryText  = isNaN(days)
    ? "No expiry date"
    : isExpired
      ? "Expired"
      : isExpiring
        ? `Expires in ${days}d`
        : `${days}d remaining`;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, type: "spring", stiffness: 280, damping: 26 }}
      whileHover={{ y: -4, boxShadow: "0 12px 36px rgba(90,40,160,0.15)" }}
      style={{
        background: "rgba(255,255,255,0.92)", backdropFilter: "blur(20px)",
        borderRadius: 20, border: "1px solid rgba(200,185,255,0.25)",
        boxShadow: "0 4px 20px rgba(90,40,160,0.08)",
        overflow: "hidden", cursor: "pointer",
        transition: "box-shadow 0.2s",
      }}
    >
      {/* Top stripe */}
      <div style={{
        height: 4,
        background: isOpen
          ? "linear-gradient(90deg, #7c3aed, #a78bfa)"
          : "linear-gradient(90deg, #94a3b8, #cbd5e1)",
      }} />

      <div style={{ padding: "20px 22px" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
          <div style={{ flex: 1, minWidth: 0, paddingRight: 10 }}>
            <h3 style={{
              fontSize: 15, fontWeight: 800, color: "#1c2a38",
              margin: "0 0 5px", lineHeight: 1.3,
              overflow: "hidden", textOverflow: "ellipsis",
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
            }}>
              {job.title}
            </h3>
          </div>
          <span style={{
            flexShrink: 0, fontSize: 11, fontWeight: 700, padding: "4px 10px",
            borderRadius: 999, whiteSpace: "nowrap",
            background: isOpen ? "rgba(16,185,129,0.1)" : "rgba(100,116,139,0.1)",
            color: isOpen ? "#10b981" : "#64748b",
          }}>
            {isOpen ? "Open" : "Closed"}
          </span>
        </div>

        {/* Infos */}
        <div style={{ display: "flex", flexDirection: "column", gap: 7, marginBottom: 16 }}>
          {job.department && (
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Building2 size={13} color="#94a3b8" />
              <span style={{ fontSize: 12, color: "#64748b", fontWeight: 500 }}>{job.department}</span>
            </div>
          )}
          {job.location && (
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <MapPin size={13} color="#94a3b8" />
              <span style={{ fontSize: 12, color: "#64748b", fontWeight: 500 }}>{job.location}</span>
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <User size={13} color="#94a3b8" />
            <span style={{ fontSize: 12, fontWeight: 600, color: job.manager ? "#475569" : "#ef4444" }}>
              {job.manager ? job.manager.email.split("@")[0] : "No manager"}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <Calendar size={13} color={expiryColor} />
            <span style={{ fontSize: 12, fontWeight: 600, color: expiryColor }}>
              {expiryText}{validDate ? ` · ${new Date(job.date_expiration).toLocaleDateString("fr-FR")}` : ""}
            </span>
          </div>
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: "rgba(200,185,255,0.2)", marginBottom: 14 }} />

        {/* CTA */}
        <Link href={`/rh/ranking/${job.id}`} style={{ textDecoration: "none" }}>
          <motion.div
            whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            style={{
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              background: "linear-gradient(135deg, #7c3aed, #6d28d9)",
              color: "#fff", borderRadius: 12, padding: "10px 0",
              fontSize: 13, fontWeight: 700, cursor: "pointer",
              boxShadow: "0 4px 14px rgba(124,58,237,0.25)",
            }}
          >
            View Ranking
            <ChevronRight size={15} />
          </motion.div>
        </Link>
      </div>
    </motion.div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function RHJobs() {
  const [jobs,       setJobs]       = useState<RHJob[]>([]);
  const [notifs,     setNotifs]     = useState<Notification[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [search,     setSearch]     = useState("");
  const [filter,     setFilter]     = useState<"all" | "open" | "closed">("all");

  useEffect(() => {
    fetch(`${API_BASE}/jobs/rh/dashboard`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setJobs).catch(() => setJobs([]))
      .finally(() => setLoading(false));

    fetch(`${API_BASE}/notifications`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then(setNotifs).catch(() => setNotifs([]));
  }, []);

  async function markRead(id: number) {
    await fetch(`${API_BASE}/notifications/${id}/read`, { method: "PATCH", headers: authHeaders() });
    setNotifs(p => p.map(n => n.id === id ? { ...n, read: true } : n));
  }

  async function markAllRead() {
    await fetch(`${API_BASE}/notifications/read-all`, { method: "PATCH", headers: authHeaders() });
    setNotifs(p => p.map(n => ({ ...n, read: true })));
  }

  const filtered = jobs
    .filter(j => filter === "all" ? true : j.status === filter)
    .filter(j => j.title.toLowerCase().includes(search.toLowerCase()) ||
                 (j.department ?? "").toLowerCase().includes(search.toLowerCase()));

  return (
    <>
      <style>{`
        @keyframes floatLogo { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
        @keyframes shimmer   { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
      `}</style>

      <RHSidebar />

      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 48px", maxWidth: 1320, margin: "0 auto" }}>

          {/* TopBar */}
          <TopBar notifs={notifs} onMarkRead={markRead} onMarkAllRead={markAllRead} />

          {/* Search + Filters */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            style={{
              marginLeft: 55, marginBottom: 24,
              display: "flex", alignItems: "center", gap: 12,
            }}
          >
            {/* Search */}
            <div style={{
              flex: 1, display: "flex", alignItems: "center", gap: 10,
              background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
              borderRadius: 14, border: "1px solid rgba(200,185,255,0.25)",
              boxShadow: "0 2px 12px rgba(90,40,160,0.06)",
              padding: "10px 16px",
            }}>
              <Search size={16} color="#94a3b8" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search for a job..."
                style={{
                  flex: 1, border: "none", outline: "none", fontSize: 14,
                  color: "#1c2a38", background: "transparent", fontFamily: "inherit",
                }}
              />
            </div>

            {/* Filters */}
            <div style={{
              display: "flex", gap: 6,
              background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
              borderRadius: 14, border: "1px solid rgba(200,185,255,0.25)",
              boxShadow: "0 2px 12px rgba(90,40,160,0.06)",
              padding: "6px",
            }}>
              {(["all", "open", "closed"] as const).map(f => (
                <button key={f} onClick={() => setFilter(f)} style={{
                  padding: "6px 16px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  cursor: "pointer", border: "none", transition: "all 0.15s",
                  background: filter === f ? "#7c3aed" : "transparent",
                  color: filter === f ? "#fff" : "#64748b",
                }}>
                  {f === "all" ? "All" : f === "open" ? "Open" : "Closed"}
                </button>
              ))}
            </div>

            {/* Count */}
            <div style={{
              background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
              borderRadius: 14, border: "1px solid rgba(200,185,255,0.25)",
              boxShadow: "0 2px 12px rgba(90,40,160,0.06)",
              padding: "10px 18px", fontSize: 13, fontWeight: 700, color: "#7c3aed", whiteSpace: "nowrap",
            }}>
              {loading ? "..." : `${filtered.length} job${filtered.length > 1 ? "s" : ""}`}
            </div>
          </motion.div>

          {/* Grid */}
          <div style={{
            marginLeft: 55,
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: 20,
          }}>
            {loading ? (
              [1, 2, 3, 4, 5, 6].map(i => (
                <div key={i} style={{
                  background: "rgba(255,255,255,0.88)", borderRadius: 20,
                  border: "1px solid rgba(200,185,255,0.25)", padding: 22,
                  display: "flex", flexDirection: "column", gap: 12,
                }}>
                  <Skel w="70%" h={18} />
                  <Skel w="50%" h={13} />
                  <Skel w="60%" h={13} />
                  <Skel w="40%" h={13} />
                  <Skel w="100%" h={38} radius={12} />
                </div>
              ))
            ) : filtered.length === 0 ? (
              <div style={{
                gridColumn: "1 / -1", textAlign: "center", padding: "60px 0",
                display: "flex", flexDirection: "column", alignItems: "center", gap: 12,
              }}>
                <Briefcase size={40} color="#cbd5e1" />
                <p style={{ fontSize: 15, color: "#94a3b8", fontWeight: 600, margin: 0 }}>
                  No jobs found
                </p>
              </div>
            ) : filtered.map((job, i) => (
              <JobCard key={job.id} job={job} index={i} />
            ))}
          </div>

        </div>
      </div>
    </>
  );
}