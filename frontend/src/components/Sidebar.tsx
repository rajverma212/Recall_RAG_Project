import { NavLink } from 'react-router-dom'
import {
  MessageSquare,
  Search,
  FileText,
  BarChart2,
  FlaskConical,
  Activity,
  Layers,
} from 'lucide-react'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
}

const NAV: NavItem[] = [
  { to: '/', label: 'Ask', icon: <MessageSquare size={18} /> },
  { to: '/retrieval', label: 'Retrieval Inspector', icon: <Search size={18} /> },
  { to: '/documents', label: 'Documents', icon: <FileText size={18} /> },
  { to: '/evaluations', label: 'Evaluations', icon: <BarChart2 size={18} /> },
  { to: '/analytics', label: 'Analytics', icon: <Activity size={18} /> },
  { to: '/experiments', label: 'Experiments', icon: <FlaskConical size={18} /> },
]

export function Sidebar() {
  return (
    <aside className="flex h-screen w-56 flex-col border-r border-slate-700/50 bg-surface-950">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-slate-700/50">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-500">
          <Layers size={14} className="text-white" />
        </div>
        <span className="text-sm font-bold tracking-tight text-slate-100">RAG Platform</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2">
        <div className="space-y-0.5">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-accent-500/15 text-accent-400'
                    : 'text-slate-400 hover:bg-surface-800 hover:text-slate-200'
                }`
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer */}
      <div className="border-t border-slate-700/50 px-4 py-3">
        <p className="text-[10px] font-medium uppercase tracking-wider text-slate-600">
          Production RAG
        </p>
      </div>
    </aside>
  )
}
