import { useState } from 'react'
import type { SearchRequest, SearchFilters } from '@/types'
import clsx from 'clsx'

interface Props {
  filters: SearchFilters | undefined
  onChange: (req: Partial<SearchRequest>) => void
  values: Partial<SearchRequest>
}

const SEVERITIES = ['TRACE', 'DEBUG', 'INFO', 'WARN', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL']

export default function FilterPanel({ filters, onChange, values }: Props) {
  const [open, setOpen] = useState(false)

  const hasActiveFilters = !!(
    values.service_name || values.environment || values.severity?.length ||
    values.deployment_version || values.trace_id || values.time_from || values.time_to
  )

  return (
    <div className="border border-border rounded-lg">
      <button
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          'w-full flex items-center justify-between px-4 py-2.5 text-sm font-medium transition-colors',
          open ? 'rounded-t-lg' : 'rounded-lg',
          hasActiveFilters ? 'text-accent' : 'text-[#1f2328]'
        )}
      >
        <span>Filters {hasActiveFilters ? '(active)' : ''}</span>
        <span className="text-muted">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-4 grid grid-cols-2 gap-4">
          {/* Service */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Service</label>
            <select
              value={values.service_name ?? ''}
              onChange={(e) => onChange({ service_name: e.target.value || undefined })}
              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
            >
              <option value="">Any</option>
              {filters?.services.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {/* Environment */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Environment</label>
            <select
              value={values.environment ?? ''}
              onChange={(e) => onChange({ environment: e.target.value || undefined })}
              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
            >
              <option value="">Any</option>
              {filters?.environments.map((e) => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>

          {/* Severity (multi-select) */}
          <div className="col-span-2">
            <label className="block text-xs font-medium text-muted mb-1">Severity</label>
            <div className="flex flex-wrap gap-1.5">
              {SEVERITIES.map((sev) => {
                const active = values.severity?.includes(sev)
                return (
                  <button
                    key={sev}
                    onClick={() => {
                      const current = values.severity ?? []
                      onChange({
                        severity: active
                          ? current.filter((s) => s !== sev)
                          : [...current, sev],
                      })
                    }}
                    className={clsx(
                      'text-xs px-2.5 py-1 rounded-full border transition-colors',
                      active
                        ? 'bg-accent text-white border-accent'
                        : 'border-border text-muted hover:border-accent/50'
                    )}
                  >
                    {sev}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Deployment version */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Deployment version</label>
            <select
              value={values.deployment_version ?? ''}
              onChange={(e) => onChange({ deployment_version: e.target.value || undefined })}
              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
            >
              <option value="">Any</option>
              {filters?.deployment_versions.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>

          {/* Trace ID */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1">Trace ID</label>
            <input
              type="text"
              value={values.trace_id ?? ''}
              onChange={(e) => onChange({ trace_id: e.target.value || undefined })}
              placeholder="e.g. abc123"
              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
            />
          </div>

          {/* Time range */}
          <div>
            <label className="block text-xs font-medium text-muted mb-1">From</label>
            <input
              type="datetime-local"
              value={values.time_from ?? ''}
              onChange={(e) => onChange({ time_from: e.target.value || undefined })}
              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted mb-1">To</label>
            <input
              type="datetime-local"
              value={values.time_to ?? ''}
              onChange={(e) => onChange({ time_to: e.target.value || undefined })}
              className="w-full border border-border rounded-md px-2 py-1.5 text-sm"
            />
          </div>

          {/* Clear */}
          {hasActiveFilters && (
            <div className="col-span-2 flex justify-end">
              <button
                onClick={() => onChange({
                  service_name: undefined, environment: undefined,
                  severity: undefined, deployment_version: undefined,
                  trace_id: undefined, time_from: undefined, time_to: undefined,
                })}
                className="text-xs text-muted hover:text-accent transition-colors"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
