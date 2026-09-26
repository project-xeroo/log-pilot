import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listDeployments, compareDeployments } from "@/api";
import type { DeploymentSnapshot } from "@/types";
import { GitCompare } from "lucide-react";

function DiffRow({ k, base, head }: { k: string; base: unknown; head: unknown }) {
  return (
    <tr style={{ borderBottom: "1px solid var(--border)" }}>
      <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 13 }}>{k}</td>
      <td
        style={{
          padding: "8px 12px",
          fontFamily: "monospace",
          fontSize: 13,
          color: "var(--danger)",
          background: "#f851491a",
        }}
      >
        {JSON.stringify(base)}
      </td>
      <td style={{ padding: "8px 12px", color: "var(--text-muted)", fontSize: 18, textAlign: "center" }}>
        →
      </td>
      <td
        style={{
          padding: "8px 12px",
          fontFamily: "monospace",
          fontSize: 13,
          color: "var(--success)",
          background: "#3fb9501a",
        }}
      >
        {JSON.stringify(head)}
      </td>
    </tr>
  );
}

function DeployCard({
  dep,
  label,
  selected,
  onClick,
}: {
  dep: DeploymentSnapshot;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        padding: "12px 16px",
        background: selected ? "var(--surface2)" : "var(--surface)",
        border: `1px solid ${selected ? "var(--accent)" : "var(--border)"}`,
        borderRadius: "var(--radius)",
        cursor: "pointer",
        marginBottom: 8,
        transition: "border-color 0.1s",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div>
          <span style={{ fontSize: 12, color: "var(--text-muted)", textTransform: "uppercase" }}>{label}</span>
          <div style={{ fontWeight: 600, marginTop: 2 }}>{dep.service_name}</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {dep.version} · {dep.environment}
          </div>
        </div>
        <div style={{ textAlign: "right", fontSize: 12, color: "var(--text-muted)" }}>
          {new Date(dep.deployed_at).toLocaleString()}
          {dep.deployed_by && <div>by {dep.deployed_by}</div>}
        </div>
      </div>
    </div>
  );
}

export default function DeploymentsPage() {
  const [baseId, setBaseId] = useState<string | null>(null);
  const [headId, setHeadId] = useState<string | null>(null);
  const [serviceFilter, setServiceFilter] = useState("");
  const [page, setPage] = useState(1);

  const { data: deployments } = useQuery({
    queryKey: ["deployments", serviceFilter, page],
    queryFn: () =>
      listDeployments({ service_name: serviceFilter || undefined, page }),
  });

  const { data: diff, isFetching: diffLoading } = useQuery({
    queryKey: ["diff", baseId, headId],
    queryFn: () => compareDeployments(baseId!, headId!),
    enabled: !!baseId && !!headId && baseId !== headId,
  });

  function selectDeployment(id: string) {
    if (!baseId) { setBaseId(id); return; }
    if (!headId && id !== baseId) { setHeadId(id); return; }
    // Reset
    setBaseId(id);
    setHeadId(null);
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20 }}>Deployment Comparison</h1>
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>
          Select two deployments to diff their configuration and metadata.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 24 }}>
        {/* Left — deployment list */}
        <div>
          <input
            value={serviceFilter}
            onChange={(e) => { setServiceFilter(e.target.value); setPage(1); }}
            placeholder="Filter by service name…"
            style={{ marginBottom: 12 }}
          />

          <p style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 8 }}>
            {!baseId
              ? "Click a deployment to set as Base"
              : !headId
              ? "Click another to set as Head"
              : "Click to reset selection"}
          </p>

          {deployments?.items.map((d: DeploymentSnapshot) => (
            <DeployCard
              key={d.id}
              dep={d}
              label={d.id === baseId ? "BASE" : d.id === headId ? "HEAD" : ""}
              selected={d.id === baseId || d.id === headId}
              onClick={() => selectDeployment(d.id)}
            />
          ))}

          {(!deployments || deployments.items.length === 0) && (
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No deployments found.</p>
          )}

          {deployments && deployments.total > 20 && (
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button disabled={page === 1} onClick={() => setPage((p) => p - 1)} style={{ padding: "4px 10px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}>←</button>
              <button disabled={page * 20 >= deployments.total} onClick={() => setPage((p) => p + 1)} style={{ padding: "4px 10px", background: "var(--surface2)", border: "1px solid var(--border)", borderRadius: "var(--radius)", color: "var(--text)" }}>→</button>
            </div>
          )}
        </div>

        {/* Right — diff panel */}
        <div>
          {!baseId && (
            <div
              style={{
                height: 300,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--surface)",
                border: "1px dashed var(--border)",
                borderRadius: "var(--radius)",
                color: "var(--text-muted)",
                gap: 12,
              }}
            >
              <GitCompare size={24} />
              <span>Select two deployments from the left panel</span>
            </div>
          )}

          {baseId && !headId && (
            <div
              style={{
                height: 300,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--surface)",
                border: "1px dashed var(--border)",
                borderRadius: "var(--radius)",
                color: "var(--text-muted)",
              }}
            >
              Base selected — now select Head
            </div>
          )}

          {diffLoading && <p style={{ color: "var(--text-muted)" }}>Computing diff…</p>}

          {diff && (
            <div>
              {/* Summary bar */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  gap: 12,
                  marginBottom: 20,
                }}
              >
                {[
                  {
                    label: "Version",
                    value: diff.version_changed ? `${diff.base.version} → ${diff.head.version}` : "No change",
                    color: diff.version_changed ? "var(--warning)" : "var(--success)",
                  },
                  {
                    label: "Deployer",
                    value: diff.deployer_changed ? `${diff.base.deployed_by} → ${diff.head.deployed_by}` : "Same",
                    color: diff.deployer_changed ? "var(--warning)" : "var(--text-muted)",
                  },
                  {
                    label: "Time between",
                    value: `${Math.round(diff.time_between_seconds / 60)}m`,
                    color: "var(--text-muted)",
                  },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    style={{
                      background: "var(--surface)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius)",
                      padding: 14,
                    }}
                  >
                    <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 }}>{label}</div>
                    <div style={{ fontWeight: 600, color }}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Config diff table */}
              <div
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  overflow: "hidden",
                }}
              >
                <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>Config Diff</span>
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {Object.keys(diff.config_diff).length} changed keys
                  </span>
                </div>
                {Object.keys(diff.config_diff).length > 0 ? (
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        {["Key", "Base", "", "Head"].map((h, i) => (
                          <th key={i} style={{ padding: "8px 12px", textAlign: "left", fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(diff.config_diff).map(([k, { base, head }]) => (
                        <DiffRow key={k} k={k} base={base} head={head} />
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p style={{ padding: 20, color: "var(--success)", margin: 0 }}>
                    ✓ No configuration differences between these deployments.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
