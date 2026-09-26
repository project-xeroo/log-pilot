import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--bg)", gap: 16 }}>
      <AlertTriangle size={40} color="var(--text-muted)" />
      <h1 style={{ margin: 0, fontSize: 28 }}>404</h1>
      <p style={{ color: "var(--text-muted)", margin: 0 }}>Page not found.</p>
      <button onClick={() => navigate("/feed")} style={{ padding: "8px 18px", background: "var(--accent)", border: "none", borderRadius: "var(--radius)", color: "#fff", cursor: "pointer" }}>
        Go to Feed
      </button>
    </div>
  );
}
