"""
hand_utils.py — Derived features for a parsed Hand.

Covers:
- Street segmentation
- Pot size reconstruction
- Position assignment
- Action classification helpers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from parser import Hand


# ---------------------------------------------------------------------------
# Street segmentation
# ---------------------------------------------------------------------------

STREETS = ('preflop', 'flop', 'turn', 'river')
_STREET_ORDER = ['flop', 'turn', 'river']


def split_streets(actions: list[str]) -> tuple[dict[str, list[str]], dict[str, str | None]]:
    """
    Partition actions by street.

    Returns:
        streets  — {'preflop': [...], 'flop': [...], 'turn': [...], 'river': [...]}
        boards   — {'flop': 'Ah5s2c', 'turn': 'Td', 'river': None, ...}
    """
    streets: dict[str, list[str]] = {s: [] for s in STREETS}
    boards: dict[str, str | None] = {'flop': None, 'turn': None, 'river': None}
    current = 'preflop'
    db_count = 0

    for action in actions:
        if action.startswith('d db'):
            if db_count < 3:
                street_name = _STREET_ORDER[db_count]
                boards[street_name] = action.split()[-1]
                current = street_name
                db_count += 1
        else:
            streets[current].append(action)

    return streets, boards


# ---------------------------------------------------------------------------
# Pot reconstruction
# ---------------------------------------------------------------------------

@dataclass
class PotState:
    pot: float = 0.0
    street_bets: list[float] = field(default_factory=list)   # per-player this street

    def copy(self) -> 'PotState':
        return PotState(pot=self.pot, street_bets=list(self.street_bets))


def reconstruct_pot(hand: 'Hand') -> list[float]:
    """
    Replay all actions and return a list of pot sizes, one per action step.
    Index i corresponds to the pot size *after* actions[i] is applied.
    """
    n = hand.n_players
    stacks = list(hand.starting_stacks)
    street_bets = [0.0] * n          # amount each player has put in this street
    pot = sum(hand.blinds_or_straddles) + sum(hand.antes)

    # Seed street_bets with the blind/ante contributions
    for i, blind in enumerate(hand.blinds_or_straddles):
        if i < n:
            street_bets[i] = blind
    for i, ante in enumerate(hand.antes):
        if i < n:
            street_bets[i] += ante

    history: list[float] = []
    db_count = 0

    for action in hand.actions:
        parts = action.split()

        if action.startswith('d db'):
            # New street — collect street bets into pot, reset
            pot += sum(street_bets)
            street_bets = [0.0] * n
            db_count += 1

        elif action.startswith('d dh'):
            pass  # deal hole cards — no money movement

        elif len(parts) >= 2 and parts[0].startswith('p') and parts[0][1:].isdigit():
            pidx = int(parts[0][1:]) - 1   # 0-indexed
            verb = parts[1]

            if verb == 'cbr' and len(parts) >= 3:
                total_bet = float(parts[2])
                additional = total_bet - street_bets[pidx]
                stacks[pidx] = max(0.0, stacks[pidx] - additional)
                street_bets[pidx] = total_bet

            elif verb == 'cc':
                # call — match the current max bet on this street
                facing = max(street_bets)
                additional = facing - street_bets[pidx]
                additional = min(additional, stacks[pidx])
                stacks[pidx] -= additional
                street_bets[pidx] += additional

        history.append(pot + sum(street_bets))

    return history


def final_pot(hand: 'Hand') -> float:
    """Return the final pot size for a hand."""
    hist = reconstruct_pot(hand)
    return hist[-1] if hist else sum(hand.blinds_or_straddles) + sum(hand.antes)


# ---------------------------------------------------------------------------
# Position assignment
# ---------------------------------------------------------------------------

POSITION_NAMES_6 = {0: 'SB', 1: 'BB', 2: 'UTG', 3: 'HJ', 4: 'CO', 5: 'BTN'}
POSITION_NAMES_5 = {0: 'SB', 1: 'BB', 2: 'UTG', 3: 'CO', 4: 'BTN'}
POSITION_NAMES_4 = {0: 'SB', 1: 'BB', 2: 'UTG', 3: 'BTN'}
POSITION_NAMES_3 = {0: 'SB', 1: 'BB', 2: 'BTN'}
POSITION_NAMES_2 = {0: 'SB/BTN', 1: 'BB'}

_POSITION_MAPS = {
    2: POSITION_NAMES_2,
    3: POSITION_NAMES_3,
    4: POSITION_NAMES_4,
    5: POSITION_NAMES_5,
    6: POSITION_NAMES_6,
}


def assign_positions(hand: 'Hand') -> dict[int, str]:
    """
    Return {player_idx (1-based): position_name} for each player.
    Works for 2–6 players.
    """
    n = hand.n_players
    pos_map = _POSITION_MAPS.get(n, {})
    return {i + 1: pos_map.get(i, f'p{i+1}') for i in range(n)}


def button_player(hand: 'Hand') -> int:
    """Return the 1-based index of the button player."""
    return hand.n_players   # last player in the list is always BTN


# ---------------------------------------------------------------------------
# Action classification helpers
# ---------------------------------------------------------------------------

def preflop_actions(hand: 'Hand') -> list[str]:
    streets, _ = split_streets(hand.actions)
    return streets['preflop']


def count_preflop_raises(hand: 'Hand') -> int:
    """Count the number of cbr actions preflop (open=1, 3bet=2, 4bet=3, …)."""
    return sum(1 for a in preflop_actions(hand) if 'cbr' in a)


def went_to_showdown(hand: 'Hand') -> bool:
    return any('sm' in a for a in hand.actions)


def players_who_saw_flop(hand: 'Hand') -> list[int]:
    """Return list of 1-based player indices still in when flop was dealt."""
    folded: set[int] = set()
    for action in hand.actions:
        parts = action.split()
        if action.startswith('d db'):
            break
        if len(parts) >= 2 and parts[0].startswith('p') and parts[0][1:].isdigit():
            if parts[1] == 'f':
                folded.add(int(parts[0][1:]))
    return [i for i in range(1, hand.n_players + 1) if i not in folded]


def is_multiway(hand: 'Hand') -> bool:
    return len(players_who_saw_flop(hand)) >= 3


# ---------------------------------------------------------------------------
# Summary dict (useful for DataFrame construction)
# ---------------------------------------------------------------------------

def hand_summary(hand: 'Hand') -> dict:
    n_raises = count_preflop_raises(hand)
    return {
        'hand_id': hand.hand_id,
        'file': hand.file,
        'date': hand.date_str,
        'table': hand.table,
        'n_players': hand.n_players,
        'pot_final': final_pot(hand),
        'n_preflop_raises': n_raises,
        'went_to_showdown': went_to_showdown(hand),
        'is_multiway': is_multiway(hand),
        'n_actions': len(hand.actions),
        'has_winnings': hand.winnings is not None,
    }
