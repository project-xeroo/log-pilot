import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getReport, updateReport, deleteReport, createOutcome, exportReport } from "@/api";
import { useAuthStore } from "@/store/authStore";
import toast from "react-hot-toast";
import {
  Edit2,
  Save,
  X,
  Download,
  Trash2,
  CheckCircle,
  ArrowLeft,
} from "lucide-react";
import type { IncidentReport, OutcomeVerdict } from "@/types";

// ---------------------------------------------------------------------------
// Editable section
// ---------------------------------------------------------------------------

function Section({
  title,
  content,
  isEditing,
  value,
  onChange,
}: {
  title: string;
  content: string | null;
  isEditing: boolean;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <section style={{ marginBottom: 32 }}>
      <h2
        style={{
          fontSize: 14,
          fontWeight: 700,
          color: "var(--accent)",
          textTransform: "uppercase",
          letterSpacing: 0.8,
          margin: "0 0 10px",
          paddingBottom: 6,
          borderBottom: "1px solid var(--border)",
        }}
      >
        {title}
      </h2>
      {isEditing ? (
        <textarea
          rows={6}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{ resize: "vertical", fontFamily: "monospace", fontSize: 13 }}
        />
      ) : content ? (
        <div style={{ fontSize: 14, lineHeight: 1.7 }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      ) : (
        <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>Not available.</p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Outcome feedback modal
// ---------------------------------------------------------------------------

function OutcomeModal({
  reportId,
  incidentId,
  onClose,
}: {
  reportId: string;
  incidentId: string;
  onClose: () => void;
}) {
  const [verdict, setVerdict] = useState<OutcomeVerdict>("true_positive");
  const [rcaAccurate, setRcaAccurate] = useState<boolean | null>(null);
  const [forecastAccurate, setForecastAccurate] = useState<boolean | null>(null);
  const [ttd, setTtd] = useState("");
  const [ttr, setTtr] = useState("");
  const [actionTaken, setActionTaken] = useState("");
  const [indicators, setIndicators] = useState("");
  const [notes, setNotes] = useState("");

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      createOutcome({
        incident_id: incidentId,
        report_id: reportId,
        verdict,
        rca_accurate: rcaAccurate ?? undefined,
        forecast_accurate: forecastAccurate ?? undefined,
        time_to_detect_seconds: ttd ? parseFloat(ttd) : undefined,
        time_to_resolve_seconds: ttr ? parseFloat(ttr) : undefined,
        action_taken: actionTaken || undefined,
        fired_indicators: indicators
          ? indicators.split(",").map((s) => s.trim()).filter(Boolean)
          : undefined,
        notes: notes || undefined,
      }),
    onSuccess: () => {
      toast.success("Outcome logged — forecasting weights updated");
      onClose();
    },
    onError: () => toast.error("Failed to log outcome"),
  });

  const triBtn = (
    label: string,
    val: boolean | null,
    current: boolean | null,
    set: (v: boolean | null) => void
  ) => (
    <button
      onClick={() => set(val)}
      style={{
        padding: "5px 12px",
        borderRadius: "var(--radius)",
        border: "1px solid var(--border)",
        background: current === val ? "var(--accent)" : "var(--surface2)",
        color: current === val ? "#fff" : "var(--text)",
        fontSize: 12,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
      onClick={onClose}
    >
      <div
        style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: 32, width: 520, maxHeight: "90vh", overflowY: "auto" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: "0 0 20px" }}>Log Incident Outcome</h2>
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 20 }}>
          This outcome is recorded and immediately used to refine forecasting weights.
        </p>

        <label style={{ display: "block", marginBottom: 14 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Verdict</span>
          <select value={verdict} onChange={(e) => setVerdict(e.target.value as OutcomeVerdict)}>
            <option value="true_positive">True Positive — real incident, prediction correct</option>
            <option value="false_positive">False Positive — alert fired, no real incident</option>
            <option value="false_negative">False Negative — incident occurred, NOT predicted</option>
            <option value="true_negative">True Negative — no alert, no incident</option>
          </select>
        </label>

        <div style={{ marginBottom: 14 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>RCA accurate?</span>
          <div style={{ display: "flex", gap: 8 }}>
            {triBtn("Yes", true, rcaAccurate, setRcaAccurate)}
            {triBtn("No", false, rcaAccurate, setRcaAccurate)}
            {triBtn("N/A", null, rcaAccurate, setRcaAccurate)}
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 6 }}>Forecast accurate?</span>
          <div style={{ display: "flex", gap: 8 }}>
            {triBtn("Yes", true, forecastAccurate, setForecastAccurate)}
            {triBtn("No", false, forecastAccurate, setForecastAccurate)}
            {triBtn("N/A", null, forecastAccurate, setForecastAccurate)}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <label>
            <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Time to detect (s)</span>
            <input value={ttd} onChange={(e) => setTtd(e.target.value)} type="number" placeholder="120" />
          </label>
          <label>
            <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Time to resolve (s)</span>
            <input value={ttr} onChange={(e) => setTtr(e.target.value)} type="number" placeholder="3600" />
          </label>
        </div>

        <label style={{ display: "block", marginBottom: 14 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Fired indicators (comma-separated)</span>
          <input value={indicators} onChange={(e) => setIndicators(e.target.value)} placeholder="error_rate_spike, latency_p99_high" />
        </label>

        <label style={{ display: "block", marginBottom: 14 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Action taken</span>
          <input value={actionTaken} onChange={(e) => setActionTaken(e.target.value)} placeholder="Rolled back deployment v2.3.1" />
        </label>

        <label style={{ display: "block", marginBottom: 24 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Notes</span>
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} style={{ resize: "vertical" }} />
        </label>

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "8px 18px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}>
            Cancel
          </button>
          <button
            disabled={isPending}
            onClick={() => mutate()}
            style={{ padding: "8px 18px", background: "var(--success)", border: "none", borderRadius: "var(--radius)", color: "#fff", fontWeight: 600 }}
          >
            <CheckCircle size={14} style={{ marginRight: 6, verticalAlign: "middle" }} />
            Log Outcome
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const can = useAuthStore((s) => s.can);

  const { data: report, isLoading } = useQuery({
    queryKey: ["report", id],
    queryFn: () => getReport(id!),
    enabled: !!id,
  });

  const [isEditing, setIsEditing] = useState(false);
  const [showOutcomeModal, setShowOutcomeModal] = useState(false);
  const [edits, setEdits] = useState<Partial<IncidentReport>>({});

  const { mutate: save, isPending: isSaving } = useMutation({
    mutationFn: () => updateReport(id!, edits),
    onSuccess: (updated) => {
      qc.setQueryData(["report", id], updated);
      setIsEditing(false);
      setEdits({});
      toast.success("Report saved");
    },
    onError: () => toast.error("Failed to save"),
  });

  const { mutate: remove } = useMutation({
    mutationFn: () => deleteReport(id!),
    onSuccess: () => {
      toast.success("Report deleted");
      navigate("/reports");
    },
  });

  async function handleExport(format: "pdf" | "markdown") {
    if (!id) return;
    try {
      const blob = await exportReport(id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `incident-report-${id.slice(0, 8)}.${format === "pdf" ? "pdf" : "md"}`;
      a.click();
      URL.revokeObjectURL(url);
      qc.invalidateQueries({ queryKey: ["report", id] });
    } catch {
      toast.error("Export failed");
    }
  }

  function startEdit() {
    if (!report) return;
    setEdits({
      title: report.title,
      summary: report.summary ?? "",
      timeline: report.timeline ?? "",
      impact_analysis: report.impact_analysis ?? "",
      root_cause: report.root_cause ?? "",
      resolution: report.resolution ?? "",
      preventive_actions: report.preventive_actions ?? "",
    });
    setIsEditing(true);
  }

  if (isLoading) return <p style={{ color: "var(--text-muted)" }}>Loading…</p>;
  if (!report) return <p style={{ color: "var(--danger)" }}>Report not found.</p>;

  const sections: { key: keyof IncidentReport; title: string }[] = [
    { key: "summary", title: "Summary" },
    { key: "timeline", title: "Timeline" },
    { key: "impact_analysis", title: "Impact Analysis" },
    { key: "root_cause", title: "Root Cause" },
    { key: "resolution", title: "Resolution" },
    { key: "preventive_actions", title: "Preventive Actions" },
  ];

  return (
    <div style={{ maxWidth: 900 }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <button
          onClick={() => navigate("/reports")}
          style={{ background: "none", border: "none", color: "var(--text-muted)", fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, marginBottom: 16, padding: 0 }}
        >
          <ArrowLeft size={14} /> Back to Reports
        </button>

        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div>
            {isEditing ? (
              <input
                value={(edits.title as string) || ""}
                onChange={(e) => setEdits((d) => ({ ...d, title: e.target.value }))}
                style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, width: 500 }}
              />
            ) : (
              <h1 style={{ margin: "0 0 6px", fontSize: 20 }}>{report.title}</h1>
            )}
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
                {report.incident_id} · {report.severity?.toUpperCase()} · {report.status}
              </span>
              {report.generation_model && (
                <span style={{ fontSize: 11, color: "var(--text-muted)", background: "var(--surface2)", padding: "2px 8px", borderRadius: 10 }}>
                  {report.generation_model} · {report.generation_duration_ms?.toFixed(0)}ms
                </span>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            {isEditing ? (
              <>
                <button onClick={() => setIsEditing(false)} style={{ padding: "7px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", display: "flex", alignItems: "center", gap: 6 }}>
                  <X size={14} /> Discard
                </button>
                <button onClick={() => save()} disabled={isSaving} style={{ padding: "7px 14px", background: "var(--success)", border: "none", borderRadius: "var(--radius)", color: "#fff", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
                  <Save size={14} /> {isSaving ? "Saving…" : "Save"}
                </button>
              </>
            ) : (
              <>
                {can("report:update") && (
                  <button onClick={startEdit} style={{ padding: "7px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", display: "flex", alignItems: "center", gap: 6 }}>
                    <Edit2 size={14} /> Edit
                  </button>
                )}
                <button onClick={() => handleExport("markdown")} style={{ padding: "7px 14px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)", display: "flex", alignItems: "center", gap: 6 }}>
                  <Download size={14} /> MD
                </button>
                <button onClick={() => handleExport("pdf")} style={{ padding: "7px 14px", background: "var(--accent)", border: "none", borderRadius: "var(--radius)", color: "#fff", display: "flex", alignItems: "center", gap: 6 }}>
                  <Download size={14} /> PDF
                </button>
                {can("outcome:write") && (
                  <button onClick={() => setShowOutcomeModal(true)} style={{ padding: "7px 14px", background: "var(--success)", border: "none", borderRadius: "var(--radius)", color: "#fff", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
                    <CheckCircle size={14} /> Log Outcome
                  </button>
                )}
                {can("report:delete") && (
                  <button onClick={() => { if (confirm("Delete this report?")) remove(); }} style={{ padding: "7px 14px", background: "var(--danger)", border: "none", borderRadius: "var(--radius)", color: "#fff", display: "flex", alignItems: "center", gap: 6 }}>
                    <Trash2 size={14} />
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Meta row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: 16,
          marginBottom: 32,
          fontSize: 13,
        }}
      >
        {[
          { label: "Started", value: report.started_at ? new Date(report.started_at).toLocaleString() : "—" },
          { label: "Resolved", value: report.resolved_at ? new Date(report.resolved_at).toLocaleString() : "—" },
          { label: "TTD", value: report.ttd_seconds ? `${report.ttd_seconds}s` : "—" },
          { label: "TTR", value: report.ttr_seconds ? `${Math.round(report.ttr_seconds / 60)}m` : "—" },
        ].map(({ label, value }) => (
          <div key={label}>
            <div style={{ color: "var(--text-muted)", marginBottom: 4, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
            <div style={{ fontWeight: 600 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Sections */}
      {sections.map(({ key, title }) => (
        <Section
          key={key}
          title={title}
          content={report[key] as string | null}
          isEditing={isEditing}
          value={(edits[key] as string) ?? (report[key] as string) ?? ""}
          onChange={(v) => setEdits((d) => ({ ...d, [key]: v }))}
        />
      ))}

      {showOutcomeModal && (
        <OutcomeModal
          reportId={id!}
          incidentId={report.incident_id || id!}
          onClose={() => setShowOutcomeModal(false)}
        />
      )}
    </div>
  );
}
