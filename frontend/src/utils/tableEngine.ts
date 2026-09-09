// tableEngine.ts — pure client-side poker table state machine for the Hand
// Builder. No React. Seat convention matches the DB / hand_utils.py:
// p1 = SB, p2 = BB, ..., pN = BTN (HU: p1 = BTN/SB, p2 = BB). Emits .phhs
// action strings ('p3 cbr 2.50', 'p4 f', 'p1 cc') — the grammar the backend
// derive endpoint parses via hand_utils.split_streets.
//
// Event-sourced: the table is a fold over (config, events). Undo pops the
// last event and replays — no inverse-operation bookkeeping.
//
// v1 simplifications: an all-in below the min-raise does not re-close the
// betting round differently (players yet to act keep all options), and side
// pots aren't modeled (pot = sum of all chips in, which is what the DB's
// SUM(invested) convention uses too).

export type Street = 'preflop' | 'flop' | 'turn' | 'river'
export const STREET_ORDER: Street[] = ['preflop', 'flop', 'turn', 'river']

// Mirrors hand_utils.POSITION_NAMES_* (0-indexed seat -> label).
const POSITION_NAMES: Record<number, string[]> = {
  2: ['BTN', 'BB'],
  3: ['SB', 'BB', 'BTN'],
  4: ['SB', 'BB', 'UTG', 'BTN'],
  5: ['SB', 'BB', 'UTG', 'CO', 'BTN'],
  6: ['SB', 'BB', 'UTG', 'HJ', 'CO', 'BTN'],
}

export interface TableConfig {
  nPlayers: number
  stackBB: number
}

export type TableEvent =
  | { kind: 'action'; verb: 'f' | 'cc' | 'cbr'; amount?: number }
  | { kind: 'board'; cards: string }

export interface SeatState {
  seatIdx: number // 1-based
  position: string
  stack: number
  streetBet: number
  invested: number
  folded: boolean
  allIn: boolean
}

export interface TableState {
  nPlayers: number
  seats: SeatState[]
  street: Street
  boards: { flop: string | null; turn: string | null; river: string | null }
  collectedPot: number // chips collected from completed streets
  actions: Record<Street, string[]>
  toAct: number | null // seatIdx whose turn it is, null if none
  awaitingBoard: Street | null // next street needs its board dealt
  handOver: boolean // folded down to one player
  lastRaiseIncrement: number
  maxStreetBet: number
  /** Seats still owing a decision this street, in acting order. Internal. */
  pendingActors: number[]
}

export interface LegalActions {
  seatIdx: number
  canCheck: boolean
  callAmount: number // additional chips to call (0 if check)
  canRaise: boolean
  minRaiseTo: number // min legal total this street
  maxRaiseTo: number // all-in total this street
}

export function positionLabel(nPlayers: number, seatIdx: number): string {
  return POSITION_NAMES[nPlayers]?.[seatIdx - 1] ?? `p${seatIdx}`
}

function activeInOrder(state: TableState, order: number[]): number[] {
  return order.filter(i => {
    const s = state.seats[i - 1]
    return !s.folded && !s.allIn
  })
}

function streetActingOrder(nPlayers: number, street: Street): number[] {
  const all = Array.from({ length: nPlayers }, (_, i) => i + 1)
  if (nPlayers === 2) return street === 'preflop' ? [1, 2] : [2, 1]
  if (street === 'preflop') return [...all.slice(2), 1, 2]
  return all
}

/** Seats still contesting the pot (not folded), regardless of all-in. */
function unfolded(state: TableState): number[] {
  return state.seats.filter(s => !s.folded).map(s => s.seatIdx)
}

function initState(config: TableConfig): TableState {
  const seats: SeatState[] = Array.from({ length: config.nPlayers }, (_, i) => ({
    seatIdx: i + 1,
    position: positionLabel(config.nPlayers, i + 1),
    stack: config.stackBB,
    streetBet: 0,
    invested: 0,
    folded: false,
    allIn: false,
  }))
  // Post blinds: p1 = 0.5, p2 = 1.0
  const post = (idx: number, amt: number) => {
    const s = seats[idx]
    const a = Math.min(amt, s.stack)
    s.stack -= a
    s.streetBet += a
    s.invested += a
    if (s.stack === 0) s.allIn = true
  }
  post(0, 0.5)
  post(1, 1.0)

  const state: TableState = {
    nPlayers: config.nPlayers,
    seats,
    street: 'preflop',
    boards: { flop: null, turn: null, river: null },
    collectedPot: 0,
    actions: { preflop: [], flop: [], turn: [], river: [] },
    toAct: null,
    awaitingBoard: null,
    handOver: false,
    lastRaiseIncrement: 1.0,
    maxStreetBet: 1.0,
    pendingActors: [],
  }
  setPending(state, activeInOrder(state, streetActingOrder(config.nPlayers, 'preflop')))
  return state
}

function setPending(state: TableState, p: number[]) {
  state.pendingActors = p
  state.toAct = p[0] ?? null
}

function closeStreet(state: TableState) {
  for (const s of state.seats) {
    state.collectedPot += s.streetBet
    s.streetBet = 0
  }
  state.maxStreetBet = 0
  state.lastRaiseIncrement = 1.0
  setPending(state, [])

  const alive = unfolded(state)
  if (alive.length <= 1) {
    state.handOver = true
    state.awaitingBoard = null
    return
  }
  const nextIdx = STREET_ORDER.indexOf(state.street) + 1
  state.awaitingBoard = nextIdx < STREET_ORDER.length ? STREET_ORDER[nextIdx] : null
}

function applyBoardEvent(state: TableState, cards: string) {
  const street = state.awaitingBoard
  if (!street || street === 'preflop') throw new Error('Not awaiting a board')
  state.boards[street as 'flop' | 'turn' | 'river'] = cards
  state.street = street
  state.awaitingBoard = null
  const order = activeInOrder(state, streetActingOrder(state.nPlayers, street))
  if (order.length >= 2) {
    setPending(state, order)
  } else {
    // 0-1 players can still act (others all-in) — no betting this street.
    closeStreet(state)
  }
}

function applyActionEvent(state: TableState, ev: { verb: 'f' | 'cc' | 'cbr'; amount?: number }) {
  const actor = state.toAct
  if (actor == null) throw new Error('No one to act')
  const seat = state.seats[actor - 1]
  const p = state.pendingActors

  if (ev.verb === 'f') {
    seat.folded = true
    state.actions[state.street].push(`p${actor} f`)
    setPending(state, p.slice(1))
  } else if (ev.verb === 'cc') {
    const owe = Math.max(0, state.maxStreetBet - seat.streetBet)
    const paid = Math.min(owe, seat.stack)
    seat.stack -= paid
    seat.streetBet += paid
    seat.invested += paid
    if (seat.stack === 0) seat.allIn = true
    state.actions[state.street].push(`p${actor} cc`)
    setPending(state, p.slice(1))
  } else {
    const total = ev.amount ?? 0
    const add = total - seat.streetBet
    if (add <= 0 || add > seat.stack + 1e-9) throw new Error('Illegal raise size')
    state.lastRaiseIncrement = Math.max(total - state.maxStreetBet, state.lastRaiseIncrement)
    state.maxStreetBet = total
    seat.stack = Math.max(0, seat.stack - add)
    seat.streetBet = total
    seat.invested += add
    if (seat.stack === 0) seat.allIn = true
    state.actions[state.street].push(`p${actor} cbr ${total.toFixed(2)}`)
    // Everyone else still in (and not all-in) must respond, in order after the aggressor.
    const order = streetActingOrder(state.nPlayers, state.street)
    const start = order.indexOf(actor)
    const rotated = [...order.slice(start + 1), ...order.slice(0, start)]
    setPending(state, activeInOrder(state, rotated))
  }

  if (unfolded(state).length <= 1) {
    // Fold-out: collect bets, hand over.
    closeStreet(state)
    state.handOver = true
    state.awaitingBoard = null
    return
  }
  if (state.pendingActors.length === 0) closeStreet(state)
}

export function buildTable(config: TableConfig, events: TableEvent[]): TableState {
  const state = initState(config)
  for (const ev of events) {
    if (ev.kind === 'board') applyBoardEvent(state, ev.cards)
    else applyActionEvent(state, ev)
  }
  return state
}

export function legalActions(state: TableState): LegalActions | null {
  const actor = state.toAct
  if (actor == null) return null
  const seat = state.seats[actor - 1]
  const owe = Math.max(0, state.maxStreetBet - seat.streetBet)
  const maxTo = seat.streetBet + seat.stack
  const minTo = Math.min(
    state.maxStreetBet > 0 ? state.maxStreetBet + state.lastRaiseIncrement : 1.0,
    maxTo,
  )
  return {
    seatIdx: actor,
    canCheck: owe === 0,
    callAmount: Math.min(owe, seat.stack),
    canRaise: maxTo > state.maxStreetBet + 1e-9,
    minRaiseTo: minTo,
    maxRaiseTo: maxTo,
  }
}

export function totalPot(state: TableState): number {
  return state.collectedPot + state.seats.reduce((a, s) => a + s.streetBet, 0)
}

/** Streets that have begun (board dealt, or preflop), oldest first. */
export function streetsReached(state: TableState): Street[] {
  const reached: Street[] = ['preflop']
  for (const s of ['flop', 'turn', 'river'] as const) {
    if (state.boards[s]) reached.push(s)
  }
  return reached
}

/** Payload for POST /hand-builder/derive. */
export function toDerivePayload(state: TableState, heroSeat: number, initialStacks: number[]) {
  const reached = streetsReached(state)
  return {
    n_players: state.nPlayers,
    stacks_bb: initialStacks,
    hero_seat: heroSeat,
    preflop_actions: state.actions.preflop,
    flop_actions: state.actions.flop,
    flop_board: state.boards.flop,
    turn_actions: state.actions.turn,
    turn_board: state.boards.turn,
    river_actions: state.actions.river,
    river_board: state.boards.river,
    current_street: reached[reached.length - 1],
  }
}
