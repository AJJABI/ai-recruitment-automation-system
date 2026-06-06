/**
 * RHManagers.tsx — RH Space · Gestion des Managers
 *
 * Sections :
 *   1. KPIs  — total managers / actifs / en attente / jobs non assignés
 *   2. Liste  — tableau managers avec statut, jobs count, accordéon jobs
 *   3. Modal  — inviter un nouveau manager (email only → n8n)
 *   4. Modal  — assigner des jobs à un manager
 */

import { useState, useEffect, useRef } from "react";
import { Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users, UserCheck, Clock, Briefcase, Plus, Search,
  ChevronDown, ChevronRight, X, Mail, CheckCircle2,
  AlertCircle, Trash2, ExternalLink, UserPlus,
} from "lucide-react";
import { API_BASE, authHeaders } from "./managerShared";
import bgWave from "../assets/imagee.png";
import logoImg from "../assets/logoo.png";
import RHSidebar from "./RHSidebar";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ManagerJob {
  id:         number;
  title:      string;
  department: string | null;
  location:   string | null;
  status:     "open" | "closed";
  pipeline?:  {
    total:      number;
    acceptes:   number;
    rejetes:    number;
    en_attente: number;
  };
}

interface Manager {
  id:         number;
  email:      string;
  is_active:  boolean;
  full_name:  string;
  poste:      string;
  created_at: string | null;
  jobs_count: number;
  jobs:       ManagerJob[];
}

interface AllJob {
  id:         number;
  title:      string;
  department: string | null;
  location:   string | null;
  status:     "open" | "closed";
  manager:    { id: number; email: string } | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function relTime(iso: string | null) {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "just now";
  if (m < 60) return `${m}min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function initials(email: string, fullName: string) {
  if (fullName?.trim()) {
    return fullName.trim().split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

const AVATAR_COLORS = ["#4a1d96","#1e3a6e","#0e7490","#065f46","#7c2d12","#1d4ed8"];

function Avatar({ email, fullName, index, size = 38 }: { email: string; fullName: string; index: number; size?: number }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", flexShrink: 0,
      background: AVATAR_COLORS[index % AVATAR_COLORS.length],
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.32, fontWeight: 700, color: "#fff", letterSpacing: "0.02em",
    }}>
      {initials(email, fullName)}
    </div>
  );
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

function Card({ children, delay = 0, style }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, type: "spring", stiffness: 300, damping: 28 }}
      style={{
        background: "rgba(255,255,255,0.88)",
        backdropFilter: "blur(20px)",
        borderRadius: 20,
        border: "1px solid rgba(200,185,255,0.25)",
        boxShadow: "0 4px 24px rgba(90,40,160,0.08)",
        overflow: "hidden",
        ...style,
      }}
    >
      {children}
    </motion.div>
  );
}

function Toast({ msg, type, onDone }: { msg: string; type: "ok" | "err"; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 3500); return () => clearTimeout(t); }, []);
  return (
    <div style={{
      position: "fixed", bottom: 28, right: 28, zIndex: 300,
      padding: "12px 20px", borderRadius: 12, fontSize: 13, fontWeight: 600,
      background: type === "ok" ? "#f0fdf4" : "#fef2f2",
      border: `1px solid ${type === "ok" ? "#86efac" : "#fca5a5"}`,
      color: type === "ok" ? "#16a34a" : "#dc2626",
      boxShadow: "0 4px 20px rgba(0,0,0,0.12)",
      display: "flex", alignItems: "center", gap: 8,
    }}>
      {type === "ok" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
      {msg}
    </div>
  );
}

// ─── Modal — Inviter un Manager ───────────────────────────────────────────────

function InviteModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: (email: string) => void }) {
  const [email,   setEmail]   = useState("");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/managers/invite`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Error sending invitation");
      onSuccess(email.trim());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 200,
      background: "rgba(15,10,40,0.55)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ type: "spring", stiffness: 380, damping: 28 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 20, padding: "32px 36px",
          width: 440, boxShadow: "0 24px 64px rgba(60,12,120,0.18)",
          border: "1px solid rgba(200,185,255,0.3)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 24 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(124,58,237,0.1)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <UserPlus size={18} color="#7c3aed" />
              </div>
              <h2 style={{ fontSize: 17, fontWeight: 800, color: "#1c2a38", margin: 0 }}>Invite a Manager</h2>
            </div>
            <p style={{ fontSize: 12, color: "#64748b", margin: 0, lineHeight: 1.5 }}>
              An email will be sent to the manager to create their password.
              You will never see their password.
            </p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", padding: 4 }}>
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 8, letterSpacing: "0.04em" }}>
            EMAIL ADDRESS
          </label>
          <div style={{ position: "relative", marginBottom: error ? 8 : 24 }}>
            <Mail size={15} color="#94a3b8" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="manager@company.com"
              autoFocus
              required
              style={{
                width: "100%", padding: "10px 12px 10px 36px",
                borderRadius: 10, border: `1.5px solid ${error ? "#fca5a5" : "#e2e8f0"}`,
                fontSize: 14, outline: "none", boxSizing: "border-box",
                transition: "border-color 0.15s",
                background: "#f8fafc", color: "#1c2a38",
              }}
              onFocus={e => (e.target.style.borderColor = "#7c3aed")}
              onBlur={e => (e.target.style.borderColor = error ? "#fca5a5" : "#e2e8f0")}
            />
          </div>

          {error && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
              borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5",
              fontSize: 12, color: "#dc2626", marginBottom: 20,
            }}>
              <AlertCircle size={13} />
              {error}
            </div>
          )}

          {/* Info box */}
          <div style={{
            display: "flex", gap: 10, padding: "10px 12px",
            borderRadius: 10, background: "rgba(124,58,237,0.05)",
            border: "1px solid rgba(124,58,237,0.15)",
            marginBottom: 24,
          }}>
            <div style={{ flexShrink: 0, marginTop: 2 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#7c3aed" }} />
            </div>
            <p style={{ fontSize: 12, color: "#5b4ecf", margin: 0, lineHeight: 1.55 }}>
              The manager will receive an activation link valid for <strong>24h</strong>. Their account will appear
              in <strong>Pending</strong> status until activation.
            </p>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                flex: 1, padding: "10px", borderRadius: 10, fontSize: 13, fontWeight: 600,
                border: "1px solid #e2e8f0", background: "#f8fafc", color: "#64748b", cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !email.trim()}
              style={{
                flex: 2, padding: "10px", borderRadius: 10, fontSize: 13, fontWeight: 700,
                border: "none", cursor: loading ? "not-allowed" : "pointer",
                background: loading || !email.trim() ? "#e2e8f0" : "linear-gradient(135deg,#7c3aed,#4a1d96)",
                color: loading || !email.trim() ? "#94a3b8" : "#fff",
                transition: "all 0.15s", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              }}
            >
              {loading ? (
                <>
                  <div style={{ width: 14, height: 14, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 0.7s linear infinite" }} />
                  Sending…
                </>
              ) : (
                <><Mail size={14} /> Send invitation</>
              )}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

// ─── Modal — Assigner des Jobs ────────────────────────────────────────────────

function AssignJobsModal({
  manager, allJobs, onClose, onSuccess,
}: {
  manager:    Manager;
  allJobs:    AllJob[];
  onClose:    () => void;
  onSuccess:  () => void;
}) {
  // Jobs open et non assignés (ou déjà assignés à CE manager)
  const available = allJobs.filter(j =>
    j.status === "open" && (j.manager === null || j.manager.id === manager.id)
  );

  const alreadyAssigned = new Set(manager.jobs.map(j => j.id));
  const [selected, setSelected]   = useState<Set<number>>(new Set(alreadyAssigned));
  const [loading,  setLoading]    = useState(false);
  const [error,    setError]      = useState("");
  const [query,    setQuery]      = useState("");

  const filtered = available.filter(j =>
    j.title.toLowerCase().includes(query.toLowerCase()) ||
    (j.department ?? "").toLowerCase().includes(query.toLowerCase())
  );

  function toggle(jobId: number) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  }

  async function handleSave() {
    setLoading(true);
    setError("");
    try {
      // Jobs à assigner (dans selected mais pas encore assignés)
      const toAssign = [...selected].filter(id => !alreadyAssigned.has(id));
      // Jobs à désassigner (étaient assignés mais retirés de selected)
      const toUnassign = [...alreadyAssigned].filter(id => !selected.has(id));

      for (const jobId of toAssign) {
        const res = await fetch(`${API_BASE}/managers/${manager.id}/jobs`, {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ job_id: jobId }),
        });
        if (!res.ok) {
          const d = await res.json();
          throw new Error(d.detail ?? "Assignment error");
        }
      }

      for (const jobId of toUnassign) {
        const res = await fetch(`${API_BASE}/managers/${manager.id}/jobs/${jobId}`, {
          method: "DELETE",
          headers: authHeaders(),
        });
        if (!res.ok) {
          const d = await res.json();
          throw new Error(d.detail ?? "Unassignment error");
        }
      }

      onSuccess();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const changed = (
    [...selected].some(id => !alreadyAssigned.has(id)) ||
    [...alreadyAssigned].some(id => !selected.has(id))
  );

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 200,
      background: "rgba(15,10,40,0.55)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }} onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ type: "spring", stiffness: 380, damping: 28 }}
        onClick={e => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 20, width: 500,
          boxShadow: "0 24px 64px rgba(60,12,120,0.18)",
          border: "1px solid rgba(200,185,255,0.3)",
          display: "flex", flexDirection: "column", maxHeight: "80vh",
        }}
      >
        {/* Header */}
        <div style={{ padding: "24px 28px 16px", borderBottom: "1px solid #f1f5f9" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 10, background: "rgba(124,58,237,0.1)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Briefcase size={17} color="#7c3aed" />
              </div>
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 800, color: "#1c2a38", margin: 0 }}>Assign jobs</h2>
                <p style={{ fontSize: 12, color: "#64748b", margin: "2px 0 0" }}>
                  {manager.full_name || manager.email}
                </p>
              </div>
            </div>
            <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8" }}>
              <X size={18} />
            </button>
          </div>
          {/* Search */}
          <div style={{ position: "relative", marginTop: 14 }}>
            <Search size={13} color="#94a3b8" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search a job…"
              style={{
                width: "100%", padding: "8px 10px 8px 30px", borderRadius: 8,
                border: "1px solid #e2e8f0", fontSize: 13, outline: "none",
                background: "#f8fafc", color: "#1c2a38", boxSizing: "border-box",
              }}
            />
          </div>
        </div>

        {/* Job list */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
          {filtered.length === 0 ? (
            <div style={{ textAlign: "center", padding: "32px 0", color: "#94a3b8", fontSize: 13 }}>
              No open jobs available
            </div>
          ) : filtered.map(job => {
            const checked = selected.has(job.id);
            return (
              <div
                key={job.id}
                onClick={() => toggle(job.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "10px 12px", borderRadius: 10, cursor: "pointer",
                  marginBottom: 4,
                  background: checked ? "rgba(124,58,237,0.06)" : "transparent",
                  border: `1px solid ${checked ? "rgba(124,58,237,0.2)" : "transparent"}`,
                  transition: "all 0.12s",
                }}
              >
                {/* Checkbox */}
                <div style={{
                  width: 18, height: 18, borderRadius: 5, flexShrink: 0,
                  border: `2px solid ${checked ? "#7c3aed" : "#d1d5db"}`,
                  background: checked ? "#7c3aed" : "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "all 0.12s",
                }}>
                  {checked && <svg width="10" height="8" viewBox="0 0 10 8" fill="none"><path d="M1 4L3.5 6.5L9 1" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#1c2a38", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{job.title}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 1 }}>
                    {[job.department, job.location].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
                  background: "rgba(16,185,129,0.1)", color: "#10b981",
                }}>
                  Open
                </span>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ padding: "14px 28px 24px", borderTop: "1px solid #f1f5f9" }}>
          {error && (
            <div style={{
              display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
              borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5",
              fontSize: 12, color: "#dc2626", marginBottom: 12,
            }}>
              <AlertCircle size={13} />{error}
            </div>
          )}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 12, color: "#94a3b8" }}>
              {selected.size} job{selected.size > 1 ? "s" : ""} selected
            </span>
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={onClose} style={{ padding: "8px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600, border: "1px solid #e2e8f0", background: "#f8fafc", color: "#64748b", cursor: "pointer" }}>
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={loading || !changed}
                style={{
                  padding: "8px 22px", borderRadius: 10, fontSize: 13, fontWeight: 700,
                  border: "none", cursor: loading || !changed ? "not-allowed" : "pointer",
                  background: loading || !changed ? "#e2e8f0" : "linear-gradient(135deg,#7c3aed,#4a1d96)",
                  color: loading || !changed ? "#94a3b8" : "#fff",
                  display: "flex", alignItems: "center", gap: 8,
                }}
              >
                {loading
                  ? <><div style={{ width: 13, height: 13, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 0.7s linear infinite" }} />Saving…</>
                  : "Save"
                }
              </button>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

// ─── Manager Row (avec accordéon jobs) ───────────────────────────────────────

function ManagerRow({
  manager, index, allJobs,
  onInvalidate,
}: {
  manager:      Manager;
  index:        number;
  allJobs:      AllJob[];
  onInvalidate: () => void;
}) {
  const [open,       setOpen]       = useState(false);
  const [assigning,  setAssigning]  = useState(false);
  const [toast,      setToast]      = useState<{ msg: string; type: "ok"|"err" } | null>(null);

  async function handleUnassign(jobId: number, jobTitle: string) {
    try {
      const res = await fetch(`${API_BASE}/managers/${manager.id}/jobs/${jobId}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail);
      }
      setToast({ msg: `Job « ${jobTitle} » unassigned`, type: "ok" });
      onInvalidate();
    } catch (err: any) {
      setToast({ msg: err.message, type: "err" });
    }
  }

  return (
    <>
      {toast && <Toast msg={toast.msg} type={toast.type} onDone={() => setToast(null)} />}
      <AnimatePresence>
        {assigning && (
          <AssignJobsModal
            manager={manager}
            allJobs={allJobs}
            onClose={() => setAssigning(false)}
            onSuccess={() => {
              setAssigning(false);
              setToast({ msg: "Jobs updated", type: "ok" });
              onInvalidate();
            }}
          />
        )}
      </AnimatePresence>

      {/* Main row */}
      <motion.tr
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ delay: index * 0.04 }}
        style={{ borderBottom: open ? "none" : "1px solid rgba(240,235,255,0.6)", cursor: "pointer" }}
        onMouseEnter={e => { if (!open) e.currentTarget.style.background = "rgba(124,58,237,0.02)"; }}
        onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
        onClick={() => setOpen(o => !o)}
      >
        {/* Manager info */}
        <td style={{ padding: "14px 24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Avatar email={manager.email} fullName={manager.full_name} index={index} />
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38" }}>
                {manager.full_name || manager.email.split("@")[0]}
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>{manager.email}</div>
            </div>
          </div>
        </td>

        {/* Status */}
        <td style={{ padding: "14px 16px" }}>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            fontSize: 11, fontWeight: 700, padding: "4px 10px", borderRadius: 999,
            background: manager.is_active ? "rgba(16,185,129,0.1)" : "rgba(245,158,11,0.1)",
            color: manager.is_active ? "#10b981" : "#f59e0b",
          }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />
            {manager.is_active ? "Active" : "Pending"}
          </span>
        </td>

        {/* Jobs count */}
        <td style={{ padding: "14px 16px", textAlign: "center" }}>
          <span style={{
            fontSize: 14, fontWeight: 800,
            color: manager.jobs_count > 0 ? "#7c3aed" : "#cbd5e1",
          }}>
            {manager.jobs_count}
          </span>
        </td>

        {/* Invited */}
        <td style={{ padding: "14px 16px", fontSize: 12, color: "#94a3b8" }}>
          {relTime(manager.created_at)}
        </td>

        {/* Actions */}
        <td style={{ padding: "14px 24px" }} onClick={e => e.stopPropagation()}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={() => setAssigning(true)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600,
                border: "1px solid rgba(124,58,237,0.25)",
                background: "rgba(124,58,237,0.06)", color: "#7c3aed", cursor: "pointer",
                transition: "all 0.12s",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "rgba(124,58,237,0.12)")}
              onMouseLeave={e => (e.currentTarget.style.background = "rgba(124,58,237,0.06)")}
            >
              <Briefcase size={13} />
              Assign jobs
            </button>
            <div style={{ display: "flex", alignItems: "center", gap: 4, color: "#94a3b8" }} onClick={() => setOpen(o => !o)}>
              <motion.div animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.2 }}>
                <ChevronRight size={16} />
              </motion.div>
            </div>
          </div>
        </td>
      </motion.tr>

      {/* Accordéon — jobs assignés */}
      <AnimatePresence>
        {open && (
          <motion.tr
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ borderBottom: "1px solid rgba(240,235,255,0.6)" }}
          >
            <td colSpan={5} style={{ padding: 0 }}>
              <motion.div
                initial={{ height: 0 }}
                animate={{ height: "auto" }}
                exit={{ height: 0 }}
                style={{ overflow: "hidden", background: "rgba(124,58,237,0.02)" }}
              >
                <div style={{ padding: "12px 24px 16px 80px" }}>
                  {manager.jobs.length === 0 ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#94a3b8", fontSize: 13, padding: "8px 0" }}>
                      <Briefcase size={15} />
                      No jobs assigned — click "Assign jobs"
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {manager.jobs.map(job => (
                        <div key={job.id} style={{
                          display: "flex", alignItems: "center", gap: 12,
                          padding: "10px 14px", borderRadius: 10,
                          background: "#fff", border: "1px solid rgba(200,185,255,0.2)",
                        }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: "#1c2a38" }}>{job.title}</div>
                            <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
                              {[job.department, job.location].filter(Boolean).join(" · ")}
                            </div>
                          </div>
                          {/* Pipeline mini */}
                          {job.pipeline && (
                            <div style={{ display: "flex", gap: 10, fontSize: 11, color: "#64748b" }}>
                              <span style={{ color: "#64748b" }}>{job.pipeline.total} candidates</span>
                              <span style={{ color: "#10b981", fontWeight: 700 }}>✓ {job.pipeline.acceptes}</span>
                              <span style={{ color: "#ef4444", fontWeight: 700 }}>✗ {job.pipeline.rejetes}</span>
                            </div>
                          )}
                          <span style={{
                            fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999,
                            background: job.status === "open" ? "rgba(16,185,129,0.1)" : "rgba(100,116,139,0.1)",
                            color: job.status === "open" ? "#10b981" : "#64748b",
                          }}>
                            {job.status === "open" ? "Open" : "Closed"}
                          </span>
                          {/* View pipeline */}
                          <Link href={`/rh/pipeline/${job.id}`} style={{ textDecoration: "none" }}>
                            <div style={{
                              display: "flex", alignItems: "center", gap: 4,
                              fontSize: 11, fontWeight: 700, color: "#7c3aed", cursor: "pointer",
                              padding: "4px 8px", borderRadius: 6, border: "1px solid rgba(124,58,237,0.2)",
                            }}>
                              <ExternalLink size={11} /> Pipeline
                            </div>
                          </Link>
                          {/* Unassign */}
                          <button
                            onClick={() => handleUnassign(job.id, job.title)}
                            style={{
                              background: "none", border: "none", cursor: "pointer",
                              color: "#cbd5e1", padding: 4, borderRadius: 6, display: "flex",
                              transition: "color 0.12s",
                            }}
                            title="Unassign this job"
                            onMouseEnter={e => (e.currentTarget.style.color = "#ef4444")}
                            onMouseLeave={e => (e.currentTarget.style.color = "#cbd5e1")}
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            </td>
          </motion.tr>
        )}
      </AnimatePresence>
    </>
  );
}

// ─── KPI Cards ────────────────────────────────────────────────────────────────

function KPICards({ managers, allJobs, loading }: { managers: Manager[]; allJobs: AllJob[]; loading: boolean }) {
  const total       = managers.length;
  const active      = managers.filter(m => m.is_active).length;
  const pending     = managers.filter(m => !m.is_active).length;
  const unassigned  = allJobs.filter(j => j.status === "open" && !j.manager).length;

  const kpis = [
    { label: "Total Managers",    value: total,     color: "#7c3aed", bg: "rgba(124,58,237,0.08)", icon: Users },
    { label: "Active",            value: active,    color: "#10b981", bg: "rgba(16,185,129,0.08)", icon: UserCheck },
    { label: "Pending",           value: pending,   color: "#f59e0b", bg: "rgba(245,158,11,0.08)", icon: Clock },
    { label: "Unassigned Jobs",   value: unassigned,color: "#ef4444", bg: "rgba(239,68,68,0.08)",  icon: Briefcase },
  ];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginLeft: 55, marginBottom: 20 }}>
      {kpis.map(({ label, value, color, bg, icon: Icon }, i) => (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05, type: "spring", stiffness: 300, damping: 28 }}
          style={{
            background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
            borderRadius: 18, border: "1px solid rgba(200,185,255,0.25)",
            boxShadow: "0 4px 16px rgba(90,40,160,0.07)",
            padding: "20px 24px", display: "flex", alignItems: "center", gap: 16,
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

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function RHManagers() {
  const [managers,  setManagers]  = useState<Manager[]>([]);
  const [allJobs,   setAllJobs]   = useState<AllJob[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [search,    setSearch]    = useState("");
  const [filter,    setFilter]    = useState<"all"|"active"|"pending">("all");
  const [inviting,  setInviting]  = useState(false);
  const [toast,     setToast]     = useState<{ msg: string; type: "ok"|"err" } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [mRes, jRes] = await Promise.all([
        fetch(`${API_BASE}/managers`,          { headers: authHeaders() }),
        fetch(`${API_BASE}/jobs/rh/dashboard`, { headers: authHeaders() }),
      ]);
      if (mRes.ok) setManagers(await mRes.json());
      if (jRes.ok) {
        const jobs = await jRes.json();
        setAllJobs(jobs.map((j: any) => ({
          id:         j.id,
          title:      j.title,
          department: j.department,
          location:   j.location,
          status:     j.status,
          manager:    j.manager,
        })));
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Filtered managers
  const displayed = managers.filter(m => {
    const matchSearch = (
      m.email.toLowerCase().includes(search.toLowerCase()) ||
      (m.full_name ?? "").toLowerCase().includes(search.toLowerCase())
    );
    const matchFilter =
      filter === "all"     ? true :
      filter === "active"  ? m.is_active :
      !m.is_active;
    return matchSearch && matchFilter;
  });

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes spin    { to{transform:rotate(360deg)} }
        @keyframes floatLogo { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
      `}</style>

      <RHSidebar />

      {/* Toast */}
      {toast && <Toast msg={toast.msg} type={toast.type} onDone={() => setToast(null)} />}

      {/* Modals */}
      <AnimatePresence>
        {inviting && (
          <InviteModal
            onClose={() => setInviting(false)}
            onSuccess={email => {
              setInviting(false);
              setToast({ msg: `Invitation sent to ${email}`, type: "ok" });
              load();
            }}
          />
        )}
      </AnimatePresence>

      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 48px", maxWidth: 1320, margin: "0 auto" }}>

          {/* TopBar */}
          <motion.div
            initial={{ opacity: 0, y: -16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 28 }}
            style={{
              marginLeft: 55, marginBottom: 28,
              background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
              borderRadius: 20, border: "1px solid rgba(200,185,255,0.25)",
              boxShadow: "0 4px 24px rgba(90,40,160,0.08)",
              padding: "16px 24px",
              display: "flex", alignItems: "center", justifyContent: "space-between",
              position: "relative", zIndex: 100, overflow: "visible",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <img src={logoImg} alt="logo" style={{ height: 36, animation: "floatLogo 3s ease-in-out infinite" }} />
              <div>
                <h1 style={{ fontSize: 20, fontWeight: 800, color: "#1c2a38", margin: 0, letterSpacing: "-0.02em" }}>
                  Managers Management
                </h1>
                <p style={{ fontSize: 11, color: "#94a3b8", margin: 0, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                  Invitations · Assignments · Access
                </p>
              </div>
            </div>
            {/* Invite button */}
            <motion.button
              whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
              onClick={() => setInviting(true)}
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "10px 20px", borderRadius: 12, fontSize: 13, fontWeight: 700,
                border: "none", cursor: "pointer",
                background: "linear-gradient(135deg,#7c3aed,#4a1d96)",
                color: "#fff", boxShadow: "0 4px 14px rgba(124,58,237,0.35)",
              }}
            >
              <UserPlus size={16} />
              Invite a Manager
            </motion.button>
          </motion.div>

          {/* KPIs */}
          <KPICards managers={managers} allJobs={allJobs} loading={loading} />

          {/* Table */}
          <div style={{ marginLeft: 55 }}>
            <Card delay={0.1} style={{ overflow: "visible" }}>
              {/* Table header */}
              <div style={{ padding: "20px 24px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <h2 style={{ fontSize: 16, fontWeight: 700, color: "#1c2a38", margin: 0 }}>Managers List</h2>
                  <p style={{ fontSize: 12, color: "#64748b", margin: "3px 0 0" }}>
                    {displayed.length} manager{displayed.length > 1 ? "s" : ""}
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {/* Search */}
                  <div style={{ position: "relative" }}>
                    <Search size={13} color="#94a3b8" style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
                    <input
                      value={search}
                      onChange={e => setSearch(e.target.value)}
                      placeholder="Search…"
                      style={{
                        padding: "7px 10px 7px 30px", borderRadius: 10, border: "1px solid #e2e8f0",
                        fontSize: 13, outline: "none", background: "#f8fafc", color: "#1c2a38", width: 200,
                      }}
                    />
                  </div>
                  {/* Filter pills */}
                  <div style={{ display: "flex", gap: 6 }}>
                    {(["all","active","pending"] as const).map(f => (
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
                        {f === "all" ? "All" : f === "active" ? "Active" : "Pending"}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid rgba(200,185,255,0.2)" }}>
                      <th style={{ padding: "10px 24px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Manager</th>
                      <th style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Status</th>
                      <th style={{ padding: "10px 16px", textAlign: "center", fontSize: 11, fontWeight: 700, color: "#7c3aed", letterSpacing: "0.08em", textTransform: "uppercase" }}>Jobs</th>
                      <th style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Invited</th>
                      <th style={{ padding: "10px 24px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      [1,2,3].map(i => (
                        <tr key={i} style={{ borderBottom: "1px solid rgba(240,235,255,0.6)" }}>
                          <td style={{ padding: "14px 24px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                              <Skel w={38} h={38} radius={999} />
                              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                <Skel w={120} h={13} />
                                <Skel w={160} h={11} />
                              </div>
                            </div>
                          </td>
                          <td style={{ padding: "14px 16px" }}><Skel w={70} h={22} radius={999} /></td>
                          <td style={{ padding: "14px 16px", textAlign: "center" }}><Skel w={24} h={18} /></td>
                          <td style={{ padding: "14px 16px" }}><Skel w={80} h={13} /></td>
                          <td style={{ padding: "14px 24px" }}><Skel w={110} h={30} radius={8} /></td>
                        </tr>
                      ))
                    ) : displayed.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ padding: "48px", textAlign: "center" }}>
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                            <Users size={32} color="#e2e8f0" />
                            <p style={{ fontSize: 13, color: "#94a3b8", margin: 0 }}>
                              {search || filter !== "all" ? "No managers found" : "No managers invited yet"}
                            </p>
                            {!search && filter === "all" && (
                              <button
                                onClick={() => setInviting(true)}
                                style={{
                                  display: "flex", alignItems: "center", gap: 6,
                                  padding: "8px 16px", borderRadius: 10, fontSize: 12, fontWeight: 700,
                                  background: "rgba(124,58,237,0.08)", color: "#7c3aed",
                                  border: "1px solid rgba(124,58,237,0.2)", cursor: "pointer",
                                }}
                              >
                                <Plus size={14} /> Invite first manager
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ) : displayed.map((manager, i) => (
                      <ManagerRow
                        key={manager.id}
                        manager={manager}
                        index={i}
                        allJobs={allJobs}
                        onInvalidate={load}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

        </div>
      </div>
    </>
  );
}