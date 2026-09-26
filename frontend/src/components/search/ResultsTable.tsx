import type { LogRecordResult } from '@/types'
import clsx from 'clsx'

interface Props {
  results: LogRecordResult[]
  latency_ms?: number
  total: number
}

const SEVERITY_CLASS: Record<string, string> = {
  ERROR: 'badge-error',
  CRITICAL: 'badge-critical',
  FATAL: 'badge-critical',
  WARN: 'badge-warn',
  WARNING: 'badge-warn',
  INFO: 'badge-info',
  DEBUG: 'badge-debug',
  TRACE: 'badge-debug',
}

export default function ResultsTable({ results, latency_ms, total }: Props) {
  if (results.length === 0) {
    return (
      <div className="text-center py-16 text-muted">
        <p className="font-medium">No results found.</p>
        <p className="text-sm mt-1">Try adjusting your query or filters.</p>
      </div>
    )
  }

  return (
    <div>
      {/* Stats bar */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm text-muted">
          {total.toLocaleString()} result{total !== 1 ? 's' : ''}
        </span>
        {latency_ms !== undefined && (
          <span className="text-xs text-muted">{latency_ms.toFixed(0)} ms</span>
        )}
      </div>

      {/* Rows */}
      <div className="space-y-2">
        {results.map((r) => (
          <div key={r.id} className="card hover:border-accent/30 transition-colors">
            {/* Header */}
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span
                className={clsx(
                  'text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase',
                  SEVERITY_CLASS[r.severity] ?? 'badge-debug'
                )}
              >
                {r.severity}
              </span>
              {r.service_name && (
                <span className="text-xs text-muted font-medium">{r.service_name}</span>
              )}
              {r.environment && (
                <span className="text-xs text-muted">{r.environment}</span>
              )}
              {r.timestamp && (
                <span className="ml-auto text-xs text-muted">
                  {new Date(r.timestamp).toLocaleString()}
                </span>
              )}
              {r.similarity_score !== null && (
                <span className="text-[10px] text-muted ml-1">
                  {(r.similarity_score * 100).toFixed(1)}% match
                </span>
              )}
            </div>

            {/* Message */}
            {r.message && (
              <p className="font-mono text-[12px] text-[#1f2328] break-all leading-relaxed">
                {r.message}
              </p>
            )}

            {/* Metadata pills */}
            <div className="flex flex-wrap gap-2 mt-2">
              {r.trace_id && (
                <MetaPill label="trace" value={r.trace_id} />
              )}
              {r.request_id && (
                <MetaPill label="req" value={r.request_id} />
              )}
              {r.http_method && r.http_path && (
                <MetaPill label="http" value={`${r.http_method} ${r.http_path}`} />
              )}
              {r.http_status && (
                <MetaPill label="status" value={String(r.http_status)} />
              )}
              {r.deployment_version && (
                <MetaPill label="ver" value={r.deployment_version} />
              )}
              {r.pii_was_redacted && (
                <MetaPill label="pii" value="redacted" />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function MetaPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] text-muted border border-border rounded px-1.5 py-0.5">
      <span className="text-[9px] uppercase tracking-wide font-semibold">{label}</span>
      <span className="font-mono truncate max-w-[200px]">{value}</span>
    </span>
  )
}
