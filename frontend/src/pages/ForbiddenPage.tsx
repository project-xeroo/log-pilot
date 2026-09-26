import { useNavigate } from "react-router-dom";
import { ShieldOff } from "lucide-react";

export default function ForbiddenPage() {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--bg)", gap: 16 }}>
      <ShieldOff size={40} color="var(--danger)" />
      <h1 style={{ margin: 0, fontSize: 28 }}>403</h1>
      <p style={{ color: "var(--text-muted)", margin: 0 }}>You don't have permission to access this page.</p>
      <button onClick={() => navigate(-1)} style={{ padding: "8px 18px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", cursor: "pointer" }}>
        Go back
      </button>
    </div>
  );
}
