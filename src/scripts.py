"""
scripts.py — High-level convenience functions for interactive analysis.

Designed for use in notebooks or a REPL:

    from scripts import load, top_players, player_stats, rake_stats

All functions that query the database accept an optional `con` argument.
If omitted, a fresh connection to db/poker.db is opened automatically.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from parser import Hand

_SRC = Path(__file__).parent
_ROOT = _SRC.parent
_POKER_DB = _ROOT / 'db' / 'poker.db'
_LABELS_DB = _ROOT / 'labels' / 'labels.db'


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _con(con: sqlite3.Connection | None, db_path: Path = _POKER_DB) -> tuple[sqlite3.Connection, bool]:
    """Return (connection, should_close). Caller must close if should_close is True."""
    if con is not None:
        return con, False
    return sqlite3.connect(str(db_path)), True


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load(path: str | Path) -> list['Hand']:
    """Load all hands from a single .phhs file."""
    import sys
    sys.path.insert(0, str(_SRC))
    from parser import load_file
    return load_file(Path(path))


def load_all(folder: str | Path = '.') -> list['Hand']:
    """Load all .phhs files in a folder."""
    import sys
    sys.path.insert(0, str(_SRC))
    from parser import load_directory
    return load_directory(Path(folder))


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def connect(db_path: str | Path = _POKER_DB) -> sqlite3.Connection:
    """Open a connection to poker.db (or a custom path). Caller is responsible for closing."""
    return sqlite3.connect(str(db_path))


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest(
    folder: str | Path = '.',
    reprocess: str | None = None,
    reprocess_all: bool = False,
) -> None:
    """
    Ingest all .phhs files in *folder* into db/poker.db.

    Args:
        folder:        Directory containing .phhs files.
        reprocess:     Filename to force re-ingest (removes its old rows first).
        reprocess_all: If True, wipe and re-ingest every file.
    """
    import sys
    sys.path.insert(0, str(_SRC))
    import ingest as _ingest

    conn = _ingest.get_connection()
    done = _ingest._ingested_files(conn)
    folder = Path(folder)

    for path in sorted(folder.glob('*.phhs')):
        filename = path.name
        force = reprocess_all or (filename == reprocess)
        if force and filename in done:
            print(f'[ingest] Re-processing {filename}...')
            _ingest._remove_file(conn, filename)
        elif filename in done:
            print(f'[ingest] Skipping {filename} (already ingested)')
            continue
        print(f'[ingest] Ingesting {filename}...')
        n = _ingest.ingest_file(conn, path)
        print(f'[ingest] {filename}: {n} hands')

    conn.close()
    print('[ingest] Done.')


# ---------------------------------------------------------------------------
# Labelling
# ---------------------------------------------------------------------------

def add_labels(path_or_folder: str | Path) -> int:
    """
    Run the auto-labeller on a file or folder and write results to labels/labels.db.
    Returns the number of new label rows inserted.
    """
    import sys
    sys.path.insert(0, str(_SRC))
    from parser import load_file, load_directory
    from labeller import label_hand, insert_labels
    from labeller import get_connection as _lbl_con

    p = Path(path_or_folder)
    hands = load_directory(p) if p.is_dir() else load_file(p)
    conn = _lbl_con()
    total = 0
    for hand in hands:
        total += insert_labels(label_hand(hand), conn)
    conn.close()
    print(f'Inserted {total:,} label rows for {len(hands):,} hands.')
    return total


# ---------------------------------------------------------------------------
# Player leaderboards
# ---------------------------------------------------------------------------

def top_players(
    n: int = 10,
    by: str = 'net_won',
    min_hands: int = 5,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """
    Return the top-N players ranked by *by*.

    Args:
        by: 'net_won' | 'net_won_pre_rake' | 'invested'
    """
    conn, should_close = _con(con)
    try:
        if by == 'net_won_pre_rake':
            query = """
                WITH hand_rake AS (
                    SELECT hand_id,
                           SUM(invested)                 total_invested,
                           SUM(invested) - SUM(winnings) rake
                    FROM player_hands
                    GROUP BY hand_id
                    HAVING SUM(CASE WHEN winnings IS NULL THEN 1 ELSE 0 END) = 0
                      AND SUM(invested) - SUM(winnings) >= 0
                )
                SELECT ph.player_id,
                       COUNT(*)                                                    hands,
                       ROUND(SUM(ph.invested), 2)                                  total_invested,
                       ROUND(SUM(hr.rake * ph.invested / hr.total_invested), 2)    rake_paid,
                       ROUND(SUM(ph.net_won), 2)                                   net_won,
                       ROUND(SUM(ph.net_won)
                           + SUM(hr.rake * ph.invested / hr.total_invested), 2)    net_won_pre_rake
                FROM player_hands ph
                JOIN hand_rake hr ON ph.hand_id = hr.hand_id
                WHERE ph.net_won IS NOT NULL
                GROUP BY ph.player_id
                HAVING hands >= ?
                ORDER BY net_won_pre_rake DESC
                LIMIT ?
            """
        else:
            query = f"""
                SELECT player_id,
                       COUNT(*)                   hands,
                       ROUND(SUM(invested), 2)    total_invested,
                       ROUND(SUM(net_won), 2)     net_won,
                       ROUND(AVG(net_won), 4)     avg_per_hand
                FROM player_hands
                WHERE net_won IS NOT NULL
                GROUP BY player_id
                HAVING hands >= ?
                ORDER BY {by} DESC
                LIMIT ?
            """
        return pd.read_sql(query, conn, params=[min_hands, n])
    finally:
        if should_close:
            conn.close()


def bottom_players(
    n: int = 10,
    by: str = 'net_won',
    min_hands: int = 5,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """Return the bottom-N players (biggest losers) ranked by *by*."""
    conn, should_close = _con(con)
    try:
        query = f"""
            SELECT player_id,
                   COUNT(*)                   hands,
                   ROUND(SUM(invested), 2)    total_invested,
                   ROUND(SUM(net_won), 2)     net_won,
                   ROUND(AVG(net_won), 4)     avg_per_hand
            FROM player_hands
            WHERE net_won IS NOT NULL
            GROUP BY player_id
            HAVING hands >= ?
            ORDER BY {by} ASC
            LIMIT ?
        """
        return pd.read_sql(query, conn, params=[min_hands, n])
    finally:
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Player deep-dive
# ---------------------------------------------------------------------------

def player_stats(
    player_id: str,
    con: sqlite3.Connection | None = None,
) -> dict:
    """
    Return a summary dict for one player covering overall P&L,
    positional breakdown, and label breakdown.
    """
    conn, should_close = _con(con)
    try:
        overall = pd.read_sql("""
            SELECT COUNT(*)                hands,
                   ROUND(SUM(invested),2)  total_invested,
                   ROUND(SUM(net_won),2)   net_won,
                   ROUND(AVG(net_won),4)   avg_per_hand,
                   ROUND(100.0*SUM(saw_flop)/COUNT(*),1)   flop_seen_pct,
                   ROUND(100.0*SUM(went_to_sd)/COUNT(*),1) showdown_pct
            FROM player_hands WHERE player_id = ?
        """, conn, params=[player_id]).iloc[0].to_dict()

        by_position = pd.read_sql("""
            SELECT position, n_players,
                   COUNT(*)                hands,
                   ROUND(SUM(net_won),2)   net_won
            FROM player_hands
            WHERE player_id = ? AND net_won IS NOT NULL
            GROUP BY position, n_players ORDER BY net_won DESC
        """, conn, params=[player_id])

        by_label = pd.read_sql("""
            SELECT l.label,
                   COUNT(*)                hands,
                   ROUND(SUM(ph.net_won),2) net_won
            FROM player_hands ph
            JOIN labels l ON ph.hand_id = l.hand_id
            WHERE ph.player_id = ? AND ph.net_won IS NOT NULL
            GROUP BY l.label ORDER BY net_won DESC
        """, conn, params=[player_id])

        return {
            'player_id':   player_id,
            'overall':     overall,
            'by_position': by_position,
            'by_label':    by_label,
        }
    finally:
        if should_close:
            conn.close()


def player_hand_history(
    player_id: str,
    label: str | None = None,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """
    Return every hand for a player as a DataFrame, optionally filtered to a label.
    Columns: hand_id, position, n_players, invested, net_won, saw_flop, went_to_sd.
    """
    conn, should_close = _con(con)
    try:
        if label:
            query = """
                SELECT ph.hand_id, ph.position, ph.n_players, ph.stack,
                       ph.invested, ph.net_won, ph.saw_flop, ph.went_to_sd
                FROM player_hands ph
                JOIN labels l ON ph.hand_id = l.hand_id
                WHERE ph.player_id = ? AND l.label = ?
                ORDER BY ph.hand_id
            """
            return pd.read_sql(query, conn, params=[player_id, label])
        else:
            query = """
                SELECT hand_id, position, n_players, stack,
                       invested, net_won, saw_flop, went_to_sd
                FROM player_hands
                WHERE player_id = ?
                ORDER BY hand_id
            """
            return pd.read_sql(query, conn, params=[player_id])
    finally:
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Hand lookup
# ---------------------------------------------------------------------------

def hand_details(
    hand_id: int,
    con: sqlite3.Connection | None = None,
) -> dict:
    """
    Return a dict with player rows and labels for a specific hand_id.
    Keys: 'players' (DataFrame), 'labels' (list[str]).
    """
    conn, should_close = _con(con)
    try:
        players = pd.read_sql("""
            SELECT player_id, seat_idx, position, stack, invested, winnings, net_won,
                   saw_flop, went_to_sd
            FROM player_hands WHERE hand_id = ?
            ORDER BY seat_idx
        """, conn, params=[hand_id])

        labels = [
            r[0] for r in
            conn.execute("SELECT label FROM labels WHERE hand_id = ?", (hand_id,)).fetchall()
        ]

        return {'hand_id': hand_id, 'players': players, 'labels': labels}
    finally:
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def label_counts(con: sqlite3.Connection | None = None) -> pd.DataFrame:
    """Return a DataFrame of label counts sorted by frequency."""
    conn, should_close = _con(con)
    try:
        return pd.read_sql("""
            SELECT label, COUNT(*) count
            FROM labels GROUP BY label ORDER BY count DESC
        """, conn)
    finally:
        if should_close:
            conn.close()


def hands_with_label(
    label: str,
    limit: int = 20,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """Return player_hands rows for hands carrying a specific label."""
    conn, should_close = _con(con)
    try:
        return pd.read_sql("""
            SELECT ph.hand_id, ph.player_id, ph.position, ph.n_players,
                   ph.invested, ph.net_won, ph.saw_flop, ph.went_to_sd
            FROM player_hands ph
            JOIN labels l ON ph.hand_id = l.hand_id
            WHERE l.label = ?
            ORDER BY ph.hand_id
            LIMIT ?
        """, conn, params=[label, limit])
    finally:
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------

def positional_stats(
    n_players: int | None = 6,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """
    Return positional net P&L stats.

    Args:
        n_players: Filter to a specific table size (e.g. 6 for 6-max).
                   Pass None to return all sizes grouped together.
    """
    conn, should_close = _con(con)
    try:
        where = "WHERE n_players = ?" if n_players is not None else ""
        params = [n_players] if n_players is not None else []
        return pd.read_sql(f"""
            SELECT position,
                   COUNT(*)                                        hands,
                   ROUND(SUM(net_won), 2)                          net_won,
                   ROUND(AVG(net_won), 4)                          avg_per_hand,
                   ROUND(100.0 * SUM(saw_flop)   / COUNT(*), 1)   flop_seen_pct,
                   ROUND(100.0 * SUM(went_to_sd) / COUNT(*), 1)   showdown_pct
            FROM player_hands
            {where}
            GROUP BY position ORDER BY net_won DESC
        """, conn, params=params)
    finally:
        if should_close:
            conn.close()


def rake_stats(con: sqlite3.Connection | None = None) -> dict:
    """
    Return a summary dict of rake collected across all hands with known winnings.
    Keys: raked_hands, total_rake, avg_rake_per_hand, avg_rake_pct.
    """
    conn, should_close = _con(con)
    try:
        row = pd.read_sql("""
            WITH hand_rake AS (
                SELECT hand_id,
                       SUM(invested)              total_invested,
                       SUM(invested) - SUM(winnings) rake
                FROM player_hands
                GROUP BY hand_id
                HAVING SUM(CASE WHEN winnings IS NULL THEN 1 ELSE 0 END) = 0
            )
            SELECT COUNT(*)                              raked_hands,
                   ROUND(SUM(rake), 2)                   total_rake,
                   ROUND(AVG(rake), 4)                   avg_rake_per_hand,
                   ROUND(AVG(100.0*rake/total_invested), 2) avg_rake_pct
            FROM hand_rake WHERE rake >= 0
        """, conn).iloc[0]
        return row.to_dict()
    finally:
        if should_close:
            conn.close()


def pot_type_stats(
    pot_types: list[str] | None = None,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """
    Return net P&L and showdown/flop stats broken down by pot-type label.

    Default pot types: limp_pot, single_raised_pot, 3bet_pot, 4bet_pot, squeeze.
    """
    conn, should_close = _con(con)
    try:
        if pot_types is None:
            pot_types = ['limp_pot', 'single_raised_pot', '3bet_pot', '4bet_pot', 'squeeze']
        rows = []
        for label in pot_types:
            r = pd.read_sql("""
                SELECT COUNT(DISTINCT ph.hand_id)              unique_hands,
                       ROUND(SUM(ph.net_won), 2)               net_won,
                       ROUND(100.0*SUM(ph.went_to_sd)/COUNT(*),1) sd_pct,
                       ROUND(100.0*SUM(ph.saw_flop)/COUNT(*),1)   flop_seen_pct
                FROM player_hands ph
                JOIN labels l ON ph.hand_id = l.hand_id
                WHERE l.label = ? AND ph.net_won IS NOT NULL
            """, conn, params=[label]).iloc[0].to_dict()
            r['pot_type'] = label
            rows.append(r)
        return pd.DataFrame(rows).set_index('pot_type')
    finally:
        if should_close:
            conn.close()


# ---------------------------------------------------------------------------
# Quick summary
# ---------------------------------------------------------------------------

def summary(con: sqlite3.Connection | None = None) -> None:
    """Print a quick overview of what's in the database."""
    conn, should_close = _con(con)
    try:
        hands   = conn.execute("SELECT COUNT(DISTINCT hand_id) FROM player_hands").fetchone()[0]
        players = conn.execute("SELECT COUNT(DISTINCT player_id) FROM player_hands").fetchone()[0]
        files   = conn.execute("SELECT COUNT(*) FROM ingested_files").fetchone()[0]
        labels  = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        ul      = conn.execute("SELECT COUNT(DISTINCT label) FROM labels").fetchone()[0]
        print(f"Files ingested : {files}")
        print(f"Hands          : {hands:,}")
        print(f"Unique players : {players:,}")
        print(f"Labels         : {labels:,} rows, {ul} types")
        rs = rake_stats(con=conn)
        print(f"Rake tracked   : ${rs['total_rake']:.2f} over {int(rs['raked_hands'])} hands "
              f"({rs['avg_rake_pct']:.2f}% avg)")
    finally:
        if should_close:
            conn.close()
