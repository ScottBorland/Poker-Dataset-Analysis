// Modernist header bar: brand, route tabs, and a right-hand controls slot.
// 2px bottom rule; active tab carries a 3px accent bottom border.

import { ReactNode } from 'react'

export type AppView = 'builder' | 'solver'

interface Tab {
  view: AppView
  label: string
  enabled: boolean
}

export function AppChrome({
  view, onView, right,
}: {
  view: AppView
  onView: (v: AppView) => void
  right?: ReactNode
}) {
  const tabs: Tab[] = [
    { view: 'builder', label: 'Hand builder', enabled: true },
    { view: 'solver', label: 'Solver', enabled: true },
  ]
  return (
    <header className="flex items-stretch border-b-2 border-divider-strong bg-ground shrink-0">
      <div className="flex items-center px-5 border-r-2 border-divider-strong">
        <span className="font-extrabold text-[15px] tracking-brand uppercase">
          <span className="text-ink">Poker</span><span className="text-accent">Flow</span>
        </span>
      </div>

      <nav className="flex items-stretch">
        {tabs.map(t => {
          const active = view === t.view
          return (
            <button
              key={t.view}
              disabled={!t.enabled}
              onClick={() => t.enabled && onView(t.view)}
              className={`px-4 flex items-center border-r border-divider-mid uppercase
                ${active
                  ? 'font-extrabold text-[11px] tracking-seat text-ink border-b-[3px] border-b-accent'
                  : 'font-semibold text-[11px] tracking-seat text-ink-muted hover:text-ink'}
                disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-ink-muted`}
            >
              {t.label}
            </button>
          )
        })}
        {/* Parked routes — shown for parity with the handoff, not wired. */}
        {['Explorer', 'Query'].map(label => (
          <span
            key={label}
            className="px-4 flex items-center border-r border-divider-mid uppercase
              font-semibold text-[11px] tracking-seat text-ink-dim cursor-not-allowed"
            title="Parked — not wired in this build"
          >
            {label}
          </span>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3 px-5">{right}</div>
    </header>
  )
}
