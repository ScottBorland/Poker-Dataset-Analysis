"""
labeller.py — Auto-label hands and store results in labels/labels.db.

Auto-labellers:
    label_hand(hand) -> list[LabelRow]

CLI usage:
    python labeller.py --file "data/abs NLH handhq_1-OBFUSCATED.phhs"
    python labeller.py --dir data/
    python labeller.py --dir data/ --label 3bet_pot  # filter to one label

Manual label:
    python labeller.py --add --hand-id 3017235114 --file abs.phhs --label hero_spot --note "interesting"
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Resolve imports whether run directly or as module
import sys
sys.path.insert(0, str(Path(__file__).parent))

from parser import Hand, load_file, load_directory
from hand_utils import (
    split_streets,
    count_preflop_raises,
    went_to_showdown,
    is_multiway,
    players_who_saw_flop,
)

# ---------------------------------------------------------------------------
# Card utilities
# ---------------------------------------------------------------------------

RANK_ORDER = '23456789TJQKA'
RANK_VALUE = {r: i + 2 for i, r in enumerate(RANK_ORDER)}


def _parse_cards(card_str: str) -> list[tuple[str, str]]:
    """Parse e.g. 'Ah5s2c' → [('A','h'), ('5','s'), ('2','c')]."""
    cards = []
    i = 0
    while i + 1 < len(card_str):
        cards.append((card_str[i], card_str[i + 1]))
        i += 2
    return cards


def _canonical_hand(c1: tuple[str, str], c2: tuple[str, str]) -> str:
    """Return canonical notation: 'AKs', 'AKo', or 'AA'."""
    r1, s1 = c1
    r2, s2 = c2
    v1, v2 = RANK_VALUE.get(r1, 0), RANK_VALUE.get(r2, 0)
    if v2 > v1:
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return f'{r1}{r1}'
    return f'{r1}{r2}{"s" if s1 == s2 else "o"}'

DB_PATH = Path(__file__).parent.parent / 'labels' / 'labels.db'


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS labels (
    hand_id     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    label       TEXT NOT NULL,
    street      TEXT,
    player_idx  INTEGER,
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_label
    ON labels(hand_id, label, COALESCE(player_idx, -1));

CREATE INDEX IF NOT EXISTS idx_label ON labels(label);
CREATE INDEX IF NOT EXISTS idx_hand  ON labels(hand_id);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Label row
# ---------------------------------------------------------------------------

@dataclass
class LabelRow:
    hand_id: int
    file: str
    label: str
    street: Optional[str] = None
    player_idx: Optional[int] = None
    note: Optional[str] = None


def insert_labels(rows: list[LabelRow], conn: sqlite3.Connection) -> int:
    """Insert rows, ignoring conflicts. Returns number of rows inserted."""
    inserted = 0
    for r in rows:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO labels(hand_id, file, label, street, player_idx, note) "
                "VALUES (?,?,?,?,?,?)",
                (r.hand_id, r.file, r.label, r.street, r.player_idx, r.note),
            )
            inserted += conn.execute("SELECT changes()").fetchone()[0]
        except sqlite3.Error as e:
            print(f"[labeller] DB error on hand {r.hand_id}: {e}")
    conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Auto-labellers
# ---------------------------------------------------------------------------

def _label_flop_texture(boards: dict, hand: Hand) -> list[LabelRow]:
    """Generate flop texture labels for hands that reached a flop."""
    flop_str = boards.get('flop')
    if not flop_str:
        return []
    cards = _parse_cards(flop_str)
    if len(cards) != 3:
        return []

    rows: list[LabelRow] = []
    ranks = [c[0] for c in cards]
    suits = [c[1] for c in cards]
    rank_vals = sorted([RANK_VALUE.get(r, 0) for r in ranks], reverse=True)

    def add(label: str) -> None:
        rows.append(LabelRow(hand.hand_id, hand.file, label, 'flop', note=flop_str))

    # Suit texture
    n_suits = len(set(suits))
    if n_suits == 3:
        add('flop_rainbow')
    elif n_suits == 2:
        add('flop_two_tone')
    else:
        add('flop_monotone')

    # Paired board
    if len(set(ranks)) < 3:
        add('flop_paired')

    # High card
    if 14 in rank_vals:
        add('flop_ace_high')
    elif 13 in rank_vals:
        add('flop_king_high')

    # Low (all cards 9 or below — no broadway cards)
    if all(v <= 9 for v in rank_vals):
        add('flop_low')

    # Two or more broadway cards (T+)
    if sum(1 for v in rank_vals if v >= 10) >= 2:
        add('flop_two_broadway')

    # Connectedness: all 3 unique ranks within a 5-card window → straight draw possible
    unique_vals = sorted(set(rank_vals))
    span = unique_vals[-1] - unique_vals[0] if len(unique_vals) >= 2 else 0
    if len(unique_vals) == 3 and span <= 4:
        add('flop_connected')

    # Dry: rainbow AND no straight draw potential (unique ranks span > 4) AND unpaired
    if n_suits == 3 and span > 4 and len(set(ranks)) == 3:
        add('flop_dry')

    return rows


def _extract_hole_cards(hand: Hand) -> dict[int, str]:
    """Return {1-based player idx: card_str} for players with revealed hole cards."""
    cards: dict[int, str] = {}
    for action in hand.actions:
        parts = action.split()
        # 'd dh pN XxYy' — deal action with known cards
        if action.startswith('d dh') and len(parts) >= 4:
            p, card_str = parts[2], parts[3]
            if '?' not in card_str and p[1:].isdigit():
                cards[int(p[1:])] = card_str
        # 'pN sm XxYy' — show/muck at showdown
        elif len(parts) >= 3 and parts[0].startswith('p') and parts[0][1:].isdigit() and parts[1] == 'sm':
            card_str = parts[2]
            if '?' not in card_str:
                cards.setdefault(int(parts[0][1:]), card_str)
    return cards


def _label_hole_cards(hand: Hand) -> list[LabelRow]:
    """Generate per-player hole card labels for players with revealed cards."""
    rows: list[LabelRow] = []
    for pidx, card_str in _extract_hole_cards(hand).items():
        cards = _parse_cards(card_str)
        if len(cards) != 2:
            continue
        c1, c2 = cards
        r1, s1 = c1
        r2, s2 = c2
        v1, v2 = RANK_VALUE.get(r1, 0), RANK_VALUE.get(r2, 0)
        hi_v, lo_v = max(v1, v2), min(v1, v2)
        is_pair = r1 == r2
        is_suited = s1 == s2
        gap = hi_v - lo_v

        def add(label: str) -> None:
            rows.append(LabelRow(hand.hand_id, hand.file, label, 'preflop', pidx))

        add(f'hand_{_canonical_hand(c1, c2)}')

        if is_pair:
            add('pocket_pair')
            if hi_v >= 10:
                add('premium_pair')
        else:
            add('suited' if is_suited else 'offsuit')
            if gap == 1:
                add('suited_connector' if is_suited else 'connector')
            elif gap == 2:
                add('suited_one_gapper' if is_suited else 'one_gapper')
            if hi_v >= 10 and lo_v >= 10:
                add('broadway')
            if hi_v == 14:
                add('ace_x')
                if is_suited:
                    add('ace_x_suited')

    return rows


def label_hand(hand: Hand) -> list[LabelRow]:
    """Run all auto-detectors on a hand. Returns list of applicable LabelRows."""
    rows: list[LabelRow] = []
    streets, boards = split_streets(hand.actions)
    preflop = streets['preflop']
    n_raises = count_preflop_raises(hand)

    def add(label: str, street: str | None = None, player_idx: int | None = None):
        rows.append(LabelRow(hand.hand_id, hand.file, label, street, player_idx))

    # --- Preflop situation ---
    if n_raises == 0:
        has_limp = any('cc' in a for a in preflop if a.startswith('p'))
        if has_limp:
            add('limp_pot', 'preflop')
    elif n_raises == 1:
        add('single_raised_pot', 'preflop')
        add('rfi', 'preflop')
    elif n_raises == 2:
        add('3bet_pot', 'preflop')
        if _detect_squeeze(preflop):
            add('squeeze', 'preflop')
    elif n_raises == 3:
        add('4bet_pot', 'preflop')
    else:
        add('4bet_pot', 'preflop')
        add('5bet_pot', 'preflop')

    # --- Postflop ---
    flop_players = players_who_saw_flop(hand)

    if boards['flop'] is not None:
        flop_actions = streets['flop']
        preflop_aggressor = _find_preflop_aggressor(preflop)
        first_bet = _first_bet_player(flop_actions)

        if preflop_aggressor is not None and first_bet == preflop_aggressor:
            add('cbet_flop', 'flop', preflop_aggressor)

        # Donk bet: first bettor is not the preflop aggressor
        if first_bet is not None and first_bet != preflop_aggressor:
            add('donk_bet_flop', 'flop', first_bet)

        if _has_check_raise(flop_actions):
            add('check_raise_flop', 'flop')

        if is_multiway(hand):
            add('multi_way', 'flop')

    if boards['turn'] is not None and _has_check_raise(streets['turn']):
        add('check_raise_turn', 'turn')

    if boards['river'] is not None and _has_check_raise(streets['river']):
        add('check_raise_river', 'river')

    # --- Player count at flop ---
    n_flop = len(flop_players)
    if n_flop == 2:
        add('heads_up_flop', 'flop')
        # blind vs blind: only SB(p1) and BB(p2) in a hand with 3+ seats
        if set(flop_players) == {1, 2} and hand.n_players >= 3:
            add('blind_vs_blind', 'preflop')
    elif n_flop == 3:
        add('3way_flop', 'flop')

    # --- Outcome ---
    if went_to_showdown(hand):
        add('showdown')

    if _all_in_preflop(hand, preflop):
        add('all_in_preflop', 'preflop')

    # --- Flop texture ---
    rows.extend(_label_flop_texture(boards, hand))

    # --- Hole cards (showdown hands / 888poker) ---
    rows.extend(_label_hole_cards(hand))

    return rows


def _detect_squeeze(preflop: list[str]) -> bool:
    """Return True if there was a raise, then ≥1 call, then another raise."""
    raise_seen = False
    call_after_raise = False
    for action in preflop:
        if 'cbr' in action:
            if raise_seen and call_after_raise:
                return True
            raise_seen = True
            call_after_raise = False
        elif 'cc' in action and raise_seen:
            call_after_raise = True
    return False


def _find_preflop_aggressor(preflop: list[str]) -> int | None:
    """Return 1-based index of the last cbr preflop (the preflop aggressor)."""
    last_raiser = None
    for action in preflop:
        if 'cbr' in action:
            parts = action.split()
            if parts[0].startswith('p') and parts[0][1:].isdigit():
                last_raiser = int(parts[0][1:])
    return last_raiser


def _first_bet_player(flop_actions: list[str]) -> int | None:
    """Return 1-based index of the first player to bet/raise on the flop."""
    for action in flop_actions:
        if 'cbr' in action:
            parts = action.split()
            if parts[0].startswith('p') and parts[0][1:].isdigit():
                return int(parts[0][1:])
    return None


def _has_check_raise(street_actions: list[str]) -> bool:
    """True if any player checked then later raised on the same street."""
    checked: set[int] = set()
    for action in street_actions:
        parts = action.split()
        if not (parts[0].startswith('p') and parts[0][1:].isdigit()):
            continue
        pidx = int(parts[0][1:])
        verb = parts[1] if len(parts) > 1 else ''
        if verb == 'cc':
            checked.add(pidx)
        elif verb == 'cbr' and pidx in checked:
            return True
    return False


def _all_in_preflop(hand: Hand, preflop: list[str]) -> bool:
    """Return True if any player went all-in preflop."""
    stacks = list(hand.starting_stacks)
    street_bets = list(hand.blinds_or_straddles) + [0.0] * (hand.n_players - len(hand.blinds_or_straddles))
    for action in preflop:
        parts = action.split()
        if not (parts[0].startswith('p') and parts[0][1:].isdigit()):
            continue
        pidx = int(parts[0][1:]) - 1
        verb = parts[1] if len(parts) > 1 else ''
        if verb == 'cbr' and len(parts) >= 3:
            total_bet = float(parts[2])
            additional = total_bet - street_bets[pidx]
            stacks[pidx] -= additional
            street_bets[pidx] = total_bet
            if stacks[pidx] <= 0:
                return True
        elif verb == 'cc':
            facing = max(street_bets[:hand.n_players])
            additional = facing - street_bets[pidx]
            additional = min(additional, stacks[pidx])
            stacks[pidx] -= additional
            street_bets[pidx] += additional
            if stacks[pidx] <= 0:
                return True
    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _run_auto_label(hands: list[Hand], conn: sqlite3.Connection, filter_label: str | None = None):
    total_rows = 0
    for hand in hands:
        rows = label_hand(hand)
        if filter_label:
            rows = [r for r in rows if r.label == filter_label]
        n = insert_labels(rows, conn)
        total_rows += n
    print(f"[labeller] Inserted {total_rows} new label rows for {len(hands)} hands.")


def main():
    parser = argparse.ArgumentParser(description='Auto-label poker hands into labels.db')
    src = parser.add_mutually_exclusive_group()
    src.add_argument('--file', help='Path to a single .phhs file')
    src.add_argument('--dir',  help='Directory containing .phhs files')

    parser.add_argument('--label',   help='Only insert this specific label (filter)')
    parser.add_argument('--db',      default=str(DB_PATH), help='Path to SQLite DB')

    # Manual label addition
    parser.add_argument('--add',       action='store_true', help='Manually add one label')
    parser.add_argument('--hand-id',   type=int)
    parser.add_argument('--hand-file', help='Source filename for manual label')
    parser.add_argument('--street')
    parser.add_argument('--player-idx', type=int)
    parser.add_argument('--note')

    args = parser.parse_args()
    conn = get_connection(Path(args.db))

    if args.add:
        if not (args.hand_id and args.hand_file and args.label):
            parser.error('--add requires --hand-id, --hand-file, and --label')
        row = LabelRow(args.hand_id, args.hand_file, args.label,
                       args.street, args.player_idx, args.note)
        n = insert_labels([row], conn)
        print(f"[labeller] Inserted {n} row(s).")
        return

    if args.file:
        hands = load_file(args.file)
    elif args.dir:
        hands = load_directory(args.dir)
    else:
        parser.error('Provide --file or --dir (or --add for manual entry)')

    _run_auto_label(hands, conn, filter_label=args.label)
    conn.close()


if __name__ == '__main__':
    main()
