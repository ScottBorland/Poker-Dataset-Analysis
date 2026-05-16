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

# Rank ordering high→low for canonical hand notation
_RANKS = list('AKQJT98765432')
_RANK_IDX = {r: i for i, r in enumerate(_RANKS)}

# Module-level cache so 888poker files are only parsed once per session
_888_hands_cache: list | None = None
_LABELS_DB = _ROOT / 'labels' / 'labels.db'

# Lazy cache: filename (basename) → list of full Paths on disk
_phhs_path_map: dict[str, list] | None = None


def _get_phhs_path_map() -> dict[str, list]:
    """Build (or return cached) mapping of .phhs basename → list of full Paths."""
    global _phhs_path_map
    if _phhs_path_map is None:
        from collections import defaultdict
        m: dict[str, list] = defaultdict(list)
        phhs_root = _ROOT / 'data' / 'phhs files'
        if phhs_root.is_dir():
            for p in phhs_root.rglob('*.phhs'):
                m[p.name].append(p)
        _phhs_path_map = dict(m)
    return _phhs_path_map


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
                       COUNT(*)                              hands,
                       ROUND(100.0*SUM(vpip)/COUNT(*), 1)   vpip_pct,
                       ROUND(100.0*SUM(pfr) /COUNT(*), 1)   pfr_pct,
                       ROUND(SUM(invested), 2)               total_invested,
                       ROUND(SUM(net_won), 2)                net_won,
                       ROUND(AVG(net_won), 4)                avg_per_hand
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
                   COUNT(*)                              hands,
                   ROUND(100.0*SUM(vpip)/COUNT(*), 1)   vpip_pct,
                   ROUND(100.0*SUM(pfr) /COUNT(*), 1)   pfr_pct,
                   ROUND(SUM(invested), 2)               total_invested,
                   ROUND(SUM(net_won), 2)                net_won,
                   ROUND(AVG(net_won), 4)                avg_per_hand
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


def vpip_pfr_stats(
    min_hands: int = 100,
    con: sqlite3.Connection | None = None,
) -> pd.DataFrame:
    """
    Return VPIP%, PFR%, and aggression factor for all players with enough hands.
    Sorted by hands descending so high-volume regulars appear first.

    VPIP%  — % of hands player voluntarily put money in preflop
    PFR%   — % of hands player raised preflop
    AF     — PFR / (VPIP - PFR); aggression factor (ratio of raises to calls preflop)
    """
    conn, should_close = _con(con)
    try:
        return pd.read_sql("""
            SELECT player_id,
                   COUNT(*)                                        hands,
                   ROUND(100.0 * SUM(vpip) / COUNT(*), 1)         vpip_pct,
                   ROUND(100.0 * SUM(pfr)  / COUNT(*), 1)         pfr_pct,
                   ROUND(CASE WHEN SUM(vpip) - SUM(pfr) = 0 THEN NULL
                         ELSE 1.0 * SUM(pfr) / (SUM(vpip) - SUM(pfr))
                         END, 2)                                   af,
                   ROUND(SUM(net_won), 2)                          net_won
            FROM player_hands
            GROUP BY player_id
            HAVING hands >= ?
            ORDER BY hands DESC
        """, conn, params=[min_hands])
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
            SELECT COUNT(*)                                  hands,
                   ROUND(100.0*SUM(vpip)/COUNT(*), 1)        vpip_pct,
                   ROUND(100.0*SUM(pfr) /COUNT(*), 1)        pfr_pct,
                   ROUND(SUM(invested),2)                    total_invested,
                   ROUND(SUM(net_won),2)                     net_won,
                   ROUND(AVG(net_won),4)                     avg_per_hand,
                   ROUND(100.0*SUM(saw_flop)/COUNT(*),1)     flop_seen_pct,
                   ROUND(100.0*SUM(went_to_sd)/COUNT(*),1)   showdown_pct
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


def label_replay(
    labels: str | list[str],
    player_id: str | None = None,
    position: str | None = None,
    n_players: int | None = None,
    max_hands: int = 500,
    replay: bool = True,
    con: sqlite3.Connection | None = None,
) -> dict:
    """
    Filter hands by one or more labels, print stats, and optionally open the replayer.

    If a list of labels is given, a hand must carry ALL of them (AND logic).

    Stats:
    - Avg pot size in BB (from loaded sample)
    - If player_id given: that player's net P&L, avg/hand, flop%, showdown%, VPIP/PFR
    - Otherwise: avg P&L per position across all seated players

    Args:
        labels:     Label string or list. List = hand must have ALL labels.
        player_id:  Restrict to hands where this player was seated; stats focus on them.
        position:   Filter by the position player_id held (requires player_id).
        n_players:  Filter to a specific table size (e.g. 6 for 6-max).
        max_hands:  Cap on hands loaded for the replayer (default 500).
                    Stats always cover the full matching set.
        replay:     Set False to print stats only, without opening the replayer.

    Examples:
        label_replay('3bet_pot')
        label_replay(['3bet_pot', 'flop_monotone'])
        label_replay('squeeze', n_players=6)
        label_replay('flop_dry', player_id='ScottyWotty', position='BTN')
        label_replay('all_in_preflop', replay=False)   # stats only
    """
    import sys
    sys.path.insert(0, str(_SRC))
    from hand_utils import compute_investments

    if isinstance(labels, str):
        labels = [labels]

    if position is not None and player_id is None:
        print("[label_replay] 'position' filter requires 'player_id' — ignoring it.")
        position = None

    conn, should_close = _con(con)
    try:
        # ---- 1. Build matching hand_id set ----
        # INTERSECT across all labels, then optionally filter by player/n_players
        intersect_sql = '\nINTERSECT\n'.join(
            ['SELECT hand_id FROM labels WHERE label = ?'] * len(labels)
        )
        ph_conditions: list[str] = []
        ph_params: list = []
        if n_players is not None:
            ph_conditions.append('ph.n_players = ?')
            ph_params.append(n_players)
        if player_id is not None:
            ph_conditions.append('ph.player_id = ?')
            ph_params.append(player_id)
        if position is not None:
            ph_conditions.append('ph.position = ?')
            ph_params.append(position)

        if ph_conditions:
            where = 'WHERE ' + ' AND '.join(ph_conditions)
            id_sql = f"""
                SELECT DISTINCT lq.hand_id
                FROM ({intersect_sql}) lq
                JOIN player_hands ph ON lq.hand_id = ph.hand_id
                {where}
            """
        else:
            id_sql = intersect_sql

        all_ids = [r[0] for r in conn.execute(id_sql, labels + ph_params).fetchall()]
        total = len(all_ids)

        if not all_ids:
            print(f"No hands found matching: {labels}")
            return {'stats': {}, 'by_position': pd.DataFrame(), 'hands': []}

        # ---- 2. Temp table for all matching IDs (avoids SQLite variable limits) ----
        conn.execute('CREATE TEMP TABLE IF NOT EXISTS _lr_ids (hand_id INTEGER PRIMARY KEY)')
        conn.execute('DELETE FROM _lr_ids')
        conn.executemany('INSERT OR IGNORE INTO _lr_ids VALUES (?)', [(i,) for i in all_ids])

        # ---- 3. DB stats over ALL matching hands ----
        if player_id:
            row = conn.execute("""
                SELECT COUNT(*)                                       hands,
                       ROUND(SUM(net_won), 2)                         net_won,
                       ROUND(AVG(net_won), 4)                         avg_per_hand,
                       ROUND(AVG(net_won) * 100, 2)                   per_100,
                       ROUND(100.0 * SUM(saw_flop)   / COUNT(*), 1)   flop_pct,
                       ROUND(100.0 * SUM(went_to_sd) / COUNT(*), 1)   sd_pct,
                       ROUND(100.0 * SUM(vpip) / COUNT(*), 1)         vpip_pct,
                       ROUND(100.0 * SUM(pfr)  / COUNT(*), 1)         pfr_pct
                FROM player_hands ph
                JOIN _lr_ids hi ON ph.hand_id = hi.hand_id
                WHERE ph.player_id = ?
            """, [player_id]).fetchone()
            db_stats = {
                'hands': row[0], 'net_won': row[1], 'avg_per_hand': row[2],
                'per_100': row[3], 'flop_pct': row[4], 'sd_pct': row[5],
                'vpip_pct': row[6], 'pfr_pct': row[7],
            }
            by_position = pd.DataFrame()
        else:
            db_stats = {'hands': total}
            by_position = pd.read_sql("""
                SELECT ph.position,
                       COUNT(*)                                          hands,
                       ROUND(SUM(ph.net_won), 2)                         net_won,
                       ROUND(AVG(ph.net_won) * 100, 2)                   per_100,
                       ROUND(100.0 * SUM(ph.saw_flop)   / COUNT(*), 1)   flop_pct,
                       ROUND(100.0 * SUM(ph.went_to_sd) / COUNT(*), 1)   sd_pct
                FROM player_hands ph
                JOIN _lr_ids hi ON ph.hand_id = hi.hand_id
                WHERE ph.net_won IS NOT NULL
                GROUP BY ph.position ORDER BY per_100 DESC
            """, conn)

        # ---- 4. File/venue info for replay subset ----
        replay_ids = all_ids[:max_hands]
        conn.execute('CREATE TEMP TABLE IF NOT EXISTS _lr_rpl (hand_id INTEGER PRIMARY KEY)')
        conn.execute('DELETE FROM _lr_rpl')
        conn.executemany('INSERT OR IGNORE INTO _lr_rpl VALUES (?)', [(i,) for i in replay_ids])

        file_rows = conn.execute("""
            SELECT DISTINCT ph.hand_id, ph.file, ph.venue
            FROM player_hands ph
            JOIN _lr_rpl ri ON ph.hand_id = ri.hand_id
        """).fetchall()

    finally:
        if should_close:
            conn.close()

    # ---- 5. Load Hand objects from disk ----
    # Always load — also needed to compute pot-in-BB even when replay=False
    from collections import defaultdict
    from parser import load_file
    from parser_888 import load_file_888

    by_file: dict[tuple[str, str], set[int]] = defaultdict(set)
    for hand_id, file_, venue in file_rows:
        by_file[(file_, venue)].add(hand_id)

    phhs_map = _get_phhs_path_map()
    data_dir = _ROOT / 'data'
    loaded_hands: list = []

    for (filename, venue), ids in sorted(by_file.items()):
        if venue == '888poker':
            path = data_dir / '888poker' / filename
            if not path.exists():
                print(f"[label_replay] File not found, skipping: {filename}")
                continue
            loaded_hands.extend(h for h in load_file_888(path) if h.hand_id in ids)
        else:
            # Abs poker files may be nested — try all paths matching this basename
            candidates = phhs_map.get(filename, [])
            if not candidates:
                print(f"[label_replay] File not found, skipping: {filename}")
                continue
            found_ids: set[int] = set()
            for path in candidates:
                new_hands = [h for h in load_file(path) if h.hand_id in ids and h.hand_id not in found_ids]
                loaded_hands.extend(new_hands)
                found_ids.update(h.hand_id for h in new_hands)
                if found_ids >= ids:
                    break   # found all needed hands from this filename

    # ---- 6. Compute avg pot-in-BB from loaded hands ----
    # Use sum(compute_investments) — correctly returns uncalled bets, unlike final_pot()
    pot_bbs = []
    for h in loaded_hands:
        bb = h.blinds_or_straddles[1] if len(h.blinds_or_straddles) > 1 else 0
        if bb > 0:
            pot_bbs.append(sum(compute_investments(h)) / bb)
    avg_pot_bb = round(sum(pot_bbs) / len(pot_bbs), 1) if pot_bbs else None

    # ---- 7. Print stats ----
    filter_parts = []
    if n_players:
        filter_parts.append(f'{n_players}-max')
    if position:
        filter_parts.append(f'@ {position}')
    filter_str = ('  |  ' + '  |  '.join(filter_parts)) if filter_parts else ''

    print(f"\n{'='*54}")
    print(f"  Labels : {', '.join(labels)}{filter_str}")
    print(f"{'='*54}")
    print(f"  Total matching hands : {total:,}")
    if total > max_hands:
        print(f"  Loaded for replayer  : {len(loaded_hands):,}  (first {max_hands:,})")
    if avg_pot_bb is not None:
        sample_note = f"  (sample of {len(pot_bbs):,})" if total > max_hands else ''
        print(f"  Avg pot size         : {avg_pot_bb} BB{sample_note}")

    if player_id:
        s = db_stats
        print(f"\n  --- {player_id} ---")
        n = s.get('hands') or 0
        if n:
            nw = s['net_won'] or 0.0
            p100 = s['per_100'] or 0.0
            avg = s['avg_per_hand'] or 0.0
            print(f"  Hands      : {n:,}")
            print(f"  Net P&L    : ${nw:+.2f}  (${p100:+.2f} / 100 hands)")
            print(f"  Avg / hand : ${avg:+.4f}")
            print(f"  Flop seen  : {s['flop_pct']}%   Showdown : {s['sd_pct']}%")
            print(f"  VPIP / PFR : {s['vpip_pct']}% / {s['pfr_pct']}%")
        else:
            print(f"  {player_id} not found in these hands.")
    else:
        if not by_position.empty:
            print(f"\n  P&L by position (population across all seated players):")
            print(by_position.to_string(index=False))
    print()

    if not replay or not loaded_hands:
        return {'stats': db_stats, 'by_position': by_position, 'hands': loaded_hands}

    print(f"Launching replayer with {len(loaded_hands)} hands  (N/P to navigate, Q to quit)...")
    from replayer.main import run
    run(loaded_hands)

    return {'stats': db_stats, 'by_position': by_position, 'hands': loaded_hands}


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


# ---------------------------------------------------------------------------
# Starting-hand analysis + replayer launcher
# ---------------------------------------------------------------------------

def _load_888_hands() -> list:
    """Load all 888poker Hand objects, cached for the session."""
    global _888_hands_cache
    if _888_hands_cache is None:
        import sys
        sys.path.insert(0, str(_SRC))
        from parser_888 import load_file_888
        data_dir = _ROOT / 'data' / '888poker'
        if not data_dir.is_dir():
            raise FileNotFoundError(f"888poker data directory not found: {data_dir}")
        _888_hands_cache = []
        for f in sorted(data_dir.glob('*.txt')):
            if 'Summary' not in f.name:
                _888_hands_cache.extend(load_file_888(f))
        print(f"[hand_replay] Loaded {len(_888_hands_cache)} 888poker hands into cache")
    return _888_hands_cache


def _cards_to_canonical(cards: str) -> str | None:
    """'KdQs' → 'KQo',  'AsAh' → 'AA',  '????' → None."""
    if len(cards) != 4 or '?' in cards:
        return None
    r1, s1, r2, s2 = cards[0], cards[1], cards[2], cards[3]
    if r1 not in _RANK_IDX or r2 not in _RANK_IDX:
        return None
    if _RANK_IDX[r1] > _RANK_IDX[r2]:
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ('s' if s1 == s2 else 'o')


def _parse_hand_query(hand: str) -> list[str]:
    """
    Normalise user input into a list of canonical forms to match.
      'AQs' → ['AQs']
      'AQo' → ['AQo']
      'AQ'  → ['AQs', 'AQo']   (both suited and offsuit)
      'AA'  → ['AA']
    """
    hand = hand.strip()
    if len(hand) == 2:
        r1, r2 = hand[0].upper(), hand[1].upper()
        if r1 not in _RANK_IDX or r2 not in _RANK_IDX:
            raise ValueError(f"Invalid hand: {hand!r}")
        if _RANK_IDX[r1] > _RANK_IDX[r2]:
            r1, r2 = r2, r1
        return [r1 + r2] if r1 == r2 else [r1 + r2 + 's', r1 + r2 + 'o']
    elif len(hand) == 3:
        r1, r2, suf = hand[0].upper(), hand[1].upper(), hand[2].lower()
        if r1 not in _RANK_IDX or r2 not in _RANK_IDX or suf not in ('s', 'o'):
            raise ValueError(f"Invalid hand: {hand!r}. Use 'AQs', 'KTo', 'AA', or 'AQ'")
        if _RANK_IDX[r1] > _RANK_IDX[r2]:
            r1, r2 = r2, r1
        if r1 == r2:
            raise ValueError(f"Pairs cannot be suited/offsuit: use '{r1}{r2}'")
        return [r1 + r2 + suf]
    else:
        raise ValueError(f"Invalid hand: {hand!r}. Use 'AQs', 'KTo', 'AA', or 'AQ'")


def hand_replay(
    hand: str,
    position: str | None = None,
    label: str | None = None,
    player_id: str = 'ScottyWotty',
    con: sqlite3.Connection | None = None,
) -> dict:
    """
    Find all hands where *player_id* was dealt a specific starting hand,
    print stats, and launch the pygame replayer on those hands.

    Args:
        hand:      Starting hand, e.g. 'AQs', 'KK', 'T9o', 'AK' (matches both suited & offsuit)
        position:  Optional filter: 'BTN' | 'CO' | 'HJ' | 'UTG' | 'SB' | 'BB'
        label:     Optional situation label: '3bet_pot' | 'squeeze' | 'single_raised_pot' | ...
        player_id: Whose hole cards to match (default: 'ScottyWotty')

    Returns:
        dict with keys 'stats' (dict), 'by_position' (DataFrame), 'hands' (list[Hand])

    Example:
        hand_replay('AQs')
        hand_replay('AQs', position='BTN')
        hand_replay('AQ', label='3bet_pot')
        hand_replay('KK', position='SB')
    """
    import sys
    sys.path.insert(0, str(_SRC))

    targets = set(_parse_hand_query(hand))

    # Load (or retrieve cached) 888poker hands
    all_hands = _load_888_hands()

    # Filter by hole cards
    matching_hands = []
    for h in all_hands:
        if player_id not in h.players:
            continue
        pidx = h.players.index(player_id) + 1  # 1-based
        prefix = f'd dh p{pidx} '
        for action in h.actions:
            if action.startswith(prefix):
                canonical = _cards_to_canonical(action[len(prefix):])
                if canonical in targets:
                    matching_hands.append(h)
                break

    if not matching_hands:
        print(f"No hands found for {hand!r}")
        return {'stats': {}, 'by_position': pd.DataFrame(), 'hands': []}

    matching_ids = [h.hand_id for h in matching_hands]

    # Query db for stats and apply optional filters via a temp table
    conn, should_close = _con(con)
    try:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS _hr_ids (hand_id INTEGER PRIMARY KEY)")
        conn.execute("DELETE FROM _hr_ids")
        conn.executemany("INSERT OR IGNORE INTO _hr_ids VALUES (?)", [(i,) for i in matching_ids])

        label_join  = "JOIN labels l ON ph.hand_id = l.hand_id" if label else ""
        pos_clause  = "AND ph.position = :pos" if position else ""
        lbl_clause  = "AND l.label = :lbl" if label else ""
        params = {'pid': player_id, 'pos': position, 'lbl': label}

        base_query = f"""
            FROM player_hands ph
            JOIN _hr_ids hi ON ph.hand_id = hi.hand_id
            {label_join}
            WHERE ph.player_id = :pid
            {pos_clause}
            {lbl_clause}
        """

        overall = conn.execute(f"""
            SELECT COUNT(DISTINCT ph.hand_id)                       hands,
                   ROUND(SUM(ph.net_won), 2)                        net_won,
                   ROUND(AVG(ph.net_won) * 100, 2)                  per_100,
                   ROUND(100.0 * SUM(ph.saw_flop)   / COUNT(*), 1)  flop_pct,
                   ROUND(100.0 * SUM(ph.went_to_sd) / COUNT(*), 1)  sd_pct,
                   ROUND(100.0 * SUM(ph.vpip) / COUNT(*), 1)        vpip_pct,
                   ROUND(100.0 * SUM(ph.pfr)  / COUNT(*), 1)        pfr_pct
            {base_query}
        """, params).fetchone()

        by_position = pd.read_sql(f"""
            SELECT ph.position,
                   COUNT(DISTINCT ph.hand_id)      hands,
                   ROUND(SUM(ph.net_won), 2)        net_won,
                   ROUND(AVG(ph.net_won) * 100, 2)  per_100
            {base_query}
            GROUP BY ph.position ORDER BY net_won DESC
        """, conn, params=params)

        # Hand IDs that pass all filters (for replayer)
        filtered_ids = {
            r[0] for r in conn.execute(
                f"SELECT DISTINCT ph.hand_id {base_query}", params
            ).fetchall()
        }
    finally:
        if should_close:
            conn.close()

    stats = {
        'hand': hand, 'targets': sorted(targets),
        'hands': overall[0], 'net_won': overall[1], 'per_100': overall[2],
        'flop_pct': overall[3], 'sd_pct': overall[4],
        'vpip_pct': overall[5], 'pfr_pct': overall[6],
    }

    filtered_hands = [h for h in matching_hands if h.hand_id in filtered_ids]

    # Print summary
    filter_parts = [hand]
    if position:
        filter_parts.append(f'@ {position}')
    if label:
        filter_parts.append(f'[{label}]')
    title = '  ' + '  '.join(filter_parts)

    print(f"\n{'='*48}")
    print(title)
    print(f"{'='*48}")
    if overall[0]:
        print(f"  Hands      : {overall[0]}")
        print(f"  Net P&L    : ${overall[1]:+.2f}   (${overall[2]:+.2f}/100)")
        print(f"  Flop seen  : {overall[3]}%")
        print(f"  Showdown   : {overall[4]}%")
        print(f"  VPIP / PFR : {overall[5]}% / {overall[6]}%")
        if not by_position.empty:
            print()
            print(by_position.to_string(index=False))
    else:
        print("  No hands match the given filters.")
    print()

    if not filtered_hands:
        return {'stats': stats, 'by_position': by_position, 'hands': []}

    print(f"Launching replayer with {len(filtered_hands)} hands  (N/P to navigate, Q to quit)...")
    from replayer.main import run
    run(filtered_hands)

    return {'stats': stats, 'by_position': by_position, 'hands': filtered_hands}
