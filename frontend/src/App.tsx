import { useState } from 'react'
import HandBuilderPage, { SolverOpenArgs } from './pages/HandBuilderPage'
import SolverBrowsePage from './pages/SolverBrowsePage'
import SolverViewPage from './pages/SolverViewPage'
import { AppView } from './components/AppChrome'

// Lightweight view switch — no router. The Hand Builder (1b) is the home
// screen. The Solver tab (1c) opens on a list of every stored solution;
// picking one — or a "Open in solver" handoff from the builder — swaps in the
// Solver view for that spot. Re-clicking the Solver tab returns to the list.

export default function App() {
  const [view, setView] = useState<AppView>('builder')
  const [solverArgs, setSolverArgs] = useState<SolverOpenArgs | null>(null)

  function openSolver(args: SolverOpenArgs) {
    setSolverArgs(args)
    setView('solver')
  }

  function navigate(next: AppView) {
    // Re-clicking Solver while a spot is open drops back to the browse list.
    if (next === 'solver' && view === 'solver') setSolverArgs(null)
    setView(next)
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-ground text-ink">
      {view === 'solver' && solverArgs ? (
        <SolverViewPage
          args={solverArgs}
          view={view}
          onView={navigate}
        />
      ) : view === 'solver' ? (
        <SolverBrowsePage
          view={view}
          onView={navigate}
          onOpen={openSolver}
        />
      ) : (
        <HandBuilderPage
          view="builder"
          onView={navigate}
          onOpenSolver={openSolver}
        />
      )}
    </div>
  )
}
