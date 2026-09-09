import { CardSelect } from './CardSelect'

interface Props {
  value: [string | null, string | null]
  onChange: (value: [string | null, string | null]) => void
  disabledCards?: string[]
}

export function ExactCardPicker({ value, onChange, disabledCards = [] }: Props) {
  function setCard(idx: 0 | 1, card: string | null) {
    const next: [string | null, string | null] = [...value]
    next[idx] = card
    onChange(next)
  }

  return (
    <div className="flex gap-4">
      {([0, 1] as const).map(idx => {
        const otherCard = value[1 - idx]
        return (
          <CardSelect
            key={idx}
            label={`Card ${idx + 1}`}
            value={value[idx]}
            onChange={card => setCard(idx, card)}
            disabledCards={otherCard ? [...disabledCards, otherCard] : disabledCards}
          />
        )
      })}
    </div>
  )
}
