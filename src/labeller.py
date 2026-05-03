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
        # Check if anyone limped
        has_limp = any('cc' in a for a in preflop if a.startswith('p'))
        if has_limp:
            add('limp_pot', 'preflop')
    elif n_raises == 1:
        add('single_raised_pot', 'preflop')
        add('rfi', 'preflop')
    elif n_raises == 2:
        add('3bet_pot', 'preflop')
        # Detect squeeze: raise + ≥1 caller before the 3-bet
        callers_before_3bet = _detect_squeeze(preflop)
        if callers_before_3bet:
            add('squeeze', 'preflop')
    elif n_raises >= 3:
        add('4bet_pot', 'preflop')

    # --- Postflop ---
    if boards['flop'] is not None:
        flop_actions = streets['flop']
        preflop_aggressor = _find_preflop_aggressor(preflop)

        if preflop_aggressor is not None:
            # cbet: preflop aggressor is first to bet on flop
            first_bet = _first_bet_player(flop_actions)
            if first_bet == preflop_aggressor:
                add('cbet_flop', 'flop', preflop_aggressor)

        # Check-raise on flop
        if _has_check_raise(flop_actions):
            add('check_raise_flop', 'flop')

        if is_multiway(hand):
            add('multi_way', 'flop')

    # --- Outcome ---
    if went_to_showdown(hand):
        add('showdown')

    # All-in preflop: any player has 0 chips remaining after preflop
    if _all_in_preflop(hand, preflop):
        add('all_in_preflop', 'preflop')

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
