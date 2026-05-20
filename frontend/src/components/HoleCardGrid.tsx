import { createPortal } from 'react-dom'
import { useEffect, useRef } from 'react'

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

function cellHand(row: number, col: number): string {
  if (row === col) return `${RANKS[row]}${RANKS[col]}`
  if (row < col) return `${RANKS[row]}${RANKS[col]}s`
  return `${RANKS[col]}${RANKS[row]}o`
}

function cellType(row: number, col: number): 'pair' | 'suited' | 'offsuit' {
  if (row === col) return 'pair'
  if (row < col) return 'suited'
  return 'offsuit'
}

interface Props {
  selected: string[]
  onChange: (hands: string[]) => void
  onClose: () => void
  anchorRect: DOMRect
}

export function HoleCardGrid({ selected, onChange, onClose, anchorRect }: Props) {
  const overlayRef = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (overlayRef.current && !overlayRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // small delay so the open-click doesn't immediately close it
    const id = setTimeout(() => document.addEventListener('mousedown', handler), 50)
    return () => {
      clearTimeout(id)
      document.removeEventListener('mousedown', handler)
    }
  }, [onClose])

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  function toggle(hand: string) {
    if (selected.includes(hand)) {
      onChange(selected.filter(h => h !== hand))
    } else {
      onChange([...selected, hand])
    }
  }

  const CELL = 28

  // Position the grid near the anchor but keep it on screen
  const top = Math.min(anchorRect.bottom + 8, window.innerHeight - RANKS.length * CELL - 80)
  const left = Math.min(anchorRect.left, window.innerWidth - RANKS.length * CELL - 24)

  return createPortal(
    <div
      ref={overlayRef}
      style={{ top, left, position: 'fixed', zIndex: 9999 }}
      className="bg-gray-900 border border-gray-700 rounded-lg shadow-2xl p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-white text-xs font-semibold">Select hole cards</span>
        <div className="flex gap-2">
          <button
            onClick={() => onChange(RANKS.flatMap((_, r) => RANKS.map((__, c) => cellHand(r, c))))}
            className="text-xs text-indigo-400 hover:text-indigo-200"
          >
            All
          </button>
          <button onClick={() => onChange([])} className="text-xs text-gray-400 hover:text-gray-200">
            Clear
          </button>
          <button onClick={onClose} className="text-xs text-gray-400 hover:text-white ml-1">✕</button>
        </div>
      </div>

      {/* Column headers */}
      <div className="flex mb-0.5">
        <div style={{ width: CELL }} />
        {RANKS.map(r => (
          <div key={r} style={{ width: CELL }} className="text-center text-gray-500 text-xs font-mono">
            {r}
          </div>
        ))}
      </div>

      {RANKS.map((rowRank, ri) => (
        <div key={rowRank} className="flex">
          {/* Row header */}
          <div
            style={{ width: CELL, height: CELL }}
            className="flex items-center justify-center text-gray-500 text-xs font-mono"
          >
            {rowRank}
          </div>
          {RANKS.map((_, ci) => {
            const hand = cellHand(ri, ci)
            const type = cellType(ri, ci)
            const isSelected = selected.includes(hand)

            const baseColor = isSelected
              ? 'bg-amber-500 text-black border-amber-400'
              : type === 'pair'
              ? 'bg-gray-700 text-gray-200 border-gray-600 hover:bg-gray-600'
              : type === 'suited'
              ? 'bg-blue-950 text-blue-300 border-blue-900 hover:bg-blue-900'
              : 'bg-gray-800 text-gray-400 border-gray-700 hover:bg-gray-700'

            return (
              <button
                key={hand}
                title={hand}
                onClick={() => toggle(hand)}
                style={{ width: CELL, height: CELL }}
                className={`border text-xs font-mono transition-colors ${baseColor}`}
              >
                {ri === ci
                  ? RANKS[ri]
                  : ri < ci
                  ? 's'
                  : 'o'}
              </button>
            )
          })}
        </div>
      ))}

      <div className="mt-2 text-xs text-gray-500 flex gap-3">
        <span><span className="inline-block w-3 h-3 bg-amber-500 rounded-sm mr-1" />selected</span>
        <span><span className="inline-block w-3 h-3 bg-blue-950 rounded-sm mr-1 border border-blue-900" />suited</span>
        <span><span className="inline-block w-3 h-3 bg-gray-700 rounded-sm mr-1" />pair</span>
        <span><span className="inline-block w-3 h-3 bg-gray-800 rounded-sm mr-1" />offsuit</span>
      </div>
    </div>,
    document.body,
  )
}
