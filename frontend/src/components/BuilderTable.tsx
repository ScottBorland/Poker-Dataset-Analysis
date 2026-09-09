// Diagrammatic seat grid for the Hand Builder (design_handoff 1b). No felt
// oval: seats sit on a 3x3 CSS grid, 2px gaps showing the ground through as
// rules; the centre cell is the board. Seats map to cells by position so the
// ring order stays readable as nPlayers changes.

import { PlayingCard } from './modernist'
import { Street } from '../utils/tableEngine'

export interface BuilderSeat {
  seatIdx: number
  position: string
  holeCards: (string | null)[]
  stack: number | null
  invested: number
  bet: number | null       // chips in this street
  toCall: number | null    // chips still owed (facing)
  folded: boolean
  revealedButFolded?: boolean
  isActing: boolean
  isHero: boolean
  isButton: boolean
}

// position name -> 3x3 cell index (4 = board). One map covers 2..6 players.
const CELL: Record<string, number> = { UTG: 0, HJ: 1, CO: 2, BB: 3, BTN: 5, SB: 7 }

const STREETS: Street[] = ['preflop', 'flop', 'turn', 'river']

interface Props {
  seats: BuilderSeat[]
  tableCaption: string       // 'TABLE · 6-MAX · 100 BB DEEP'
  board: string[]
  boardLabel: string         // 'BOARD · K-HIGH RAINBOW'
  potBB: number
  lastAction: string | null
  street: Street
  reachedStreets: Street[]
  onStreetClick?: (s: Street) => void
  onSeatClick?: (seatIdx: number) => void
  onSeatCardsClick?: (seatIdx: number) => void
  onBoardClick?: () => void
}

export function BuilderTable({
  seats, tableCaption, board, boardLabel, potBB, lastAction,
  street, reachedStreets, onStreetClick,
  onSeatClick, onSeatCardsClick, onBoardClick,
}: Props) {
  const byCell = new Map<number, BuilderSeat>()
  seats.forEach(s => {
    const c = CELL[s.position]
    if (c != null) byCell.set(c, s)
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="font-extrabold text-[11px] tracking-label uppercase text-ink-muted">
          {tableCaption}
        </div>
        <div className="inline-flex">
          {STREETS.map((s, i) => {
            const reached = reachedStreets.includes(s)
            const active = s === street
            const idx = STREETS.indexOf(s)
            const curIdx = STREETS.indexOf(street)
            return (
              <button
                key={s}
                disabled={!reached || !onStreetClick}
                onClick={() => onStreetClick?.(s)}
                className={`font-extrabold text-[10px] tracking-btn uppercase px-3 py-[6px]
                  border border-divider-strong ${i > 0 ? '-ml-px' : ''}
                  ${active ? 'bg-accent text-ground border-accent relative z-10'
                    : idx < curIdx ? 'text-ink-muted hover:bg-[rgba(243,242,242,.08)]'
                    : 'text-ink-dim'}
                  disabled:cursor-not-allowed`}
              >
                {s}
              </button>
            )
          })}
        </div>
      </div>

      <div
        className="grid gap-[2px] bg-[rgba(243,242,242,.45)] border-2 border-[rgba(243,242,242,.45)]"
        style={{ gridTemplateColumns: 'repeat(3, minmax(0,1fr))' }}
      >
        {Array.from({ length: 9 }).map((_, cell) => {
          if (cell === 4) {
            return (
              <BoardCell
                key="board"
                board={board} label={boardLabel} potBB={potBB}
                lastAction={lastAction} onBoardClick={onBoardClick}
              />
            )
          }
          const seat = byCell.get(cell)
          if (!seat) return <div key={cell} className="bg-ground min-h-[150px]" />
          return (
            <SeatCell
              key={cell}
              seat={seat}
              onSeatClick={onSeatClick}
              onSeatCardsClick={onSeatCardsClick}
            />
          )
        })}
      </div>
    </div>
  )
}

function SeatCell({
  seat, onSeatClick, onSeatCardsClick,
}: {
  seat: BuilderSeat
  onSeatClick?: (s: number) => void
  onSeatCardsClick?: (s: number) => void
}) {
  const ring = seat.isHero
    ? 'shadow-[inset_0_0_0_2px_#ff563c]'
    : seat.isActing
    ? 'shadow-[inset_0_0_0_4px_#f3f2f2,0_0_28px_rgba(243,242,242,.45)] bg-[rgba(243,242,242,.10)]'
    : ''
  const raised = seat.isHero || seat.isActing
  return (
    <div
      className={`px-4 py-4 flex flex-col gap-2 ${raised ? 'bg-surface' : 'bg-ground'} ${ring}
        ${onSeatClick ? 'cursor-pointer' : ''}`}
      onClick={onSeatClick ? () => onSeatClick(seat.seatIdx) : undefined}
      title={onSeatClick ? 'Select this seat as hero' : undefined}
    >
      <div className="flex items-center gap-1.5">
        <span className={`font-extrabold text-[11px] tracking-seat uppercase
          ${seat.folded ? 'text-ink-dim' : 'text-ink'}`}>
          {seat.position}
        </span>
        {seat.isHero && (
          <span className="bg-accent text-ground font-extrabold text-[9px] tracking-seat uppercase px-[5px] py-[2px]">
            Hero
          </span>
        )}
        {!seat.isHero && seat.isActing && (
          <span className="bg-ink text-ground font-extrabold text-[13px] tracking-seat uppercase px-[7px] py-[3px]">
            To act
          </span>
        )}
        {seat.isButton && (
          <span className="border border-divider-strong text-ink-muted font-extrabold text-[9px] px-[4px] leading-[14px]">
            D
          </span>
        )}
        <span className="ml-auto font-bold text-[15px] tabular-nums text-white">
          {seat.stack != null ? fmt(seat.stack) : '—'}
        </span>
      </div>

      {seat.folded ? (
        // Folded players show no cards — just the empty spacer keeps every
        // seat cell the same height so the grid rules stay aligned.
        <div className="h-[75px]" />
      ) : (
        <div
          className={`flex gap-[3px] w-fit ${onSeatCardsClick ? 'cursor-pointer hover:opacity-80' : ''}`}
          onClick={onSeatCardsClick
            ? e => { e.stopPropagation(); onSeatCardsClick(seat.seatIdx) }
            : undefined}
          title={onSeatCardsClick ? 'Click to set hole cards' : undefined}
        >
          {[0, 1].map(i => (
            <PlayingCard key={i} card={seat.holeCards[i]} live w={54} h={75} />
          ))}
        </div>
      )}

      <div className="h-3">
        {seat.folded ? (
          <span className="font-extrabold text-[10px] tracking-seat uppercase text-ink-dim">Folded</span>
        ) : seat.bet && seat.bet > 0 ? (
          <span className="font-extrabold text-[10px] tracking-seat uppercase text-accent-light">
            Bet {fmt(seat.bet)} BB
          </span>
        ) : seat.toCall && seat.toCall > 0 ? (
          <span className="font-extrabold text-[10px] tracking-seat uppercase text-white">
            Facing {fmt(seat.toCall)} BB
          </span>
        ) : null}
      </div>
    </div>
  )
}

function BoardCell({
  board, label, potBB, lastAction, onBoardClick,
}: {
  board: string[]
  label: string
  potBB: number
  lastAction: string | null
  onBoardClick?: () => void
}) {
  return (
    <div className="bg-surface px-4 py-4 flex flex-col gap-3">
      <div className="font-extrabold text-[11px] tracking-label uppercase text-ink-muted">{label}</div>
      <div className="flex gap-[4px]">
        {Array.from({ length: 5 }).map((_, i) => {
          const c = board[i]
          if (c) return <PlayingCard key={i} card={c} w={66} h={93} />
          return (
            <div
              key={i}
              onClick={i === board.length ? onBoardClick : undefined}
              style={{ width: 66, height: 93 }}
              className={`border-2 border-dashed border-surface-deep
                ${i === board.length && onBoardClick ? 'cursor-pointer hover:border-accent-light' : ''}`}
            />
          )
        })}
      </div>
      <div className="font-extrabold text-[26px] tracking-[-.02em] text-ink leading-none">
        POT {potBB.toFixed(2)} BB
      </div>
      {lastAction && (
        <div className="font-semibold text-[10px] uppercase tracking-seat text-ink-muted">
          Last: {lastAction}
        </div>
      )}
    </div>
  )
}

function fmt(n: number): string {
  return n % 1 === 0 ? String(n) : n.toFixed(2)
}
