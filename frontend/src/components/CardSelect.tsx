// Single-card rank+suit dropdown pair, shared by ExactCardPicker (hole cards)
// and BoardCardsPicker (flop/turn/river).

const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
const SUITS = ['h', 'd', 'c', 's']
const SUIT_LABEL: Record<string, string> = { h: '♥ h', d: '♦ d', c: '♣ c', s: '♠ s' }

interface Props {
  value: string | null
  onChange: (card: string | null) => void
  disabledCards?: string[]
  label?: string
}

export function CardSelect({ value, onChange, disabledCards = [], label }: Props) {
  const disabled = new Set(disabledCards)
  const rank = value ? value[0] : ''
  const suit = value ? value[1] : ''

  function setCard(nextRank: string, nextSuit: string) {
    onChange(nextRank && nextSuit ? `${nextRank}${nextSuit}` : null)
  }

  return (
    <div className="flex flex-col gap-1">
      {label && <label className="text-xs text-gray-500">{label}</label>}
      <div className="flex gap-1">
        <select
          value={rank}
          onChange={e => setCard(e.target.value, suit || 'h')}
          className="border border-gray-300 rounded px-1.5 py-1 text-sm bg-white"
        >
          <option value="">–</option>
          {RANKS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <select
          value={suit}
          onChange={e => setCard(rank || 'A', e.target.value)}
          className="border border-gray-300 rounded px-1.5 py-1 text-sm bg-white"
        >
          <option value="">–</option>
          {SUITS.map(s => {
            const card = `${rank || '?'}${s}`
            const isDisabled = disabled.has(card)
            return <option key={s} value={s} disabled={isDisabled}>{SUIT_LABEL[s]}</option>
          })}
        </select>
      </div>
    </div>
  )
}
