import { useQuery } from "@tanstack/react-query";
import { listWeights } from "@/api";
import type { ForecastWeight } from "@/types";

function WeightBar({ value, max }: { value: number; max: number }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={{ background: "var(--surface2)", borderRadius: 4, height: 6, width: 120 }}>
      <div
        style={{
          height: 6,
          borderRadius: 4,
          width: `${pct}%`,
          background: value >= 1 ? "var(--success)" : "var(--danger)",
          transition: "width 0.3s",
        }}
      />
    </div>
  );
}

export default function WeightsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["weights"],
    queryFn: listWeights,
    refetchInterval: 10_000,  // poll every 10s to see live updates
  });

  const maxWeight = Math.max(...(data?.items.map((w) => w.weight) ?? [1]));

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20 }}>Forecasting Weights</h1>
        <p style={{ margin: 0, color: "var(--text-muted)", fontSize: 13 }}>
          Indicator weights updated in real-time from logged incident outcomes. Precision and recall
          improve as more outcomes are recorded.
        </p>
      </div>

      {isLoading && <p style={{ color: "var(--text-muted)" }}>Loading…</p>}

      {data && (
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
                {["Indicator", "Weight", "Precision", "Recall", "TP", "FP", "FN", "Total Fired"].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: "10px 16px",
                      textAlign: "left",
                      fontSize: 11,
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
              {data.items.map((w: ForecastWeight) => (
                <tr key={w.indicator_name} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td style={{ padding: "10px 16px", fontFamily: "monospace", fontSize: 13 }}>
                    {w.indicator_name}
                  </td>
                  <td style={{ padding: "10px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <WeightBar value={w.weight} max={maxWeight} />
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{w.weight.toFixed(3)}</span>
                    </div>
                  </td>
                  <td style={{ padding: "10px 16px", color: w.precision >= 0.7 ? "var(--success)" : "var(--warning)" }}>
                    {(w.precision * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: "10px 16px", color: w.recall >= 0.7 ? "var(--success)" : "var(--warning)" }}>
                    {(w.recall * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: "10px 16px", color: "var(--success)" }}>{w.true_positive_count}</td>
                  <td style={{ padding: "10px 16px", color: "var(--danger)" }}>{w.false_positive_count}</td>
                  <td style={{ padding: "10px 16px", color: "var(--warning)" }}>{w.false_negative_count}</td>
                  <td style={{ padding: "10px 16px", color: "var(--text-muted)" }}>{w.total_fired}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
                    No weights yet — log incident outcomes to begin training.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
