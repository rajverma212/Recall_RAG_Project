import { NavLink } from 'react-router-dom'
import { useDocuments } from '../hooks/useDocuments'

interface NavItem {
  to: string
  label: string
}

const NAV: NavItem[] = [
  { to: '/', label: 'Ask' },
  { to: '/documents', label: 'Documents' },
  { to: '/retrieval', label: 'Retrieval Inspector' },
  { to: '/evaluations', label: 'Evaluations' },
  { to: '/hallucination', label: 'Hallucination' },
  { to: '/analytics', label: 'Analytics' },
  { to: '/experiments', label: 'Experiments' },
  { to: '/prompts', label: 'Prompts' },
  { to: '/system', label: 'System' },
]

export function Sidebar() {
  const { data: documents } = useDocuments()
  const docCount = documents?.length ?? 0

  return (
    <aside className="flex h-screen w-52 flex-col bg-surface-950 px-3 py-5">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-2 pb-6">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-500">
          <span className="font-serif text-base italic leading-none text-surface-900">R</span>
        </div>
        <span className="text-sm font-bold tracking-tight text-slate-100">Recall</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto">
        <div className="space-y-0.5">
          {NAV.map((item, i) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `group flex items-center gap-3 rounded-[9px] px-3 py-2 text-[13px] transition-colors ${
                  isActive
                    ? 'bg-accent-500/[0.12] font-semibold text-accent-500'
                    : 'font-medium text-slate-600 hover:bg-surface-800 hover:text-slate-100'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`font-serif text-[13px] italic ${
                      isActive ? 'text-accent-500' : 'text-accent-500/50'
                    }`}
                  >
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  {item.label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Corpus footer badge */}
      <div className="mt-4 rounded-[9px] bg-surface-850 px-3.5 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-success-400 animate-pulse-dot" />
          </span>
          <span className="section-label">Production</span>
        </div>
        <p className="mt-1.5 text-[13px] font-semibold text-slate-100">
          {docCount} {docCount === 1 ? 'document' : 'documents'}
        </p>
      </div>
    </aside>
  )
}
