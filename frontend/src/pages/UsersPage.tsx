import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listUsers, updateUser } from "@/api";
import type { User, Role } from "@/types";
import toast from "react-hot-toast";
import { Shield, Check, X } from "lucide-react";

const ROLE_COLORS: Record<Role, string> = {
  admin: "#8b5cf6",
  sre: "#3b82d4",
  developer: "#3fb950",
  viewer: "#8b949e",
};

export default function UsersPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRole, setEditRole] = useState<Role>("viewer");
  const [editActive, setEditActive] = useState(true);

  const { data, isLoading } = useQuery({
    queryKey: ["users", page],
    queryFn: () => listUsers({ page }),
  });

  const { mutate: save, isPending } = useMutation({
    mutationFn: (id: string) => updateUser(id, { role: editRole, is_active: editActive }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setEditingId(null);
      toast.success("User updated");
    },
    onError: () => toast.error("Failed to update user"),
  });

  function startEdit(user: User) {
    setEditingId(user.id);
    setEditRole(user.role);
    setEditActive(user.is_active);
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20, display: "flex", alignItems: "center", gap: 8 }}>
          <Shield size={20} color="var(--purple)" /> User Management
        </h1>
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>
          Manage roles and access for Admin, Developer, SRE, and Viewer accounts.
        </p>
      </div>

      {isLoading && <p style={{ color: "var(--text-muted)" }}>Loading…</p>}

      {data && (
        <>
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  {["Name", "Email", "Role", "Active", "Actions"].map((h) => (
                    <th key={h} style={{ padding: "10px 16px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((u: User) => (
                  <tr key={u.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "12px 16px", fontWeight: 500 }}>{u.full_name}</td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)", fontSize: 13 }}>{u.email}</td>
                    <td style={{ padding: "12px 16px" }}>
                      {editingId === u.id ? (
                        <select
                          value={editRole}
                          onChange={(e) => setEditRole(e.target.value as Role)}
                          style={{ width: 130 }}
                        >
                          <option value="admin">admin</option>
                          <option value="sre">sre</option>
                          <option value="developer">developer</option>
                          <option value="viewer">viewer</option>
                        </select>
                      ) : (
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            padding: "2px 8px",
                            borderRadius: 10,
                            background: ROLE_COLORS[u.role] + "33",
                            color: ROLE_COLORS[u.role],
                            textTransform: "uppercase",
                            letterSpacing: 0.5,
                          }}
                        >
                          {u.role}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {editingId === u.id ? (
                        <input
                          type="checkbox"
                          checked={editActive}
                          onChange={(e) => setEditActive(e.target.checked)}
                          style={{ width: "auto" }}
                        />
                      ) : u.is_active ? (
                        <Check size={16} color="var(--success)" />
                      ) : (
                        <X size={16} color="var(--danger)" />
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {editingId === u.id ? (
                        <div style={{ display: "flex", gap: 6 }}>
                          <button
                            disabled={isPending}
                            onClick={() => save(u.id)}
                            style={{ padding: "4px 12px", background: "var(--success)", border: "none", borderRadius: "var(--radius)", color: "#fff", fontSize: 12, cursor: "pointer" }}
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            style={{ padding: "4px 12px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", fontSize: 12, cursor: "pointer" }}
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => startEdit(u)}
                          style={{ padding: "4px 12px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", fontSize: 12, cursor: "pointer" }}
                        >
                          Edit
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {data.total > 20 && (
            <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 16 }}>
              <button disabled={page === 1} onClick={() => setPage((p) => p - 1)} style={{ padding: "6px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}>← Prev</button>
              <button disabled={page * 20 >= data.total} onClick={() => setPage((p) => p + 1)} style={{ padding: "6px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}>Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
