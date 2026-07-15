import { useState } from 'react'
import { useExperiments, usePrompts } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import { StatusBadge } from '../components/StatusBadge'
import type { Experiment, PromptVersion } from '../lib/types'

function ExperimentCard({ exp }: { exp: Experiment }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-[14px] border border-surface-200 bg-surface-800">
      <button className="flex w-full items-start gap-3 px-5 py-4 text-left" onClick={() => setOpen((o) => !o)}>
        <div className="min-w-0 flex-1">
          <p className="text-[14px] font-semibold text-slate-100">{exp.name}</p>
          {exp.description && <p className="mt-0.5 truncate text-[12px] text-slate-400">{exp.description}</p>}
          <p className="mt-1 text-[10px] text-slate-600">{new Date(exp.created_at).toLocaleDateString()}</p>
        </div>
        {exp.metrics && (
          <div className="flex-shrink-0 space-y-0.5 text-right">
            {Object.entries(exp.metrics)
              .slice(0, 2)
              .map(([k, v]) => (
                <p key={k} className="text-[12px] tabular-nums text-slate-400">
                  <span className="text-slate-600">{k}: </span>
                  {(v * 100).toFixed(1)}%
                </p>
              ))}
          </div>
        )}
      </button>
      {open && (
        <div className="space-y-3 border-t border-surface-50 px-5 py-4">
          <p className="section-label">Config</p>
          <pre className="overflow-x-auto rounded-[10px] bg-surface-850 p-3 font-mono text-[11px] text-slate-400">
            {JSON.stringify(exp.config, null, 2)}
          </pre>
          {exp.metrics && (
            <>
              <p className="section-label">Metrics</p>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(exp.metrics).map(([k, v]) => (
                  <div key={k} className="rounded-[10px] bg-surface-850 px-3 py-2">
                    <p className="text-[10px] uppercase tracking-label text-slate-600">{k}</p>
                    <p className="font-serif text-[20px] tabular-nums text-slate-100">
                      {(v * 100).toFixed(1)}%
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function PromptCard({ prompt }: { prompt: PromptVersion }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      className={`rounded-[14px] border ${
        prompt.is_active ? 'border-accent-500/40 bg-accent-500/[0.05]' : 'border-surface-200 bg-surface-800'
      }`}
    >
      <button className="flex w-full items-start gap-3 px-5 py-4 text-left" onClick={() => setOpen((o) => !o)}>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-[14px] font-semibold text-slate-100">{prompt.name}</p>
            {prompt.is_active && (
              <span className="rounded-full bg-accent-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-500">
                Active
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[12px] text-slate-500">v{prompt.version}</p>
          {prompt.description && <p className="mt-1 truncate text-[12px] text-slate-600">{prompt.description}</p>}
        </div>
        <StatusBadge status={prompt.is_active ? 'ready' : 'processing'} />
      </button>
      {open && (
        <div className="border-t border-surface-50 px-5 py-4">
          <p className="section-label mb-2">System Prompt</p>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-[10px] bg-surface-850 p-3 font-mono text-[11px] text-slate-400">
            {prompt.system_prompt}
          </pre>
        </div>
      )}
    </div>
  )
}

export function ExperimentsPage() {
  const { data: experiments, isLoading: expLoading } = useExperiments()
  const { data: prompts, isLoading: promptsLoading } = usePrompts()
  const [tab, setTab] = useState<'experiments' | 'prompts'>('experiments')

  return (
    <div className="h-full overflow-y-auto px-8 py-7">
      <h1 className="text-[26px] font-bold leading-tight tracking-tight text-slate-100">
        Experiments &amp; Prompts
      </h1>
      <p className="mt-0.5 text-[13px] text-slate-400">Track experiments and manage prompt versions</p>

      {/* Tab bar */}
      <div className="mt-5 flex gap-1 border-b border-surface-200">
        {(['experiments', 'prompts'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2.5 text-[13px] font-medium capitalize transition-colors ${
              tab === t
                ? 'border-accent-500 text-accent-500'
                : 'border-transparent text-slate-500 hover:text-slate-100'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-4">
        {tab === 'experiments' && (
          <>
            {expLoading && (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            )}
            {!expLoading && (!experiments || experiments.length === 0) && (
              <EmptyState
                icon={<span className="font-serif text-[34px] italic">⚗</span>}
                title="No experiments yet"
                description="Experiments A/B-test different prompt or retrieval configurations and track which one answers more accurately. Create one via the API to see its variants and results here."
              />
            )}
            {experiments && experiments.length > 0 && (
              <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
                {experiments.map((exp) => (
                  <ExperimentCard key={exp.id} exp={exp} />
                ))}
              </div>
            )}
          </>
        )}

        {tab === 'prompts' && (
          <>
            {promptsLoading && (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            )}
            {!promptsLoading && (!prompts || prompts.length === 0) && (
              <EmptyState
                icon={<span className="font-serif text-[34px] italic">¶</span>}
                title="No prompt versions yet"
                description="Each version is a snapshot of the system prompt used to generate answers, so you can compare and roll back. Configure one via the API to see it here."
              />
            )}
            {prompts?.map((p) => <PromptCard key={p.version} prompt={p} />)}
          </>
        )}
      </div>
    </div>
  )
}
