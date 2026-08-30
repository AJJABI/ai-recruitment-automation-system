

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLocation, Link } from "wouter";
import {
  LayoutDashboard, Briefcase, Users, MessageSquare,
  ChevronRight, AlertCircle, LogOut,
} from "lucide-react";
import logoImg from "../assets/logoo.png";
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

// ─── Nav ──────────────────────────────────────────────────────────────────────
const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

// ─── Floating label (Dashboard style) ─────────────────────────────────────────
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
            position: "absolute", right: "100%", top: "50%",
            transform: "translateY(-50%)", width: 0, height: 0,
            borderTop: "5px solid transparent", borderBottom: "5px solid transparent",
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

// ─── Sidebar — pill violette flottante (Dashboard style) ──────────────────────
function Sidebar() {
  const [location]   = useLocation();
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
      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      overflow: "visible",
      userSelect: "none", width: 58,
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
                width: 40, height: 40, margin: "0 auto",
                borderRadius: 13, display: "flex", alignItems: "center", justifyContent: "center",
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
                width: 40, height: 40, margin: "0 auto",
                borderRadius: 13, display: "flex", alignItems: "center", justifyContent: "center",
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

// ─── Card wrapper (Dashboard style) ───────────────────────────────────────────
function Card({ children, delay = 0 }: { children: React.ReactNode; delay?: number }) {
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

function SkeletonCard() {
  return (
    <div style={{
      background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
      borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)",
      padding: 20, display: "flex", flexDirection: "column", gap: 14,
      boxShadow: "0 2px 16px rgba(90,40,160,0.07)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Skel w={38} h={38} radius={10} />
        <Skel w={88} h={22} radius={8} />
      </div>
      <div><Skel w="65%" h={16} /><div style={{ marginTop: 6 }}><Skel w="45%" h={12} /></div></div>
      <div style={{ display: "flex", gap: 6 }}>
        {[0, 1, 2].map(j => <Skel key={j} w={30} h={30} radius={99} />)}
      </div>
      <Skel w="100%" h={38} radius={10} />
    </div>
  );
}

// ─── Types ─────────────────────────────────────────────────────────────────────
interface JobItem {
  id: number;
  title: string;
  department: string;
  pipeline?: { total: number; entretien_planifie: number };
  candidats_preselectionnes?: Array<{
    application_id: number;
    full_name: string;
    status_v2: string;
  }>;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────
const AVATAR_PALETTE = ["#0d9488", "#0e7490", "#0369a1", "#7c3aed", "#065f46", "#9a3412"];

function initials(name: string) {
  return name ? name.split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase() : "?";
}

function count(job: JobItem) {
  return job.pipeline?.total ?? job.candidats_preselectionnes?.length ?? 0;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function AllCandidates() {
  const [, navigate] = useLocation();
  const role = getRoleFromToken();

  const [jobs,    setJobs]    = useState<JobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }

    const endpoint = role === "RH"
      ? `${API_BASE}/jobs/rh/dashboard`
      : `${API_BASE}/jobs/manager/dashboard`;

    fetch(endpoint, { headers: authHeaders() })
      .then(r => {
        if (r.status === 401) { localStorage.removeItem("access_token"); navigate("/login"); return undefined; }
        if (!r.ok) throw new Error(`Error ${r.status}`);
        return r.json() as Promise<JobItem[]>;
      })
      // ✅ Le backend renvoie "open" ou "closed" — on exclut seulement les fermés
      .then(d => d && setJobs(d.filter((j: any) => j.status !== "closed")))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Unknown error"))
      .finally(() => setLoading(false));
  }, []);

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

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
        {/* Overlay */}
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 48px", maxWidth: 1260, margin: "0 auto" }}>

          {/* ── TopBar ── */}
          <motion.div
            initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
            style={{ marginBottom: 28 }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              {/* Logo + page title */}
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                
                <h1 style={{ fontSize: 28, fontWeight: 700, color: TEXT_MAIN, margin: 0, lineHeight: 1.1 }}>
                  Jobs Applied
                </h1>
              </div>
              {/* Date pill */}
              <div style={{
                display: "flex", alignItems: "center", gap: 7,
                padding: "7px 14px", borderRadius: 999,
                background: "rgba(255,255,255,0.85)", backdropFilter: "blur(8px)",
                border: "1px solid rgba(255,255,255,0.9)",
                fontSize: 12, fontWeight: 500, color: "#475569",
                boxShadow: "0 1px 4px rgba(90,40,160,0.08)",
              }}>
                <Briefcase size={13} style={{ color: TEAL }} />
                <span style={{ fontSize: 10, fontWeight: 700, color: TEXT_MUTED, letterSpacing: "0.18em" }}>{dateLabel}</span>
              </div>
            </div>

            {/* Subtitle */}
            <div style={{ marginLeft: 4 }}>
              <p style={{ fontSize: 13, color: TEXT_SUB, margin: 0 }}>
                {loading ? "—" : `${jobs.length} active job${jobs.length !== 1 ? "s" : ""}`}
              </p>
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

          {/* ── Job cards grid ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(288px, 1fr))", gap: 16 }}>
            {loading
              ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
              : jobs.map((job, i) => {
                  const candidates = job.candidats_preselectionnes ?? [];
                  return (
                    <motion.div
                      key={job.id}
                      initial={{ opacity: 0, y: 18, scale: 0.97 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      transition={{ delay: i * 0.07, type: "spring", stiffness: 200, damping: 22 }}
                    >
                      <Card delay={i * 0.05}>
                        <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
                          {/* Top row */}
                          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
                            <div style={{
                              width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              background: TEAL_BG, border: `1px solid ${TEAL_BORDER}`,
                            }}>
                              <Briefcase size={16} color={TEAL} />
                            </div>
                            <span style={{
                              fontSize: 10, fontWeight: 700, letterSpacing: "0.07em",
                              padding: "4px 10px", borderRadius: 8,
                              background: "rgba(255,255,255,0.7)", color: TEXT_SUB,
                              border: "1px solid rgba(255,255,255,0.9)",
                            }}>
                              {job.department}
                            </span>
                          </div>

                          {/* Job title */}
                          <div style={{ fontSize: 14, fontWeight: 700, color: TEXT_MAIN }}>{job.title}</div>

                          {/* Avatar stack */}
                          <div style={{ display: "flex", alignItems: "center" }}>
                            {candidates.slice(0, 5).map((c, idx) => (
                              <div key={c.application_id} style={{
                                width: 30, height: 30, borderRadius: "50%",
                                border: "2px solid rgba(255,255,255,0.9)", flexShrink: 0,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: 10, fontWeight: 700, color: "#fff",
                                background: AVATAR_PALETTE[idx % AVATAR_PALETTE.length],
                                marginLeft: idx > 0 ? -9 : 0,
                                position: "relative", zIndex: 10 - idx,
                                boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
                              }}>
                                {initials(c.full_name)}
                              </div>
                            ))}
                            {candidates.length > 5 && (
                              <div style={{
                                width: 30, height: 30, borderRadius: "50%",
                                border: "2px solid rgba(255,255,255,0.9)", flexShrink: 0,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: 10, fontWeight: 700, color: TEXT_SUB,
                                background: "#f1f5f9", marginLeft: -9, position: "relative", zIndex: 1,
                              }}>
                                +{candidates.length - 5}
                              </div>
                            )}
                            {candidates.length === 0 && (
                              <span style={{ fontSize: 11, color: TEXT_MUTED, fontStyle: "italic" }}>No candidates yet</span>
                            )}
                          </div>

                          {/* CTA */}
                          <button
                            onClick={() => navigate(`/candidates/${job.id}`)}
                            style={{
                              width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                              padding: "10px 14px", borderRadius: 10,
                              border: `1px solid ${TEAL_BORDER}`, background: TEAL_BG,
                              cursor: "pointer", fontSize: 12, fontWeight: 700,
                              color: TEAL, letterSpacing: "0.04em", transition: "background 0.15s, border-color 0.15s",
                            }}
                            onMouseEnter={e => { e.currentTarget.style.background = "rgba(13,148,136,0.14)"; e.currentTarget.style.borderColor = TEAL; }}
                            onMouseLeave={e => { e.currentTarget.style.background = TEAL_BG; e.currentTarget.style.borderColor = TEAL_BORDER; }}
                          >
                            <span>View Candidates</span>
                            <ChevronRight size={14} />
                          </button>
                        </div>
                      </Card>
                    </motion.div>
                  );
                })}
          </div>

          {/* ── Empty state ── */}
          {!loading && !error && jobs.length === 0 && (
            <div style={{ textAlign: "center", padding: "72px 0" }}>
              <div style={{
                width: 52, height: 52, borderRadius: 16,
                background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
                border: "1px solid rgba(255,255,255,0.9)",
                display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 14px",
                boxShadow: "0 2px 16px rgba(90,40,160,0.07)",
              }}>
                <Users size={22} color={TEAL} />
              </div>
              <p style={{ fontSize: 14, fontWeight: 700, color: TEXT_MAIN, margin: "0 0 6px" }}>No candidates yet</p>
              <p style={{ fontSize: 12, color: TEXT_SUB, margin: 0 }}>
                Candidates will appear here once assigned to a pipeline.
              </p>
            </div>
          )}

        </div>
      </div>
    </>
  );
}