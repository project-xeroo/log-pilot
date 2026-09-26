import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchApi } from '@/api'
import type { SearchRequest, SearchResponse, SearchFilters } from '@/types'
import FilterPanel from '@/components/search/FilterPanel'
import ResultsTable from '@/components/search/ResultsTable'
import clsx from 'clsx'

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState<SearchRequest | null>(null)
  const [mode, setMode] = useState<'keyword' | 'semantic'>('keyword')
  const [filters, setFilters] = useState<Partial<SearchRequest>>({})

  // Fetch available filter options
  const { data: filterOptions } = useQuery<SearchFilters>({
    queryKey: ['search-filters'],
    queryFn: searchApi.getFilters,
    staleTime: 60_000,
  })

  // Run search only when form is submitted
  const { data: results, isFetching, error } = useQuery<SearchResponse>({
    queryKey: ['search', submitted],
    queryFn: () => searchApi.search(submitted!),
    enabled: !!submitted,
    staleTime: 0,
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return
    setSubmitted({ query: query.trim(), mode, ...filters })
  }

  const updateFilter = (patch: Partial<SearchRequest>) => {
    setFilters((f) => ({ ...f, ...patch }))
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Search</h1>
        <p className="text-sm text-muted mt-0.5">
          Keyword (FTS + regex) or semantic (vector similarity) log search
        </p>
      </div>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="space-y-3 mb-6">
        {/* Mode toggle + input */}
        <div className="flex gap-2">
          <div className="flex border border-border rounded-lg overflow-hidden shrink-0">
            {(['keyword', 'semantic'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={clsx(
                  'px-3 py-2 text-xs font-medium capitalize transition-colors',
                  mode === m ? 'bg-accent text-white' : 'text-muted hover:bg-surface'
                )}
              >
                {m}
              </button>
            ))}
          </div>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              mode === 'semantic'
                ? "Describe what you're looking for\u2026"
                : 'Keyword, phrase, or regex\u2026'
            }
            className="flex-1 border border-border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <button
            type="submit"
            disabled={!query.trim() || isFetching}
            className="bg-accent text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-accent/90 disabled:opacity-50 transition-colors"
          >
            {isFetching ? '…' : 'Search'}
          </button>
        </div>

        {/* Filter panel */}
        <FilterPanel
          filters={filterOptions}
          values={filters}
          onChange={updateFilter}
        />
      </form>

      {/* Results */}
      {error && (
        <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3 mb-4">
          Search failed. Please try again.
        </div>
      )}

      {isFetching && (
        <div className="text-sm text-muted py-8 text-center animate-pulse">Searching…</div>
      )}

      {results && !isFetching && (
        <ResultsTable
          results={results.results}
          total={results.total}
          latency_ms={results.latency_ms}
        />
      )}

      {!results && !isFetching && !submitted && (
        <div className="text-center py-16 text-muted">
          <p className="text-3xl mb-3">🔍</p>
          <p className="font-medium">Enter a query to search your logs.</p>
          <p className="text-sm mt-1">
            Use <strong>keyword</strong> for exact text / regex,{' '}
            <strong>semantic</strong> for meaning-based search.
          </p>
        </div>
      )}
    </div>
  )
}
