import { useCallback, useState } from 'react'
import { Upload, Trash2, FileText, ChevronDown } from 'lucide-react'
import { useDocuments, useIngest, useDeleteDocument } from '../hooks'
import { StatusBadge } from '../components/StatusBadge'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { ChunkingStrategy } from '../lib/types'

const STRATEGIES: ChunkingStrategy[] = ['fixed', 'recursive', 'semantic']

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
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed py-10 px-6 text-center transition-colors ${
        dragging
          ? 'border-accent-500 bg-accent-500/10'
          : 'border-slate-700/60 hover:border-slate-600 hover:bg-surface-800/40'
      } ${disabled ? 'pointer-events-none opacity-50' : ''}`}
    >
      <Upload size={24} className="mb-3 text-slate-500" />
      <p className="text-sm font-medium text-slate-300">
        Drag & drop files here, or{' '}
        <span className="text-accent-400">click to browse</span>
      </p>
      <p className="mt-1 text-xs text-slate-500">PDF, TXT, DOCX supported</p>
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
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-700/50 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Documents</h1>
        <p className="text-xs text-slate-500 mt-0.5">Manage your indexed document corpus</p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Upload area */}
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-slate-400">Chunking strategy</label>
            <div className="relative">
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as ChunkingStrategy)}
                className="appearance-none rounded-lg border border-slate-700/60 bg-surface-850 py-1.5 pl-3 pr-7 text-xs text-slate-300 outline-none focus:border-accent-500/60"
              >
                {STRATEGIES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <ChevronDown size={12} className="pointer-events-none absolute right-2 top-2 text-slate-500" />
            </div>
          </div>
          <DropZone onFiles={handleFiles} disabled={ingest.isPending} />
          {ingest.isPending && (
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Spinner size="sm" /> Uploading and ingesting...
            </div>
          )}
          {ingest.data && (
            <div className="rounded-lg border border-success-400/30 bg-success-900/20 px-3 py-2 text-xs text-success-400">
              Ingested <strong>{ingest.data.filename}</strong> — {ingest.data.num_chunks} chunks
              {ingest.data.num_duplicates_skipped > 0 && `, ${ingest.data.num_duplicates_skipped} duplicates skipped`}
            </div>
          )}
          {ingest.error && (
            <div className="rounded-lg border border-danger-400/30 bg-danger-900/20 px-3 py-2 text-xs text-danger-400">
              {ingest.error.message}
            </div>
          )}
        </div>

        {/* Documents table */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Indexed Documents
              {docs && <span className="ml-1.5 text-slate-600">({docs.length})</span>}
            </h2>
          </div>

          {isLoading && (
            <div className="flex justify-center py-10">
              <Spinner />
            </div>
          )}
          {error && (
            <p className="text-sm text-danger-400">{error.message}</p>
          )}
          {docs && docs.length === 0 && (
            <EmptyState
              icon={<FileText size={28} />}
              title="No documents yet"
              description="Upload files above to begin indexing."
            />
          )}
          {docs && docs.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-slate-700/50">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/50 bg-surface-900">
                    {['Filename', 'Status', 'Chunks', 'Strategy', 'Pages', 'Ingested'].map((h) => (
                      <th
                        key={h}
                        className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500"
                      >
                        {h}
                      </th>
                    ))}
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {docs.map((doc) => (
                    <tr key={doc.id} className="hover:bg-surface-800/40 transition-colors">
                      <td className="px-4 py-3 max-w-xs">
                        <div className="flex items-center gap-2">
                          <FileText size={13} className="flex-shrink-0 text-slate-500" />
                          <span className="truncate text-slate-200 text-xs font-medium">
                            {doc.title ?? doc.filename}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={doc.status} />
                      </td>
                      <td className="px-4 py-3 tabular-nums text-xs text-slate-400">
                        {doc.num_chunks}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {doc.chunking_strategy ?? '—'}
                      </td>
                      <td className="px-4 py-3 tabular-nums text-xs text-slate-500">
                        {doc.num_pages ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {new Date(doc.ingested_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => deleteDoc.mutate(doc.id)}
                          disabled={deleteDoc.isPending}
                          className="rounded p-1 text-slate-600 hover:bg-danger-900/50 hover:text-danger-400 transition-colors"
                          aria-label="Delete document"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
