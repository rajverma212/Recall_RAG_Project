import { useState } from 'react'
import { useExperiments, usePrompts } from '../hooks'
import { Spinner } from '../components/Spinner'
import { EmptyState } from '../components/EmptyState'
import { StatusBadge } from '../components/StatusBadge'
import { FlaskConical, CheckCircle } from 'lucide-react'
import type { Experiment, PromptVersion } from '../lib/types'

function ExperimentCard({ exp }: { exp: Experiment }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-xl border border-slate-700/50 bg-surface-850">
      <button
        className="w-full flex items-start gap-3 px-4 py-4 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <FlaskConical size={16} className="flex-shrink-0 mt-0.5 text-accent-400" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-200">{exp.name}</p>
          {exp.description && (
            <p className="mt-0.5 text-xs text-slate-500 truncate">{exp.description}</p>
          )}
          <p className="mt-1 text-[10px] text-slate-600">
            {new Date(exp.created_at).toLocaleDateString()}
          </p>
        </div>
        {exp.metrics && (
          <div className="flex-shrink-0 text-right">
            {Object.entries(exp.metrics)
              .slice(0, 2)
              .map(([k, v]) => (
                <p key={k} className="text-xs tabular-nums text-slate-400">
                  <span className="text-slate-600">{k}: </span>
                  {(v * 100).toFixed(1)}%
                </p>
              ))}
          </div>
        )}
      </button>
      {open && (
        <div className="border-t border-slate-800 px-4 py-3 space-y-2">
          <p className="text-xs font-medium text-slate-500">Config</p>
          <pre className="rounded-lg bg-surface-900 p-3 text-[11px] font-mono text-slate-400 overflow-x-auto">
            {JSON.stringify(exp.config, null, 2)}
          </pre>
          {exp.metrics && (
            <>
              <p className="text-xs font-medium text-slate-500 mt-3">Metrics</p>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(exp.metrics).map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-surface-900 px-3 py-2">
                    <p className="text-[10px] text-slate-500 uppercase">{k}</p>
                    <p className="text-sm font-bold tabular-nums text-slate-200">
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
      className={`rounded-xl border ${prompt.is_active ? 'border-accent-500/40 bg-accent-500/5' : 'border-slate-700/50 bg-surface-850'}`}
    >
      <button
        className="w-full flex items-start gap-3 px-4 py-4 text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-slate-200">{prompt.name}</p>
            {prompt.is_active && (
              <span className="flex items-center gap-0.5 rounded-full bg-accent-500/20 px-2 py-0.5 text-[10px] font-medium text-accent-400">
                <CheckCircle size={10} /> Active
              </span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-500">v{prompt.version}</p>
          {prompt.description && (
            <p className="mt-1 text-xs text-slate-600 truncate">{prompt.description}</p>
          )}
        </div>
        <StatusBadge status={prompt.is_active ? 'ready' : 'processing'} />
      </button>
      {open && (
        <div className="border-t border-slate-800 px-4 py-3">
          <p className="text-xs font-medium text-slate-500 mb-2">System Prompt</p>
          <pre className="rounded-lg bg-surface-900 p-3 text-[11px] font-mono text-slate-400 whitespace-pre-wrap overflow-x-auto max-h-64 overflow-y-auto">
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
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-700/50 px-6 py-4">
        <h1 className="text-lg font-semibold text-slate-100">Experiments & Prompts</h1>
        <p className="text-xs text-slate-500 mt-0.5">Track experiments and manage prompt versions</p>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-slate-700/50 px-6">
        {(['experiments', 'prompts'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`capitalize px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === t
                ? 'border-accent-500 text-accent-400'
                : 'border-transparent text-slate-500 hover:text-slate-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
        {tab === 'experiments' && (
          <>
            {expLoading && (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            )}
            {!expLoading && (!experiments || experiments.length === 0) && (
              <EmptyState
                icon={<FlaskConical size={28} />}
                title="No experiments"
                description="Experiments will appear here once created via the API."
              />
            )}
            {experiments?.map((exp) => <ExperimentCard key={exp.id} exp={exp} />)}
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
                icon={<FlaskConical size={28} />}
                title="No prompt versions"
                description="Prompt versions will appear here once configured."
              />
            )}
            {prompts?.map((p) => <PromptCard key={p.version} prompt={p} />)}
          </>
        )}
      </div>
    </div>
  )
}
