import { NavLink, useLocation } from 'react-router-dom'
import {
  BarChart2,
  BriefcaseBusiness,
  LayoutGrid,
  Monitor,
  Settings,
  Users,
} from 'lucide-react'

const PORTFOLIO_TABS = [
  { to: '/portfolio/overview', label: 'Overview' },
  { to: '/portfolio/positions', label: 'Open Positions' },
  { to: '/portfolio/history', label: 'Trade History' },
  { to: '/portfolio/orders', label: 'Order History' },
]

export default function Sidebar() {
  const location = useLocation()
  const inPortfolio = location.pathname.startsWith('/portfolio')

  return (
    <aside className="flex flex-col w-52 shrink-0 bg-bg-card border-r border-border h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-border">
        <span className="text-accent font-bold text-lg tracking-tight">QuantAgent</span>
        <span className="block text-text-muted text-xs mt-0.5">Dashboard</span>
      </div>

      <nav className="flex-1 py-4 space-y-0.5 px-2 overflow-y-auto">
        {/* Bots */}
        <NavLink
          to="/bots"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
            }`
          }
        >
          <LayoutGrid size={16} />
          Bots
        </NavLink>

        {/* Live Monitor */}
        <NavLink
          to="/live-monitor"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
            }`
          }
        >
          <Monitor size={16} />
          Live Monitor
        </NavLink>

        {/* Portfolio (with sub-tabs) */}
        <div>
          <NavLink
            to="/portfolio"
            className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              inPortfolio
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
            }`}
          >
            <BriefcaseBusiness size={16} />
            Portfolio
          </NavLink>

          {/* Sub-tabs — always visible */}
          <div className="ml-6 mt-0.5 space-y-0.5">
            {PORTFOLIO_TABS.map(tab => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) =>
                  `block px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    isActive
                      ? 'text-accent bg-accent/10'
                      : 'text-text-muted hover:text-text-secondary hover:bg-bg-elevated'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </div>
        </div>

        {/* Agents */}
        <NavLink
          to="/agents"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
            }`
          }
        >
          <Users size={16} />
          Agents
        </NavLink>

        {/* Breakdown */}
        <NavLink
          to="/breakdown"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
            }`
          }
        >
          <BarChart2 size={16} />
          Breakdown
        </NavLink>

        {/* Settings */}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              isActive
                ? 'bg-accent/15 text-accent'
                : 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary'
            }`
          }
        >
          <Settings size={16} />
          Settings
        </NavLink>
      </nav>

      <div className="px-4 py-3 border-t border-border">
        <span className="text-text-muted text-xs">Hyperliquid</span>
      </div>
    </aside>
  )
}
