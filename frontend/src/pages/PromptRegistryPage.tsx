import { useState } from 'react'
import { usePrompts } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import { FileCode, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react'
import type { PromptVersion } from '../lib/types'

function PromptCard({ prompt }: { prompt: PromptVersion }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className={`rounded-xl border ${
        prompt.is_active
          ? 'border-accent-500/40 bg-accent-500/5'
          : 'border-slate-700/50 bg-surface-850'
      }`}
    >
      <button
        className="w-full flex items-start gap-3 px-5 py-4 text-left"
        onClick={() => setExpanded((o) => !o)}
      >
        <FileCode
          size={16}
          className={`flex-shrink-0 mt-0.5 ${prompt.is_active ? 'text-accent-400' : 'text-slate-500'}`}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-slate-200">{prompt.name}</p>
            {prompt.is_active && (
              <span className="flex items-center gap-0.5 rounded-full bg-accent-500/20 px-2 py-0.5 text-[10px] font-semibold text-accent-400 uppercase tracking-wide">
                <CheckCircle size={10} className="mr-0.5" />
                Active
              </span>
            )}
            <span className="rounded-md bg-surface-900 px-2 py-0.5 text-[10px] font-mono text-slate-500">
              v{prompt.version}
            </span>
          </div>
          {prompt.description && (
            <p className="mt-1 text-xs text-slate-500">{prompt.description}</p>
          )}
        </div>
        <span className="flex-shrink-0 text-slate-600 mt-0.5">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-slate-800 px-5 py-4">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
            System Prompt
          </p>
          <pre className="rounded-lg bg-surface-900 p-4 text-[11px] font-mono text-slate-400 whitespace-pre-wrap overflow-x-auto max-h-80 overflow-y-auto leading-relaxed">
            {prompt.system_prompt}
          </pre>
        </div>
      )}
    </div>
  )
}

export function PromptRegistryPage() {
  const { data: prompts, isLoading, error } = usePrompts()

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-slate-700/50 px-6 py-4">
        <div className="flex items-center gap-2">
          <FileCode size={18} className="text-accent-400" />
          <h1 className="text-lg font-semibold text-slate-100">Prompt Registry</h1>
        </div>
        <p className="text-xs text-slate-500 mt-0.5">
          Browse versioned system prompts and their active status
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
        {isLoading && (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-sm text-danger-400">
            {error.message}
          </div>
        )}

        {!isLoading && !error && (!prompts || prompts.length === 0) && (
          <EmptyState
            icon={<FileCode size={28} />}
            title="No prompt versions"
            description="Prompt versions will appear here once configured via the API."
          />
        )}

        {prompts && prompts.length > 0 && (
          <>
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-500">
                {prompts.length} version{prompts.length !== 1 ? 's' : ''} ·{' '}
                {prompts.filter((p) => p.is_active).length} active
              </p>
            </div>
            <div className="space-y-3">
              {prompts.map((p: PromptVersion) => (
                <PromptCard key={p.version} prompt={p} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
