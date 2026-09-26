import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listReports, generateReport } from "@/api";
import { useAuthStore } from "@/store/auth";
import toast from "react-hot-toast";
import { Plus, FileText, RefreshCw } from "lucide-react";
import type { IncidentReport } from "@/types";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "var(--danger)",
  high: "#f97316",
  medium: "var(--warning)",
  low: "var(--success)",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "var(--text-muted)",
  review: "var(--warning)",
  approved: "var(--success)",
  exported: "var(--purple)",
};

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        padding: "2px 8px",
        borderRadius: 10,
        background: color + "22",
        color,
        textTransform: "uppercase",
        letterSpacing: 0.5,
      }}
    >
      {label}
    </span>
  );
}

function GenerateModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    incident_id: "",
    title: "",
    severity: "medium",
    started_at: "",
    resolved_at: "",
    affected_services: "",
    context_logs: "",
  });

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      generateReport({
        ...form,
        affected_services: form.affected_services
          ? form.affected_services.split(",").map((s) => s.trim())
          : undefined,
        context_logs: form.context_logs
          ? form.context_logs.split("\n").filter(Boolean)
          : undefined,
        started_at: form.started_at || undefined,
        resolved_at: form.resolved_at || undefined,
      }),
    onSuccess: (report) => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Report draft created in < 2 minutes ✓");
      onClose();
      navigate(`/reports/${report.id}`);
    },
    onError: () => toast.error("Failed to generate report"),
  });

  const field = (key: keyof typeof form, label: string, props?: object) => (
    <label key={key} style={{ display: "block", marginBottom: 14 }}>
      <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
        {label}
      </span>
      <input
        value={form[key]}
        onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
        {...props}
      />
    </label>
  );

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 10,
          padding: 32,
          width: 560,
          maxHeight: "90vh",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: "0 0 24px" }}>Generate Incident Report</h2>

        {field("incident_id", "Incident ID *", { required: true, placeholder: "INC-1234" })}
        {field("title", "Title *", { required: true, placeholder: "Payment service latency spike" })}

        <label style={{ display: "block", marginBottom: 14 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
            Severity
          </span>
          <select
            value={form.severity}
            onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </label>

        {field("started_at", "Started at (ISO 8601)", { placeholder: "2024-06-01T14:32:00Z" })}
        {field("resolved_at", "Resolved at (ISO 8601)", { placeholder: "2024-06-01T16:05:00Z" })}
        {field("affected_services", "Affected services (comma-separated)", {
          placeholder: "payment-service, api-gateway",
        })}

        <label style={{ display: "block", marginBottom: 24 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
            Relevant log lines (one per line — optional)
          </span>
          <textarea
            rows={4}
            value={form.context_logs}
            onChange={(e) => setForm((f) => ({ ...f, context_logs: e.target.value }))}
            placeholder="2024-06-01T14:32:00Z ERROR payment-service connection timeout..."
            style={{ resize: "vertical" }}
          />
        </label>

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              padding: "8px 18px",
              background: "var(--surface2)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              color: "var(--text)",
            }}
          >
            Cancel
          </button>
          <button
            disabled={isPending || !form.incident_id || !form.title}
            onClick={() => mutate()}
            style={{
              padding: "8px 18px",
              background: "var(--accent)",
              border: "none",
              borderRadius: "var(--radius)",
              color: "#fff",
              fontWeight: 600,
              opacity: isPending ? 0.7 : 1,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            {isPending ? <><RefreshCw size={14} className="spin" /> Generating…</> : "Generate Report"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const [showModal, setShowModal] = useState(false);
  const [page, setPage] = useState(1);
  const { hasRole } = useAuthStore();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["reports", page],
    queryFn: () => listReports({ page }),
  });

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: "0 0 4px", fontSize: 20 }}>Incident Reports</h1>
          <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>
            Agent-drafted incident & pre-mortem reports
          </p>
        </div>
        {hasRole("admin", "sre") && (
          <button
            onClick={() => setShowModal(true)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "8px 16px",
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "var(--radius)",
              fontWeight: 600,
            }}
          >
            <Plus size={16} /> Generate Report
          </button>
        )}
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
                  {["Title", "Incident", "Severity", "Status", "Created"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "10px 16px",
                        textAlign: "left",
                        fontSize: 12,
                        color: "var(--text-muted)",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: 0.5,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((r: IncidentReport) => (
                  <tr
                    key={r.id}
                    onClick={() => navigate(`/reports/${r.id}`)}
                    style={{
                      borderBottom: "1px solid var(--border)",
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface2)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                  >
                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <FileText size={14} color="var(--text-muted)" />
                        <span style={{ fontWeight: 500 }}>{r.title}</span>
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)", fontSize: 13 }}>
                      {r.incident_id || "—"}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      {r.severity && (
                        <Badge
                          label={r.severity}
                          color={SEVERITY_COLORS[r.severity] || "var(--text-muted)"}
                        />
                      )}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <Badge
                        label={r.status}
                        color={STATUS_COLORS[r.status] || "var(--text-muted)"}
                      />
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)", fontSize: 13 }}>
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}
                    >
                      No reports yet — generate the first one above.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.total > 20 && (
            <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                style={{ padding: "6px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
              >
                ← Prev
              </button>
              <span style={{ lineHeight: "32px", color: "var(--text-muted)" }}>
                Page {page} of {Math.ceil(data.total / 20)}
              </span>
              <button
                disabled={page * 20 >= data.total}
                onClick={() => setPage((p) => p + 1)}
                style={{ padding: "6px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}

      {showModal && <GenerateModal onClose={() => setShowModal(false)} />}
    </div>
  );
}
