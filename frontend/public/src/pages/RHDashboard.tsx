/**
 * RHDashboard.tsx — RH Space
 * 5 sections: KPIs | Jobs Table | Alerts | Final Phase Notifications | Charts per Job
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell, User, Briefcase,
  AlertTriangle, CheckCircle2, XCircle, Clock,
  TrendingUp, ChevronRight, AlertCircle, BarChart2,
  UserCheck, Building2, Plus, ChevronDown, Search,
} from "lucide-react";
import { API_BASE, authHeaders } from "./managerShared";
import RHSidebar from "./RHSidebar";
import bgWave from "../assets/imagee.png";
import logoImg from "../assets/logoo.png";

// ─── Types ───────────────────────────────────────────────────────────────────

interface RHJob {
  id: number;
  title: string;
  department: string;
  location: string;
  status: "open" | "closed";
  date_expiration: string;
  created_at: string;
  pipeline: {
    total: number;
    en_attente: number;
    preselectionnes: number;
    test_envoye: number;
    test_complete: number;
    entretien_planifie: number;
    acceptes: number;
    rejetes: number;
  };
  manager: { id: number; email: string } | null;
}

interface Notification {
  id: number;
  message: string;
  type: "info" | "success" | "warning" | "error";
  read: boolean;
  link: string | null;
  created_at: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function daysUntil(iso: string) {
  const diff = new Date(iso).getTime() - Date.now();
  return Math.ceil(diff / 86400000);
}

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

function Card({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 300, damping: 28 }}
      style={{
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(20px)",
        borderRadius: 20,
        border: "1px solid rgba(200,185,255,0.25)",
        boxShadow: "0 4px 24px rgba(90,40,160,0.08), 0 1px 4px rgba(0,0,0,0.04)",
        overflow: "hidden",
      }}
    >
      {children}
    </motion.div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

// ─── TopBar ──────────────────────────────────────────────────────────────────

function TopBar({
  notifs, onMarkRead, onMarkAllRead,
}: {
  notifs: Notification[];
  onMarkRead: (id: number) => void;
  onMarkAllRead: () => void;
}) {
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const unreadCount = notifs.filter(n => !n.read).length;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const typeStyle = {
    info:    { bg: "rgba(59,130,246,0.08)",  dot: "#3b82f6" },
    success: { bg: "rgba(16,185,129,0.08)",  dot: "#10b981" },
    warning: { bg: "rgba(245,158,11,0.08)",  dot: "#f59e0b" },
    error:   { bg: "rgba(239,68,68,0.08)",   dot: "#ef4444" },
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 28 }}
      style={{
        marginLeft: 55, marginBottom: 28,
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(20px)",
        borderRadius: 20,
        border: "1px solid rgba(200,185,255,0.25)",
        boxShadow: "0 4px 24px rgba(90,40,160,0.08)",
        padding: "16px 24px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        overflow: "visible",
        position: "relative",
        zIndex: 100,
      }}
    >
      {/* Logo + Title */}
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 800, color: "#1c2a38", margin: 0, letterSpacing: "-0.02em" }}>
            HR Dashboard
          </h1>
          <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Recruitment Management
          </p>
        </div>
      </div>

      {/* Right icons */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {/* Bell */}
        <div ref={bellRef} style={{ position: "relative", zIndex: 1000 }}>
          <div
            onClick={() => setBellOpen(o => !o)}
            style={{
              width: 38, height: 38, borderRadius: 11,
              background: bellOpen ? "rgba(124,58,237,0.10)" : "rgba(255,255,255,0.8)",
              backdropFilter: "blur(8px)",
              border: `1px solid ${bellOpen ? "rgba(124,58,237,0.25)" : "rgba(255,255,255,0.9)"}`,
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
              position: "relative", transition: "background 0.15s, border 0.15s",
            }}
          >
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
                transition={{ type: "spring", stiffness: 400, damping: 28 }}
                style={{
                  position: "absolute", top: "calc(100% + 10px)", right: 0, width: 320,
                  background: "rgba(255,255,255,0.97)", backdropFilter: "blur(20px)",
                  borderRadius: 16, border: "1px solid rgba(200,185,255,0.35)",
                  boxShadow: "0 8px 32px rgba(90,40,160,0.15)", zIndex: 1001, overflow: "hidden",
                }}
              >
                <div style={{
                  padding: "14px 16px 12px", borderBottom: "1px solid rgba(240,235,255,0.8)",
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Bell size={14} color="#7c3aed" />
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>Notifications</span>
                    {unreadCount > 0 && (
                      <span style={{
                        fontSize: 10, fontWeight: 800,
                        background: "rgba(124,58,237,0.1)", color: "#7c3aed",
                        borderRadius: 999, padding: "1px 7px",
                      }}>{unreadCount} new</span>
                    )}
                  </div>
                  {unreadCount > 0 && (
                    <button onClick={onMarkAllRead} style={{
                      fontSize: 11, fontWeight: 600, cursor: "pointer",
                      background: "none", border: "none", color: "#0d9488",
                    }}>Mark all read</button>
                  )}
                </div>
                <div style={{ maxHeight: 320, overflowY: "auto", padding: "8px 10px" }}>
                  {notifs.length === 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "28px 0", gap: 8 }}>
                      <CheckCircle2 size={22} color="#10b981" />
                      <p style={{ fontSize: 12, color: "#64748b", margin: 0 }}>You're all caught up!</p>
                    </div>
                  ) : notifs.slice(0, 10).map((notif, i) => {
                    const s = typeStyle[notif.type] ?? typeStyle.info;
                    return (
                      <motion.div
                        key={notif.id}
                        initial={{ opacity: 0, x: 6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.03 }}
                        onClick={() => { if (!notif.read) onMarkRead(notif.id); }}
                        style={{
                          display: "flex", alignItems: "flex-start", gap: 10,
                          padding: "9px 10px", borderRadius: 10, marginBottom: 4,
                          background: notif.read ? "#f8fafc" : s.bg,
                          border: `1px solid ${notif.read ? "#f1f5f9" : "transparent"}`,
                          cursor: "pointer", opacity: notif.read ? 0.6 : 1,
                        }}
                      >
                        <div style={{ paddingTop: 5, flexShrink: 0 }}>
                          <div style={{ width: 7, height: 7, borderRadius: "50%", background: notif.read ? "#cbd5e1" : s.dot }} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ fontSize: 12, fontWeight: notif.read ? 500 : 700, color: "#1c2a38", margin: 0, lineHeight: 1.4 }}>
                            {notif.message}
                          </p>
                          <p style={{ fontSize: 10, color: "#94a3b8", margin: "2px 0 0" }}>
                            {relTime(notif.created_at)}
                          </p>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Account */}
        <Link href="/rh/account" style={{ textDecoration: "none" }}>
          <motion.div
            whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.95 }}
            style={{
              width: 38, height: 38, borderRadius: 11,
              background: "rgba(255,255,255,0.8)", backdropFilter: "blur(8px)",
              border: "1px solid rgba(255,255,255,0.9)",
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
            }}
          >
            <User size={16} color="#64748b" />
          </motion.div>
        </Link>
      </div>
    </motion.div>
  );
}

// ─── Section 1 — KPI Cards ────────────────────────────────────────────────────

function KPISection({ jobs, loading }: { jobs: RHJob[]; loading: boolean }) {
  const totalJobs   = jobs.length;
  const openJobs    = jobs.filter(j => j.status === "open").length;
  const closedJobs  = jobs.filter(j => j.status === "closed").length;
  const totalManagers = new Set(jobs.filter(j => j.manager).map(j => j.manager!.id)).size;

  const kpis = [
    { label: "Total Jobs",    value: totalJobs,    icon: Briefcase,  color: "#7c3aed", bg: "rgba(124,58,237,0.08)"  },
    { label: "Open Jobs",     value: openJobs,     icon: CheckCircle2, color: "#10b981", bg: "rgba(16,185,129,0.08)" },
    { label: "Closed Jobs",   value: closedJobs,   icon: XCircle,    color: "#ef4444", bg: "rgba(239,68,68,0.08)"   },
    { label: "Managers",      value: totalManagers, icon: UserCheck,  color: "#f59e0b", bg: "rgba(245,158,11,0.08)"  },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginLeft: 55, marginBottom: 20 }}>
      {kpis.map(({ label, value, icon: Icon, color, bg }, i) => (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05, type: "spring", stiffness: 300, damping: 28 }}
          whileHover={{ y: -3, boxShadow: "0 8px 28px rgba(90,40,160,0.14)" }}
          style={{
            background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
            borderRadius: 18, border: "1px solid rgba(200,185,255,0.25)",
            boxShadow: "0 4px 16px rgba(90,40,160,0.07)",
            padding: "20px 24px",
            display: "flex", alignItems: "center", gap: 16,
          }}
        >
          <div style={{ width: 46, height: 46, borderRadius: 14, background: bg, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Icon size={22} color={color} />
          </div>
          <div>
            {loading ? <Skel w={40} h={22} /> : (
              <div style={{ fontSize: 26, fontWeight: 800, color: "#1c2a38", lineHeight: 1 }}>{value}</div>
            )}
            <div style={{ fontSize: 12, color: "#64748b", fontWeight: 600, marginTop: 3 }}>{label}</div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ─── Section 2 — Jobs Table ───────────────────────────────────────────────────

const PER_PAGE = 2;

function JobDropdown({
  jobs,
  selectedId,
  onSelect,
}: {
  jobs: RHJob[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
}) {
  const [open, setOpen]       = useState(false);
  const [query, setQuery]     = useState("");
  const ref                   = useRef<HTMLDivElement>(null);
  const selected              = jobs.find(j => j.id === selectedId);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const filtered = jobs.filter(j =>
    j.title.toLowerCase().includes(query.toLowerCase()) ||
    j.department.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div ref={ref} style={{ position: "relative", minWidth: 240 }}>
      {/* Trigger */}
      <div
        onClick={() => { setOpen(o => !o); setQuery(""); }}
        style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "7px 12px", borderRadius: 10, cursor: "pointer",
          background: open ? "rgba(124,58,237,0.07)" : "rgba(255,255,255,0.8)",
          border: `1px solid ${open ? "rgba(124,58,237,0.30)" : "rgba(200,185,255,0.35)"}`,
          transition: "all 0.15s", userSelect: "none",
        }}
      >
        <Briefcase size={14} color="#7c3aed" />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: "#1c2a38", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 180 }}>
          {selected ? (selected.title.length > 26 ? selected.title.slice(0, 26) + "…" : selected.title) : "All jobs"}
        </span>
        <ChevronDown size={14} color="#94a3b8" style={{ transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0deg)", flexShrink: 0 }} />
      </div>

      {/* Dropdown panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 420, damping: 28 }}
            style={{
              position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 200,
              width: 300, background: "rgba(255,255,255,0.98)", backdropFilter: "blur(20px)",
              borderRadius: 14, border: "1px solid rgba(200,185,255,0.35)",
              boxShadow: "0 8px 32px rgba(90,40,160,0.14)", overflow: "hidden",
            }}
          >
            {/* Search */}
            <div style={{ padding: "10px 12px", borderBottom: "1px solid rgba(200,185,255,0.2)", display: "flex", alignItems: "center", gap: 8 }}>
              <Search size={13} color="#94a3b8" />
              <input
                autoFocus
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search jobs…"
                style={{
                  flex: 1, border: "none", outline: "none", fontSize: 13,
                  background: "transparent", color: "#1c2a38",
                }}
              />
            </div>

            {/* Items */}
            <div style={{ maxHeight: 260, overflowY: "auto", padding: "6px 6px" }}>
              {/* All jobs option */}
              <div
                onClick={() => { onSelect(null); setOpen(false); }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  padding: "8px 10px", borderRadius: 8, cursor: "pointer",
                  background: selectedId === null ? "rgba(124,58,237,0.08)" : "transparent",
                  marginBottom: 2,
                }}
                onMouseEnter={e => { if (selectedId !== null) (e.currentTarget as HTMLDivElement).style.background = "rgba(124,58,237,0.04)"; }}
                onMouseLeave={e => { if (selectedId !== null) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
              >
                <div style={{ width: 28, height: 28, borderRadius: 8, background: "rgba(124,58,237,0.08)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  <Briefcase size={13} color="#7c3aed" />
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: selectedId === null ? "#7c3aed" : "#1c2a38" }}>All jobs</span>
                {selectedId === null && <CheckCircle2 size={13} color="#7c3aed" style={{ marginLeft: "auto" }} />}
              </div>

              {filtered.length === 0 ? (
                <div style={{ padding: "16px 10px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>No results</div>
              ) : filtered.map(j => (
                <div
                  key={j.id}
                  onClick={() => { onSelect(j.id); setOpen(false); }}
                  style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "8px 10px", borderRadius: 8, cursor: "pointer",
                    background: selectedId === j.id ? "rgba(124,58,237,0.08)" : "transparent",
                    marginBottom: 2,
                  }}
                  onMouseEnter={e => { if (selectedId !== j.id) (e.currentTarget as HTMLDivElement).style.background = "rgba(124,58,237,0.04)"; }}
                  onMouseLeave={e => { if (selectedId !== j.id) (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
                >
                  <div style={{ width: 28, height: 28, borderRadius: 8, background: j.status === "open" ? "rgba(16,185,129,0.1)" : "rgba(100,116,139,0.1)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                    <Briefcase size={13} color={j.status === "open" ? "#10b981" : "#64748b"} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: selectedId === j.id ? "#7c3aed" : "#1c2a38", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{j.title}</div>
                    <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 1 }}>{j.department}{j.location ? ` · ${j.location}` : ""}</div>
                  </div>
                  {selectedId === j.id && <CheckCircle2 size={13} color="#7c3aed" style={{ flexShrink: 0 }} />}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function JobsTable({ jobs, loading }: { jobs: RHJob[]; loading: boolean }) {
  const [filter, setFilter] = useState<"all" | "open" | "closed">("open");
  const [page,   setPage]   = useState(1);

  const filtered   = filter === "all" ? jobs : jobs.filter(j => j.status === filter);
  const totalPages = Math.ceil(filtered.length / PER_PAGE);
  const paginated  = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  useEffect(() => { setPage(1); }, [filter]);

  const STAGES = [
    { key: "total",               label: "Applied",     color: "#64748b" },
    { key: "preselectionnes",     label: "Shortlisted", color: "#7c3aed" },
    { key: "test_envoye",         label: "Test",        color: "#3b82f6" },
    { key: "entretien_planifie",  label: "Interview",   color: "#f59e0b" },
    { key: "acceptes",            label: "Accepted",    color: "#10b981" },
    { key: "rejetes",             label: "Rejected",    color: "#ef4444" },
  ];

  return (
    <Card delay={0.1}>
      <div style={{ padding: "20px 24px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Recruitment Cycle</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: "3px 0 0" }}>Pipeline view by job</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {(["all", "open", "closed"] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                padding: "5px 14px", borderRadius: 999, fontSize: 12, fontWeight: 600,
                cursor: "pointer", border: "none", transition: "all 0.15s",
                background: filter === f ? "#7c3aed" : "rgba(124,58,237,0.08)",
                color: filter === f ? "#fff" : "#7c3aed",
              }}
            >
              {f === "all" ? "All" : f === "open" ? "Open" : "Closed"}
            </button>
          ))}
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid rgba(200,185,255,0.2)" }}>
              <th style={{ padding: "10px 24px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Job</th>
              <th style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Manager</th>
              {STAGES.map(s => (
                <th key={s.key} style={{ padding: "10px 12px", textAlign: "center", fontSize: 11, fontWeight: 700, color: s.color, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                  {s.label}
                </th>
              ))}
              <th style={{ padding: "10px 16px", textAlign: "center", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              [1,2,3,4].map(i => (
                <tr key={i}>
                  <td style={{ padding: "14px 24px" }}><Skel w={180} h={14} /></td>
                  <td style={{ padding: "14px 16px" }}><Skel w={100} h={12} /></td>
                  {STAGES.map(s => <td key={s.key} style={{ padding: "14px 12px", textAlign: "center" }}><Skel w={24} h={12} /></td>)}
                  <td style={{ padding: "14px 16px", textAlign: "center" }}><Skel w={60} h={20} radius={999} /></td>
                </tr>
              ))
            ) : paginated.length === 0 ? (
              <tr>
                <td colSpan={9} style={{ padding: "40px", textAlign: "center", fontSize: 13, color: "#94a3b8" }}>
                  No jobs found
                </td>
              </tr>
            ) : paginated.map((job, i) => (
              <motion.tr
                key={job.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04 }}
                style={{ borderBottom: "1px solid rgba(240,235,255,0.6)", cursor: "pointer" }}
                onMouseEnter={e => (e.currentTarget.style.background = "rgba(124,58,237,0.03)")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                onClick={() => window.location.href = `/rh/pipeline/${job.id}`}
              >
                <td style={{ padding: "14px 24px" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>{job.title}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                    {job.department} {job.location ? `· ${job.location}` : ""}
                  </div>
                </td>
                <td style={{ padding: "14px 16px" }}>
                  {job.manager ? (
                    <div style={{ fontSize: 12, color: "#475569", fontWeight: 500 }}>
                      {job.manager.email.split("@")[0]}
                    </div>
                  ) : (
                    <span style={{ fontSize: 11, color: "#ef4444", fontWeight: 600 }}>Unassigned</span>
                  )}
                </td>
                {STAGES.map(s => (
                  <td key={s.key} style={{ padding: "14px 12px", textAlign: "center" }}>
                    <span style={{
                      fontSize: 14, fontWeight: 700,
                      color: (job.pipeline as any)[s.key] > 0 ? s.color : "#cbd5e1",
                    }}>
                      {(job.pipeline as any)[s.key] ?? 0}
                    </span>
                  </td>
                ))}
                <td style={{ padding: "14px 16px", textAlign: "center" }}>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 999,
                    background: job.status === "open" ? "rgba(16,185,129,0.1)" : "rgba(100,116,139,0.1)",
                    color: job.status === "open" ? "#10b981" : "#64748b",
                  }}>
                    {job.status === "open" ? "Open" : "Closed"}
                  </span>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!loading && totalPages > 1 && (
        <div style={{ padding: "12px 24px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid rgba(200,185,255,0.15)" }}>
          <span style={{ fontSize: 12, color: "#94a3b8" }}>
            Showing {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, filtered.length)} of {filtered.length} jobs
          </span>
          <div style={{ display: "flex", gap: 4 }}>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setPage(p)}
                style={{
                  width: 28, height: 28, borderRadius: 8, fontSize: 12, fontWeight: 700,
                  cursor: "pointer", border: "none", transition: "all 0.15s",
                  background: page === p ? "#7c3aed" : "rgba(124,58,237,0.08)",
                  color: page === p ? "#fff" : "#7c3aed",
                }}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// ─── Section 3 — Alertes ─────────────────────────────────────────────────────

function AlertsSection({ jobs, loading }: { jobs: RHJob[]; loading: boolean }) {
  const alerts: { type: "error" | "warning" | "info"; message: string; jobId?: number }[] = [];

  if (!loading) {
    jobs.filter(j => j.status === "open").forEach(job => {
      if (!job.manager) {
        alerts.push({ type: "error", message: `"${job.title}" — no manager assigned`, jobId: job.id });
      }
      const days = daysUntil(job.date_expiration);
      if (days > 0 && days <= 15) {
        alerts.push({ type: "warning", message: `"${job.title}" — expires in ${days} day${days > 1 ? "s" : ""}`, jobId: job.id });
      }
      if (job.pipeline.acceptes === 0 && job.pipeline.entretien_planifie === 0 && job.pipeline.total > 5) {
        alerts.push({ type: "info", message: `"${job.title}" — 0 accepted out of ${job.pipeline.total} applicants`, jobId: job.id });
      }
    });
  }

  const alertStyle = {
    error:   { bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.2)",   color: "#dc2626", icon: XCircle      },
    warning: { bg: "rgba(245,158,11,0.08)",  border: "rgba(245,158,11,0.2)",  color: "#d97706", icon: AlertTriangle },
    info:    { bg: "rgba(59,130,246,0.08)",  border: "rgba(59,130,246,0.2)",  color: "#2563eb", icon: AlertCircle   },
  };

  return (
    <Card delay={0.15}>
      <div style={{ padding: "20px 24px 16px" }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Pipeline Alerts</h2>
        <p style={{ fontSize: 12, color: "#64748b", margin: "3px 0 0" }}>Actions required</p>
      </div>
      <div style={{ padding: "0 24px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
        {loading ? [1,2].map(i => <Skel key={i} w="100%" h={44} radius={12} />) :
          alerts.length === 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 0", color: "#10b981" }}>
              <CheckCircle2 size={18} />
              <span style={{ fontSize: 13, fontWeight: 600 }}>No alerts — everything is in order</span>
            </div>
          ) : alerts.slice(0, 4).map((alert, i) => {
            const s = alertStyle[alert.type];
            const Icon = s.icon;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "11px 14px", borderRadius: 12,
                  background: s.bg, border: `1px solid ${s.border}`,
                }}
              >
                <Icon size={16} color={s.color} style={{ flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: "#1c2a38", flex: 1 }}>{alert.message}</span>
                {alert.jobId && (
                  <Link href={`/rh/pipeline/${alert.jobId}`}>
                    <span style={{ fontSize: 11, color: s.color, fontWeight: 700, cursor: "pointer" }}>
                      View →
                    </span>
                  </Link>
                )}
              </motion.div>
            );
          })
        }
      </div>
    </Card>
  );
}

// ─── Section 4 — Notifications Phase Finale ──────────────────────────────────

function FinalPhaseNotifs({
  notifs, loading, onMarkRead,
}: {
  notifs: Notification[];
  loading: boolean;
  onMarkRead: (id: number) => void;
}) {
  // Include final phase notifications and in-person interview updates
  const finalNotifs = notifs.filter(n =>
    // English messages
    n.message.includes("accepted") ||
    n.message.includes("activated their account") ||
    n.message.includes("In-person interview scheduled") ||
    n.message.includes("interview scheduled") ||
    n.message.includes("hired") ||
    n.message.includes("approved") ||
    n.message.includes("needs further review") ||
    n.message.includes("promoted") ||
    n.message.includes("filled") ||
    n.message.includes("rejected") ||
    // French messages (legacy — already in DB)
    n.message.includes("accepté(e)") ||
    n.message.includes("validé(e)") ||
    n.message.includes("activé son compte") ||
    n.message.includes("Entretien présentiel") ||
    n.message.includes("présentiel") ||
    n.message.includes("Entretien réservé") ||
    n.message.includes("embauché(e)") ||
    n.message.includes("pourvu")
  ).slice(0, 4);

  const getStyle = (n: Notification) => {
    if (n.type === "success") return { dot: "#10b981", bg: "rgba(16,185,129,0.06)" };
    if (n.type === "warning") return { dot: "#f59e0b", bg: "rgba(245,158,11,0.06)" };
    if (n.type === "error")   return { dot: "#ef4444", bg: "rgba(239,68,68,0.06)"  };
    return { dot: "#3b82f6", bg: "rgba(59,130,246,0.06)" };
  };

  return (
    <Card delay={0.2}>
      <div style={{ padding: "20px 24px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Final Phase</h2>
          <p style={{ fontSize: 12, color: "#64748b", margin: "3px 0 0" }}>In-person interviews & candidate activity</p>
        </div>
        {finalNotifs.filter(n => !n.read).length > 0 && (
          <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 999, background: "rgba(13,148,136,0.1)", color: "#0d9488", border: "1px solid rgba(13,148,136,0.2)" }}>
            {finalNotifs.filter(n => !n.read).length} new
          </span>
        )}
      </div>
      <div style={{ padding: "0 16px 20px", display: "flex", flexDirection: "column", gap: 6 }}>
        {loading ? [1,2,3].map(i => (
          <div key={i} style={{ display: "flex", gap: 10, padding: "8px" }}>
            <Skel w={8} h={8} radius={999} />
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
              <Skel w="80%" h={12} />
              <Skel w="30%" h={10} />
            </div>
          </div>
        )) : finalNotifs.length === 0 ? (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "16px 8px", color: "#94a3b8" }}>
            <Clock size={16} />
            <span style={{ fontSize: 13 }}>No recent activity</span>
          </div>
        ) : finalNotifs.map((n, i) => {
          const isPresentiel = n.message.includes("In-person") || n.message.includes("interview scheduled") || n.message.includes("présentiel") || n.message.includes("Entretien présentiel") || n.message.includes("Entretien réservé");
          const s = isPresentiel
            ? { dot: "#0d9488", bg: "rgba(13,148,136,0.07)" }
            : getStyle(n);
          return (
            <motion.div
              key={n.id}
              initial={{ opacity: 0, x: 6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.04 }}
              onClick={() => { if (!n.read) onMarkRead(n.id); if (n.link) window.location.href = n.link; }}
              style={{
                display: "flex", alignItems: "flex-start", gap: 10,
                padding: "9px 10px", borderRadius: 10,
                background: n.read ? "#f8fafc" : s.bg,
                cursor: n.link ? "pointer" : "default",
                opacity: n.read ? 0.65 : 1,
                border: isPresentiel && !n.read ? "1px solid rgba(13,148,136,0.15)" : "1px solid transparent",
              }}
            >
              <div style={{ paddingTop: 6, flexShrink: 0 }}>
                <div style={{ width: 7, height: 7, borderRadius: "50%", background: n.read ? "#cbd5e1" : s.dot }} />
              </div>
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: 12, fontWeight: n.read ? 500 : 700, color: "#1c2a38", margin: 0, lineHeight: 1.45 }}>
                  {n.message}
                </p>
                <p style={{ fontSize: 10, color: "#94a3b8", margin: "2px 0 0" }}>{relTime(n.created_at)}</p>
              </div>
              {isPresentiel && n.link && !n.read && (
                <span style={{ fontSize: 10, color: "#0d9488", fontWeight: 700, alignSelf: "center", flexShrink: 0 }}>
                  View →
                </span>
              )}
            </motion.div>
          );
        })}
      </div>
    </Card>
  );
}

// ChartsSection removed: "Statistics by Job" has been deleted per request.

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export default function RHDashboard() {
  const [jobs,       setJobs]       = useState<RHJob[]>([]);
  const [notifs,     setNotifs]     = useState<Notification[]>([]);
  const [loadJobs,   setLoadJobs]   = useState(true);
  const [loadNotifs, setLoadNotifs] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/jobs/rh/dashboard`, { headers: authHeaders() })
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
    await fetch(`${API_BASE}/notifications/${id}/read`, { method: "PATCH", headers: authHeaders() });
    setNotifs(prev => prev.map(n => n.id === id ? { ...n, read: true } : n));
  }

  async function markAllRead() {
    await fetch(`${API_BASE}/notifications/read-all`, { method: "PATCH", headers: authHeaders() });
    setNotifs(prev => prev.map(n => ({ ...n, read: true })));
  }

  return (
    <>
      <style>{`
        @keyframes floatLogo { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
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

          {/* Section 1 — KPIs */}
          <KPISection jobs={jobs} loading={loadJobs} />

          {/* Section 2 — Jobs Table */}
          <div style={{ marginLeft: 55, marginBottom: 20 }}>
            <JobsTable jobs={jobs} loading={loadJobs} />
          </div>

          {/* Section 3 + 4 — Alerts + Notifications */}
          <div style={{ marginLeft: 55, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }}>
            <AlertsSection jobs={jobs} loading={loadJobs} />
            <FinalPhaseNotifs notifs={notifs} loading={loadNotifs} onMarkRead={markRead} />
          </div>

          {/* Section 5 removed: Statistics by Job */}

        </div>
      </div>
    </>
  );
}