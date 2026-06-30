import { useState } from 'react'
import { usePrompts } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import type { PromptVersion } from '../lib/types'

function PromptCard({ prompt }: { prompt: PromptVersion }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      className={`rounded-[14px] border ${
        prompt.is_active ? 'border-accent-500/40 bg-accent-500/[0.05]' : 'border-surface-200 bg-surface-800'
      }`}
    >
      <button
        className="flex w-full items-start gap-3 px-5 py-4 text-left"
        onClick={() => setExpanded((o) => !o)}
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[14px] font-semibold text-slate-100">{prompt.name}</p>
            {prompt.is_active && (
              <span className="rounded-full bg-accent-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-500">
                Active
              </span>
            )}
            <span className="rounded-md bg-surface-850 px-2 py-0.5 font-mono text-[10px] text-slate-500">
              v{prompt.version}
            </span>
          </div>
          {prompt.description && <p className="mt-1 text-[12px] text-slate-400">{prompt.description}</p>}
        </div>
        <span className="mt-0.5 flex-shrink-0 font-serif text-[17px] italic text-accent-500">
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-surface-50 px-5 py-4">
          <p className="section-label mb-2">System Prompt</p>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-[10px] bg-surface-850 p-4 font-mono text-[11px] leading-relaxed text-slate-400">
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
    <div className="h-full overflow-y-auto px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
        Prompt Registry
      </h1>
      <p className="mt-0.5 text-[13px] text-slate-400">
        Browse versioned system prompts and their active status
      </p>

      <div className="mt-6 space-y-4">
        {isLoading && (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        )}

        {error && (
          <div className="rounded-[10px] border border-danger-400/30 bg-danger-900/30 px-4 py-3 text-[13px] text-danger-400">
            {error.message}
          </div>
        )}

        {!isLoading && !error && (!prompts || prompts.length === 0) && (
          <EmptyState
            icon={<span className="font-serif text-[34px] italic">¶</span>}
            title="No prompt versions"
            description="Prompt versions will appear here once configured via the API."
          />
        )}

        {prompts && prompts.length > 0 && (
          <>
            <p className="section-label">
              {prompts.length} version{prompts.length !== 1 ? 's' : ''} ·{' '}
              {prompts.filter((p) => p.is_active).length} active
            </p>
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
