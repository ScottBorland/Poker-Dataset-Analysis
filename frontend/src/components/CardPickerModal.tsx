// Popup card picker: a 4x13 grid of the full deck. Click cards to build the
// requested selection (2 hole cards, 3 flop cards, 1 turn/river card, ...).
// Cards already in use elsewhere are disabled; clicking an already-picked
// card unpicks it. Confirms automatically when `count` cards are picked.

import { useEffect, useState } from 'react'

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const SUITS = ['s', 'h', 'd', 'c']
const SUIT_SYMBOLS: Record<string, string> = { h: '♥', d: '♦', c: '♣', s: '♠' }
const SUIT_TEXT: Record<string, string> = { h: 'text-red-600', d: 'text-red-600', c: 'text-gray-900', s: 'text-gray-900' }

interface Props {
  title: string
  count: number
  initial?: (string | null)[]
  disabledCards?: string[]
  onConfirm: (cards: string[]) => void
  onCancel: () => void
}

export function CardPickerModal({ title, count, initial = [], disabledCards = [], onConfirm, onCancel }: Props) {
  const [picked, setPicked] = useState<string[]>(
    () => initial.filter((c): c is string => Boolean(c)).slice(0, count)
  )
  const disabled = new Set(disabledCards)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  function toggle(card: string) {
    // Compute the next selection outside the state updater — scheduling
    // onConfirm inside setPicked's updater fires it twice under React 18
    // StrictMode (updaters are double-invoked in dev).
    if (picked.includes(card)) {
      setPicked(picked.filter(c => c !== card))
      return
    }
    if (picked.length >= count) return
    const next = [...picked, card]
    setPicked(next)
    if (next.length === count) {
      // Let the selection render before closing so the click feels acknowledged.
      setTimeout(() => onConfirm(next), 120)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-xl shadow-2xl p-4 flex flex-col gap-3"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-8">
          <div className="text-sm font-semibold text-gray-800">{title}</div>
          <div className="text-xs text-gray-400">{picked.length} / {count} picked</div>
        </div>
        <div className="flex flex-col gap-1">
          {SUITS.map(suit => (
            <div key={suit} className="flex gap-1">
              {RANKS.map(rank => {
                const card = rank + suit
                const isPicked = picked.includes(card)
                const isDisabled = disabled.has(card) && !isPicked
                return (
                  <button
                    key={card}
                    disabled={isDisabled}
                    onClick={() => toggle(card)}
                    className={`w-9 h-12 rounded-md border text-sm font-semibold leading-none flex flex-col items-center justify-center gap-0.5 transition-colors ${
                      isPicked
                        ? 'bg-amber-400 border-amber-500 text-slate-900'
                        : isDisabled
                        ? 'bg-gray-100 border-gray-200 text-gray-300 cursor-not-allowed'
                        : `bg-white border-gray-300 hover:bg-gray-100 ${SUIT_TEXT[suit]}`
                    }`}
                  >
                    <span>{rank}</span>
                    <span className={isPicked ? '' : SUIT_TEXT[suit]}>{SUIT_SYMBOLS[suit]}</span>
                  </button>
                )
              })}
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={() => setPicked([])}
            className="px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100"
          >
            Clear
          </button>
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-xs border border-gray-300 rounded hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(picked)}
            disabled={picked.length !== count}
            className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded disabled:opacity-40 hover:bg-indigo-700"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
