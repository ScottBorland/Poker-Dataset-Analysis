"""
fingerprint.py — Compute per-player, per-street strategic-situation fingerprints.

A "fingerprint" is a structured tuple identifying a strategically-equivalent
poker situation. One row is produced per (player_idx, street) pair for every
street the hand reached, for every player still in when the street started.

Fields (see the Fingerprint dataclass) capture:
    - Board texture (postflop only)
    - Positional layout (HU explicit, multiway collapsed)
    - Preflop pot type
    - Whether this player acts last postflop (in_position)
    - What the player faced at their first decision on the street
    - SPR bucket at the start of the street (postflop only)

Two independent hands that produce the same fingerprint should be
strategically equivalent decision points for the tagged player.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import sys
sys.path.insert(0, str(Path(__file__).parent))

from hand_utils import split_streets, assign_positions, street_start_state

if TYPE_CHECKING:
    from parser import Hand


RANK_ORDER = '23456789TJQKA'
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANK_ORDER)}

# Postflop "position strength" — later position = higher rank. BTN acts last.
POSITION_RANK = {'BTN': 6, 'CO': 5, 'HJ': 4, 'UTG': 3, 'SB': 2, 'BB': 1}


def _resolve_positions(hand: 'Hand', streets: dict) -> dict[int, str]:
    """
    Return {1-based player_idx: position_name}.

    For 3+ players, defers to hand_utils.assign_positions (empirically correct
    for the .phhs data we've inspected).

    For HU, the .phhs data does NOT follow the 'p1 = BTN' convention baked into
    hand_utils: the player who acts LAST postflop is the BTN (in position). We
    determine this dynamically from the actions instead.
    """
    if hand.n_players != 2:
        return assign_positions(hand)

    # Look at the earliest postflop street with 2+ player actions.
    for street in ('flop', 'turn', 'river'):
        actors = [
            int(a.split()[0][1:])
            for a in streets.get(street, [])
            if a and a[0] == 'p' and a.split()[0][1:].isdigit()
        ]
        distinct_in_order = list(dict.fromkeys(actors))
        if len(distinct_in_order) == 2:
            oop, ip = distinct_in_order[0], distinct_in_order[1]
            return {oop: 'BB', ip: 'BTN'}

    # No usable postflop data — infer from preflop (BTN acts first in HU).
    preflop_actors = [
        int(a.split()[0][1:])
        for a in streets.get('preflop', [])
        if a and a[0] == 'p' and a.split()[0][1:].isdigit()
    ]
    distinct = list(dict.fromkeys(preflop_actors))
    if distinct:
        btn = distinct[0]
        bb = 2 if btn == 1 else 1
        return {btn: 'BTN', bb: 'BB'}

    # No actions at all: fall back to hand_utils default.
    return assign_positions(hand)


# ---------------------------------------------------------------------------
# Fingerprint dataclass
# ---------------------------------------------------------------------------

@dataclass
class Fingerprint:
    hand_id: int
    file: str
    player_idx: int
    street: str                        # 'preflop' | 'flop' | 'turn' | 'river'
    positions: str                     # 'BTN_vs_BB' etc. HU; 'multiway' 3+
    n_players_street: int
    pot_type: str                      # 'unopened'|'limped'|'srp'|'3bet'|'4bet'|'5bet+'
    in_position: bool
    facing: str
    spr_bucket: Optional[str]          # NULL on preflop
    board_high_card: Optional[str]     # NULL on preflop
    board_paired: Optional[bool]
    board_monotone: Optional[bool]
    board_two_tone: Optional[bool]
    board_connectedness: Optional[str] # 'connected'|'gapped'|'disconnected'

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Card / board helpers
# ---------------------------------------------------------------------------

def _parse_cards(card_str: str) -> list[tuple[str, str]]:
    """Parse 'Ah5s2cTd' → [('A','h'), ('5','s'), ('2','c'), ('T','d')]."""
    cards = []
    i = 0
    while i + 1 < len(card_str):
        cards.append((card_str[i], card_str[i + 1]))
        i += 2
    return cards


def _max_cards_in_window(vals: list[int], window: int) -> int:
    """Max number of unique-rank cards within any rank-window of the given size."""
    if not vals:
        return 0
    vals = sorted(set(vals))
    best = 1
    for i, v in enumerate(vals):
        count = 1
        for j in range(i + 1, len(vals)):
            if vals[j] - v < window:
                count += 1
            else:
                break
        best = max(best, count)
    return best


def _board_texture(board_str: str) -> dict:
    """Compute board texture fields for a concatenated board string (3, 4, or 5 cards)."""
    cards = _parse_cards(board_str)
    if not cards:
        return {
            'board_high_card': None, 'board_paired': None,
            'board_monotone': None, 'board_two_tone': None,
            'board_connectedness': None,
        }
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]
    rank_vals = [RANK_VALUE.get(r, 0) for r in ranks]

    high_val = max(rank_vals)
    high_card = RANK_ORDER[high_val - 2]

    paired = len(set(ranks)) < len(ranks)

    suit_counts = Counter(suits)
    max_suit = max(suit_counts.values())
    monotone = max_suit >= 3                     # a flush is possible
    two_tone = (not monotone) and max_suit == 2  # only a flush draw

    # Connectedness: how densely packed are the ranks?
    # Add wheel-ace: treat ace as also rank 1 to catch A-2-3 style boards.
    with_wheel = list(rank_vals)
    if 14 in rank_vals:
        with_wheel.append(1)

    if _max_cards_in_window(with_wheel, 5) >= 3:
        connectedness = 'connected'
    elif _max_cards_in_window(with_wheel, 7) >= 3:
        connectedness = 'gapped'
    else:
        connectedness = 'disconnected'

    return {
        'board_high_card': high_card,
        'board_paired': paired,
        'board_monotone': monotone,
        'board_two_tone': two_tone,
        'board_connectedness': connectedness,
    }


# ---------------------------------------------------------------------------
# Hand-level derivations
# ---------------------------------------------------------------------------

def _pot_type(preflop_actions: list[str]) -> str:
    """Classify the preflop betting pattern."""
    n_raises = sum(1 for a in preflop_actions if 'cbr' in a)
    if n_raises == 0:
        any_call = any(
            len(a.split()) >= 2 and a.split()[1] == 'cc'
            for a in preflop_actions if a.startswith('p')
        )
        return 'limped' if any_call else 'unopened'
    if n_raises == 1:
        return 'srp'
    if n_raises == 2:
        return '3bet'
    if n_raises == 3:
        return '4bet'
    return '5bet+'


def _players_at_each_street(hand: 'Hand') -> dict[str, list[int]]:
    """Return {street: sorted list of 1-based player indices in at the start of the street}."""
    n = hand.n_players
    still_in = set(range(1, n + 1))
    street_order = ['preflop', 'flop', 'turn', 'river']
    result: dict[str, list[int]] = {'preflop': sorted(still_in)}

    db_count = 0
    for action in hand.actions:
        if action.startswith('d db'):
            db_count += 1
            if db_count <= 3:
                result[street_order[db_count]] = sorted(still_in)
        else:
            parts = action.split()
            if (len(parts) >= 2
                and parts[0].startswith('p')
                and parts[0][1:].isdigit()
                and parts[1] == 'f'):
                still_in.discard(int(parts[0][1:]))

    for s in street_order:
        result.setdefault(s, [])
    return result


def _positions_string(players_in: list[int], positions: dict[int, str]) -> str:
    """Format the positional layout for the players in on this street."""
    if len(players_in) == 2:
        pos_names = [positions.get(p, f'p{p}') for p in players_in]
        pos_names.sort(key=lambda p: -POSITION_RANK.get(p, 0))
        return f'{pos_names[0]}_vs_{pos_names[1]}'
    if len(players_in) >= 3:
        return 'multiway'
    return 'heads_up'


def _in_position(player_idx: int, players_in: list[int], positions: dict[int, str]) -> bool:
    """True iff this player has the latest postflop position among remaining players."""
    my_rank = POSITION_RANK.get(positions.get(player_idx, ''), 0)
    for p in players_in:
        if p == player_idx:
            continue
        other = POSITION_RANK.get(positions.get(p, ''), 0)
        if other > my_rank:
            return False
    return True


def _facing_preflop(player_idx: int, preflop_actions: list[str]) -> str:
    """What did this player face at their first preflop decision?"""
    n_raises = 0
    n_limps = 0
    for action in preflop_actions:
        parts = action.split()
        if not (parts and parts[0].startswith('p') and parts[0][1:].isdigit()):
            continue
        pidx = int(parts[0][1:])
        verb = parts[1] if len(parts) > 1 else ''
        if pidx == player_idx:
            return _classify_preflop_state(n_raises, n_limps)
        if verb == 'cbr':
            n_raises += 1
        elif verb == 'cc' and n_raises == 0:
            n_limps += 1
    # Player never acted (e.g. BB with everyone folding): return current state.
    return _classify_preflop_state(n_raises, n_limps)


def _classify_preflop_state(n_raises: int, n_limps: int) -> str:
    if n_raises == 0 and n_limps == 0:
        return 'unopened'
    if n_raises == 0:
        return 'facing_limp'
    if n_raises == 1:
        return 'facing_raise'
    if n_raises == 2:
        return 'facing_3bet'
    if n_raises == 3:
        return 'facing_4bet'
    return 'facing_5bet+'


def _facing_postflop(player_idx: int, street_actions: list[str]) -> str:
    """What did this player face at their first decision on this postflop street?"""
    saw_bet = False
    saw_raise = False
    saw_check = False
    for action in street_actions:
        parts = action.split()
        if not (parts and parts[0].startswith('p') and parts[0][1:].isdigit()):
            continue
        pidx = int(parts[0][1:])
        verb = parts[1] if len(parts) > 1 else ''
        if pidx == player_idx:
            if saw_raise:
                return 'facing_raise'
            if saw_bet:
                return 'facing_bet'
            if saw_check:
                return 'facing_check'
            return 'first_to_act'
        if verb == 'cbr':
            if saw_bet:
                saw_raise = True
            saw_bet = True
        elif verb == 'cc' and not saw_bet:
            saw_check = True
    return 'first_to_act'


# ---------------------------------------------------------------------------
# Stack / pot reconstruction for SPR
# ---------------------------------------------------------------------------

def _spr_bucket(hand: 'Hand', street: str) -> Optional[str]:
    """Effective SPR at the start of the street, bucketed."""
    if street == 'preflop':
        return None
    stacks, pot, still_in = street_start_state(hand, street)
    if pot <= 0 or not still_in:
        return None
    effective = min(stacks[p - 1] for p in still_in)
    spr = effective / pot
    if spr < 3:
        return '0-3'
    if spr < 6:
        return '3-6'
    if spr < 13:
        return '6-13'
    if spr < 20:
        return '13-20'
    return '20+'


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def compute_fingerprints(hand: 'Hand') -> list[Fingerprint]:
    """Return every (player_idx, street) fingerprint for this hand."""
    fps: list[Fingerprint] = []
    streets, boards = split_streets(hand.actions)
    positions = _resolve_positions(hand, streets)
    pot_type = _pot_type(streets['preflop'])
    players_at = _players_at_each_street(hand)

    board_by_street: dict[str, dict] = {}
    running = ''
    for s in ('flop', 'turn', 'river'):
        if boards.get(s):
            running += boards[s]
            board_by_street[s] = _board_texture(running)
        else:
            board_by_street[s] = _board_texture('')  # all-None

    for street in ('preflop', 'flop', 'turn', 'river'):
        players_in = players_at[street]
        if not players_in:
            continue

        positions_str = _positions_string(players_in, positions)
        spr = _spr_bucket(hand, street)
        board_fields = (
            {'board_high_card': None, 'board_paired': None,
             'board_monotone': None, 'board_two_tone': None,
             'board_connectedness': None}
            if street == 'preflop' else board_by_street[street]
        )

        for pidx in players_in:
            if street == 'preflop':
                facing = _facing_preflop(pidx, streets['preflop'])
            else:
                facing = _facing_postflop(pidx, streets[street])

            fps.append(Fingerprint(
                hand_id=hand.hand_id,
                file=hand.file,
                player_idx=pidx,
                street=street,
                positions=positions_str,
                n_players_street=len(players_in),
                pot_type=pot_type,
                in_position=_in_position(pidx, players_in, positions),
                facing=facing,
                spr_bucket=spr,
                **board_fields,
            ))

    return fps
