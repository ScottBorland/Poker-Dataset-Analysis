// Shared poker-table visual: an oval table with seats arranged around it,
// used by Solved Spot, Fingerprint Hand Replay, and the interactive Hand
// Builder. Seat layout mirrors the pygame replayer (seat 0 at the bottom,
// clockwise). Optionally interactive: pass onSeatClick / onSeatCardsClick /
// onBoardClick and the corresponding elements become clickable (used by the
// Hand Builder to select a hero seat and open card pickers); omit them and
// the table is a pure display, as before.

const SUIT_SYMBOLS: Record<string, string> = { h: '♥', d: '♦', c: '♣', s: '♠' }
const SUIT_COLORS: Record<string, string> = { h: '#dc2626', d: '#dc2626', c: '#1f2937', s: '#1f2937' }

const W = 860
const H = 500
const CENTER = { x: W / 2, y: H / 2 }
const RX = 335
const RY = 175

function seatPosition(i: number, n: number) {
  const angle = Math.PI / 2 + (2 * Math.PI * i) / n // seat 0 at bottom, clockwise
  return {
    x: CENTER.x + RX * Math.cos(angle),
    y: CENTER.y + RY * Math.sin(angle),
  }
}

// Point between a seat and the table center, for bet chips.
function betPosition(i: number, n: number) {
  const angle = Math.PI / 2 + (2 * Math.PI * i) / n
  return {
    x: CENTER.x + RX * 0.56 * Math.cos(angle),
    y: CENTER.y + RY * 0.5 * Math.sin(angle),
  }
}

const CARD_SIZES = {
  sm: { w: 54, h: 75, font: 22 },
  md: { w: 72, h: 100, font: 28 },
  lg: { w: 96, h: 135, font: 36 },
}

export function Card({ card, size = 'md' }: { card: string | null; size?: 'sm' | 'md' | 'lg' }) {
  const { w, h, font } = CARD_SIZES[size]
  if (!card) {
    return (
      <div
        style={{ width: w, height: h }}
        className="rounded-md border border-slate-500/40 bg-slate-700"
      />
    )
  }
  const rank = card[0]
  const suit = card[1]
  const color = SUIT_COLORS[suit] ?? '#1f2937'
  return (
    <div
      style={{ width: w, height: h, color }}
      className="rounded-md bg-white flex flex-col items-center justify-center font-semibold leading-none"
    >
      <span style={{ fontSize: font }}>{rank}</span>
      <span style={{ fontSize: font }}>{SUIT_SYMBOLS[suit] ?? suit}</span>
    </div>
  )
}

export interface SeatDisplay {
  seatIdx: number
  label: string
  holeCards: (string | null)[]
  stack: number | null
  bet: number | null
  folded: boolean
  isActing: boolean
  isHero: boolean
  isButton?: boolean
}

interface Props {
  seats: SeatDisplay[]
  board: string[]
  pot: number
  potLabel?: string
  lastAction?: string | null
  /** Interactive hooks — omit for a display-only table. */
  onSeatClick?: (seatIdx: number) => void
  onSeatCardsClick?: (seatIdx: number) => void
  onBoardClick?: () => void
  selectedSeat?: number | null
}

export function PokerTable({
  seats, board, pot, potLabel, lastAction,
  onSeatClick, onSeatCardsClick, onBoardClick, selectedSeat,
}: Props) {
  const n = Math.max(seats.length, 1)
  return (
    <div className="bg-slate-900 rounded-xl p-4">
      <div className="relative w-full" style={{ maxWidth: W, aspectRatio: `${W} / ${H}`, margin: '0 auto' }}>
        <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 w-full h-full">
          <defs>
            <radialGradient id="feltGrad" cx="50%" cy="42%" r="65%">
              <stop offset="0%" stopColor="#26504b" />
              <stop offset="100%" stopColor="#1f3d3a" />
            </radialGradient>
          </defs>
          <ellipse
            cx={CENTER.x} cy={CENTER.y} rx={RX - 34} ry={RY - 30}
            fill="url(#feltGrad)" stroke="#0d1a19" strokeWidth={8}
          />
          <ellipse
            cx={CENTER.x} cy={CENTER.y} rx={RX - 60} ry={RY - 52}
            fill="none" stroke="#ffffff14" strokeWidth={1.5}
          />
        </svg>

        {/* Board + pot */}
        <div
          className="absolute flex flex-col items-center gap-1.5"
          style={{ left: CENTER.x, top: CENTER.y - 26, transform: 'translate(-50%, -50%)' }}
        >
          <div
            className={`flex gap-1.5 ${onBoardClick ? 'cursor-pointer' : ''}`}
            onClick={onBoardClick}
            title={onBoardClick ? 'Set board cards' : undefined}
          >
            {board.map((c, i) => <Card key={i} card={c} size="md" />)}
            {Array.from({ length: Math.max(0, 5 - board.length) }).map((_, i) => (
              <div
                key={`ph-${i}`}
                style={{ width: CARD_SIZES.md.w, height: CARD_SIZES.md.h }}
                className={`rounded-md border border-dashed border-white/15 ${
                  onBoardClick ? 'hover:border-amber-300/60 hover:bg-white/5' : ''
                }`}
              />
            ))}
          </div>
          <div className="text-slate-100 text-sm font-medium bg-black/40 rounded-full px-3 py-0.5 whitespace-nowrap">
            {potLabel ?? `Pot ${pot.toFixed(2)}`}
          </div>
          {lastAction && (
            <div className="text-amber-200/90 text-[11px] bg-black/30 rounded-full px-2.5 py-0.5 max-w-[280px] text-center">
              {lastAction}
            </div>
          )}
        </div>

        {/* Bet chips */}
        {seats.map((seat, i) => {
          if (seat.bet == null || seat.bet <= 0) return null
          const { x, y } = betPosition(i, n)
          return (
            <div
              key={`bet-${seat.seatIdx}`}
              className="absolute flex items-center gap-1 bg-black/45 rounded-full pl-1 pr-2 py-0.5"
              style={{ left: x, top: y, transform: 'translate(-50%, -50%)' }}
            >
              <span className="w-3 h-3 rounded-full bg-amber-400 border border-amber-200 inline-block" />
              <span className="text-amber-100 text-[11px] font-semibold tabular-nums">
                {seat.bet.toFixed(seat.bet % 1 === 0 ? 0 : 2)}
              </span>
            </div>
          )
        })}

        {/* Seats */}
        {seats.map((seat, i) => {
          const { x, y } = seatPosition(i, n)
          const isSelected = selectedSeat === seat.seatIdx
          return (
            <div
              key={seat.seatIdx}
              className={`absolute flex flex-col items-center gap-1 rounded-xl ${seat.folded ? 'opacity-35' : ''} ${
                seat.isActing ? 'ring-4 ring-amber-400/70 bg-amber-400/10 px-2 py-1 shadow-[0_0_40px_rgba(251,191,36,0.5)]' : ''
              }`}
              style={{ left: x, top: y, transform: 'translate(-50%, -50%)' }}
            >
              {seat.isActing && (
                <div className="text-[13px] font-bold tracking-widest text-slate-900 bg-amber-400 border border-amber-200 rounded-full px-2.5 py-0.5 shadow-[0_0_16px_rgba(251,191,36,0.9)] animate-pulse">
                  TO ACT
                </div>
              )}
              <div
                className={`flex gap-1 rounded-lg p-0.5 ${
                  seat.isActing ? 'ring-4 ring-amber-400 shadow-[0_0_32px_rgba(251,191,36,0.95)]'
                  : isSelected ? 'ring-2 ring-teal-400' : ''
                } ${onSeatCardsClick ? 'cursor-pointer hover:ring-2 hover:ring-slate-400' : ''}`}
                onClick={onSeatCardsClick ? () => onSeatCardsClick(seat.seatIdx) : undefined}
                title={onSeatCardsClick ? 'Set hole cards' : undefined}
              >
                {seat.holeCards.map((c, ci) => <Card key={ci} card={c} size="sm" />)}
              </div>
              <div
                className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium whitespace-nowrap ${
                  seat.isActing
                    ? 'bg-amber-400 text-slate-900'
                    : seat.isHero
                    ? 'bg-teal-600 text-white'
                    : 'bg-slate-800 text-slate-200'
                } ${onSeatClick ? 'cursor-pointer hover:brightness-125' : ''}`}
                onClick={onSeatClick ? () => onSeatClick(seat.seatIdx) : undefined}
                title={onSeatClick ? 'Select this seat as hero' : undefined}
              >
                {seat.isButton && (
                  <span className="w-3.5 h-3.5 rounded-full bg-white text-slate-900 text-[9px] font-bold flex items-center justify-center">
                    D
                  </span>
                )}
                {seat.label}
              </div>
              <div className="text-[15px] font-bold text-white tabular-nums">
                {seat.stack != null ? seat.stack.toFixed(seat.stack % 1 === 0 ? 0 : 2) : '—'}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
