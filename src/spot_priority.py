"""spot_priority.py — Rank heads-up fingerprint types by how much they're worth solving.

Scoped to ScottyWotty's own 888poker hands. Priority combines frequency
(how often this exact situation comes up) with value-at-stake (average pot
size in BB), since a rare-but-huge-pot spot can matter more than a common
min-raise limp pot.

Reuses the same DB/index patterns already proven in src/api.py's
/fingerprints/distribution venue-filtered branch: start from the small
venue-filtered slice of player_hands (via idx_ph_venue_hand), then join
into fingerprints by (hand_id, file, player_idx=seat_idx).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from typing import Any, Optional

import pandas as pd

from api import FP_TYPE_COLUMNS

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'poker.db')


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA cache_size = -262144")
    con.execute("PRAGMA mmap_size = 2147483648")
    con.execute("PRAGMA temp_store = MEMORY")
    return con


def rank_spots(
    limit: int = 50,
    min_count: int = 30,
    venue: str = '888poker',
    con: Optional[sqlite3.Connection] = None,
) -> pd.DataFrame:
    """Return heads-up fingerprint types ranked by priority_score = count * avg_pot_bb.

    Excludes 'multiway' positions (v1 scope is heads-up only, see the plan doc).
    avg_pot_bb is computed per-hand first (SUM(invested)/AVG(big_blind) grouped
    by hand_id) before averaging across hands, to avoid double-counting the
    2 player_hands rows each hand contributes.
    """
    close_after = con is None
    con = con or _connect()
    try:
        fp_cols_sql = ", ".join(f"fp.{c}" for c in FP_TYPE_COLUMNS)

        sql = f"""
            WITH hand_pot_bb AS (
                SELECT ph.hand_id, SUM(ph.invested) / AVG(ph.big_blind) AS pot_bb
                FROM player_hands ph INDEXED BY idx_ph_venue_hand
                WHERE ph.venue = ? AND ph.big_blind > 0
                GROUP BY ph.hand_id
            )
            SELECT {fp_cols_sql}, COUNT(*) AS n, AVG(hb.pot_bb) AS avg_pot_bb
            FROM player_hands ph INDEXED BY idx_ph_venue_hand
            JOIN fingerprints fp
                ON fp.hand_id = ph.hand_id AND fp.file = ph.file AND fp.player_idx = ph.seat_idx
            JOIN hand_pot_bb hb ON hb.hand_id = ph.hand_id
            WHERE ph.venue = ?
                AND fp.positions IS NOT NULL AND fp.positions != 'multiway'
            GROUP BY {fp_cols_sql}
            HAVING n >= ?
            ORDER BY n * avg_pot_bb DESC
            LIMIT ?
        """
        rows = con.execute(sql, [venue, venue, min_count, limit]).fetchall()
        df = pd.DataFrame([dict(r) for r in rows])
        if df.empty:
            return df
        for col in ('in_position', 'board_paired', 'board_monotone', 'board_two_tone'):
            df[col] = df[col].map(lambda v: None if v is None else bool(v))
        df['avg_pot_bb'] = df['avg_pot_bb'].round(2)
        df['priority_score'] = (df['n'] * df['avg_pot_bb']).round(1)
        df = df.rename(columns={'n': 'count'})
        return df.sort_values('priority_score', ascending=False).reset_index(drop=True)
    finally:
        if close_after:
            con.close()


def _print_top(df: pd.DataFrame, by: str, n: int) -> None:
    print(f"\n=== Top {n} by {by} ===")
    cols = [*FP_TYPE_COLUMNS, 'count', 'avg_pot_bb', 'priority_score']
    with pd.option_context('display.max_rows', n, 'display.width', 200):
        print(df.sort_values(by, ascending=False).head(n)[cols].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=50, help='How many fingerprint types to rank')
    parser.add_argument('--min-count', type=int, default=30, help='Minimum sample size per group')
    parser.add_argument('--venue', default='888poker')
    parser.add_argument('--top', type=int, default=20, help='How many rows to print per view')
    args = parser.parse_args()

    df = rank_spots(limit=args.limit, min_count=args.min_count, venue=args.venue)
    if df.empty:
        print("No fingerprint types found matching the given filters.")
    else:
        _print_top(df, 'priority_score', args.top)
        _print_top(df, 'count', args.top)
