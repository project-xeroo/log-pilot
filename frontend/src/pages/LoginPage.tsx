import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { login } from "@/api";
import { useAuthStore } from "@/store/auth";
import { getMe } from "@/api";
import toast from "react-hot-toast";
import { AlertTriangle } from "lucide-react";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  const { mutate, isPending } = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: async (token) => {
      // Temporarily store the token so getMe() can use it
      useAuthStore.setState({ token: token.access_token, role: token.role });
      const user = await getMe();
      setAuth(token.access_token, user);
      toast.success(`Welcome, ${user.full_name}`);
      navigate("/reports");
    },
    onError: () => toast.error("Invalid email or password"),
  });

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg)",
      }}
    >
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 10,
          padding: "40px 48px",
          width: 380,
        }}
      >
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <AlertTriangle size={32} color="var(--accent)" />
          <h1 style={{ margin: "12px 0 4px", fontSize: 22 }}>LogPilot</h1>
          <p style={{ color: "var(--text-muted)", margin: 0, fontSize: 13 }}>
            Sign in to your workspace
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            mutate();
          }}
        >
          <label style={{ display: "block", marginBottom: 16 }}>
            <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Email
            </span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              required
            />
          </label>

          <label style={{ display: "block", marginBottom: 24 }}>
            <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>

          <button
            type="submit"
            disabled={isPending}
            style={{
              width: "100%",
              padding: "10px",
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontSize: 14,
              fontWeight: 600,
              opacity: isPending ? 0.7 : 1,
            }}
          >
            {isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
