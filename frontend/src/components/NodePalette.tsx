import type { DragEvent } from 'react'

interface PaletteItem {
  type: string
  label: string
  icon: string
  accent: string
}

const ITEMS: PaletteItem[] = [
  { type: 'numPlayers', label: 'Players', icon: '👥', accent: 'border-orange-500 text-orange-400' },
  { type: 'holeCards', label: 'Hole Cards', icon: '🃏', accent: 'border-purple-500 text-purple-400' },
  { type: 'showdown', label: 'Showdown', icon: '🎯', accent: 'border-teal-500 text-teal-400' },
  { type: 'flopType', label: 'Flop Type', icon: '🂠', accent: 'border-green-500 text-green-400' },
  { type: 'preflopAction', label: 'Preflop Action', icon: '♠', accent: 'border-blue-500 text-blue-400' },
  { type: 'playerName', label: 'Player', icon: '🙋', accent: 'border-rose-500 text-rose-400' },
  { type: 'playerPosition', label: 'Position', icon: '🪑', accent: 'border-yellow-500 text-yellow-400' },
]

export function NodePalette() {
  function onDragStart(e: DragEvent<HTMLDivElement>, type: string) {
    e.dataTransfer.setData('application/reactflow', type)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div className="w-44 shrink-0 bg-gray-950 border-r border-gray-800 flex flex-col p-3 gap-2">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Filters</div>
      {ITEMS.map(item => (
        <div
          key={item.type}
          draggable
          onDragStart={e => onDragStart(e, item.type)}
          className={`flex items-center gap-2 px-2 py-2 rounded border bg-gray-900 cursor-grab active:cursor-grabbing select-none
            ${item.accent} hover:bg-gray-800 transition-colors`}
        >
          <span className="text-base leading-none">{item.icon}</span>
          <span className="text-xs font-medium text-gray-300">{item.label}</span>
        </div>
      ))}
      <div className="mt-auto text-xs text-gray-600 leading-relaxed">
        Drag a filter onto the canvas, connect nodes, then click <strong className="text-gray-500">Run Query</strong>.
      </div>
    </div>
  )
}
