"""
state.py — Hand state machine for the pygame step-through replayer.

Usage:
    from replayer.state import HandState, build_initial_state, apply_action

    state = build_initial_state(hand)
    state = apply_action(state, hand.actions[0])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parser import Hand

# Card suit → unicode symbol for display
SUIT_SYMBOLS = {'h': '♥', 'd': '♦', 'c': '♣', 's': '♠'}
SUIT_COLORS  = {'h': 'red', 'd': 'red', 'c': 'black', 's': 'black'}


def fmt_card(card: str) -> str:
    """'Ah' → 'A♥'"""
    if len(card) == 2:
        rank, suit = card[0], card[1]
        return rank + SUIT_SYMBOLS.get(suit, suit)
    return card


def fmt_amount(amount: float) -> str:
    return f"${amount:.2f}"


@dataclass
class HandState:
    step: int                              # index of next action to apply
    stacks: list[float]
    street_bets: list[float]              # per-player contribution this street
    pot: float                            # chips committed from previous streets
    board: list[str]                      # community cards dealt so far
    hole_cards: dict[int, list[str]]      # {player_idx (1-based): [card, card]}
    shown_cards: dict[int, list[str]]     # cards shown at showdown
    folded: set[int]                      # 1-based player indices
    street: str                           # 'preflop' | 'flop' | 'turn' | 'river'
    action_log: list[str]                 # human-readable history
    current_actor: int | None             # 1-based, None if not determined
    hand_over: bool

    @property
    def total_pot(self) -> float:
        return self.pot + sum(self.street_bets)

    def display_pot(self) -> str:
        return fmt_amount(self.total_pot)

    def copy(self) -> 'HandState':
        return deepcopy(self)


def build_initial_state(hand: 'Hand') -> HandState:
    """Construct a HandState before any actions have been applied."""
    n = hand.n_players
    stacks = list(hand.starting_stacks)
    street_bets = [0.0] * n

    # Post blinds / antes
    pot = 0.0
    for i, ante in enumerate(hand.antes):
        if i < n and ante > 0:
            stacks[i] -= ante
            street_bets[i] += ante

    for i, blind in enumerate(hand.blinds_or_straddles):
        if i < n and blind > 0:
            stacks[i] -= blind
            street_bets[i] += blind

    log = []
    for i, blind in enumerate(hand.blinds_or_straddles):
        if i < n and blind > 0:
            pos = 'SB' if i == 0 else 'BB'
            log.append(f"p{i+1} posts {pos} {fmt_amount(blind)}")

    return HandState(
        step=0,
        stacks=stacks,
        street_bets=street_bets,
        pot=pot,
        board=[],
        hole_cards={},
        shown_cards={},
        folded=set(),
        street='preflop',
        action_log=log,
        current_actor=None,
        hand_over=False,
    )


_STREET_ORDER = ['flop', 'turn', 'river']
_DB_INDEX = {'flop': 0, 'turn': 1, 'river': 2}


def apply_action(state: HandState, action: str) -> HandState:
    """
    Return a new HandState with the given raw action applied.
    Does NOT mutate the input state.
    """
    s = state.copy()
    s.step += 1
    parts = action.split()

    # --- Deal hole cards ---
    if action.startswith('d dh'):
        # 'd dh p1 ????' or 'd dh p1 AhKd'
        if len(parts) >= 4:
            pidx = int(parts[2][1:])   # 'p1' → 1
            cards_str = parts[3]
            if cards_str != '????':
                # Revealed cards: parse pairs of chars
                cards = [cards_str[i:i+2] for i in range(0, len(cards_str), 2)]
                s.hole_cards[pidx] = cards
            else:
                s.hole_cards[pidx] = ['??', '??']
        s.current_actor = None
        return s

    # --- Deal board ---
    if action.startswith('d db'):
        # Collect street bets into pot
        s.pot += sum(s.street_bets)
        s.street_bets = [0.0] * len(s.stacks)

        cards_str = parts[-1]
        new_cards = [cards_str[i:i+2] for i in range(0, len(cards_str), 2)]
        s.board.extend(new_cards)

        db_count = len(s.board)
        if db_count <= 3:
            s.street = 'flop'
            s.action_log.append(f"--- Flop: {' '.join(fmt_card(c) for c in s.board)} ---")
        elif db_count == 4:
            s.street = 'turn'
            s.action_log.append(f"--- Turn: {fmt_card(s.board[3])} ---")
        elif db_count == 5:
            s.street = 'river'
            s.action_log.append(f"--- River: {fmt_card(s.board[4])} ---")
        s.current_actor = None
        return s

    # --- Player actions ---
    if len(parts) >= 2 and parts[0].startswith('p') and parts[0][1:].isdigit():
        pidx = int(parts[0][1:])   # 1-based
        verb = parts[1]
        s.current_actor = pidx

        if verb == 'f':
            s.folded.add(pidx)
            s.action_log.append(f"p{pidx} folds")

            # Check if only one player remains
            active = [i for i in range(1, len(s.stacks)+1) if i not in s.folded]
            if len(active) == 1:
                s.hand_over = True

        elif verb == 'cc':
            facing = max(s.street_bets) if s.street_bets else 0.0
            additional = facing - s.street_bets[pidx - 1]
            additional = min(additional, s.stacks[pidx - 1])
            s.stacks[pidx - 1] -= additional
            s.street_bets[pidx - 1] += additional
            if additional == 0:
                s.action_log.append(f"p{pidx} checks")
            else:
                s.action_log.append(f"p{pidx} calls {fmt_amount(additional)}")

        elif verb == 'cbr' and len(parts) >= 3:
            total_bet = float(parts[2])
            prev_bet = s.street_bets[pidx - 1]
            additional = total_bet - prev_bet
            additional = min(additional, s.stacks[pidx - 1])
            s.stacks[pidx - 1] -= additional
            s.street_bets[pidx - 1] = prev_bet + additional
            facing = max(s.street_bets)
            if prev_bet == 0 and facing == total_bet:
                s.action_log.append(f"p{pidx} bets {fmt_amount(total_bet)}")
            else:
                s.action_log.append(f"p{pidx} raises to {fmt_amount(total_bet)}")

        elif verb == 'sm' and len(parts) >= 3:
            cards_str = parts[2]
            cards = [cards_str[i:i+2] for i in range(0, len(cards_str), 2)]
            s.shown_cards[pidx] = cards
            s.hole_cards[pidx] = cards
            s.action_log.append(f"p{pidx} shows {' '.join(fmt_card(c) for c in cards)}")

    return s


def _precompute_known_cards(hand: 'Hand') -> dict[int, list[str]]:
    """Return {seat_1based: [card, card]} for any player whose actual cards are revealed."""
    known: dict[int, list[str]] = {}
    for action in hand.actions:
        parts = action.split()
        # d dh pN XxYy — revealed deal (skip hidden '????')
        if (len(parts) == 4 and parts[0] == 'd' and parts[1] == 'dh'
                and parts[3] != '????'):
            pidx = int(parts[2][1:])
            known[pidx] = [parts[3][i:i+2] for i in range(0, len(parts[3]), 2)]
        # pN sm XxYy — explicit show (skip mucked '????')
        elif (len(parts) >= 3 and parts[0].startswith('p')
              and parts[0][1:].isdigit() and parts[1] == 'sm'
              and parts[2] != '????'):
            pidx = int(parts[0][1:])
            known[pidx] = [parts[2][i:i+2] for i in range(0, len(parts[2]), 2)]
    return known


class ReplaySession:
    """
    Manages stepping forward/backward through a hand's actions.
    """

    def __init__(self, hand: 'Hand'):
        self.hand = hand
        self.known_cards: dict[int, list[str]] = _precompute_known_cards(hand)
        self._states: list[HandState] = [build_initial_state(hand)]
        self._first_step = 0   # temporary; updated below after skipping hidden deals
        # Skip past hidden deals so the first visible frame is meaningful
        while self.can_advance() and self._is_hidden_deal(self.hand.actions[self.step]):
            action = self.hand.actions[self.step]
            self._states.append(apply_action(self.state, action))
        self._first_step = self.step   # normalise the displayed counter from here

    @property
    def state(self) -> HandState:
        return self._states[-1]

    @property
    def step(self) -> int:
        return len(self._states) - 1

    @property
    def display_step(self) -> int:
        """0-based step counter that ignores the skipped hidden deals."""
        return self.step - self._first_step

    @property
    def display_total_steps(self) -> int:
        """Total meaningful steps (excludes skipped hidden deals) for display."""
        return len(self.hand.actions) - self._first_step

    @property
    def total_steps(self) -> int:
        """Raw total used by can_advance() — must stay as the full action count."""
        return len(self.hand.actions)

    def can_advance(self) -> bool:
        return self.step < self.total_steps

    def can_rewind(self) -> bool:
        return self.step > 0

    @staticmethod
    def _is_hidden_deal(action: str) -> bool:
        """True for 'd dh pN ????' actions — visually a no-op."""
        parts = action.split()
        return (len(parts) == 4 and parts[0] == 'd' and parts[1] == 'dh'
                and parts[3] == '????')

    def advance(self):
        """Advance one meaningful step, skipping hidden hole-card deals."""
        if self.can_advance():
            action = self.hand.actions[self.step]
            new_state = apply_action(self.state, action)
            self._states.append(new_state)
            # Keep advancing past hidden deals so the user never lands on a no-op
            while self.can_advance() and self._is_hidden_deal(self.hand.actions[self.step]):
                action = self.hand.actions[self.step]
                new_state = apply_action(self.state, action)
                self._states.append(new_state)

    def rewind(self):
        if self.can_rewind():
            self._states.pop()

    def reset(self):
        self._states = [self._states[0]]
        # Re-skip hidden deals after reset
        while self.can_advance() and self._is_hidden_deal(self.hand.actions[self.step]):
            self._states.append(apply_action(self.state, self.hand.actions[self.step]))

    def jump_to(self, step: int):
        """Jump to an absolute step (re-replays from start if needed)."""
        if step < self.step:
            self.reset()
        while self.step < step and self.can_advance():
            self.advance()
