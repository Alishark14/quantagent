import { NavLink } from 'react-router-dom'
import {
  BarChart2,
  LayoutGrid,
  List,
  Settings,
  TrendingUp,
  Users,
} from 'lucide-react'

const NAV = [
  { to: '/bots', icon: LayoutGrid, label: 'Bots' },
  { to: '/', icon: TrendingUp, label: 'Overview' },
  { to: '/trades', icon: List, label: 'Trades' },
  { to: '/agents', icon: Users, label: 'Agents' },
  { to: '/breakdown', icon: BarChart2, label: 'Breakdown' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  return (
    <aside className="flex flex-col w-52 shrink-0 bg-bg-card border-r border-border h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-border">
        <span className="text-accent font-bold text-lg tracking-tight">QuantAgent</span>
        <span className="block text-text-muted text-xs mt-0.5">Dashboard</span>
      </div>
      <nav className="flex-1 py-4 space-y-0.5 px-2">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-accent/15 text-accent'
                  : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-4 py-3 border-t border-border">
        <span className="text-text-muted text-xs">Deribit Testnet</span>
      </div>
    </aside>
  )
}
