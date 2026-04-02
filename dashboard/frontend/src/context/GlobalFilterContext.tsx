import { createContext, useContext, useState } from 'react'

export type Mode = 'all' | 'paper' | 'live'

interface GlobalFilter {
  mode: Mode
  setMode: (m: Mode) => void
}

const GlobalFilterContext = createContext<GlobalFilter>({
  mode: 'all',
  setMode: () => {},
})

export function GlobalFilterProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<Mode>('all')
  return (
    <GlobalFilterContext.Provider value={{ mode, setMode }}>
      {children}
    </GlobalFilterContext.Provider>
  )
}

export const useGlobalFilter = () => useContext(GlobalFilterContext)
