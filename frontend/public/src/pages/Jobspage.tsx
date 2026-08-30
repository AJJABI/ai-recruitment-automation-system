/**
 * JobsPage.tsx — Page RH : liste tous les jobs créés
 * Path : /rh/jobs
 * - Voir tous les jobs (open/closed)
 * - Stats pipeline par job
 * - Bouton "Créer un job" → /rh/jobs/create
 * - Fermer un job → PATCH /jobs/{id}/close
 */

import { useState, useEffect, useCallback } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  RefreshCw, AlertCircle, Plus, X,
  MapPin, Calendar, ChevronRight, Lock,
  Loader2, CheckCircle2, Building2, Briefcase,
} from "lucide-react";
import RHSidebar from "./RHSidebar";
import logoImg from "../assets/logoo.png";
import bgWave  from "../assets/imagee.png";

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE    = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const JOBS_PER_PAGE = 4;


// ─── Auth helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null { return localStorage.getItem("access_token"); }
function authHeaders() {
  const t = getToken();
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface Pipeline {
  total:              number;
  en_attente:         number;
  preselectionnes:    number;
  test_envoye:        number;
  test_complete:      number;
  entretien_planifie: number;
  acceptes:           number;
  rejetes:            number;
}

interface Manager {
  id:    number;
  email: string;
}

interface Job {
  id:         number;
  title:      string;
  department: string | null;
  location:   string | null;
  level:      string | null;
  status:     "open" | "closed";
  created_at: string | null;
  pipeline:   Pipeline;
  manager:    Manager | null;
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
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "12px 16px" }}>
      {[1,2,3,4,5].map(i => (
        <div key={i} style={{
          padding: "16px", borderRadius: 14,
          background: "rgba(255,255,255,0.5)", border: "1px solid rgba(255,255,255,0.7)",
          display: "flex", flexDirection: "column", gap: 10,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Skel w="220px" h={14} />
              <Skel w="140px" h={11} />
            </div>
            <Skel w={70} h={24} radius={8} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {[60,50,70,55].map((w,j) => <Skel key={j} w={w} h={18} radius={6} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Confirm Modal ────────────────────────────────────────────────────────────

function ConfirmClose({ job, onConfirm, onCancel, loading }: {
  job: Job; onConfirm: () => void; onCancel: () => void; loading: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(15,10,40,0.45)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onCancel}
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
            onClick={onCancel}
            style={{
              padding: "9px 18px", borderRadius: 10, fontSize: 12, fontWeight: 600,
              border: "1px solid #e2e8f0", background: "#f8fafc", color: "#64748b", cursor: "pointer",
            }}
          >Cancel</button>
          <button
            onClick={onConfirm}
            disabled={loading}
            style={{
              padding: "9px 18px", borderRadius: 10, fontSize: 12, fontWeight: 700,
              border: "none", background: "#ef4444", color: "#fff",
              cursor: loading ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 6,
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? <><Loader2 size={12} style={{ animation: "spin 1s linear infinite" }} /> Closing…</> : <><Lock size={12} /> Close job</>}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function JobsPage() {
  const [, navigate] = useLocation();

  const [jobs,        setJobs]        = useState<Job[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState<string | null>(null);
  const [filter,      setFilter]      = useState<"ALL" | "open" | "closed">("ALL");
  const [page,        setPage]        = useState(0);
  const [closingJob,  setClosingJob]  = useState<Job | null>(null);
  const [closeLoading,setCloseLoading]= useState(false);
  const [closedIds,   setClosedIds]   = useState<Set<number>>(new Set());

  useEffect(() => { if (!getToken()) navigate("/"); }, [navigate]);

  const fetchJobs = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/jobs/rh/dashboard`, { headers: authHeaders() });
      if (res.status === 401) { localStorage.removeItem("access_token"); navigate("/"); return; }
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data: Job[] = await res.json();
      data.sort((a, b) => b.id - a.id);
      setJobs(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally { setLoading(false); }
  }, [navigate]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  const handleClose = async () => {
    if (!closingJob) return;
    setCloseLoading(true);
    try {
      const res = await fetch(`${API_BASE}/jobs/${closingJob.id}/close`, {
        method: "PATCH", headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Close failed");
      setClosedIds(s => new Set([...s, closingJob.id]));
      setJobs(prev => prev.map(j => j.id === closingJob.id ? { ...j, status: "closed" } : j));
      setClosingJob(null);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Erreur");
    } finally { setCloseLoading(false); }
  };

  // Enrichir avec closedIds locaux
  const enriched = jobs.map(j => ({
    ...j,
    status: closedIds.has(j.id) ? "closed" as const : j.status,
  }));

  const filtered = filter === "ALL" ? enriched : enriched.filter(j => j.status === filter);
  const totalPages = Math.ceil(filtered.length / JOBS_PER_PAGE);
  const pageJobs   = filtered.slice(page * JOBS_PER_PAGE, (page + 1) * JOBS_PER_PAGE);

  const counts = {
    ALL:    enriched.length,
    open:   enriched.filter(j => j.status === "open").length,
    closed: enriched.filter(j => j.status === "closed").length,
  };

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  }).toUpperCase();

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        .job-row { transition: background 0.15s, box-shadow 0.15s, transform 0.15s; }
        .job-row:hover { background: rgba(255,255,255,0.98) !important; box-shadow: 0 4px 18px rgba(90,40,160,0.10) !important; transform: translateY(-1px); }
      `}</style>

      <RHSidebar />

      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 64px", maxWidth: 1200, margin: "0 auto" }}>

          {/* ── Header ── */}
          <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} style={{ marginBottom: 28 }}>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div>
                  <h1 style={{ fontSize: 28, fontWeight: 700, color: "#1c2a38", margin: 0, lineHeight: 1.1 }}>Jobs Management</h1>
                  <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.18em", margin: "4px 0 0", textTransform: "uppercase" }}>{dateLabel}</p>
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <motion.button
                  onClick={fetchJobs} disabled={loading}
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "8px 16px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.9)", background: "rgba(255,255,255,0.80)",
                    backdropFilter: "blur(8px)", color: "#64748b",
                    cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.5 : 1,
                    boxShadow: "0 1px 6px rgba(90,40,160,0.08)", transition: "all 0.15s",
                  }}
                >
                  <RefreshCw size={13} style={loading ? { animation: "spin 1s linear infinite" } : {}} />
                  {loading ? "Loading…" : "Refresh"}
                </motion.button>

                <motion.button
                  onClick={() => navigate("/rh/jobs/create")}
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "8px 20px", borderRadius: 10, fontSize: 12, fontWeight: 700,
                    border: "none",
                    background: "linear-gradient(135deg, #4a1d96, #7c3aed)",
                    color: "#fff", cursor: "pointer",
                    boxShadow: "0 4px 14px rgba(74,29,150,0.30)", transition: "all 0.15s",
                  }}
                >
                  <Plus size={13} /> Create a job
                </motion.button>
              </div>
            </div>

            {/* KPI pills */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {[
                { label: `${counts.ALL} total`,    color: "#7c3aed", f: "ALL"    },
                { label: `${counts.open} open`,    color: "#16a34a", f: "open"   },
                { label: `${counts.closed} closed`,color: "#94a3b8", f: "closed" },
              ].map(({ label, color, f }) => (
                <motion.div
                  key={f}
                  whileHover={{ scale: 1.03, y: -1 }}
                  onClick={() => { setFilter(f as typeof filter); setPage(0); }}
                  style={{
                    display: "flex", alignItems: "center", gap: 7,
                    padding: "7px 14px", borderRadius: 999,
                    background: filter === f ? `${color}15` : "rgba(255,255,255,0.85)",
                    backdropFilter: "blur(8px)",
                    border: `1px solid ${filter === f ? color : "rgba(255,255,255,0.9)"}`,
                    fontSize: 12, fontWeight: 600,
                    color: filter === f ? color : "#475569",
                    boxShadow: "0 1px 4px rgba(90,40,160,0.08)", cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                >
                  <div style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
                  {label}
                </motion.div>
              ))}
            </div>
          </motion.div>

          {/* ── Error ── */}
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

          {/* ── Card principale ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            style={{
              background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
              borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)", overflow: "hidden",
              boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
            }}
          >
            {/* Card header */}
            <div style={{
              padding: "16px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div>
                <h2 style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0 }}>
                  {filter === "ALL" ? "All jobs" : filter === "open" ? "Open jobs" : "Closed jobs"}
                </h2>
                <p style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                  {loading ? "—" : `${filtered.length} result${filtered.length !== 1 ? "s" : ""}`}
                </p>
              </div>
              <Briefcase size={16} color="#7c3aed" style={{ opacity: 0.5 }} />
            </div>

            {/* Skeleton */}
            {loading && <JobSkeleton />}

            {/* Empty */}
            {!loading && !error && filtered.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", padding: "64px 0", gap: 14 }}>
                <div style={{
                  width: 56, height: 56, borderRadius: 16, background: "rgba(124,58,237,0.08)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <Briefcase size={24} color="#7c3aed" />
                </div>
                <p style={{ fontSize: 14, color: "#64748b", margin: 0 }}>No jobs in this category.</p>
                <motion.button
                  onClick={() => navigate("/rh/jobs/create")}
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "9px 20px", borderRadius: 10, fontSize: 12, fontWeight: 700,
                    border: "none", background: "linear-gradient(135deg, #4a1d96, #7c3aed)",
                    color: "#fff", cursor: "pointer", boxShadow: "0 4px 14px rgba(74,29,150,0.25)",
                  }}
                >
                  <Plus size={13} /> Create first job
                </motion.button>
              </div>
            )}

            {/* Job rows */}
            {!loading && !error && pageJobs.length > 0 && (
              <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                {pageJobs.map((job, i) => {
                  const isOpen   = job.status === "open";
                  const statusBg = isOpen ? "#f0fdf4" : "#f8fafc";
                  const statusColor  = isOpen ? "#16a34a" : "#94a3b8";
                  const statusBorder = isOpen ? "#bbf7d0" : "#e2e8f0";
                  const statusDot    = isOpen ? "#16a34a" : "#94a3b8";

                  return (
                    <motion.div
                      key={job.id}
                      initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                      className="job-row"
                      style={{
                        padding: "16px", borderRadius: 14,
                        background: "rgba(255,255,255,0.72)",
                        border: "1px solid rgba(255,255,255,0.85)",
                        backdropFilter: "blur(10px)",
                        display: "flex", alignItems: "flex-start", gap: 14,
                      }}
                    >
                      {/* Barre latérale statut */}
                      <div style={{ width: 4, alignSelf: "stretch", borderRadius: 3, background: statusDot, flexShrink: 0, minHeight: 40 }} />

                      {/* Icône job */}
                      <div style={{
                        width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                        background: "rgba(124,58,237,0.08)",
                        display: "flex", alignItems: "center", justifyContent: "center",
                      }}>
                        <Building2 size={16} color="#7c3aed" />
                      </div>

                      {/* Infos principales */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          <p style={{ fontSize: 14, fontWeight: 700, color: "#1c2a38", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {job.title}
                          </p>
                          {job.level && (
                            <span style={{
                              fontSize: 10, padding: "2px 8px", borderRadius: 5, fontWeight: 600,
                              background: "rgba(124,58,237,0.08)", color: "#7c3aed", border: "1px solid rgba(124,58,237,0.15)",
                              flexShrink: 0,
                            }}>{job.level}</span>
                          )}
                        </div>

                        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                          {job.department && (
                            <span style={{ fontSize: 11, color: "#94a3b8", display: "flex", alignItems: "center", gap: 3 }}>
                              <Briefcase size={10} /> {job.department}
                            </span>
                          )}
                          {job.location && (
                            <span style={{ fontSize: 11, color: "#94a3b8", display: "flex", alignItems: "center", gap: 3 }}>
                              <MapPin size={10} /> {job.location}
                            </span>
                          )}
                          {job.created_at && (
                            <span style={{ fontSize: 11, color: "#94a3b8", display: "flex", alignItems: "center", gap: 3 }}>
                              <Calendar size={10} /> {new Date(job.created_at).toLocaleDateString("en-US")}
                            </span>
                          )}
                        </div>

                        {/* Pipeline mini stats */}
                        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
                          {[
                            { label: `${job.pipeline.total} candidates`,     color: "#475569", bg: "rgba(71,85,105,0.08)"   },
                            { label: `${job.pipeline.preselectionnes} pre.`,  color: "#7c3aed", bg: "rgba(124,58,237,0.08)" },
                            { label: `${job.pipeline.acceptes} accepted`,    color: "#16a34a", bg: "rgba(22,163,74,0.08)"   },
                            { label: `${job.pipeline.rejetes} rejected`,     color: "#ef4444", bg: "rgba(239,68,68,0.08)"   },
                          ].map(({ label, color, bg }) => (
                            <span key={label} style={{
                              fontSize: 10, padding: "3px 9px", borderRadius: 6, fontWeight: 600,
                              background: bg, color, border: `1px solid ${color}20`,
                            }}>{label}</span>
                          ))}
                          {job.manager && (
                            <span style={{
                              fontSize: 10, padding: "3px 9px", borderRadius: 6, fontWeight: 600,
                              background: "rgba(8,145,178,0.08)", color: "#0891b2", border: "1px solid rgba(8,145,178,0.15)",
                            }}>👤 {job.manager.email}</span>
                          )}
                        </div>
                      </div>

                      {/* Actions droite */}
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8, flexShrink: 0 }}>
                        {/* Badge statut */}
                        <span style={{
                          padding: "4px 12px", fontSize: 10, fontWeight: 700,
                          letterSpacing: "0.06em", borderRadius: 8, whiteSpace: "nowrap",
                          background: statusBg, border: `1px solid ${statusBorder}`, color: statusColor,
                        }}>
                          {isOpen ? "OPEN" : "CLOSED"}
                        </span>

                        {/* Boutons action */}
                        <div style={{ display: "flex", gap: 6 }}>
                          {isOpen && (
                            <motion.button
                              whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                              onClick={() => setClosingJob(job)}
                              style={{
                                padding: "5px 12px", borderRadius: 7, fontSize: 10, fontWeight: 700,
                                border: "1px solid #fca5a5", background: "rgba(239,68,68,0.07)",
                                color: "#ef4444", cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
                                transition: "all 0.15s",
                              }}
                            >
                              <Lock size={9} /> Close
                            </motion.button>
                          )}
                          {isOpen && (
                            <motion.button
                              whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
                              onClick={() => navigate(`/rh/jobs/${job.id}`)}
                              style={{
                                padding: "5px 12px", borderRadius: 7, fontSize: 10, fontWeight: 700,
                                border: "1px solid rgba(124,58,237,0.25)", background: "rgba(124,58,237,0.07)",
                                color: "#7c3aed", cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
                                transition: "all 0.15s",
                              }}
                            >
                              View <ChevronRight size={9} />
                            </motion.button>
                          )}
                        </div>

                        {/* Closed indicator */}
                        {!isOpen && (
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <CheckCircle2 size={11} color="#94a3b8" />
                            <span style={{ fontSize: 10, color: "#94a3b8" }}>GDPR timer active</span>
                          </div>
                        )}
                      </div>
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
                  onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                  style={{
                    padding: "6px 14px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.7)", background: "rgba(255,255,255,0.7)",
                    color: "#64748b", cursor: page === 0 ? "not-allowed" : "pointer",
                    opacity: page === 0 ? 0.35 : 1,
                  }}
                >← Previous</button>

                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  {Array.from({ length: totalPages }).map((_, i) => (
                    <button key={i} onClick={() => setPage(i)} style={{
                      width: 30, height: 30, borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
                      border: i === page ? "1px solid #7c3aed" : "1px solid rgba(255,255,255,0.7)",
                      background: i === page ? "rgba(124,58,237,0.12)" : "rgba(255,255,255,0.6)",
                      color: i === page ? "#7c3aed" : "#64748b",
                    }}>{i + 1}</button>
                  ))}
                </div>

                <button
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}
                  style={{
                    padding: "6px 14px", borderRadius: 8, fontSize: 11, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.7)", background: "rgba(255,255,255,0.7)",
                    color: "#64748b", cursor: page >= totalPages - 1 ? "not-allowed" : "pointer",
                    opacity: page >= totalPages - 1 ? 0.35 : 1,
                  }}
                >Next →</button>
              </div>
            )}
          </motion.div>
        </div>
      </div>

      {/* Confirm close modal */}
      <AnimatePresence>
        {closingJob && (
          <ConfirmClose
            job={closingJob}
            onConfirm={handleClose}
            onCancel={() => setClosingJob(null)}
            loading={closeLoading}
          />
        )}
      </AnimatePresence>
    </>
  );
}