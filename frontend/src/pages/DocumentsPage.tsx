import { useCallback, useState } from 'react'
import { useDocuments, useIngest, useDeleteDocument } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { ChunkingStrategy, Document } from '../lib/types'

const STRATEGIES: ChunkingStrategy[] = ['fixed', 'recursive', 'semantic']

// Document corpus states render as an amber "active" pill in the Ember system
// (ready/completed → amber), with processing/error keeping warn/danger tints.
function DocStatus({ status }: { status: string }) {
  const isReady = status === 'ready' || status === 'completed'
  const cls = isReady
    ? 'bg-accent-500/10 text-accent-500'
    : status === 'processing'
      ? 'bg-warning-400/10 text-warning-400'
      : status === 'error'
        ? 'bg-danger-400/10 text-danger-400'
        : 'bg-surface-200 text-slate-400'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {isReady ? 'completed' : status}
    </span>
  )
}

function DropZone({
  onFiles,
  disabled,
}: {
  onFiles: (files: File[]) => void
  disabled?: boolean
}) {
  const [dragging, setDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const files = Array.from(e.dataTransfer.files)
      if (files.length) onFiles(files)
    },
    [onFiles],
  )

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`relative flex cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[14px] border-[1.5px] border-dashed px-6 py-9 text-center transition-colors ${
        dragging
          ? 'border-accent-500 bg-accent-500/[0.06]'
          : 'border-[#38342e] bg-surface-800 hover:border-accent-500/50'
      } ${disabled ? 'pointer-events-none opacity-50' : ''}`}
    >
      {/* Subtle shimmer sweep */}
      <span className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2 -skew-x-12 animate-shimmer bg-gradient-to-r from-transparent via-white/[0.02] to-transparent" />
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-[12px] bg-accent-500/10 text-[18px] text-accent-500">
        ↑
      </div>
      <p className="text-[14px] font-semibold text-slate-100">Drag &amp; drop files here</p>
      <p className="mt-1 text-[13px] text-slate-400">
        or <span className="text-accent-500 underline">click to browse</span> — PDF, TXT, DOCX
        supported
      </p>
      <input
        type="file"
        multiple
        className="sr-only"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? [])
          if (files.length) onFiles(files)
          e.target.value = ''
        }}
        disabled={disabled}
      />
    </label>
  )
}

export function DocumentsPage() {
  const [strategy, setStrategy] = useState<ChunkingStrategy>('recursive')
  const { data: docs, isLoading, error } = useDocuments()
  const ingest = useIngest()
  const deleteDoc = useDeleteDocument()

  const handleFiles = useCallback(
    (files: File[]) => {
      for (const file of files) {
        ingest.mutate({ file, strategy })
      }
    },
    [ingest, strategy],
  )

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      {/* Top bar */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
            Documents
          </h1>
          <p className="mt-0.5 text-[13px] text-slate-400">Manage your indexed document corpus</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-[13px] text-slate-400">Chunking strategy</label>
          <div className="relative">
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as ChunkingStrategy)}
              className="appearance-none rounded-[10px] border border-surface-200 bg-surface-800 py-2 pl-3.5 pr-8 text-[13px] font-medium text-slate-100 outline-none focus:border-accent-500/60"
            >
              {STRATEGIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-accent-500">
              ▾
            </span>
          </div>
        </div>
      </div>

      {/* Upload area */}
      <DropZone onFiles={handleFiles} disabled={ingest.isPending} />
      {ingest.isPending && (
        <div className="mt-3 flex items-center gap-2 text-[13px] text-slate-400">
          <Spinner size="sm" /> Uploading and ingesting...
        </div>
      )}
      {ingest.data && (
        <div className="mt-3 rounded-[10px] border border-success-400/30 bg-success-900/20 px-3.5 py-2.5 text-[12px] text-success-400">
          Ingested <strong>{ingest.data.filename}</strong> — {ingest.data.num_chunks} chunks
          {ingest.data.num_duplicates_skipped > 0 &&
            `, ${ingest.data.num_duplicates_skipped} duplicates skipped`}
        </div>
      )}
      {ingest.error && (
        <div className="mt-3 rounded-[10px] border border-danger-400/30 bg-danger-900/20 px-3.5 py-2.5 text-[12px] text-danger-400">
          {ingest.error.message}
        </div>
      )}

      {/* Documents table */}
      <div className="mt-6 rounded-[14px] border border-surface-200 bg-surface-800">
        <div className="flex items-center gap-2 px-5 py-4">
          <h2 className="section-label">Indexed Documents</h2>
          {docs && (
            <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-accent-500/10 px-1.5 text-[11px] font-semibold text-accent-500">
              {docs.length}
            </span>
          )}
        </div>

        {isLoading && (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        )}
        {error && <p className="px-5 pb-5 text-[13px] text-danger-400">{error.message}</p>}
        {docs && docs.length === 0 && (
          <EmptyState
            icon={<span className="font-serif text-[34px] italic">▦</span>}
            title="No documents yet"
            description="Upload files above to begin indexing."
          />
        )}
        {docs && docs.length > 0 && (
          <table className="w-full">
            <thead>
              <tr className="border-b border-surface-50">
                {['Filename', 'Status', 'Chunks', 'Strategy', 'Pages', 'Ingested'].map((h) => (
                  <th
                    key={h}
                    className="px-5 py-2.5 text-left text-[10px] font-medium uppercase tracking-label text-slate-600"
                  >
                    {h}
                  </th>
                ))}
                <th className="px-5 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {docs.map((doc: Document) => (
                <tr
                  key={doc.id}
                  className="border-b border-surface-50 transition-colors last:border-0 hover:bg-surface-850"
                >
                  <td className="max-w-xs px-5 py-3.5">
                    <div className="flex items-center gap-2.5">
                      <span className="h-[18px] w-[14px] flex-shrink-0 rounded-[2px] border border-[#38342e] bg-surface-200" />
                      <span className="truncate text-[13px] text-slate-100">
                        {doc.title ?? doc.filename}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <DocStatus status={doc.status} />
                  </td>
                  <td className="px-5 py-3.5 text-[13px] tabular-nums text-slate-400">
                    {doc.num_chunks}
                  </td>
                  <td className="px-5 py-3.5 text-[13px] text-slate-400">
                    {doc.chunking_strategy ?? '—'}
                  </td>
                  <td className="px-5 py-3.5 text-[13px] tabular-nums text-slate-400">
                    {doc.num_pages ?? '—'}
                  </td>
                  <td
                    className="px-5 py-3.5 text-[13px] text-slate-600"
                    title={new Date(doc.ingested_at).toLocaleString()}
                  >
                    {new Date(doc.ingested_at).toLocaleString(undefined, {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <button
                      onClick={() => deleteDoc.mutate(doc.id)}
                      disabled={deleteDoc.isPending}
                      className="text-[16px] leading-none text-slate-500 transition-colors hover:text-danger-400"
                      aria-label="Delete document"
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
