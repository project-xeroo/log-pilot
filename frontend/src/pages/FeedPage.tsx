import { useEffect } from 'react'
import { useFeedStore } from '@/store/feedStore'
import FeedCard from '@/components/alerts/FeedCard'

export default function FeedPage() {
  const { entries, total, isLoading, fetchFeed, fetchUnread, markRead } = useFeedStore()

  useEffect(() => {
    fetchFeed({ limit: 50 })
    fetchUnread()
  }, [fetchFeed, fetchUnread])

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Agent Feed</h1>
          <p className="text-sm text-muted mt-0.5">
            What the agent has noticed, said, or drafted
          </p>
        </div>
        {total > 0 && (
          <span className="text-sm text-muted">{total} entries</span>
        )}
      </div>

      {/* Loading */}
      {isLoading && entries.length === 0 && (
        <div className="text-sm text-muted py-12 text-center">Loading…</div>
      )}

      {/* Empty */}
      {!isLoading && entries.length === 0 && (
        <div className="text-center py-16 text-muted">
          <p className="text-4xl mb-3">⚡</p>
          <p className="font-medium">No agent activity yet.</p>
          <p className="text-sm mt-1">Ingest some logs to get started.</p>
        </div>
      )}

      {/* Feed entries */}
      <div className="space-y-3">
        {entries.map((entry) => (
          <FeedCard
            key={entry.id}
            entry={entry}
            onRead={markRead}
          />
        ))}
      </div>

      {/* Load more */}
      {entries.length < total && (
        <div className="mt-6 text-center">
          <button
            onClick={() => fetchFeed({ limit: 50, offset: entries.length })}
            className="text-sm text-accent hover:underline"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  )
}
