import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import type { Role } from "@/types";
import {
  FileText,
  GitCompare,
  BarChart2,
  Users,
  LogOut,
  AlertTriangle,
} from "lucide-react";

interface NavItem {
  label: string;
  to: string;
  icon: React.ReactNode;
  allowedRoles?: Role[];
}

const NAV_ITEMS: NavItem[] = [
  { label: "Reports", to: "/reports", icon: <FileText size={16} /> },
  { label: "Deployments", to: "/deployments", icon: <GitCompare size={16} /> },
  { label: "Forecast Weights", to: "/weights", icon: <BarChart2 size={16} /> },
  {
    label: "User Management",
    to: "/users",
    icon: <Users size={16} />,
    allowedRoles: ["admin"],
  },
];

const ROLE_BADGE: Record<Role, string> = {
  admin: "#8b5cf6",
  sre: "#3b82d4",
  developer: "#3fb950",
  viewer: "#8b949e",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  const { user, role, logout } = useAuthStore();
  const navigate = useNavigate();
  const { hasRole } = useAuthStore();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      {/* Sidebar */}
      <nav
        style={{
          width: 220,
          background: "var(--surface)",
          borderRight: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
          padding: "20px 0",
          flexShrink: 0,
        }}
      >
        {/* Logo */}
        <div style={{ padding: "0 20px 24px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <AlertTriangle size={20} color="var(--accent)" />
            <span style={{ fontWeight: 700, fontSize: 16 }}>LogPilot</span>
          </div>
          {user && (
            <div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 4 }}>
                {user.full_name}
              </div>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "2px 8px",
                  borderRadius: 12,
                  background: role ? ROLE_BADGE[role] + "33" : "",
                  color: role ? ROLE_BADGE[role] : "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                }}
              >
                {role}
              </span>
            </div>
          )}
        </div>

        {/* Nav links */}
        <div style={{ flex: 1, padding: "12px 0" }}>
          {NAV_ITEMS.filter(
            (item) => !item.allowedRoles || hasRole(...item.allowedRoles)
          ).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "8px 20px",
                color: isActive ? "var(--accent)" : "var(--text-muted)",
                background: isActive ? "var(--surface2)" : "transparent",
                borderLeft: isActive ? "2px solid var(--accent)" : "2px solid transparent",
                textDecoration: "none",
                fontSize: 14,
                fontWeight: isActive ? 600 : 400,
                transition: "all 0.1s",
              })}
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 20px",
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            fontSize: 14,
            cursor: "pointer",
          }}
        >
          <LogOut size={16} />
          Sign out
        </button>
      </nav>

      {/* Main content */}
      <main style={{ flex: 1, padding: "32px", overflow: "auto" }}>{children}</main>
    </div>
  );
}
