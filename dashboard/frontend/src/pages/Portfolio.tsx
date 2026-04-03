import { NavLink, Routes, Route, Navigate } from 'react-router-dom'
import PortfolioOverview from './portfolio/PortfolioOverview'
import OpenPositions from './portfolio/OpenPositions'
import TradeHistory from './portfolio/TradeHistory'
import OrderHistory from './portfolio/OrderHistory'

interface Props {
  refreshTick: number
}

const TABS = [
  { to: '/portfolio/overview', label: 'Overview' },
  { to: '/portfolio/positions', label: 'Open Positions' },
  { to: '/portfolio/history', label: 'Trade History' },
  { to: '/portfolio/orders', label: 'Order History' },
]

export default function Portfolio({ refreshTick }: Props) {
  return (
    <div className="space-y-5">
      {/* Sub-tab bar */}
      <div className="flex items-center gap-1 border-b border-border">
        {TABS.map(tab => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
                isActive
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </div>

      {/* Sub-page content */}
      <Routes>
        <Route path="overview" element={<PortfolioOverview refreshTick={refreshTick} />} />
        <Route path="positions" element={<OpenPositions />} />
        <Route path="history" element={<TradeHistory refreshTick={refreshTick} />} />
        <Route path="orders" element={<OrderHistory />} />
        <Route path="" element={<Navigate to="/portfolio/overview" replace />} />
        <Route path="*" element={<Navigate to="/portfolio/overview" replace />} />
      </Routes>
    </div>
  )
}
