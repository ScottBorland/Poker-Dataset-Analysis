import type { DragEvent } from 'react'

interface PaletteItem {
  type: string
  label: string
  accent: string
}

const ITEMS: PaletteItem[] = [
  { type: 'venue',          label: 'Venue',          accent: 'border-indigo-400 text-indigo-600' },
  { type: 'numPlayers',     label: 'Players',         accent: 'border-orange-400 text-orange-600' },
  { type: 'holeCards',      label: 'Hole Cards',      accent: 'border-purple-400 text-purple-600' },
  { type: 'showdown',       label: 'Showdown',        accent: 'border-teal-400   text-teal-600'   },
  { type: 'flopType',       label: 'Flop Type',       accent: 'border-green-400  text-green-600'  },
  { type: 'preflopAction',  label: 'Preflop Action',  accent: 'border-blue-400   text-blue-600'   },
  { type: 'playerName',     label: 'Player',          accent: 'border-rose-400   text-rose-600'   },
  { type: 'playerPosition', label: 'Position',        accent: 'border-yellow-400 text-yellow-600' },
]

export function NodePalette() {
  function onDragStart(e: DragEvent<HTMLDivElement>, type: string) {
    e.dataTransfer.setData('application/reactflow', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="w-44 shrink-0 bg-white border-r border-gray-200 flex flex-col p-3 gap-2">
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Filters</div>
      {ITEMS.map(item => (
        <div
          key={item.type}
          draggable
          onDragStart={e => onDragStart(e, item.type)}
          className={`flex items-center px-2 py-2 rounded border bg-white cursor-grab active:cursor-grabbing select-none
            ${item.accent} hover:bg-gray-50 transition-colors`}
        >
          <span className="text-xs font-medium text-gray-700">{item.label}</span>
        </div>
      ))}
      <div className="mt-auto text-xs text-gray-400 leading-relaxed">
        Drag a filter onto the canvas, connect nodes, then click <strong className="text-gray-500">Run Query</strong>.
      </div>
    </div>
  )
}
