/**
 * ManagerAccount.tsx — /account
 * Thème Dashboard : sidebar pill violette flottante + background wave
 * Sections : Infos personnelles · Changer le mot de passe · Photo de profil
 */

import { useState, useEffect, useRef } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Briefcase, Users, MessageSquare,
  LogOut, User, Mail, Briefcase as BriefcaseIcon,
  Lock, Eye, EyeOff, Camera, CheckCircle2,
  AlertCircle, Save, X, Shield,
} from "lucide-react";
import logoImg from "../assets/logoo.png";
import bgWave  from "../assets/imagee.png";
import { API_BASE, authHeaders, getToken } from "./managerShared";

// ─── Design tokens ─────────────────────────────────────────────────────────────
const TEAL        = "#0d9488";
const TEAL_BG     = "rgba(13,148,136,0.08)";
const TEAL_BORDER = "rgba(13,148,136,0.2)";
const PURPLE      = "#7c3aed";
const TEXT_MAIN   = "#1c2a38";
const TEXT_SUB    = "#64748b";
const TEXT_MUTED  = "#94a3b8";

const AVATAR_PALETTE = [
  ["#4a1d96","#7c3aed"], ["#0d9488","#0e7490"],
  ["#0369a1","#2563eb"], ["#065f46","#059669"],
  ["#9a3412","#dc2626"], ["#92400e","#d97706"],
];

// ─── Nav ──────────────────────────────────────────────────────────────────────
const NAV = [
  { href: "/dashboard",        icon: LayoutDashboard, label: "Dashboard"  },
  { href: "/mission-registry", icon: Briefcase,       label: "Jobs"       },
  { href: "/candidates",       icon: Users,           label: "Candidates" },
  { href: "/interviews",       icon: MessageSquare,   label: "Interviews" },
];

// ─── Floating label ────────────────────────────────────────────────────────────
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
            width: 0, height: 0, borderTop: "5px solid transparent",
            borderBottom: "5px solid transparent", borderRight: "6px solid #3b0d8e",
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

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar() {
  const [location]   = useLocation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  return (
    <nav style={{
      position: "fixed", top: 140, left: 16, zIndex: 50,
      borderRadius: 30,
      background: "linear-gradient(180deg, #4a1d96 0%, #3b0d8e 55%, #2c0f70 100%)",
      boxShadow: "0 8px 32px rgba(60,12,120,0.30), 0 2px 8px rgba(0,0,0,0.15)",
      padding: "18px 8px",
      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      overflow: "visible", userSelect: "none", width: 58,
    }}>
      {NAV.map(({ href, icon: Icon, label }) => {
        const active  = location === href || location.startsWith(href + "/");
        const hovered = hoveredKey === href;
        return (
          <Link key={href} href={href} style={{ textDecoration: "none", position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey(href)}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.95 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              style={{
                width: 40, height: 40, margin: "0 auto", borderRadius: 13,
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "pointer",
                background: active ? "rgba(255,255,255,0.20)" : hovered ? "rgba(255,255,255,0.11)" : "transparent",
                transition: "background 0.15s", position: "relative",
              }}
            >
              {active && (
                <motion.div layoutId="activeBar" style={{
                  position: "absolute", left: -7, top: "50%", y: "-50%",
                  width: 3, height: 18, borderRadius: 3, background: "#fff",
                }} transition={{ type: "spring", stiffness: 500, damping: 30 }} />
              )}
              <Icon size={17} color={active ? "#ffffff" : "rgba(255,255,255,0.60)"} />
              <NavLabel label={label} visible={hovered} />
            </motion.div>
          </Link>
        );
      })}

      <div style={{ width: 32, height: 1, background: "rgba(255,255,255,0.14)", margin: "6px 0", flexShrink: 0 }} />

      {/* Logout */}
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

// ─── Card wrapper ──────────────────────────────────────────────────────────────
function Card({ children, delay = 0, style }: {
  children: React.ReactNode; delay?: number; style?: React.CSSProperties;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }}
      style={{
        background: "rgba(255,255,255,0.88)", backdropFilter: "blur(20px)",
        borderRadius: 20, border: "1px solid rgba(255,255,255,0.9)",
        boxShadow: "0 2px 16px rgba(90,40,160,0.07), 0 1px 4px rgba(0,0,0,0.05)",
        overflow: "hidden", ...style,
      }}
    >{children}</motion.div>
  );
}

function CardHeader({ title, subtitle, icon }: { title: string; subtitle?: string; icon: React.ReactNode }) {
  return (
    <div style={{
      padding: "18px 24px", borderBottom: "1px solid rgba(240,235,255,0.7)",
      display: "flex", alignItems: "center", gap: 12,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 11,
        background: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.18)",
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}>
        {icon}
      </div>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: TEXT_MAIN, margin: 0 }}>{title}</h2>
        {subtitle && <p style={{ fontSize: 12, color: TEXT_MUTED, marginTop: 2 }}>{subtitle}</p>}
      </div>
    </div>
  );
}

// ─── Input field ──────────────────────────────────────────────────────────────
function Field({
  label, value, onChange, type = "text", placeholder, disabled = false,
  icon, suffix,
}: {
  label: string; value: string; onChange?: (v: string) => void;
  type?: string; placeholder?: string; disabled?: boolean;
  icon?: React.ReactNode; suffix?: React.ReactNode;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <div>
      <label style={{
        fontSize: 10, fontWeight: 700, letterSpacing: "0.14em",
        textTransform: "uppercase", color: TEXT_MUTED, display: "block", marginBottom: 6,
      }}>{label}</label>
      <div style={{
        display: "flex", alignItems: "center",
        border: `1px solid ${focused ? TEAL_BORDER : "#e2e8f0"}`,
        borderRadius: 12, overflow: "hidden",
        background: disabled ? "rgba(248,250,252,0.6)" : "rgba(255,255,255,0.9)",
        transition: "border-color 0.15s",
        boxShadow: focused ? `0 0 0 3px rgba(13,148,136,0.08)` : "none",
      }}>
        {icon && (
          <div style={{ padding: "0 12px", color: focused ? TEAL : TEXT_MUTED, flexShrink: 0, display: "flex" }}>
            {icon}
          </div>
        )}
        <input
          type={type} value={value}
          onChange={e => onChange?.(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            flex: 1, border: "none", outline: "none", padding: "11px 14px",
            paddingLeft: icon ? 0 : 14,
            fontSize: 13, color: disabled ? TEXT_MUTED : TEXT_MAIN,
            background: "transparent", fontFamily: "inherit",
          }}
        />
        {suffix}
      </div>
    </div>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function Toast({ msg, type, onDone }: { msg: string; type: "ok" | "err"; onDone: () => void }) {
  useEffect(() => { const t = setTimeout(onDone, 3500); return () => clearTimeout(t); }, []);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 12, scale: 0.97 }}
      style={{
        position: "fixed", bottom: 28, left: "50%", transform: "translateX(-50%)",
        zIndex: 300, display: "flex", alignItems: "center", gap: 10,
        padding: "13px 22px", borderRadius: 14,
        background: type === "ok" ? "#f0fdf4" : "#fef2f2",
        border: `1px solid ${type === "ok" ? "#bbf7d0" : "#fca5a5"}`,
        boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
        fontSize: 13, fontWeight: 600,
        color: type === "ok" ? "#15803d" : "#991b1b",
        minWidth: 280,
      }}
    >
      {type === "ok"
        ? <CheckCircle2 size={16} style={{ flexShrink: 0 }} />
        : <AlertCircle size={16} style={{ flexShrink: 0 }} />}
      {msg}
    </motion.div>
  );
}

// ─── Avatar initials helper ────────────────────────────────────────────────────
function getInitials(name: string) {
  return name ? name.split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase() : "?";
}

function getGradient(name: string) {
  const idx = name.charCodeAt(0) % AVATAR_PALETTE.length;
  return `linear-gradient(135deg, ${AVATAR_PALETTE[idx][0]}, ${AVATAR_PALETTE[idx][1]})`;
}

// ─── Main component ────────────────────────────────────────────────────────────
export default function ManagerAccount() {
  const [, navigate] = useLocation();

  // Profile state
  const [fullName,  setFullName]  = useState("");
  const [email,     setEmail]     = useState("");
  const [poste,     setPoste]     = useState("");
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  const [savingInfo, setSavingInfo] = useState(false);

  // Password state
  const [currentPwd,  setCurrentPwd]  = useState("");
  const [newPwd,      setNewPwd]      = useState("");
  const [confirmPwd,  setConfirmPwd]  = useState("");
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew,     setShowNew]     = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [savingPwd,   setSavingPwd]   = useState(false);

  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const dateLabel = new Date().toLocaleDateString("en-US", {
    weekday: "long", day: "numeric", month: "long",
  }).toUpperCase();

  // ── Load profile ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!getToken()) { navigate("/login"); return; }

    fetch(`${API_BASE}/auth/me`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        setFullName(d.full_name ?? d.name ?? "");
        setEmail(d.email ?? "");
        setPoste(d.poste ?? "");

      })
      .catch(() => {});
  }, []);

  // ── Avatar file pick ──────────────────────────────────────────────────────────
  function handleAvatarPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => setAvatarPreview(ev.target?.result as string);
    reader.readAsDataURL(file);
  }

  // ── Save profile info ─────────────────────────────────────────────────────────
  async function handleSaveInfo() {
    setSavingInfo(true);
    try {
      const formData = new FormData();
      formData.append("full_name", fullName);
      formData.append("poste", poste);

      const res = await fetch(`${API_BASE}/auth/profile`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: formData,
      });

      if (!res.ok) throw new Error(`Error ${res.status}`);
      setToast({ msg: "Profile updated successfully!", type: "ok" });
    } catch {
      setToast({ msg: "Failed to update profile.", type: "err" });
    } finally {
      setSavingInfo(false);
    }
  }

  // ── Change password ───────────────────────────────────────────────────────────
  async function handleChangePwd() {
    if (!currentPwd || !newPwd || !confirmPwd) {
      setToast({ msg: "Please fill in all password fields.", type: "err" }); return;
    }
    if (newPwd !== confirmPwd) {
      setToast({ msg: "New passwords do not match.", type: "err" }); return;
    }
    if (newPwd.length < 8) {
      setToast({ msg: "Password must be at least 8 characters.", type: "err" }); return;
    }

    setSavingPwd(true);
    try {
      const res = await fetch(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ current_password: currentPwd, new_password: newPwd }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d?.detail ?? `Error ${res.status}`);
      }
      setCurrentPwd(""); setNewPwd(""); setConfirmPwd("");
      setToast({ msg: "Password changed successfully!", type: "ok" });
    } catch (e: unknown) {
      setToast({ msg: e instanceof Error ? e.message : "Failed to change password.", type: "err" });
    } finally {
      setSavingPwd(false);
    }
  }

  // ── Password strength ─────────────────────────────────────────────────────────
  function pwdStrength(pwd: string): { score: number; label: string; color: string } {
    if (!pwd) return { score: 0, label: "", color: "#e2e8f0" };
    let score = 0;
    if (pwd.length >= 8)  score++;
    if (pwd.length >= 12) score++;
    if (/[A-Z]/.test(pwd)) score++;
    if (/[0-9]/.test(pwd)) score++;
    if (/[^A-Za-z0-9]/.test(pwd)) score++;
    if (score <= 1) return { score, label: "Weak",   color: "#dc2626" };
    if (score <= 3) return { score, label: "Medium", color: "#d97706" };
    return { score, label: "Strong", color: "#16a34a" };
  }

  const strength = pwdStrength(newPwd);
  const displayAvatar = avatarPreview ?? null;
  const displayName   = fullName || "Manager";

  return (
    <>
      <style>{`
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes floatLogo { 0%,100%{transform:translateY(0px)} 50%{transform:translateY(-7px)} }
        @keyframes pulse-ring {
          0%   { transform: scale(1);    opacity: 0.6; }
          100% { transform: scale(1.35); opacity: 0; }
        }
      `}</style>

      <Sidebar />

      {/* ── Main — wave background ── */}
      <div style={{
        marginLeft: 62, minHeight: "100vh", position: "relative",
        backgroundImage: `url(${bgWave})`,
        backgroundSize: "cover", backgroundPosition: "center", backgroundAttachment: "fixed",
      }}>
        <div style={{ position: "absolute", inset: 0, background: "rgba(245,243,255,0.35)", pointerEvents: "none" }} />

        <div style={{ position: "relative", zIndex: 1, padding: "28px 36px 48px", maxWidth: 900, margin: "0 auto" }}>

          {/* ── TopBar ── */}
          <motion.div
            initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
            style={{ marginBottom: 32 }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
               
                <span style={{ fontSize: 30, fontWeight: 800, color: "#1c2a38", letterSpacing: "-0.02em" }}>
                  AI Recruitment System
                </span>
              </div>
              <div style={{
                padding: "7px 14px", borderRadius: 999,
                background: "rgba(255,255,255,0.85)", backdropFilter: "blur(8px)",
                border: "1px solid rgba(255,255,255,0.9)",
                fontSize: 10, fontWeight: 700, color: TEXT_MUTED, letterSpacing: "0.18em",
                boxShadow: "0 1px 4px rgba(90,40,160,0.08)",
              }}>
                {dateLabel}
              </div>
            </div>

            <div>
              <h1 style={{ fontSize: 26, fontWeight: 800, color: TEXT_MAIN, margin: 0, letterSpacing: "-0.01em" }}>
                My Account
              </h1>
              <p style={{ fontSize: 13, color: TEXT_SUB, marginTop: 4 }}>
                Manage your profile, avatar and security settings
              </p>
            </div>
          </motion.div>

          {/* ══════════════════════════════════════════════════════ */}
          {/* ── Section 1 : Avatar + Infos personnelles ── */}
          {/* ══════════════════════════════════════════════════════ */}
          <Card delay={0.05} style={{ marginBottom: 20 }}>
            <CardHeader
              title="Profile Information"
              subtitle="Update your name, position and avatar"
              icon={<User size={17} color={PURPLE} />}
            />
            <div style={{ padding: "28px 28px" }}>
              <div style={{ display: "flex", gap: 32, alignItems: "flex-start", flexWrap: "wrap" }}>

                {/* ── Avatar column ── */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14, flexShrink: 0 }}>
                  {/* Avatar circle */}
                  <div style={{ position: "relative" }}>
                    {/* Pulse ring when preview is set */}
                    {avatarPreview && (
                      <div style={{
                        position: "absolute", inset: -6, borderRadius: "50%",
                        border: `2px solid ${TEAL}`,
                        animation: "pulse-ring 1.6s ease-out infinite",
                      }} />
                    )}
                    <div style={{
                      width: 110, height: 110, borderRadius: "50%",
                      background: displayAvatar ? "transparent" : getGradient(displayName),
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 34, fontWeight: 800, color: "#fff",
                      boxShadow: "0 6px 24px rgba(90,40,160,0.22)",
                      border: "3px solid rgba(255,255,255,0.9)",
                      overflow: "hidden", position: "relative",
                    }}>
                      {displayAvatar
                        ? <img src={displayAvatar} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        : getInitials(displayName)
                      }
                    </div>

                    {/* Camera button */}
                    <motion.button
                      whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.95 }}
                      onClick={() => fileRef.current?.click()}
                      style={{
                        position: "absolute", bottom: 4, right: 4,
                        width: 32, height: 32, borderRadius: "50%",
                        background: "#3b0d8e", border: "2.5px solid #fff",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        cursor: "pointer", boxShadow: "0 2px 10px rgba(60,12,120,0.35)",
                      }}
                    >
                      <Camera size={14} color="#fff" />
                    </motion.button>
                    <input
                      ref={fileRef} type="file" accept="image/*"
                      style={{ display: "none" }}
                      onChange={handleAvatarPick}
                    />
                  </div>

                  {/* Remove preview */}
                  {avatarPreview && (
                    <button
                      onClick={() => { setAvatarPreview(null); if (fileRef.current) fileRef.current.value = ""; }}
                      style={{
                        display: "flex", alignItems: "center", gap: 5,
                        fontSize: 11, fontWeight: 600, color: "#dc2626",
                        background: "#fef2f2", border: "1px solid #fca5a5",
                        borderRadius: 8, padding: "4px 12px", cursor: "pointer",
                      }}
                    >
                      <X size={11} /> Cancel
                    </button>
                  )}

                  
                </div>

                {/* ── Form fields ── */}
                <div style={{ flex: 1, minWidth: 260, display: "flex", flexDirection: "column", gap: 18 }}>
                  <Field
                    label="Full Name"
                    value={fullName}
                    onChange={setFullName}
                    icon={<User size={15} />}
                  />
                  <Field
                    label="Email Address"
                    value={email}
                    disabled
                    icon={<Mail size={15} />}
                  />
                  <Field
                    label="Position / Role"
                    value={poste}
                    onChange={setPoste}
                    placeholder="Senior Manager"
                    icon={<BriefcaseIcon size={15} />}
                  />

                  {/* Save button */}
                  <motion.button
                    whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                    onClick={handleSaveInfo}
                    disabled={savingInfo}
                    style={{
                      alignSelf: "flex-start",
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "10px 22px", borderRadius: 11, border: "none",
                      background: "linear-gradient(135deg, #4a1d96, #3b0d8e)",
                      color: "#fff", fontSize: 13, fontWeight: 700,
                      cursor: savingInfo ? "not-allowed" : "pointer",
                      opacity: savingInfo ? 0.7 : 1,
                      boxShadow: "0 4px 16px rgba(60,12,120,0.28)",
                      transition: "opacity 0.15s",
                    }}
                  >
                    <Save size={14} />
                    {savingInfo ? "Saving…" : "Save Profile"}
                  </motion.button>
                </div>
              </div>
            </div>
          </Card>

          {/* ══════════════════════════════════════════════════════ */}
          {/* ── Section 2 : Changer le mot de passe ── */}
          {/* ══════════════════════════════════════════════════════ */}
          <Card delay={0.12}>
            <CardHeader
              title="Change Password"
              subtitle="Choose a strong password to secure your account"
              icon={<Shield size={17} color={PURPLE} />}
            />
            <div style={{ padding: "28px 28px" }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 480 }}>

                {/* Current password */}
                <Field
                  label="Current Password"
                  value={currentPwd}
                  onChange={setCurrentPwd}
                  type={showCurrent ? "text" : "password"}
                  placeholder="Enter current password"
                  icon={<Lock size={15} />}
                  suffix={
                    <button
                      onClick={() => setShowCurrent(v => !v)}
                      style={{ background: "none", border: "none", cursor: "pointer", padding: "0 12px", color: TEXT_MUTED, display: "flex" }}
                    >
                      {showCurrent ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  }
                />

                {/* New password */}
                <div>
                  <Field
                    label="New Password"
                    value={newPwd}
                    onChange={setNewPwd}
                    type={showNew ? "text" : "password"}
                    placeholder="At least 8 characters"
                    icon={<Lock size={15} />}
                    suffix={
                      <button
                        onClick={() => setShowNew(v => !v)}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: "0 12px", color: TEXT_MUTED, display: "flex" }}
                      >
                        {showNew ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    }
                  />
                  {/* Strength bar */}
                  {newPwd && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                        {[1, 2, 3, 4, 5].map(i => (
                          <div key={i} style={{
                            flex: 1, height: 4, borderRadius: 99,
                            background: i <= strength.score ? strength.color : "#e2e8f0",
                            transition: "background 0.25s",
                          }} />
                        ))}
                      </div>
                      <span style={{ fontSize: 10, fontWeight: 700, color: strength.color }}>{strength.label}</span>
                    </div>
                  )}
                </div>

                {/* Confirm password */}
                <div>
                  <Field
                    label="Confirm New Password"
                    value={confirmPwd}
                    onChange={setConfirmPwd}
                    type={showConfirm ? "text" : "password"}
                    placeholder="Repeat new password"
                    icon={<Lock size={15} />}
                    suffix={
                      <button
                        onClick={() => setShowConfirm(v => !v)}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: "0 12px", color: TEXT_MUTED, display: "flex" }}
                      >
                        {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
                      </button>
                    }
                  />
                  {/* Match indicator */}
                  {confirmPwd && (
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 6 }}>
                      {newPwd === confirmPwd
                        ? <><CheckCircle2 size={12} color="#16a34a" /><span style={{ fontSize: 11, color: "#16a34a", fontWeight: 600 }}>Passwords match</span></>
                        : <><AlertCircle  size={12} color="#dc2626" /><span style={{ fontSize: 11, color: "#dc2626", fontWeight: 600 }}>Passwords don't match</span></>
                      }
                    </div>
                  )}
                </div>

                {/* Divider hint */}
                <div style={{
                  padding: "12px 16px", borderRadius: 12,
                  background: "rgba(124,58,237,0.04)", border: "1px solid rgba(124,58,237,0.12)",
                  display: "flex", alignItems: "flex-start", gap: 10,
                }}>
                  <Shield size={14} color={PURPLE} style={{ flexShrink: 0, marginTop: 1 }} />
                  <p style={{ fontSize: 11, color: TEXT_SUB, margin: 0, lineHeight: 1.5 }}>
                    Use at least <strong>8 characters</strong>, including uppercase letters, numbers and special characters for a strong password.
                  </p>
                </div>

                {/* Submit */}
                <motion.button
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                  onClick={handleChangePwd}
                  disabled={savingPwd}
                  style={{
                    alignSelf: "flex-start",
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "10px 22px", borderRadius: 11, border: "none",
                    background: "linear-gradient(135deg, #0d9488, #0e7490)",
                    color: "#fff", fontSize: 13, fontWeight: 700,
                    cursor: savingPwd ? "not-allowed" : "pointer",
                    opacity: savingPwd ? 0.7 : 1,
                    boxShadow: "0 4px 16px rgba(13,148,136,0.28)",
                    transition: "opacity 0.15s",
                  }}
                >
                  <Lock size={14} />
                  {savingPwd ? "Updating…" : "Update Password"}
                </motion.button>
              </div>
            </div>
          </Card>

        </div>
      </div>

      {/* Toast */}
      <AnimatePresence>
        {toast && <Toast msg={toast.msg} type={toast.type} onDone={() => setToast(null)} />}
      </AnimatePresence>
    </>
  );
}