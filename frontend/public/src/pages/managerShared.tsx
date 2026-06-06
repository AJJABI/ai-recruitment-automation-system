/**
 * managerShared.tsx
 * Composants et hooks partagés entre toutes les pages de l'espace Manager.
 * Design : topbar navy gradient + sidebar blanche + Tailwind + lucide-react
 */

import { useState, useEffect, useRef } from "react";
import { useLocation } from "wouter";
import {
  BrainCircuit, LayoutDashboard, Briefcase, Users,
  CalendarDays, Zap, Bell, X, Check, CheckCheck,
} from "lucide-react";
import { LogOut } from "lucide-react";


// ─── Constants ────────────────────────────────────────────────────────────────

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// ─── Auth helpers ─────────────────────────────────────────────────────────────

export function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export function authHeaders(): HeadersInit {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

export function getRoleFromToken(): string | null {
  try {
    const t = getToken();
    if (!t) return null;
    return (JSON.parse(atob(t.split(".")[1])) as { role?: string }).role ?? null;
  } catch { return null; }
}

// ─── Clock hook ───────────────────────────────────────────────────────────────

export function useClock(): string {
  const [time, setTime] = useState(() => new Date().toTimeString().slice(0, 8));
  useEffect(() => {
    const id = setInterval(() => setTime(new Date().toTimeString().slice(0, 8)), 1000);
    return () => clearInterval(id);
  }, []);
  return time;
}

// ─── Notification types ───────────────────────────────────────────────────────

export interface Notif {
  id: number;
  message: string;
  type: string;          // "info" | "success" | "warning" | "error"
  read: boolean;
  created_at: string;
}

// ─── Notification dropdown ────────────────────────────────────────────────────

function NotifDot({ type }: { type: string }) {
  const colors: Record<string, string> = {
    success: "#16a34a",
    warning: "#d97706",
    error:   "#dc2626",
    info:    "#2563eb",
  };
  const c = colors[type] ?? "#2563eb";
  return (
    <span
      className="w-2 h-2 rounded-full shrink-0 mt-1"
      style={{ background: c }}
    />
  );
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return "À l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h}h`;
  return `il y a ${Math.floor(h / 24)}j`;
}

interface NotifPanelProps {
  notifs:     Notif[];
  unread:     number;
  onRead:     (id: number) => void;
  onReadAll:  () => void;
  onClose:    () => void;
}

function NotifPanel({ notifs, unread, onRead, onReadAll, onClose }: NotifPanelProps) {
  return (
    <div
      className="absolute right-0 top-full mt-2 z-50 flex flex-col"
      style={{
        width: 340,
        background: "#fff",
        border: "1px solid #e2e8f0",
        borderRadius: 12,
        boxShadow: "0 8px 32px rgba(30,58,110,0.13)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 shrink-0"
        style={{ borderBottom: "1px solid #f1f5f9", background: "#f8fafc" }}
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono font-bold uppercase tracking-widest" style={{ color: "#1e293b" }}>
            Notifications
          </span>
          {unread > 0 && (
            <span
              className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-full"
              style={{ background: "#dc2626", color: "#fff" }}
            >
              {unread}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {unread > 0 && (
            <button
              onClick={onReadAll}
              className="flex items-center gap-1 text-[10px] font-mono font-semibold transition-colors"
              style={{ color: "rgb(30,58,110)" }}
              title="Tout marquer comme lu"
            >
              <CheckCheck size={12} />
              Tout lire
            </button>
          )}
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-100 transition-colors"
            style={{ color: "#94a3b8" }}
          >
            <X size={13} />
          </button>
        </div>
      </div>

      {/* List */}
      <div className="overflow-y-auto" style={{ maxHeight: 340 }}>
        {notifs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2" style={{ color: "#94a3b8" }}>
            <Bell size={20} style={{ opacity: 0.4 }} />
            <p className="text-xs font-mono">Aucune notification</p>
          </div>
        ) : (
          notifs.map((n) => (
            <div
              key={n.id}
              onClick={() => !n.read && onRead(n.id)}
              className="flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors"
              style={{
                borderBottom: "1px solid #f8fafc",
                background: n.read ? "transparent" : "rgba(37,99,235,0.03)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
              onMouseLeave={(e) => (e.currentTarget.style.background = n.read ? "transparent" : "rgba(37,99,235,0.03)")}
            >
              <NotifDot type={n.type} />
              <div className="flex-1 min-w-0">
                <p
                  className="text-xs leading-snug"
                  style={{ color: n.read ? "#64748b" : "#1e293b", fontWeight: n.read ? 400 : 600 }}
                >
                  {n.message}
                </p>
                <p className="text-[10px] font-mono mt-1" style={{ color: "#94a3b8" }}>
                  {timeAgo(n.created_at)}
                </p>
              </div>
              {!n.read && (
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
                  style={{ background: "#2563eb" }}
                />
              )}
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      {notifs.length > 0 && (
        <div
          className="px-4 py-2.5 shrink-0 text-center"
          style={{ borderTop: "1px solid #f1f5f9", background: "#f8fafc" }}
        >
          <span className="text-[10px] font-mono" style={{ color: "#94a3b8" }}>
            {notifs.length} notification{notifs.length > 1 ? "s" : ""} au total
          </span>
        </div>
      )}
    </div>
  );
}

// ─── NotifBell — icône cloche + dropdown ──────────────────────────────────────

export function NotifBell() {
  const [open, setOpen]       = useState(false);
  const [notifs, setNotifs]   = useState<Notif[]>([]);
  const [loaded, setLoaded]   = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const unread = notifs.filter((n) => !n.read).length;

  async function fetchNotifs() {
    try {
      const res = await fetch(`${API_BASE}/notifications`, { headers: authHeaders() });
      if (res.ok) setNotifs(await res.json());
    } catch { /* endpoint peut ne pas exister — silence */ }
    finally { setLoaded(true); }
  }

  useEffect(() => {
    fetchNotifs();
    const id = setInterval(fetchNotifs, 30000); // poll toutes les 30s
    return () => clearInterval(id);
  }, []);

  // Fermer au clic extérieur
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  async function markRead(id: number) {
    setNotifs((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    try {
      await fetch(`${API_BASE}/notifications/${id}/read`, {
        method: "PATCH",
        headers: authHeaders(),
      });
    } catch { /* silent */ }
  }

  async function markAllRead() {
    setNotifs((prev) => prev.map((n) => ({ ...n, read: true })));
    try {
      await fetch(`${API_BASE}/notifications/read-all`, {
        method: "PATCH",
        headers: authHeaders(),
      });
    } catch { /* silent */ }
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative flex items-center justify-center w-7 h-7 rounded-lg transition-colors"
        style={{ background: open ? "rgba(255,255,255,0.1)" : "transparent" }}
        aria-label="Notifications"
      >
        <Bell size={15} style={{ color: unread > 0 ? "rgb(39,103,73)" : "rgba(255,255,255,0.55)" }} />
        {unread > 0 && (
          <>
            {/* Badge count */}
            <span
              className="absolute -top-1 -right-1 flex items-center justify-center rounded-full text-[8px] font-mono font-bold"
              style={{
                width: unread > 9 ? 16 : 14,
                height: 14,
                background: "#dc2626",
                color: "#fff",
                lineHeight: 1,
              }}
            >
              {unread > 9 ? "9+" : unread}
            </span>
            {/* Pulse ring */}
            <span
              className="absolute -top-1 -right-1 rounded-full animate-ping"
              style={{ width: 14, height: 14, background: "rgba(220,38,38,0.35)" }}
            />
          </>
        )}
      </button>

      {open && (
        <NotifPanel
          notifs={notifs}
          unread={unread}
          onRead={markRead}
          onReadAll={markAllRead}
          onClose={() => setOpen(false)}
        />
      )}
    </div>
  );
}

// ─── Topbar ───────────────────────────────────────────────────────────────────

interface TopbarProps {
  path: string;
}

export function Topbar({ path }: TopbarProps) {
  const time = useClock();
  const role = getRoleFromToken();
  const [, navigate] = useLocation();

  function handleLogout() {
    localStorage.removeItem("access_token");
    navigate("/login");
  }

  return (
    <header
      className="h-[42px] flex items-center justify-between px-5 z-30 shrink-0 relative"
      style={{
        background: "linear-gradient(90deg, rgb(30,58,110) 0%, rgb(43,76,140) 100%)",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      {/* Left — breadcrumb path */}
      <span className="text-[11px] font-mono" style={{ color: "rgba(255,255,255,0.38)", letterSpacing: "0.08em" }}>
        {path}
      </span>

      {/* Center — brand */}
      <div className="flex items-center gap-2 absolute left-1/2 -translate-x-1/2">
        <div
          className="w-2 h-2 rounded-full animate-pulse"
          style={{ background: "rgb(39,103,73)", boxShadow: "rgb(39,103,73) 0px 0px 6px" }}
        />
        <span
          className="text-[11px] font-mono tracking-[0.18em]"
          style={{ color: "rgba(255,255,255,0.88)" }}
        >
          DYNAMIX · AI RECRUITMENT
        </span>
      </div>

      {/* Right — notif + clock + role + logout */}
      <div className="flex items-center gap-3">
        <NotifBell />

        <span
          className="text-[11px] font-mono tabular-nums"
          style={{ color: "rgba(255,255,255,0.45)" }}
        >
          {time}
        </span>

        {role && (
          <span
            className="text-[10px] font-mono px-2 py-0.5 rounded"
            style={{
              background: "rgba(0,0,0,0.2)",
              border: "1px solid rgba(255,255,255,0.12)",
              color: "rgba(255,255,255,0.55)",
              letterSpacing: "0.08em",
            }}
          >
            {role}
          </span>
        )}

        <button
          onClick={handleLogout}
          className="text-[10px] font-mono px-2 py-0.5 rounded transition-colors"
          style={{
            color: "#f87171",
            border: "1px solid rgba(248,113,113,0.3)",
            background: "transparent",
            letterSpacing: "0.08em",
            cursor: "pointer",
          }}
        >
          LOGOUT
        </button>
      </div>
    </header>
  );
}

// ─── Sidebar nav item ─────────────────────────────────────────────────────────

interface NavItemProps {
  icon: React.ElementType;
  label: string;
  href: string;
  active?: boolean;
  pulse?: boolean;
}

function SidebarNavItem({ icon: Icon, label, href, active, pulse }: NavItemProps) {
  const [, navigate] = useLocation();
  return (
    <div
      onClick={() => navigate(href)}
      className="relative group w-9 h-9 flex items-center justify-center rounded-lg cursor-pointer transition-all duration-150"
    >
      <div
        className="absolute inset-0 rounded-lg"
        style={
          active
            ? { background: "rgba(30,58,110,0.063)", border: "1px solid rgba(30,58,110,0.157)" }
            : undefined
        }
      />
      {!active && (
        <div
          className="absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ background: "rgba(30,58,110,0.024)", border: "1px solid #e2e8f0" }}
        />
      )}
      <Icon
        size={16}
        className="z-10 transition-colors duration-150"
        style={{ color: active ? "rgb(30,58,110)" : "rgb(113,128,150)" }}
        aria-hidden
      />
      {pulse && (
        <span
          className="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full z-20 animate-pulse"
          style={{ background: "rgb(39,103,73)" }}
        />
      )}
      {/* Tooltip */}
      <div
        className="absolute left-11 whitespace-nowrap text-[10px] font-mono px-2 py-1 rounded pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50"
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          color: "rgb(30,58,110)",
          boxShadow: "rgba(30,58,110,0.1) 0px 2px 8px",
        }}
      >
        {label}
      </div>
    </div>
  );
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────

export interface SidebarProps {
  active: "dashboard" | "jobs" | "candidates" | "interviews" | "notifications";
}

const NAV: NavItemProps[] = [
  { icon: LayoutDashboard, label: "Dashboard",     href: "/" },
  { icon: Briefcase,       label: "Jobs",          href: "/mission-registry" },
  { icon: Users,           label: "Candidates",    href: "/candidates" },
  { icon: CalendarDays,    label: "Interviews",    href: "/interviews" },
  { icon: Zap,             label: "Notifications", href: "/notifications", pulse: true },
];

const ACTIVE_MAP: Record<SidebarProps["active"], string> = {
  dashboard:     "/",
  jobs:          "/mission-registry",
  candidates:    "/candidates",
  interviews:    "/interviews",
  notifications: "/notifications",
};

export function Sidebar({ active }: SidebarProps) {
  const activeHref = ACTIVE_MAP[active];
  return (
    <aside
      className="w-[54px] flex flex-col items-center py-4 z-20 shrink-0"
      style={{ background: "#ffffff", borderRight: "1px solid #e2e8f0" }}
    >
      {/* Logo */}
      <div className="mb-7">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{
            background: "linear-gradient(135deg, rgba(30,58,110,0.08), rgba(43,76,140,0.03))",
            border: "1px solid #e2e8f0",
          }}
        >
          <BrainCircuit size={16} style={{ color: "rgb(30,58,110)" }} aria-hidden />
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-2 flex-1">
        {NAV.map((item) => (
          <SidebarNavItem
            key={item.href}
            {...item}
            active={item.href === activeHref}
          />
        ))}
      </nav>

      {/* Status */}
      <div className="mt-auto flex flex-col items-center gap-1">
        <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: "rgb(39,103,73)" }} />
        <span
          className="text-[8px] font-mono opacity-50 origin-center"
          style={{ color: "rgb(39,103,73)", letterSpacing: "0.15em", writingMode: "vertical-rl", transform: "rotate(180deg)" }}
        >
          ON
        </span>
      </div>
    </aside>
  );
}

// ─── Page shell ───────────────────────────────────────────────────────────────
// Wrapper pour une page complète : topbar + sidebar + main

interface PageShellProps {
  path:     string;
  active:   SidebarProps["active"];
  children: React.ReactNode;
}

export function PageShell({ path, active, children }: PageShellProps) {
  return (
    <div
      className="flex flex-col h-screen"
      style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}
    >
      <Topbar path={path} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar active={active} />
        <main style={{ flex: 1, overflowY: "auto", background: "#f0f4f9" }}>
          {children}
        </main>
      </div>
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
    </div>
  );
}

// ─── Reusable UI atoms ────────────────────────────────────────────────────────

/** Skeleton pulse block */
export function Skel({ w, h, radius = 6 }: { w: string | number; h: number; radius?: number }) {
  return (
    <div
      style={{
        width: w, height: h, borderRadius: radius,
        background: "#e9eef5", animation: "pulse 1.5s ease-in-out infinite",
      }}
    />
  );
}

/** Section card */
export function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div
      style={{ background: "#fff", borderRadius: 12, border: "1px solid #e2e8f0", overflow: "hidden", ...style }}
    >
      {children}
    </div>
  );
}

export function CardHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: "12px 20px", borderBottom: "1px solid #f1f5f9", background: "#f8fafc" }}>
      {children}
    </div>
  );
}

export function CardBody({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div style={{ padding: "18px 20px", ...style }}>{children}</div>;
}

/** Error banner */
export function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div
      className="flex items-center gap-2 px-4 py-2.5 rounded-lg mb-5 text-xs font-mono"
      style={{ background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626" }}
    >
      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: "#f87171" }} />
      {msg}
    </div>
  );
}

/** Toast */
export function Toast({ msg, type, onDone }: { msg: string; type: "ok" | "err"; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500);
    return () => clearTimeout(t);
  }, []);
  return (
    <div
      style={{
        position: "fixed", bottom: 24, right: 24, zIndex: 60,
        padding: "10px 18px", borderRadius: 8,
        fontSize: 12, fontFamily: "monospace", fontWeight: 600,
        background: type === "ok" ? "#f0fdf4" : "#fef2f2",
        border: `1px solid ${type === "ok" ? "#86efac" : "#fca5a5"}`,
        color: type === "ok" ? "#16a34a" : "#dc2626",
        boxShadow: "0 4px 16px rgba(0,0,0,0.1)",
      }}
    >
      {msg}
    </div>
  );
}

/** Avatar circle */
const AVATAR_PALETTE = ["#1e3a6e", "#1d4ed8", "#7c3aed", "#0e7490", "#065f46", "#9a3412"];

export function Avatar({ name, index, size = 36 }: { name: string; index: number; size?: number }) {
  const ini = name ? name.split(" ").map((p) => p[0]).join("").slice(0, 2).toUpperCase() : "?";
  return (
    <div
      style={{
        width: size, height: size, borderRadius: "50%", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: size * 0.3, fontWeight: 700, color: "#fff",
        background: AVATAR_PALETTE[index % AVATAR_PALETTE.length],
      }}
    >
      {ini}
    </div>
  );
}

/** Score bar with animated fill */
export function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xs" style={{ color: "#64748b" }}>{label}</span>
        <span className="text-xs font-mono font-bold" style={{ color }}>
          {Math.round(value)}%
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 99, background: "#f1f5f9", overflow: "hidden" }}>
        <div
          style={{
            height: "100%", borderRadius: 99, background: color,
            width: `${Math.min(value, 100)}%`,
            transition: "width 0.7s ease-out",
          }}
        />
      </div>
    </div>
  );
}