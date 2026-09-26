import type { FeedEntry, FeedEntryType } from '@/types'
import { formatDistanceToNow } from 'date-fns'
import clsx from 'clsx'

const TYPE_META: Record<FeedEntryType, { label: string; dot: string }> = {
  anomaly_detected:    { label: 'Anomaly',    dot: 'bg-red-400' },
  risk_score_updated:  { label: 'Risk Score', dot: 'bg-orange-400' },
  chat_answer:         { label: 'Chat',        dot: 'bg-accent' },
  ingestion_completed: { label: 'Ingestion',   dot: 'bg-green-400' },
  alert_fired:         { label: 'Alert',       dot: 'bg-red-500' },
  report_drafted:      { label: 'Report',      dot: 'bg-purple-400' },
  agent_observation:   { label: 'Agent',       dot: 'bg-gray-400' },
}

interface Props {
  entry: FeedEntry
  onRead?: (id: number) => void
}

export default function FeedCard({ entry, onRead }: Props) {
  const meta = TYPE_META[entry.entry_type] ?? { label: entry.entry_type, dot: 'bg-gray-300' }
  const timeAgo = formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })

  return (
    <div
      className={clsx(
        'card transition-colors cursor-pointer',
        !entry.is_read && 'border-l-2 border-l-accent bg-accent/[0.02]'
      )}
      onClick={() => !entry.is_read && onRead?.(entry.id)}
    >
      <div className="flex items-start gap-3">
        {/* Dot */}
        <span className={clsx('mt-1.5 shrink-0 w-2 h-2 rounded-full', meta.dot)} />

        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-center gap-2 flex-wrap mb-0.5">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
              {meta.label}
            </span>
            {entry.service_name && (
              <span className="text-[11px] text-muted">· {entry.service_name}</span>
            )}
            {entry.risk_score !== null && entry.risk_score !== undefined && (
              <span
                className={clsx(
                  'text-[11px] font-semibold px-1.5 py-0.5 rounded',
                  entry.risk_score >= 80
                    ? 'bg-red-100 text-red-700'
                    : entry.risk_score >= 60
                    ? 'bg-orange-100 text-orange-700'
                    : 'bg-gray-100 text-gray-600'
                )}
              >
                Risk {Math.round(entry.risk_score)}
              </span>
            )}
            <span className="ml-auto text-[11px] text-muted shrink-0">{timeAgo}</span>
          </div>

          {/* Title */}
          <p className="text-sm font-medium text-[#1f2328] leading-snug">{entry.title}</p>

          {/* Body */}
          {entry.body && (
            <p className="mt-1 text-sm text-muted line-clamp-3 whitespace-pre-line">
              {entry.body}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
