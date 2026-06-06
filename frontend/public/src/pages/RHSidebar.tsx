/**
 * RHSidebar.tsx — Sidebar commun pour tous les pages RH
 * Pages: Dashboard | Jobs | Managers | Ranking | Logout
 */

import { useState } from "react";
import { useLocation, Link } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import { LayoutDashboard, Briefcase, Users, TrendingUp, LogOut } from "lucide-react";

// ─── Nav items ────────────────────────────────────────────────────────────────

const NAV_RH = [
  { href: "/rh/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/rh/jobs",      icon: Briefcase,       label: "Jobs"      },
  { href: "/rh/managers",  icon: Users,           label: "Managers"  },
  { href: "/rh/ranking",   icon: TrendingUp,      label: "Ranking"   },
];

// ─── Tooltip label ────────────────────────────────────────────────────────────

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
            background: "#3b0d8e", color: "#fff", fontSize: 15,
            fontWeight: 700, padding: "6px 14px", borderRadius: 10,
            boxShadow: "0 4px 18px rgba(60,12,120,0.30)", letterSpacing: "0.01em",
          }}>
            {label}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

export default function RHSidebar() {
  const [location, navigate] = useLocation();
  const [hoveredKey, setHoveredKey] = useState<string | null>(null);

  function handleLogout() {
    localStorage.removeItem("access_token");
    navigate("/login");
  }

  return (
    <nav style={{
      position: "fixed", top: 140, left: 16, zIndex: 50,
      borderRadius: 30,
      background: "linear-gradient(180deg, #4a1d96 0%, #3b0d8e 55%, #2c0f70 100%)",
      boxShadow: "0 8px 32px rgba(60,12,120,0.30), 0 2px 8px rgba(0,0,0,0.15)",
      padding: "18px 8px", display: "flex", flexDirection: "column",
      alignItems: "center", gap: 4, overflow: "visible", userSelect: "none", width: 58,
    }}>

      {/* Nav items */}
      {NAV_RH.map(({ href, icon: Icon, label }) => {
        const active  = location === href || location.startsWith(href + "/");
        const hovered = hoveredKey === href;
        return (
          <Link key={href} href={href} style={{ textDecoration: "none", position: "relative", width: "100%" }}>
            <motion.div
              onMouseEnter={() => setHoveredKey(href)}
              onMouseLeave={() => setHoveredKey(null)}
              whileHover={{ scale: 1.12 }}
              whileTap={{ scale: 0.95 }}
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
                <motion.div
                  layoutId="activeBarRH"
                  style={{
                    position: "absolute", left: -7, top: "50%", y: "-50%",
                    width: 3, height: 18, borderRadius: 3, background: "#fff",
                  }}
                  transition={{ type: "spring", stiffness: 500, damping: 30 }}
                />
              )}
              <Icon size={18} color={active ? "#fff" : "rgba(255,255,255,0.65)"} />
              <NavLabel label={label} visible={hovered} />
            </motion.div>
          </Link>
        );
      })}

      {/* Divider */}
      <div style={{ width: 28, height: 1, background: "rgba(255,255,255,0.15)", margin: "6px 0" }} />

      {/* Logout */}
      <motion.div
        onMouseEnter={() => setHoveredKey("__logout")}
        onMouseLeave={() => setHoveredKey(null)}
        whileHover={{ scale: 1.12 }}
        whileTap={{ scale: 0.95 }}
        onClick={handleLogout}
        transition={{ type: "spring", stiffness: 500, damping: 22 }}
        style={{
          width: 40, height: 40, margin: "0 auto", borderRadius: 13,
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "pointer", position: "relative",
          background: hoveredKey === "__logout" ? "rgba(255,255,255,0.11)" : "transparent",
        }}
      >
        <LogOut size={18} color="rgba(255,255,255,0.65)" />
        <NavLabel label="Logout" visible={hoveredKey === "__logout"} />
      </motion.div>

    </nav>
  );
}