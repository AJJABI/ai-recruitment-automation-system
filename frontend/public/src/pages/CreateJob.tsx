/**
 * CreateJob.tsx — Page création d'un nouveau job (espace RH)
 * Thème identique : sidebar floating-pill violette, fond wave, glassmorphism
 * POST /jobs/ → FastAPI direct (pas de n8n)
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, X, ChevronRight, AlertCircle,
  CheckCircle2, Loader2, Building2, MapPin, Calendar,
  FileText, Layers, Zap, UserCheck,
} from "lucide-react";
import RHSidebar from "./RHSidebar";
import logoImg from "../assets/logoo.png";
import bgWave  from "../assets/imagee.png";

// ─── Constants ────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";


const LEVELS   = ["Junior", "Mid", "Senior"];
const PIPELINE = [
  { value: "SEMI_AUTO", label: "Semi-Auto", desc: "HR gets reminder 48h — never auto-accept" },
  { value: "AUTO",      label: "Auto",      desc: "Agent decides alone" },
];

// ─── Auth helpers ─────────────────────────────────────────────────────────────

function getToken(): string | null { return localStorage.getItem("access_token"); }
function authHeaders() {
  const t = getToken();
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

// ─── Types ────────────────────────────────────────────────────────────────────

interface ManagerOption { id: number; email: string; full_name?: string; }
interface SkillsJson { coding: string[]; platform: string[]; mixed: string[]; }

// ─── Tag Input ────────────────────────────────────────────────────────────────

function TagInput({
  tags, onChange, placeholder, color,
}: {
  tags: string[]; onChange: (t: string[]) => void;
  placeholder: string; color: string;
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const add = () => {
    const v = input.trim();
    if (v && !tags.includes(v)) { onChange([...tags, v]); }
    setInput("");
  };

  const remove = (tag: string) => onChange(tags.filter(t => t !== tag));

  return (
    <div
      onClick={() => inputRef.current?.focus()}
      style={{
        display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center",
        padding: "8px 12px", borderRadius: 10, minHeight: 44,
        background: "rgba(255,255,255,0.7)", border: "1px solid rgba(255,255,255,0.9)",
        cursor: "text", backdropFilter: "blur(8px)",
        boxShadow: "inset 0 1px 3px rgba(0,0,0,0.04)",
      }}
    >
      {tags.map(tag => (
        <motion.span
          key={tag}
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1,   opacity: 1 }}
          exit   ={{ scale: 0.7, opacity: 0 }}
          style={{
            display: "flex", alignItems: "center", gap: 4,
            padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
            background: `${color}15`, color, border: `1px solid ${color}30`,
          }}
        >
          {tag}
          <X size={10} style={{ cursor: "pointer", opacity: 0.7 }} onClick={e => { e.stopPropagation(); remove(tag); }} />
        </motion.span>
      ))}
      <input
        ref={inputRef}
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } if (e.key === "Backspace" && !input && tags.length) { remove(tags[tags.length - 1]); } }}
        onBlur={add}
        placeholder={tags.length === 0 ? placeholder : ""}
        style={{
          border: "none", outline: "none", background: "transparent",
          fontSize: 12, color: "#1c2a38", minWidth: 120, flex: 1,
        }}
      />
    </div>
  );
}

// ─── Section Card ─────────────────────────────────────────────────────────────

function Section({ icon: Icon, title, color, children, delay = 0 }: {
  icon: React.ElementType; title: string; color: string;
  children: React.ReactNode; delay?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      style={{
        background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
        borderRadius: 18, border: "1px solid rgba(255,255,255,0.9)", overflow: "hidden",
        boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
      }}
    >
      {/* Header */}
      <div style={{
        padding: "14px 20px", borderBottom: "1px solid rgba(240,235,255,0.7)",
        display: "flex", alignItems: "center", gap: 10,
        background: "rgba(255,255,255,0.5)",
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 10,
          background: `${color}15`,
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
          <Icon size={15} color={color} />
        </div>
        <h3 style={{ fontSize: 13, fontWeight: 700, color: "#1c2a38", margin: 0 }}>{title}</h3>
      </div>
      <div style={{ padding: "18px 20px" }}>{children}</div>
    </motion.div>
  );
}

// ─── Form Field ───────────────────────────────────────────────────────────────

function Field({ label, required, children, hint }: {
  label: string; required?: boolean; children: React.ReactNode; hint?: string;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <label style={{ fontSize: 11, fontWeight: 700, color: "#475569", letterSpacing: "0.06em", textTransform: "uppercase" }}>
        {label} {required && <span style={{ color: "#ef4444" }}>*</span>}
      </label>
      {children}
      {hint && <p style={{ fontSize: 10, color: "#94a3b8", margin: 0 }}>{hint}</p>}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "10px 14px", borderRadius: 10, fontSize: 13, color: "#1c2a38",
  background: "rgba(255,255,255,0.7)", border: "1px solid rgba(255,255,255,0.9)",
  outline: "none", backdropFilter: "blur(8px)",
  boxShadow: "inset 0 1px 3px rgba(0,0,0,0.04)",
  transition: "border-color 0.15s, box-shadow 0.15s",
  width: "100%", boxSizing: "border-box" as const,
};

const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  resize: "vertical" as const,
  minHeight: 100,
  fontFamily: "inherit",
  lineHeight: 1.6,
};

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function CreateJob() {
  const [, navigate] = useLocation();

  // Form state
  const [title,          setTitle]          = useState("");
  const [company,        setCompany]        = useState("AI Recruitment System");
  const [department,     setDepartment]     = useState("");
  const [location,       setLocation]       = useState("Bizerte - Tunisia");
  const [level,          setLevel]          = useState("Mid");
  const [dateExpiration, setDateExpiration] = useState("");
  const [description,    setDescription]    = useState("");
  const [skillsRequired, setSkillsRequired] = useState("");
  const [skillsJson,     setSkillsJson]     = useState<SkillsJson>({ coding: [], platform: [], mixed: [] });
  const [bonusSkills,    setBonusSkills]    = useState<string[]>([]);
  const [managerId,      setManagerId]      = useState<number | null>(null);

  // UI state
  const [managers,     setManagers]     = useState<ManagerOption[]>([]);
  const [submitting,   setSubmitting]   = useState(false);
  const [error,        setError]        = useState<string | null>(null);
  const [success,      setSuccess]      = useState(false);

  // Redirect if no token
  useEffect(() => { if (!getToken()) navigate("/"); }, [navigate]);

  // Load managers
  useEffect(() => {
    fetch(`${API_BASE}/managers`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : [])
      .then((data: { id: number; email: string; full_name?: string }[]) => {
        setManagers(data.filter(m => m));
      })
      .catch(() => {});
  }, []);

  const handleSubmit = async () => {
    if (!title.trim())         { setError("Title is required."); return; }
    if (!description.trim())   { setError("Description is required."); return; }
    if (!skillsRequired.trim()){ setError("Required skills are required."); return; }
    if (!dateExpiration)       { setError("Expiration date is required."); return; }

    setSubmitting(true); setError(null);

    const payload: Record<string, unknown> = {
      title:           title.trim(),
      company:         company.trim()    || null,
      department:      department.trim() || null,
      location:        location.trim()   || null,
      level:           level,
      date_expiration: dateExpiration.split("T")[0],  // Format YYYY-MM-DD seulement
      description:     description.trim(),
      skills_required: skillsRequired.trim(),
      skills_json:     (skillsJson.coding.length || skillsJson.platform.length || skillsJson.mixed.length) ? skillsJson : null,
      bonus_skills:    bonusSkills.length ? bonusSkills : null,
     
      manager_id:      managerId,
    };

    try {
      const res = await fetch(`${API_BASE}/jobs/`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });

      if (res.status === 401) { localStorage.removeItem("access_token"); navigate("/"); return; }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Error ${res.status}`);
      }

      setSuccess(true);
      setTimeout(() => navigate("/mission-registry"), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  };

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  return (
    <>
      <style>{`
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        input:focus, textarea:focus, select:focus {
          border-color: rgba(74,29,150,0.35) !important;
          box-shadow: 0 0 0 3px rgba(74,29,150,0.08), inset 0 1px 3px rgba(0,0,0,0.04) !important;
        }
      `}</style>

      <RHSidebar />

      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{
          position: "absolute", inset: 0,
          background: "rgba(245,243,255,0.35)", pointerEvents: "none",
        }} />

        <div style={{
          position: "relative", zIndex: 1,
          padding: "28px 36px 64px",
          maxWidth: 900, margin: "0 auto",
        }}>

          {/* ── Header ── */}
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{ marginBottom: 28 }}
          >
            {/* Breadcrumb */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 16 }}>
              <span
                onClick={() => navigate("/mission-registry")}
                style={{ fontSize: 12, color: "#7c3aed", fontWeight: 600, cursor: "pointer" }}
              >Job Management</span>
              <ChevronRight size={13} color="#94a3b8" />
              <span style={{ fontSize: 12, color: "#94a3b8" }}>New job</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                
                <div>
                  <h1 style={{ fontSize: 26, fontWeight: 700, color: "#1c2a38", margin: 0, lineHeight: 1.1 }}>
                    Create a new job
                  </h1>
                  <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.18em", margin: "4px 0 0", textTransform: "uppercase" }}>
                    {dateLabel}
                  </p>
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", gap: 10 }}>
                <motion.button
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                  onClick={() => navigate("/mission-registry")}
                  style={{
                    padding: "9px 18px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                    border: "1px solid rgba(255,255,255,0.9)", background: "rgba(255,255,255,0.80)",
                    backdropFilter: "blur(8px)", color: "#64748b", cursor: "pointer",
                    boxShadow: "0 1px 6px rgba(90,40,160,0.08)", transition: "all 0.15s",
                  }}
                >Cancel</motion.button>

                <motion.button
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
                  onClick={handleSubmit}
                  disabled={submitting || success}
                  style={{
                    padding: "9px 22px", borderRadius: 10, fontSize: 12, fontWeight: 700,
                    border: "none",
                    background: success
                      ? "linear-gradient(135deg, #16a34a, #15803d)"
                      : "linear-gradient(135deg, #4a1d96, #7c3aed)",
                    color: "#fff", cursor: submitting || success ? "not-allowed" : "pointer",
                    display: "flex", alignItems: "center", gap: 7,
                    boxShadow: "0 4px 14px rgba(74,29,150,0.30)",
                    opacity: submitting ? 0.7 : 1, transition: "all 0.2s",
                  }}
                >
                  {submitting ? (
                    <><Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> Creating…</>
                  ) : success ? (
                    <><CheckCircle2 size={13} /> Created!</>
                  ) : (
                    <><Plus size={13} /> Create job</>
                  )}
                </motion.button>
              </div>
            </div>
          </motion.div>

          {/* ── Error banner ── */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                style={{
                  display: "flex", alignItems: "center", gap: 10,
                  marginBottom: 20, padding: "12px 16px", borderRadius: 12,
                  background: "#fef2f2", border: "1px solid #fca5a5",
                }}
              >
                <AlertCircle size={15} color="#ef4444" style={{ flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: "#991b1b", flex: 1 }}>{error}</span>
                <X size={13} color="#ef4444" style={{ cursor: "pointer" }} onClick={() => setError(null)} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── Sections ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* 1 — Informations générales */}
            <Section icon={Building2} title="General Information" color="#7c3aed" delay={0.05}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <Field label="Job Title" required>
                  <input
                    style={inputStyle}
                    placeholder="ex: Senior Full-Stack Developer"
                    value={title}
                    onChange={e => setTitle(e.target.value)}
                  />
                </Field>
                <Field label="Company">
                  <input
                    style={inputStyle}
                    placeholder="AI Recruitment System"
                    value={company}
                    disabled
                    onChange={e => setCompany(e.target.value)}
                  />
                </Field>
                <Field label="Department">
                  <input
                    style={inputStyle}
                    placeholder="ex: Engineering, Data, DevOps…"
                    value={department}
                    onChange={e => setDepartment(e.target.value)}
                  />
                </Field>
                <Field label="Location">
                  <div style={{ position: "relative" }}>
                    <MapPin size={13} color="#94a3b8" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
                    <input
                      style={{ ...inputStyle, paddingLeft: 32 }}
                      placeholder="Bizerte - Tunisia"
                      value={location}
                      disabled
                      onChange={e => setLocation(e.target.value)}
                    />
                  </div>
                </Field>
                <Field label="Level">
                  <select
                    style={{ ...inputStyle, cursor: "pointer" }}
                    value={level}
                    onChange={e => setLevel(e.target.value)}
                  >
                    {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
                  </select>
                </Field>
                <Field label="Expiration Date" required>
                  <div style={{ position: "relative" }}>
                    <Calendar size={13} color="#94a3b8" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} />
                    <input
                      type="datetime-local"
                      style={{ ...inputStyle, paddingLeft: 32 }}
                      value={dateExpiration}
                      onChange={e => setDateExpiration(e.target.value)}
                    />
                  </div>
                </Field>
              </div>
            </Section>

            {/* 2 — Description */}
            <Section icon={FileText} title="Description & Required Skills" color="#0891b2" delay={0.1}>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Field label="Job Description" required>
                  <textarea
                    style={textareaStyle}
                    placeholder="Describe the role, responsibilities, team context…"
                    value={description}
                    onChange={e => setDescription(e.target.value)}
                  />
                </Field>
                <Field label="Required Skills" required hint="Free text description — used by the matching agent">
                  <textarea
                    style={{ ...textareaStyle, minHeight: 80 }}
                    placeholder="ex: 3 years React experience, Python expertise, CI/CD experience…"
                    value={skillsRequired}
                    onChange={e => setSkillsRequired(e.target.value)}
                  />
                </Field>
              </div>
            </Section>

            {/* 3 — Skills structurés */}
            <Section icon={Layers} title="Structured Skills" color="#0d9488" delay={0.15}>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <Field label="Coding" hint="Languages & frameworks — Enter or comma to add">
                  <TagInput
                    tags={skillsJson.coding}
                    onChange={t => setSkillsJson(s => ({ ...s, coding: t }))}
                    placeholder="Python, React, TypeScript…"
                    color="#2563eb"
                  />
                </Field>
                <Field label="Platform / DevOps" hint="Tools, clouds, infrastructure">
                  <TagInput
                    tags={skillsJson.platform}
                    onChange={t => setSkillsJson(s => ({ ...s, platform: t }))}
                    placeholder="AWS, Docker, Kubernetes, n8n…"
                    color="#7c3aed"
                  />
                </Field>
                <Field label="Mixed / Soft skills">
                  <TagInput
                    tags={skillsJson.mixed}
                    onChange={t => setSkillsJson(s => ({ ...s, mixed: t }))}
                    placeholder="Agile, Communication, Leadership…"
                    color="#0891b2"
                  />
                </Field>
                <Field label="Bonus skills" hint="Optional skills — valued but not blocking">
                  <TagInput
                    tags={bonusSkills}
                    onChange={setBonusSkills}
                    placeholder="GraphQL, Terraform, Rust…"
                    color="#0d9488"
                  />
                </Field>
              </div>
            </Section>

            {/* 4 —  Manager */}
            <Section icon={Zap} title=" Assignment" color="#f59e0b" delay={0.2}>
              <div style={{ display: "grid", gap: 14 }}>

                
                {/* Manager */}
                <Field label="Assign a Manager" hint="Optional — can be assigned later">
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {/* Option "aucun" */}
                    <motion.div
                      whileHover={{ scale: 1.01 }}
                      onClick={() => setManagerId(null)}
                      style={{
                        padding: "10px 14px", borderRadius: 10, cursor: "pointer",
                        border: `1px solid ${managerId === null ? "#0d9488" : "rgba(255,255,255,0.9)"}`,
                        background: managerId === null ? "rgba(13,148,136,0.07)" : "rgba(255,255,255,0.7)",
                        backdropFilter: "blur(8px)", transition: "all 0.15s",
                        display: "flex", alignItems: "center", gap: 8,
                      }}
                    >
                      <UserCheck size={14} color={managerId === null ? "#0d9488" : "#94a3b8"} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: managerId === null ? "#0d9488" : "#64748b" }}>
                        No manager for now
                      </span>
                    </motion.div>

                    {/* Liste managers */}
                    <div style={{
                      maxHeight: 160, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6,
                    }}>
                      {managers.length === 0 ? (
                        <p style={{ fontSize: 11, color: "#94a3b8", padding: "8px 0" }}>No active managers</p>
                      ) : managers.map(m => (
                        <motion.div
                          key={m.id}
                          whileHover={{ scale: 1.01 }}
                          onClick={() => setManagerId(m.id)}
                          style={{
                            padding: "10px 14px", borderRadius: 10, cursor: "pointer",
                            border: `1px solid ${managerId === m.id ? "#7c3aed" : "rgba(255,255,255,0.9)"}`,
                            background: managerId === m.id ? "rgba(124,58,237,0.07)" : "rgba(255,255,255,0.7)",
                            backdropFilter: "blur(8px)", transition: "all 0.15s",
                            display: "flex", alignItems: "center", gap: 8,
                          }}
                        >
                          <div style={{
                            width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                            background: managerId === m.id ? "rgba(124,58,237,0.15)" : "rgba(100,116,139,0.10)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            fontSize: 11, fontWeight: 700,
                            color: managerId === m.id ? "#7c3aed" : "#64748b",
                          }}>
                            {(m.full_name || m.email).charAt(0).toUpperCase()}
                          </div>
                          <div style={{ minWidth: 0 }}>
                            <p style={{ fontSize: 12, fontWeight: 600, color: managerId === m.id ? "#7c3aed" : "#1c2a38", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {m.full_name || m.email}
                            </p>
                            {m.full_name && (
                              <p style={{ fontSize: 10, color: "#94a3b8", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.email}</p>
                            )}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                </Field>
              </div>
            </Section>

          </div>

          {/* ── Bottom action bar ── */}
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
            style={{
              marginTop: 24, display: "flex", justifyContent: "flex-end", gap: 10,
            }}
          >
            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={() => navigate("/mission-registry")}
              style={{
                padding: "10px 22px", borderRadius: 10, fontSize: 12, fontWeight: 600,
                border: "1px solid rgba(255,255,255,0.9)", background: "rgba(255,255,255,0.80)",
                backdropFilter: "blur(8px)", color: "#64748b", cursor: "pointer",
                boxShadow: "0 1px 6px rgba(90,40,160,0.08)",
              }}
            >Cancel</motion.button>

            <motion.button
              whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
              onClick={handleSubmit}
              disabled={submitting || success}
              style={{
                padding: "10px 28px", borderRadius: 10, fontSize: 12, fontWeight: 700,
                border: "none",
                background: success
                  ? "linear-gradient(135deg, #16a34a, #15803d)"
                  : "linear-gradient(135deg, #4a1d96, #7c3aed)",
                color: "#fff", cursor: submitting || success ? "not-allowed" : "pointer",
                display: "flex", alignItems: "center", gap: 7,
                boxShadow: "0 4px 14px rgba(74,29,150,0.30)",
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? (
                <><Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> Creating…</>
              ) : success ? (
                <><CheckCircle2 size={13} /> Job created successfully!</>
              ) : (
                <><Plus size={13} /> Create job</>
              )}
            </motion.button>
          </motion.div>

        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </>
  );
}