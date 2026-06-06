/**
 * MissionRegistry.tsx — Thème identique au Dashboard
 *   • Sidebar floating-pill violette (fixe, top:140, left:16)
 *     gradient #4a1d96 → #2c0f70, icônes blanches, labels popup framer-motion
 *   • Fond wave image (backgroundImage) + overlay rgba(245,243,255,0.35)
 *   • Cards glassmorphism : rgba(255,255,255,0.88) + backdrop-filter blur(20px)
 *   • Accent teal #0d9488, texte #1c2a38
 *   • AUCUN changement côté backend
 */

import { useState, useEffect, useCallback } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Briefcase, Users, MessageSquare,
  RefreshCw, AlertCircle, CheckCircle2, ChevronRight,
  LogOut,
} from "lucide-react";
import logoImg  from "../assets/logoo.png";
import bgWave   from "../assets/imagee.png";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SkillsJson {
  coding?: string[];
  platform?: string[];
  mixed?: string[];
}

interface Candidat {
  application_id: number;
  full_name: string;
  email: string;
  status_v2: string;
}

interface ManagerJob {
  id: number;
  title: string;
  department: string;
  location: string;
  level: string;
  skills_json: SkillsJson | null;
  bonus_skills: string | null;
  description: string;
  status: "open" | "closed";
  closed_at: string | null;
  date_expiration: string | null;
  candidats_preselectionnes: Candidat[];
  expand_requested:   boolean;
  expand_phase:       "cycle2" | "cycle3" | null;
  waiting_meet_count: number;
  matched_count:      number;
}

type DisplayStatus = "ACTIVE" | "IN PROGRESS" | "CLOSED";

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE    = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const FILTERS     = ["ALL", "ACTIVE", "IN PROGRESS", "CLOSED"] as const;
const JOBS_PER_PAGE = 5;

const STATUS_STYLE: Record<DisplayStatus, { bg: string; color: string; border: string; dot: string }> = {
  ACTIVE:        { bg: "#f0fdf4", color: "#16a34a", border: "#bbf7d0", dot: "#16a34a" },
  "IN PROGRESS": { bg: "#eff6ff", color: "#2563eb", border: "#bfdbfe", dot: "#3b82f6" },
  CLOSED:        { bg: "#f8fafc", color: "#94a3b8", border: "#e2e8f0", dot: "#94a3b8" },
};

const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

// ─── Auth helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null { return localStorage.getItem("access_token"); }
function authHeaders() {
  const t = getToken();
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}
function getRoleFromToken(): string | null {
  const token = getToken();
  if (!token) return null;
  try {
    const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return (JSON.parse(atob(b64)) as { role?: string }).role ?? null;
  } catch { return null; }
}
function mapDisplayStatus(job: ManagerJob): DisplayStatus {
  if (job.status === "closed" || job.closed_at) return "CLOSED";
  if ((job.candidats_preselectionnes ?? []).length > 0) return "IN PROGRESS";
  return "ACTIVE";
}

// ─── Sidebar — floating pill violette (identique Dashboard) ───────────────────

/** Floating label qui pop à droite de l'icône survolée */
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
          {/* Flèche */}
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
                  layoutId="activeBar-registry"
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

function JobSkeleton() {
  return (
    <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
      {[1, 2, 3, 4].map(i => (
        <div key={i} style={{
          padding: "14px 16px", borderRadius: 14,
          background: "rgba(255,255,255,0.5)", border: "1px solid rgba(255,255,255,0.7)",
          display: "flex", flexDirection: "column", gap: 8,
        }}>
          <Skel w="52%" h={14} />
          <Skel w="36%" h={11} />
          <div style={{ display: "flex", gap: 6 }}>
            <Skel w={50} h={18} radius={6} />
            <Skel w={42} h={18} radius={6} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Skill pills ──────────────────────────────────────────────────────────────

function SkillPills({ skillsJson }: { skillsJson: SkillsJson | null }) {
  if (!skillsJson) return null;
  const all = [
    ...(skillsJson.coding   ?? []).map(s => ({ label: s, bg: "rgba(37,99,235,0.08)",  color: "#2563eb" })),
    ...(skillsJson.platform ?? []).map(s => ({ label: s, bg: "rgba(124,58,237,0.08)", color: "#7c3aed" })),
    ...(skillsJson.mixed    ?? []).map(s => ({ label: s, bg: "rgba(8,145,178,0.08)",  color: "#0891b2" })),
  ].slice(0, 5);
  if (!all.length) return null;
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 6 }}>
      {all.map(({ label, bg, color }) => (
        <span key={label} style={{
          fontSize: 10, padding: "2px 8px", borderRadius: 5, fontWeight: 600,
          background: bg, color, border: `1px solid ${color}28`,
        }}>{label}</span>
      ))}
    </div>
  );
}

// ─── Card glassmorphism ───────────────────────────────────────────────────────

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
      }}
    >
      {children}
    </motion.div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function MissionRegistry() {
  const [, navigate] = useLocation();
  const role = getRoleFromToken();

  const [activeFilter, setActiveFilter] = useState<typeof FILTERS[number]>("ALL");
  const [jobPage, setJobPage]           = useState(0);
  const [jobs, setJobs]                 = useState<ManagerJob[]>([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState<string | null>(null);

  useEffect(() => { if (!getToken()) navigate("/"); }, [navigate]);

  const endpoint = role === "RH"
    ? `${API_BASE}/jobs/rh/dashboard`
    : `${API_BASE}/jobs/manager/dashboard`;

  // ─── FETCH CORRIGÉ ────────────────────────────────────────────────────────
  // RH  : appelle /jobs/rh/dashboard + /jobs/ → merge pour voir tous les jobs
  // MANAGER : appelle uniquement /jobs/manager/dashboard → seulement les jobs assignés
  const fetchJobs = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const dashRes = await fetch(endpoint, { headers: authHeaders() });

      if (dashRes.status === 401) { localStorage.removeItem("access_token"); navigate("/"); return; }
      if (dashRes.status === 403) throw new Error("Access denied — insufficient role.");
      if (!dashRes.ok)            throw new Error(`Server error: ${dashRes.status}`);

      const dashData: ManagerJob[] = await dashRes.json();

      if (role === "RH") {
        // RH uniquement : enrichir avec tous les jobs pour voir ceux sans candidats
        const allRes = await fetch(`${API_BASE}/jobs`, { headers: authHeaders() });
        if (allRes.ok) {
          const allData: ManagerJob[] = await allRes.json();
          const ids = new Set(dashData.map(j => j.id));
          const merged = [
            ...dashData,
            ...allData
              .filter(j => !ids.has(j.id))
              .map(j => ({ ...j, candidats_preselectionnes: j.candidats_preselectionnes ?? [] })),
          ];
          merged.sort((a, b) => b.id - a.id);
          setJobs(merged);
          return;
        }
      }

      // MANAGER : uniquement les jobs assignés — pas de merge avec /jobs/
      dashData.sort((a, b) => b.id - a.id);
      setJobs(dashData);

    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally { setLoading(false); }
  }, [endpoint, navigate, role]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  const enriched   = jobs.map(j => ({ ...j, displayStatus: mapDisplayStatus(j) }));
  const filtered   = activeFilter === "ALL" ? enriched : enriched.filter(j => j.displayStatus === activeFilter);
  const totalPages = Math.ceil(filtered.length / JOBS_PER_PAGE);
  const pageJobs   = filtered.slice(jobPage * JOBS_PER_PAGE, (jobPage + 1) * JOBS_PER_PAGE);

  const counts = {
    ALL: enriched.length,
    ACTIVE: enriched.filter(j => j.displayStatus === "ACTIVE").length,
    "IN PROGRESS": enriched.filter(j => j.displayStatus === "IN PROGRESS").length,
    CLOSED: enriched.filter(j => j.displayStatus === "CLOSED").length,
  };

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        .job-row { transition: background 0.15s, box-shadow 0.15s; }
        .job-row:hover { background: rgba(255,255,255,0.98) !important; box-shadow: 0 4px 18px rgba(90,40,160,0.10) !important; }
        .fpill { transition: all 0.15s; }
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
            {/* Top bar logo + actions */}
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 20,
            }}>
              {/* Logo + nom */}
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <img
                  src={logoImg}
                  alt="Dynamix Services"
                  style={{ width: 45, height: 45, objectFit: "contain", animation: "floatLogo 2.4s ease-in-out infinite" }}
                />
                <h1 style={{ fontSize: 28, fontWeight: 700, color: "#1c2a38", margin: 0, lineHeight: 1.1 }}>
                  Job Management
                </h1>
              </div>

              {/* Refresh button */}
              <motion.button
                onClick={fetchJobs}
                disabled={loading}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 16px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  border: "1px solid rgba(255,255,255,0.9)",
                  background: "rgba(255,255,255,0.80)",
                  backdropFilter: "blur(8px)",
                  color: "#64748b",
                  cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading ? 0.5 : 1,
                  boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
                  transition: "all 0.15s",
                }}
              >
                <RefreshCw size={13} />
                {loading ? "Loading…" : "Refresh"}
              </motion.button>
            </div>

            {/* Date label */}
            <p style={{
              fontSize: 10, fontWeight: 700, color: "#94a3b8",
              letterSpacing: "0.18em", marginBottom: 12, textTransform: "uppercase",
            }}>
              {dateLabel}
            </p>

            {/* Subtitle */}
            <div>
              <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
                {role === "RH" ? "All jobs" : "Assigned jobs"} — {loading ? "…" : `${jobs.length} total`}
              </p>
            </div>

            {/* KPI pills */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
              {([
                { label: `${counts.ALL} total`,            color: "#0d9488" },
                { label: `${counts.ACTIVE} active`,        color: "#16a34a" },
                { label: `${counts["IN PROGRESS"]} in progress`, color: "#2563eb" },
                { label: `${counts.CLOSED} closed`,        color: "#94a3b8" },
              ]).map(({ label, color }) => (
                <motion.div
                  key={label}
                  whileHover={{ scale: 1.03, y: -1 }}
                  style={{
                    display: "flex", alignItems: "center", gap: 7,
                    padding: "7px 14px", borderRadius: 999,
                    background: "rgba(255,255,255,0.85)", backdropFilter: "blur(8px)",
                    border: "1px solid rgba(255,255,255,0.9)",
                    fontSize: 12, fontWeight: 500, color: "#475569",
                    boxShadow: "0 1px 4px rgba(90,40,160,0.08)", cursor: "default",
                  }}
                >
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
                  {label}
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* ── Card principale ────────────────────────────────────────────── */}
          <Card delay={0.1}>
            {/* Card header */}
            <div style={{
              padding: "16px 20px",
              borderBottom: "1px solid rgba(240,235,255,0.7)",
              display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10,
            }}>
              <div>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Job Listings</h2>
                <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                  {loading ? "—" : `${filtered.length} result${filtered.length !== 1 ? "s" : ""}`}
                </p>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {FILTERS.map(f => (
                  <button
                    key={f}
                    className="fpill"
                    onClick={() => { setActiveFilter(f); setJobPage(0); }}
                    style={{
                      padding: "5px 12px", borderRadius: 8, fontSize: 11, fontWeight: 600, cursor: "pointer",
                      border: "1px solid",
                      borderColor: activeFilter === f ? "#0d9488" : "rgba(255,255,255,0.6)",
                      background: activeFilter === f ? "rgba(13,148,136,0.10)" : "rgba(255,255,255,0.6)",
                      color: activeFilter === f ? "#0d9488" : "#64748b",
                    }}
                  >{f}</button>
                ))}
                <div style={{
                  width: 32, height: 32, borderRadius: 10,
                  background: "rgba(13,148,136,0.10)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Briefcase size={15} color="#0d9488" />
                </div>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div style={{
                display: "flex", alignItems: "center", gap: 10,
                margin: 16, padding: "12px 16px", borderRadius: 12,
                background: "#fef2f2", border: "1px solid #fca5a5",
              }}>
                <AlertCircle size={16} color="#ef4444" style={{ flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: "#991b1b", flex: 1 }}>{error}</span>
                <button
                  onClick={fetchJobs}
                  style={{
                    fontSize: 11, fontWeight: 600, cursor: "pointer",
                    background: "none", border: "1px solid #fca5a5",
                    borderRadius: 6, color: "#991b1b", padding: "3px 10px",
                  }}
                >Retry</button>
              </div>
            )}

            {/* Skeleton */}
            {loading && <JobSkeleton />}

            {/* Empty */}
            {!loading && !error && filtered.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "64px 0", gap: 12 }}>
                <div style={{
                  width: 52, height: 52, borderRadius: 16, background: "rgba(13,148,136,0.08)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <CheckCircle2 size={24} color="#0d9488" />
                </div>
                <p style={{ fontSize: 14, color: "#64748b" }}>No jobs assigned yet.</p>
              </div>
            )}

            {/* Job rows */}
            {!loading && !error && filtered.length > 0 && (
              <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                {pageJobs.map((job, i) => {
                  const st = STATUS_STYLE[job.displayStatus];
                  const candidateCount = (job.candidats_preselectionnes ?? []).length;
                  return (
                    <motion.div
                      key={job.id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="job-row"
                      onClick={() => navigate(`/job/${job.id}`)}
                      style={{
                        display: "flex", alignItems: "center", gap: 14,
                        padding: "14px 16px", borderRadius: 14,
                        background: "rgba(255,255,255,0.72)",
                        border: "1px solid rgba(255,255,255,0.85)",
                        cursor: "pointer",
                        backdropFilter: "blur(10px)",
                      }}
                    >
                      {/* Barre couleur statut */}
                      <div style={{ width: 4, alignSelf: "stretch", borderRadius: 3, background: st.dot, flexShrink: 0 }} />

                      {/* Infos */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>{job.title}</p>
                        <p style={{ fontSize: 11, color: "#94a3b8", margin: "3px 0 0" }}>
                          {[job.department, job.location, job.level].filter(Boolean).join(" · ")}
                        </p>
                        <SkillPills skillsJson={job.skills_json} />
                      </div>

                      {/* Candidates */}
                      {candidateCount > 0 && (
                        <div style={{
                          display: "flex", alignItems: "center", gap: 5,
                          padding: "4px 10px", borderRadius: 8,
                          background: "rgba(59,130,246,0.10)", flexShrink: 0,
                        }}>
                          <Users size={11} color="#3b82f6" />
                          <span style={{ fontSize: 11, color: "#3b82f6", fontWeight: 600 }}>{candidateCount}</span>
                        </div>
                      )}

                      {/* Badge expand requis */}
                      {job.expand_requested && (
                        <span style={{
                          padding: "4px 10px", fontSize: 10, fontWeight: 700,
                          letterSpacing: "0.06em", borderRadius: 8, whiteSpace: "nowrap", flexShrink: 0,
                          background: "rgba(245,158,11,0.10)", border: "1px solid rgba(245,158,11,0.3)",
                          color: "#d97706",
                        }}>⚠ Action requise</span>
                      )}

                      {/* Badge statut */}
                      <span style={{
                        padding: "4px 12px", fontSize: 10, fontWeight: 700,
                        letterSpacing: "0.08em", borderRadius: 8, whiteSpace: "nowrap", flexShrink: 0,
                        background: st.bg, border: `1px solid ${st.border}`, color: st.color,
                      }}>{job.displayStatus}</span>

                      <ChevronRight size={16} color="#cbd5e1" style={{ flexShrink: 0 }} />
                    </motion.div>
                  );
                })}
              </div>
            )}

            {/* Pagination */}
            {!loading && totalPages > 1 && (
              <div style={{
                display: "flex", alignItems: "center", justifyContent: "space-between",
                padding: "14px 20px", borderTop: "1px solid rgba(240,235,255,0.7)",
              }}>
                <button
                  onClick={() => setJobPage(p => Math.max(0, p - 1))}
                  disabled={jobPage === 0}
                  style={{
                    padding: "6px 14px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.7)",
                    background: "rgba(255,255,255,0.7)", color: "#64748b",
                    cursor: jobPage === 0 ? "not-allowed" : "pointer",
                    opacity: jobPage === 0 ? 0.35 : 1, transition: "all 0.15s",
                  }}
                >← Previous</button>

                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  {Array.from({ length: totalPages }).map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setJobPage(i)}
                      style={{
                        width: 30, height: 30, borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
                        border: i === jobPage ? "1px solid #0d9488" : "1px solid rgba(255,255,255,0.7)",
                        background: i === jobPage ? "rgba(13,148,136,0.12)" : "rgba(255,255,255,0.6)",
                        color: i === jobPage ? "#0d9488" : "#64748b", transition: "all 0.12s",
                      }}
                    >{i + 1}</button>
                  ))}
                  <span style={{ fontSize: 11, color: "#94a3b8", marginLeft: 6 }}>
                    {jobPage * JOBS_PER_PAGE + 1}–{Math.min((jobPage + 1) * JOBS_PER_PAGE, filtered.length)} / {filtered.length}
                  </span>
                </div>

                <button
                  onClick={() => setJobPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={jobPage >= totalPages - 1}
                  style={{
                    padding: "6px 14px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.7)",
                    background: "rgba(255,255,255,0.7)", color: "#64748b",
                    cursor: jobPage >= totalPages - 1 ? "not-allowed" : "pointer",
                    opacity: jobPage >= totalPages - 1 ? 0.35 : 1, transition: "all 0.15s",
                  }}
                >Next →</button>
              </div>
            )}
          </Card>

        </div>
      </div>
    </>
  );
}