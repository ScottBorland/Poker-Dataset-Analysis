"""spot_spec_export.py — Translate a fingerprint type into a solvable spot spec.

Takes a fingerprint-type dict (the shape spot_priority.rank_spots() emits per
row) and writes a JSON "spot spec" into cfr_solver/spots/ — the file-based
contract cfr_solver/ reads to build and solve an OpenSpiel game. No shared
imports with cfr_solver/; this only writes a plain JSON file.

v1 scope: heads-up only. Handles both preflop and postflop spots — for
postflop, a single concrete representative board (the most common actual
board string among matching hands) is attached, since fingerprints only
store a texture bucket, not real cards.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).parent))

from api import FP_TYPE_COLUMNS, FingerprintKey, _fingerprint_key_predicate
import hand_utils
from hand_utils import split_streets
from range_charts import infer_spot_roles
from scripts import load_hands_by_id

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'poker.db')
SPOTS_DIR = Path(__file__).parent.parent / 'cfr_solver' / 'spots'

_STREET_ORDER = ['preflop', 'flop', 'turn', 'river']


def _connect():
    import sqlite3
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _matching_hand_rows(fingerprint_type: dict, venue: str, con) -> list[tuple[int, str, str]]:
    """Return [(hand_id, file, venue), ...] for player_hands rows matching this type."""
    key = FingerprintKey(**{c: fingerprint_type.get(c) for c in FP_TYPE_COLUMNS})
    predicate, params = _fingerprint_key_predicate(key)
    sql = f"""
        SELECT DISTINCT fp.hand_id, fp.file, ph.venue
        FROM fingerprints fp
        JOIN player_hands ph INDEXED BY idx_ph_hand
            ON ph.hand_id = fp.hand_id AND ph.file = fp.file AND ph.seat_idx = fp.player_idx
        WHERE {predicate} AND ph.venue = ?
    """
    rows = con.execute(sql, [*params, venue]).fetchall()
    return [(r['hand_id'], r['file'], r['venue']) for r in rows]


_CANDIDATE_BET_FRACTIONS = [0.33, 0.5, 0.66, 0.75, 1.0, 1.25, 1.5, 2.0]
_MIN_BUCKET_MASS = 0.05  # a bucket needs >= 5% of observed first-bets to count


def _first_bet_ratio(hand, street: str, pot_before_street: float) -> Optional[float]:
    """Ratio of the street's first bet/raise size to the pot at street start.

    Postflop-only: postflop streets always start with every player's
    street-bet at 0 (no blinds), so the first `cbr` action's total IS the
    bet size directly. Preflop sizing is relative to the blind/prior raise,
    not a clean pot-fraction, so this returns None for street='preflop'
    (harmless in practice — preflop HU volume in this dataset is already
    too thin to build a bucket list from, see the plan doc).
    """
    if street == 'preflop' or pot_before_street <= 0:
        return None
    streets, _ = split_streets(hand.actions)
    for action in streets.get(street, []):
        parts = action.split()
        if len(parts) >= 3 and parts[0].startswith('p') and parts[0][1:].isdigit() and parts[1] == 'cbr':
            return float(parts[2]) / pot_before_street
    return None


def _derive_bet_size_fractions(hands, street: str) -> list[float]:
    """Cluster observed first-bet-of-the-street sizes into a small set of
    pot-fraction buckets, keeping only buckets with meaningful mass."""
    ratios = []
    for hand in hands:
        _, pot, _ = hand_utils.street_start_state(hand, street)
        ratio = _first_bet_ratio(hand, street, pot)
        if ratio and ratio > 0:
            ratios.append(ratio)

    if not ratios:
        return []

    counts = Counter()
    for r in ratios:
        nearest = min(_CANDIDATE_BET_FRACTIONS, key=lambda c: abs(c - r))
        counts[nearest] += 1

    total = sum(counts.values())
    return sorted(f for f, n in counts.items() if n / total >= _MIN_BUCKET_MASS)


def _board_through_street(hand, street: str) -> Optional[str]:
    if street == 'preflop':
        return None
    _, boards = split_streets(hand.actions)
    running = ''
    for s in ('flop', 'turn', 'river'):
        if boards.get(s):
            running += boards[s]
        if s == street:
            break
    return running or None


def build_spot_spec(fingerprint_type: dict, spot_id: str, venue: str = '888poker') -> dict:
    con = _connect()
    try:
        rows = _matching_hand_rows(fingerprint_type, venue, con)
    finally:
        con.close()

    if not rows:
        raise ValueError(f"No matching {venue} hands for fingerprint type: {fingerprint_type}")

    hands = load_hands_by_id(rows)
    street = fingerprint_type['street']

    effective_stacks_bb: list[float] = []
    pots_bb: list[float] = []
    boards: list[str] = []

    for hand in hands:
        stacks, pot, still_in = hand_utils.street_start_state(hand, street)
        big_blind = hand.blinds_or_straddles[1] if len(hand.blinds_or_straddles) > 1 else None
        if not big_blind or not still_in:
            continue
        eff_stack = min(stacks[p - 1] for p in still_in)
        effective_stacks_bb.append(eff_stack / big_blind)
        pots_bb.append(pot / big_blind)
        board = _board_through_street(hand, street)
        if board:
            boards.append(board)

    if not effective_stacks_bb:
        raise ValueError(f"Could not derive stack/pot data for any matching hand (spot {spot_id})")

    representative_board = None
    if boards:
        representative_board = Counter(boards).most_common(1)[0][0]

    positions = fingerprint_type['positions']
    pot_type = fingerprint_type.get('pot_type')

    bet_size_fractions = _derive_bet_size_fractions(hands, street)
    action_abstraction = 'bet_buckets' if bet_size_fractions else 'push_fold'

    spec = {
        'spot_id': spot_id,
        'fingerprint_type': {c: fingerprint_type.get(c) for c in FP_TYPE_COLUMNS},
        'street': street,
        'positions': positions,
        'n_matching_hands': len(hands),
        'effective_stack_bb': round(statistics.median(effective_stacks_bb), 2),
        'pot_bb_at_street_start': round(statistics.median(pots_bb), 2),
        'action_abstraction': action_abstraction,
        'bet_size_fractions': bet_size_fractions or None,
        'board': representative_board,
        'ranges': infer_spot_roles(positions, pot_type),
        'source': {
            'venue': venue,
            'generator': 'src/spot_spec_export.py',
        },
    }
    return spec


def export_spot_spec(fingerprint_type: dict, spot_id: str, venue: str = '888poker') -> Path:
    spec = build_spot_spec(fingerprint_type, spot_id, venue)
    SPOTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SPOTS_DIR / f"{spot_id}.json"
    out_path.write_text(json.dumps(spec, indent=2))
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spot-id', required=True)
    parser.add_argument('--fingerprint-type', required=True,
                         help='JSON dict of the 12 FP_TYPE_COLUMNS values')
    parser.add_argument('--venue', default='888poker')
    args = parser.parse_args()

    fp_type = json.loads(args.fingerprint_type)
    out_path = export_spot_spec(fp_type, args.spot_id, args.venue)
    print(f"Wrote {out_path}")
    print(json.dumps(json.loads(out_path.read_text()), indent=2))
