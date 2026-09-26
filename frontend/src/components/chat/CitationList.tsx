import type { CitedRecord } from '@/types'
import { useState } from 'react'
import clsx from 'clsx'

interface Props {
  records: CitedRecord[]
}

export default function CitationList({ records }: Props) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="mt-3">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="text-[11px] text-muted hover:text-accent transition-colors flex items-center gap-1"
      >
        <span>{expanded ? '▾' : '▸'}</span>
        {records.length} source{records.length !== 1 ? 's' : ''}
      </button>

      {expanded && (
        <div className="mt-2 space-y-1.5">
          {records.map((r) => (
            <div
              key={r.id}
              className="bg-white border border-border rounded-md px-3 py-2 text-[12px]"
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-mono text-muted">[{r.id}]</span>
                <SeverityBadge severity={r.severity} />
                {r.service_name && (
                  <span className="text-muted">{r.service_name}</span>
                )}
                {r.timestamp && (
                  <span className="ml-auto text-muted text-[11px]">
                    {new Date(r.timestamp).toLocaleString()}
                  </span>
                )}
              </div>
              {r.message && (
                <p className="font-mono text-[11px] text-[#1f2328] truncate">{r.message}</p>
              )}
              {r.similarity_score !== null && (
                <span className="text-[10px] text-muted">
                  similarity {(r.similarity_score * 100).toFixed(1)}%
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const classes: Record<string, string> = {
    ERROR: 'badge-error',
    CRITICAL: 'badge-critical',
    FATAL: 'badge-critical',
    WARN: 'badge-warn',
    WARNING: 'badge-warn',
    INFO: 'badge-info',
    DEBUG: 'badge-debug',
  }
  return (
    <span className={clsx('text-[10px] font-semibold px-1.5 py-0.5 rounded uppercase', classes[severity] ?? 'badge-debug')}>
      {severity}
    </span>
  )
}
