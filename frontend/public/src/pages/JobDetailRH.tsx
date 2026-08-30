/**
 * JobDetailRH.tsx — RH Job Detail View
 * Path: /rh/jobs/:id
 * Shows complete job info with pipeline statistics
 */

import { useState, useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Briefcase, Users, Settings,
  ArrowLeft, AlertCircle, Lock, CheckCircle2,
  LogOut, MapPin, Calendar, Building2, Zap,
  Users2, TrendingUp, Loader2, X,
} from "lucide-react";
import logoImg from "../assets/logoo.png";
import bgWave from "../assets/imagee.png";

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const NAV_RH = [
  { href: "/rh/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/rh/jobs",      icon: Briefcase,       label: "Jobs"      },
  { href: "/rh/Managers",  icon: Users,           label: "Managers"  },
  { href: "/rh/account",   icon: Settings,        label: "Account"   },
];

// ─── Auth helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null { return localStorage.getItem("access_token"); }
function authHeaders() {
  const t = getToken();
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface Pipeline {
  total: number;
  en_attente: number;
  preselectionnes: number;
  test_envoye: number;
  test_complete: number;
  entretien_planifie: number;
  acceptes: number;
  rejetes: number;
}

interface Manager {
  id: number;
  email: string;
}

interface Job {
  id: number;
  title: string;
  description: string;
  department: string | null;
  location: string | null;
  level: string | null;
  company: string | null;
  skills_required: string;
  skills_json: { coding?: string[]; platform?: string[]; mixed?: string[] } | null;
  bonus_skills: string[] | null;
  status: "open" | "closed";
  created_at: string | null;
  date_expiration: string | null;
  pipeline: Pipeline;
  manager: Manager | null;
}

// ─── Sidebar RH ───────────────────────────────────────────────────────────────

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
            width: 0, height: 0,
            borderTop: "5px solid transparent", borderBottom: "5px solid transparent",
            borderRight: "6px solid #3b0d8e",
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

function Sidebar() {
  const [location] = useLocation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  return (
    <nav style={{
      position: "fixed", top: 140, left: 16, zIndex: 50, borderRadius: 30,
      background: "linear-gradient(180deg, #4a1d96 0%, #3b0d8e 55%, #2c0f70 100%)",
      boxShadow: "0 8px 32px rgba(60,12,120,0.30), 0 2px 8px rgba(0,0,0,0.15)",
      padding: "18px 8px", display: "flex", flexDirection: "column",
      alignItems: "center", gap: 4, overflow: "visible", userSelect: "none", width: 58,
    }}>
      {NAV_RH.map(({ href, icon: Icon, label }) => {
        const active = location === href || location.startsWith(href + "/");
        const hovered = hoveredKey === href;
        return (
          <a key={href} href={href} style={{ textDecoration: "none", position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey(href)}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              style={{
                width: 40, height: 40, margin: "0 auto", borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer", position: "relative",
                background: active ? "rgba(255,255,255,0.20)" : hovered ? "rgba(255,255,255,0.11)" : "transparent",
                transition: "background 0.15s",
              }}
            >
              {active && (
                <motion.div layoutId="activeBar-jobs" style={{
                  position: "absolute", left: -7, top: "50%", y: "-50%",
                  width: 3, height: 18, borderRadius: 3, background: "#fff",
                }} transition={{ type: "spring", stiffness: 500, damping: 30 }} />
              )}
              <Icon size={17} color={active ? "#ffffff" : "rgba(255,255,255,0.60)"} />
              <NavLabel label={label} visible={hovered} />
            </motion.div>
          </a>
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
                cursor: "pointer", position: "relative",
                background: hovered ? "rgba(239,68,68,0.20)" : "transparent",
                transition: "background 0.15s",
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

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function JobDetailRH() {
  const [, navigate] = useLocation();
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [closingJob, setClosingJob] = useState(false);
  const [closeConfirm, setCloseConfirm] = useState(false);
  const [closeLoading, setCloseLoading] = useState(false);

  useEffect(() => { if (!getToken()) navigate("/rh/login"); }, [navigate]);

  useEffect(() => {
    if (!jobId) return;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/jobs/rh/dashboard`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then((jobs: Job[]) => {
        const found = jobs.find(j => j.id === parseInt(jobId));
        if (!found) throw new Error("Job not found");
        setJob(found);
      })
      .catch(e => setError(e instanceof Error ? e.message : "Error loading job"))
      .finally(() => setLoading(false));
  }, [jobId, navigate]);

  const handleCloseJob = async () => {
    if (!job) return;
    setCloseLoading(true);
    try {
      const res = await fetch(`${API_BASE}/jobs/${job.id}/close`, {
        method: "PATCH",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed to close job");
      setClosingJob(true);
      setTimeout(() => navigate("/rh/jobs"), 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setCloseLoading(false);
    }
  };

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  }).toUpperCase();

  const isOpen = job?.status === "open";

  return (
    <>
      <style>{`
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
      `}</style>

      <Sidebar />

      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 64px", maxWidth: 1000, margin: "0 auto" }}>

          {/* ── Header ── */}
          <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} style={{ marginBottom: 28 }}>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div>
                  <h1 style={{ fontSize: 28, fontWeight: 700, color: "#1c2a38", margin: 0, lineHeight: 1.1 }}>Job Details</h1>
                  <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.18em", margin: "4px 0 0", textTransform: "uppercase" }}>{dateLabel}</p>
                </div>
              </div>

              <motion.button
                onClick={() => navigate("/rh/jobs")}
                whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 16px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                  border: "1px solid rgba(255,255,255,0.9)", background: "rgba(255,255,255,0.80)",
                  backdropFilter: "blur(8px)", color: "#64748b",
                  cursor: "pointer", boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
                }}
              >
                <ArrowLeft size={13} /> Back to Jobs
              </motion.button>
            </div>

            {/* Status badge */}
            {!loading && job && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  padding: "4px 12px", fontSize: 10, fontWeight: 700,
                  letterSpacing: "0.06em", borderRadius: 8, whiteSpace: "nowrap",
                  background: isOpen ? "#f0fdf4" : "#f8fafc",
                  border: `1px solid ${isOpen ? "#bbf7d0" : "#e2e8f0"}`,
                  color: isOpen ? "#16a34a" : "#94a3b8",
                }}>
                  {isOpen ? "OPEN" : "CLOSED"}
                </span>
              </div>
            )}
          </motion.div>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  marginBottom: 16, padding: "12px 16px", borderRadius: 12,
                  background: "#fef2f2", border: "1px solid #fca5a5",
                }}
              >
                <AlertCircle size={15} color="#ef4444" style={{ flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: "#991b1b", flex: 1 }}>{error}</span>
                <X size={13} color="#ef4444" style={{ cursor: "pointer" }} onClick={() => setError(null)} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Main content */}
          {loading ? (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "#94a3b8" }}>
              <Loader2 size={24} style={{ animation: "spin 1s linear infinite", marginBottom: 12 }} />
              Loading job details...
            </div>
          ) : job ? (
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24 }}>

              {/* ── Left: Job Info ── */}
              <motion.div
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
                style={{
                  background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
                  borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)", overflow: "hidden",
                  boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
                }}
              >
                <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)" }}>
                  <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: 0 }}>{job.title}</h2>
                </div>

                <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 20 }}>

                  {/* Basic Info */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                    {[
                      { icon: Building2, label: "Company", value: "Dynamix Services" },
                      { icon: MapPin, label: "Location", value: "Bizerte - Tunisia" },
                      { icon: Briefcase, label: "Department", value: job.department },
                      { icon: Zap, label: "Level", value: job.level },
                      { icon: Calendar, label: "Posted", value: job.created_at ? new Date(job.created_at).toLocaleDateString("en-US") : "—" },
                      { icon: Calendar, label: "Expires", value: job.date_expiration ? new Date(job.date_expiration).toLocaleDateString("en-US") : "—" },
                    ].map(({ icon: Icon, label, value }) => (
                      <div key={label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <div style={{
                          width: 36, height: 36, borderRadius: 10,
                          background: "rgba(124,58,237,0.08)",
                          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                        }}>
                          <Icon size={14} color="#7c3aed" />
                        </div>
                        <div>
                          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", margin: 0, textTransform: "uppercase" }}>{label}</p>
                          <p style={{ fontSize: 12, fontWeight: 600, color: "#1c2a38", margin: 0 }}>{value || "—"}</p>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Manager */}
                  {job.manager && (
                    <div style={{
                      padding: "12px 14px", borderRadius: 12,
                      background: "rgba(8,145,178,0.08)", border: "1px solid rgba(8,145,178,0.2)",
                    }}>
                      <p style={{ fontSize: 10, fontWeight: 700, color: "#0891b2", margin: "0 0 4px", textTransform: "uppercase" }}>Manager</p>
                      <p style={{ fontSize: 12, fontWeight: 600, color: "#1c2a38", margin: 0 }}>👤 {job.manager.email}</p>
                    </div>
                  )}

                  {/* Description */}
                  {job.description && (
                    <div>
                      <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", margin: "0 0 8px", textTransform: "uppercase" }}>Description</p>
                      <p style={{ fontSize: 12, color: "#475569", lineHeight: 1.6, margin: 0 }}>{job.description}</p>
                    </div>
                  )}

                  {/* Skills */}
                  {job.skills_json && (
                    <div>
                      <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", margin: "0 0 8px", textTransform: "uppercase" }}>Required Skills</p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {[...(job.skills_json.coding ?? []), ...(job.skills_json.platform ?? []), ...(job.skills_json.mixed ?? [])].map(s => (
                          <span key={s} style={{
                            fontSize: 11, padding: "3px 10px", borderRadius: 6, fontWeight: 600,
                            background: "rgba(124,58,237,0.08)", color: "#7c3aed", border: "1px solid rgba(124,58,237,0.15)",
                          }}>{s}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Bonus Skills */}
                  {job.bonus_skills && job.bonus_skills.length > 0 && (
                    <div>
                      <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", margin: "0 0 8px", textTransform: "uppercase" }}>Bonus Skills</p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {job.bonus_skills.map(s => (
                          <span key={s} style={{
                            fontSize: 11, padding: "3px 10px", borderRadius: 6, fontWeight: 600,
                            background: "rgba(245,158,11,0.08)", color: "#d97706", border: "1px solid rgba(245,158,11,0.2)",
                          }}>{s}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>

              {/* ── Right: Pipeline Stats ── */}
              <motion.div
                initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
                style={{
                  background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
                  borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)", overflow: "hidden",
                  boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
                }}
              >
                <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)" }}>
                  <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Pipeline</h2>
                </div>

                <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: 10 }}>
                  {[
                    { label: "Total", value: job.pipeline.total, color: "#475569" },
                    { label: "Pending", value: job.pipeline.en_attente, color: "#0891b2" },
                    { label: "Preselected", value: job.pipeline.preselectionnes, color: "#7c3aed" },
                    { label: "Test Sent", value: job.pipeline.test_envoye, color: "#d97706" },
                    { label: "Test Done", value: job.pipeline.test_complete, color: "#0d9488" },
                    { label: "Interview", value: job.pipeline.entretien_planifie, color: "#2563eb" },
                    { label: "Accepted", value: job.pipeline.acceptes, color: "#16a34a" },
                    { label: "Rejected", value: job.pipeline.rejetes, color: "#ef4444" },
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 12px", borderRadius: 10,
                      background: `${color}08`, border: `1px solid ${color}20`,
                    }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: "#1c2a38" }}>{label}</span>
                      <span style={{ fontSize: 13, fontWeight: 700, color, display: "flex", alignItems: "center", gap: 6 }}>
                        <Users2 size={12} /> {value}
                      </span>
                    </div>
                  ))}

                  {/* Close button */}
                  {isOpen && (
                    <motion.button
                      whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                      onClick={() => setCloseConfirm(true)}
                      style={{
                        width: "100%",
                        marginTop: 10,
                        display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                        padding: "9px 0", borderRadius: 10, fontSize: 12, fontWeight: 700,
                        border: "1px solid #fca5a5", background: "rgba(239,68,68,0.07)",
                        color: "#ef4444", cursor: "pointer",
                        transition: "all 0.15s",
                      }}
                    >
                      <Lock size={12} /> Close Job
                    </motion.button>
                  )}
                </div>
              </motion.div>

            </div>
          ) : null}

        </div>
      </div>

      {/* Close confirmation modal */}
      <AnimatePresence>
        {closeConfirm && job && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{
              position: "fixed", inset: 0, zIndex: 200,
              background: "rgba(15,10,40,0.45)", backdropFilter: "blur(4px)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
            onClick={() => !closeLoading && setCloseConfirm(false)}
          >
            <motion.div
              initial={{ scale: 0.92, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.92, opacity: 0 }}
              onClick={e => e.stopPropagation()}
              style={{
                background: "rgba(255,255,255,0.96)", backdropFilter: "blur(20px)",
                borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)",
                boxShadow: "0 20px 60px rgba(60,12,120,0.25)",
                padding: "28px 32px", maxWidth: 400, width: "90%",
              }}
            >
              <div style={{
                width: 48, height: 48, borderRadius: 14,
                background: "rgba(239,68,68,0.10)",
                display: "flex", alignItems: "center", justifyContent: "center",
                marginBottom: 16,
              }}>
                <Lock size={20} color="#ef4444" />
              </div>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: "0 0 8px" }}>
                Close this job?
              </h3>
              <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 6px" }}>
                <strong style={{ color: "#1c2a38" }}>« {job.title} »</strong>
              </p>
              <p style={{ fontSize: 12, color: "#94a3b8", margin: "0 0 24px", lineHeight: 1.6 }}>
                This action is irreversible. The job will be closed and the GDPR timer will start.
              </p>
              <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                <button
                  onClick={() => setCloseConfirm(false)}
                  disabled={closeLoading}
                  style={{
                    padding: "9px 18px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                    border: "1px solid #e2e8f0", background: "#f8fafc", color: "#64748b", cursor: "pointer",
                  }}
                >Cancel</button>
                <button
                  onClick={handleCloseJob}
                  disabled={closeLoading}
                  style={{
                    padding: "9px 18px", borderRadius: 10, fontSize: 12, fontWeight: 700,
                    border: "none", background: "#ef4444", color: "#fff",
                    cursor: closeLoading ? "not-allowed" : "pointer",
                    display: "flex", alignItems: "center", gap: 6,
                    opacity: closeLoading ? 0.7 : 1,
                  }}
                >
                  {closeLoading ? <><Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> Closing…</> : <><Lock size={12} /> Close job</>}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
