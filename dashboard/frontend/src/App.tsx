import { useState, useEffect, useCallback } from 'react'
import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Header from './components/layout/Header'
import Overview from './pages/Overview'
import Trades from './pages/Trades'
import Agents from './pages/Agents'
import Breakdown from './pages/Breakdown'
import Settings from './pages/Settings'
import Bots from './pages/Bots'
import BotDetail from './pages/BotDetail'

const AUTO_REFRESH_MS = 30_000

export default function App() {
  const [refreshTick, setRefreshTick] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const refresh = useCallback(() => {
    setRefreshing(true)
    setRefreshTick(t => t + 1)
    setLastRefresh(new Date())
    setTimeout(() => setRefreshing(false), 600)
  }, [])

  // Initial load
  useEffect(() => { refresh() }, [])

  // Auto-refresh
  useEffect(() => {
    const id = setInterval(refresh, AUTO_REFRESH_MS)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <div className="flex h-screen bg-bg-main text-text-primary overflow-hidden">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header lastRefresh={lastRefresh} onRefresh={refresh} refreshing={refreshing} />
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route path="/bots" element={<Bots refreshTick={refreshTick} />} />
            <Route path="/bots/:id" element={<BotDetail refreshTick={refreshTick} />} />
            <Route path="/" element={<Overview refreshTick={refreshTick} />} />
            <Route path="/trades" element={<Trades refreshTick={refreshTick} />} />
            <Route path="/agents" element={<Agents refreshTick={refreshTick} />} />
            <Route path="/breakdown" element={<Breakdown refreshTick={refreshTick} />} />
            <Route path="/settings" element={<Settings refreshTick={refreshTick} />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
