/**
 * Failure Risk Board — Phase 3
 *
 * Read-only view backed by service_health_states / error_clusters / dedup_events.
 * Shows per-service health metrics, active error clusters, open anomalies,
 * and unacknowledged deployment regressions.
 *
 * PRD §9.2 — Core Screens: Failure Risk Board
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Activity, Layers, GitCompare, RefreshCw } from "lucide-react";
import {
  getFleetHealth,
  listAnomalies,
  listRegressions,
  resolveAnomaly,
  acknowledgeRegression,
} from "@/api";
import { useAuthStore } from "@/store/auth";
import type {
  ServiceHealthState,
  AnomalyEvent,
  DeploymentRegression,
} from "@/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

function healthColor(score: number): string {
  if (score >= 80) return "#3fb950";
  if (score >= 50) return "#d29922";
  return "#f85149";
}

function tierBadgeStyle(tier: string): React.CSSProperties {
  const colors: Record<string, string> = {
    normal: "#3fb95022",
    warning: "#d2992233",
    critical: "#f8514933",
  };
  const text: Record<string, string> = {
    normal: "#3fb950",
    warning: "#d29922",
    critical: "#f85149",
  };
  return {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 12,
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    background: colors[tier] ?? "#e5e7eb",
    color: text[tier] ?? "#57606a",
  };
}

function severityBadgeStyle(severity: string): React.CSSProperties {
  return {
    display: "inline-block",
    padding: "2px 7px",
    borderRadius: 10,
    fontSize: 11,
    fontWeight: 600,
    background: severity === "critical" ? "#f8514922" : "#d2992222",
    color: severity === "critical" ? "#f85149" : "#d29922",
    textTransform: "uppercase",
  };
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function FleetSummaryBar({
  healthy,
  warning,
  critical,
  totalAnomalies,
  mostAtRisk,
}: {
  healthy: number;
  warning: number;
  critical: number;
  totalAnomalies: number;
  mostAtRisk: string | null;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: 16,
        marginBottom: 28,
      }}
    >
      {[
        { label: "Healthy", value: healthy, color: "#3fb950" },
        { label: "Warning", value: warning, color: "#d29922" },
        { label: "Critical", value: critical, color: "#f85149" },
        { label: "Open Anomalies", value: totalAnomalies, color: "#8b949e" },
      ].map((item) => (
        <div
          key={item.label}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            padding: "16px 20px",
          }}
        >
          <div style={{ fontSize: 24, fontWeight: 700, color: item.color }}>
            {item.value}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
            {item.label}
          </div>
        </div>
      ))}
      {mostAtRisk && (
        <div
          style={{
            gridColumn: "1 / -1",
            background: "#f8514912",
            border: "1px solid #f8514944",
            borderRadius: 8,
            padding: "10px 16px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            color: "#f85149",
          }}
        >
          <AlertTriangle size={14} />
          Most at risk: <strong>{mostAtRisk}</strong>
        </div>
      )}
    </div>
  );
}

function ServiceHealthRow({ service }: { service: ServiceHealthState }) {
  return (
    <tr>
      <td style={{ padding: "10px 16px", fontWeight: 600 }}>
        {service.service_name ?? service.service_id.slice(0, 8)}
      </td>
      <td style={{ padding: "10px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 80,
              height: 6,
              borderRadius: 3,
              background: "var(--border)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${service.health_score}%`,
                height: "100%",
                background: healthColor(service.health_score),
                borderRadius: 3,
              }}
            />
          </div>
          <span
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: healthColor(service.health_score),
            }}
          >
            {service.health_score.toFixed(0)}
          </span>
        </div>
      </td>
      <td style={{ padding: "10px 16px" }}>
        <span style={tierBadgeStyle(service.latest_risk_tier)}>
          {service.latest_risk_tier}
        </span>
      </td>
      <td style={{ padding: "10px 16px", fontSize: 13 }}>
        {service.active_cluster_count}
      </td>
      <td style={{ padding: "10px 16px", fontSize: 13 }}>
        {service.total_deduped_error_count}
      </td>
      <td style={{ padding: "10px 16px", fontSize: 13 }}>
        {service.open_anomaly_count > 0 ? (
          <span style={{ color: "#f85149", fontWeight: 600 }}>
            {service.open_anomaly_count}
          </span>
        ) : (
          <span style={{ color: "var(--text-muted)" }}>0</span>
        )}
      </td>
      <td
        style={{
          padding: "10px 16px",
          fontSize: 12,
          color: "var(--text-muted)",
          maxWidth: 220,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        title={service.top_cluster_label ?? undefined}
      >
        {service.top_cluster_label ?? "—"}
      </td>
    </tr>
  );
}

function AnomalyCard({
  anomaly,
  onResolve,
}: {
  anomaly: AnomalyEvent;
  onResolve?: (id: string) => void;
}) {
  const { user, hasRole } = useAuthStore();
  const canResolve = hasRole("sre", "admin");

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "14px 16px",
        marginBottom: 10,
        background: anomaly.severity === "critical" ? "#f8514908" : undefined,
        borderLeft: `3px solid ${anomaly.severity === "critical" ? "#f85149" : "#d29922"}`,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span style={severityBadgeStyle(anomaly.severity)}>
              {anomaly.severity}
            </span>
            <span
              style={{
                fontSize: 11,
                color: "var(--text-muted)",
                background: "var(--surface)",
                border: "1px solid var(--border)",
                padding: "1px 6px",
                borderRadius: 8,
              }}
            >
              {anomaly.anomaly_type.replace(/_/g, " ")}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {fmtDate(anomaly.detected_at)}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>
            {anomaly.explanation}
          </p>
          {anomaly.z_score !== null && (
            <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-muted)" }}>
              z-score: <strong>{anomaly.z_score.toFixed(2)}</strong>
              {anomaly.observed_value !== null && (
                <>
                  {" · "}observed: <strong>{anomaly.observed_value.toFixed(1)}</strong>
                </>
              )}
              {anomaly.baseline_mean !== null && (
                <>
                  {" · "}baseline: <strong>{anomaly.baseline_mean.toFixed(1)}</strong>
                </>
              )}
            </div>
          )}
        </div>
        {canResolve && onResolve && !anomaly.is_resolved && (
          <button
            onClick={() => onResolve(anomaly.id)}
            style={{
              fontSize: 12,
              padding: "4px 10px",
              background: "none",
              border: "1px solid var(--border)",
              borderRadius: 6,
              cursor: "pointer",
              color: "var(--text-muted)",
              whiteSpace: "nowrap",
            }}
          >
            Resolve
          </button>
        )}
      </div>
    </div>
  );
}

function RegressionCard({
  regression,
  onAcknowledge,
}: {
  regression: DeploymentRegression;
  onAcknowledge?: (id: string) => void;
}) {
  const canAck = useAuthStore((s) => s.hasRole("sre", "admin"));

  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "14px 16px",
        marginBottom: 10,
        borderLeft: "3px solid #d29922",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                background: "#d2992222",
                color: "#d29922",
                padding: "2px 7px",
                borderRadius: 8,
                textTransform: "uppercase",
              }}
            >
              {regression.regression_type.replace(/_/g, " ")}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "monospace" }}>
              v{regression.baseline_version} → v{regression.head_version}
            </span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {fmtDate(regression.detected_at)}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>{regression.explanation}</p>
          {regression.error_rate_delta !== null && (
            <div style={{ marginTop: 6, fontSize: 12, color: "var(--text-muted)" }}>
              Error rate change:{" "}
              <strong style={{ color: "#f85149" }}>
                +{(regression.error_rate_delta * 100).toFixed(1)}%
              </strong>
              {" · "}confidence: {((regression.confidence ?? 0) * 100).toFixed(0)}%
            </div>
          )}
        </div>
        {canAck && onAcknowledge && !regression.acknowledged && (
          <button
            onClick={() => onAcknowledge(regression.id)}
            style={{
              fontSize: 12,
              padding: "4px 10px",
              background: "none",
              border: "1px solid var(--border)",
              borderRadius: 6,
              cursor: "pointer",
              color: "var(--text-muted)",
              whiteSpace: "nowrap",
            }}
          >
            Acknowledge
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RiskBoardPage() {
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"health" | "anomalies" | "regressions">("health");

  const {
    data: fleet,
    isLoading: fleetLoading,
    error: fleetError,
    refetch: refetchFleet,
  } = useQuery({
    queryKey: ["fleet-health"],
    queryFn: getFleetHealth,
    refetchInterval: 30_000,
  });

  const { data: anomalies, isLoading: anomaliesLoading } = useQuery({
    queryKey: ["anomalies"],
    queryFn: () => listAnomalies({ resolved: false, limit: 50 }),
    refetchInterval: 30_000,
    enabled: activeTab === "anomalies",
  });

  const { data: regressions, isLoading: regressionsLoading } = useQuery({
    queryKey: ["regressions"],
    queryFn: () => listRegressions({ acknowledged: false, limit: 50 }),
    refetchInterval: 60_000,
    enabled: activeTab === "regressions",
  });

  const resolveAnomalyMutation = useMutation({
    mutationFn: (id: string) =>
      resolveAnomaly(id, user?.email ?? "unknown"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["anomalies"] }),
  });

  const ackRegressionMutation = useMutation({
    mutationFn: (id: string) =>
      acknowledgeRegression(id, user?.email ?? "unknown"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["regressions"] }),
  });

  const TAB_ITEMS = [
    { id: "health", label: "Service Health", icon: <Activity size={14} /> },
    { id: "anomalies", label: "Anomalies", icon: <AlertTriangle size={14} />, count: fleet?.total_open_anomalies },
    { id: "regressions", label: "Regressions", icon: <GitCompare size={14} /> },
  ] as const;

  const tableHeaderStyle: React.CSSProperties = {
    padding: "8px 16px",
    textAlign: "left",
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-muted)",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    borderBottom: "1px solid var(--border)",
    background: "var(--surface)",
  };

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Failure Risk Board</h1>
          <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--text-muted)" }}>
            Live service health metrics, anomaly feed, and deployment regressions.
          </p>
        </div>
        <button
          onClick={() => refetchFleet()}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            fontSize: 13,
            padding: "6px 14px",
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: 6,
            cursor: "pointer",
            color: "var(--text-muted)",
          }}
        >
          <RefreshCw size={13} />
          Refresh
        </button>
      </div>

      {/* Fleet summary cards */}
      {fleet && (
        <FleetSummaryBar
          healthy={fleet.healthy_count}
          warning={fleet.warning_count}
          critical={fleet.critical_count}
          totalAnomalies={fleet.total_open_anomalies}
          mostAtRisk={fleet.most_at_risk_service}
        />
      )}

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: 4,
          borderBottom: "1px solid var(--border)",
          marginBottom: 20,
        }}
      >
        {TAB_ITEMS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "8px 16px",
              background: "none",
              border: "none",
              borderBottom:
                activeTab === tab.id
                  ? "2px solid var(--accent)"
                  : "2px solid transparent",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: activeTab === tab.id ? 600 : 400,
              color: activeTab === tab.id ? "var(--accent)" : "var(--text-muted)",
              marginBottom: -1,
            }}
          >
            {tab.icon}
            {tab.label}
            {"count" in tab && tab.count !== undefined && tab.count > 0 && (
              <span
                style={{
                  background: "#f85149",
                  color: "white",
                  borderRadius: 10,
                  fontSize: 11,
                  fontWeight: 700,
                  padding: "1px 6px",
                  minWidth: 18,
                  textAlign: "center",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "health" && (
        <div>
          {fleetLoading && (
            <p style={{ color: "var(--text-muted)", fontSize: 14 }}>Loading health data…</p>
          )}
          {fleetError && (
            <p style={{ color: "#f85149", fontSize: 14 }}>
              Failed to load health data. The analysis pipeline may still be initializing.
            </p>
          )}
          {fleet && fleet.services.length === 0 && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "var(--text-muted)",
                fontSize: 14,
              }}
            >
              <Layers size={32} style={{ marginBottom: 12, opacity: 0.4 }} />
              <p>No service health data yet.</p>
              <p>
                Health states are populated after the first analysis pipeline run
                following log ingestion.
              </p>
            </div>
          )}
          {fleet && fleet.services.length > 0 && (
            <div
              style={{
                border: "1px solid var(--border)",
                borderRadius: 8,
                overflow: "hidden",
              }}
            >
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {[
                      "Service",
                      "Health Score",
                      "Risk Tier",
                      "Clusters",
                      "Deduped Errors",
                      "Open Anomalies",
                      "Top Cluster",
                    ].map((h) => (
                      <th key={h} style={tableHeaderStyle}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {fleet.services.map((svc) => (
                    <ServiceHealthRow key={svc.service_id} service={svc} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === "anomalies" && (
        <div>
          {anomaliesLoading && (
            <p style={{ color: "var(--text-muted)", fontSize: 14 }}>Loading anomalies…</p>
          )}
          {!anomaliesLoading && (!anomalies || anomalies.length === 0) && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "var(--text-muted)",
                fontSize: 14,
              }}
            >
              <Activity size={32} style={{ marginBottom: 12, opacity: 0.4 }} />
              <p>No open anomalies. All systems nominal.</p>
            </div>
          )}
          {anomalies?.map((anomaly) => (
            <AnomalyCard
              key={anomaly.id}
              anomaly={anomaly}
              onResolve={(id) => resolveAnomalyMutation.mutate(id)}
            />
          ))}
        </div>
      )}

      {activeTab === "regressions" && (
        <div>
          {regressionsLoading && (
            <p style={{ color: "var(--text-muted)", fontSize: 14 }}>
              Loading deployment regressions…
            </p>
          )}
          {!regressionsLoading && (!regressions || regressions.length === 0) && (
            <div
              style={{
                textAlign: "center",
                padding: "40px 0",
                color: "var(--text-muted)",
                fontSize: 14,
              }}
            >
              <GitCompare size={32} style={{ marginBottom: 12, opacity: 0.4 }} />
              <p>No unacknowledged deployment regressions.</p>
            </div>
          )}
          {regressions?.map((reg) => (
            <RegressionCard
              key={reg.id}
              regression={reg}
              onAcknowledge={(id) => ackRegressionMutation.mutate(id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
