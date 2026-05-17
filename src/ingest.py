"""
ingest.py — Parse .phhs files and populate db/poker.db.

Incremental by default: files already tracked in ingested_files are skipped.

Usage:
    python src/ingest.py                         # ingest all .phhs in project root
    python src/ingest.py --data-dir data/        # from a specific directory
    python src/ingest.py --reprocess file.phhs   # force re-ingest one file
    python src/ingest.py --reprocess-all         # wipe and re-ingest everything
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from parser import Hand, load_file
from parser_888 import load_file_888
from hand_utils import (
    assign_positions, players_who_saw_flop, went_to_showdown, compute_investments,
    compute_vpip_pfr,
)
from labeller import label_hand

DB_PATH = Path(__file__).parent.parent / 'db' / 'poker.db'
PROGRESS_FILE = Path(__file__).parent.parent / 'db' / 'reprocess_progress.txt'

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingested_files (
    filename    TEXT PRIMARY KEY,
    ingested_at TEXT DEFAULT (datetime('now')),
    hand_count  INTEGER
);

CREATE TABLE IF NOT EXISTS player_hands (
    player_id   TEXT NOT NULL,
    hand_id     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    seat_idx    INTEGER NOT NULL,
    n_players   INTEGER NOT NULL,
    position    TEXT,
    stack       REAL,
    invested    REAL,
    winnings    REAL,
    net_won     REAL,
    saw_flop    INTEGER NOT NULL DEFAULT 0,
    went_to_sd  INTEGER NOT NULL DEFAULT 0,
    vpip        INTEGER NOT NULL DEFAULT 0,
    pfr         INTEGER NOT NULL DEFAULT 0,
    venue       TEXT NOT NULL DEFAULT 'absolute_poker',
    big_blind   REAL,
    date        TEXT,
    PRIMARY KEY (player_id, hand_id)
);

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
CREATE INDEX IF NOT EXISTS idx_player      ON player_hands(player_id);
CREATE INDEX IF NOT EXISTS idx_ph_hand     ON player_hands(hand_id);
CREATE INDEX IF NOT EXISTS idx_ph_file     ON player_hands(file);
CREATE INDEX IF NOT EXISTS idx_big_blind   ON player_hands(big_blind);
CREATE INDEX IF NOT EXISTS idx_label       ON labels(label);
CREATE INDEX IF NOT EXISTS idx_label_hand  ON labels(hand_id);
CREATE INDEX IF NOT EXISTS idx_labels_file ON labels(file);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    for col, defn in [
        ("net_won",    "REAL"),
        ("n_players",  "INTEGER NOT NULL DEFAULT 0"),
        ("invested",   "REAL"),
        ("vpip",       "INTEGER NOT NULL DEFAULT 0"),
        ("pfr",        "INTEGER NOT NULL DEFAULT 0"),
        ("venue",      "TEXT NOT NULL DEFAULT 'absolute_poker'"),
        ("big_blind",  "REAL"),
        ("date",       "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE player_hands ADD COLUMN {col} {defn}")
            conn.commit()
        except sqlite3.OperationalError:
            pass
    return conn


def _ingested_files(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT filename FROM ingested_files").fetchall()}


def _remove_file(conn: sqlite3.Connection, filename: str) -> None:
    conn.execute("DELETE FROM player_hands WHERE file = ?", (filename,))
    conn.execute("DELETE FROM labels WHERE file = ?", (filename,))
    conn.execute("DELETE FROM ingested_files WHERE filename = ?", (filename,))
    conn.commit()


def _player_went_to_sd(hand: Hand, player_idx: int) -> bool:
    """True if the player did not fold and the hand reached showdown."""
    prefix = f'p{player_idx} '
    for a in hand.actions:
        if a.startswith(prefix):
            parts = a.split()
            if len(parts) >= 2 and parts[1] == 'f':
                return False
    return went_to_showdown(hand)


def ingest_file(conn: sqlite3.Connection, path: Path, venue: str = 'absolute_poker') -> int:
    """Parse one hand history file and upsert its data. Returns number of hands ingested."""
    filename = path.name
    if venue == '888poker':
        hands = load_file_888(path)
    else:
        hands = load_file(path)
    if not hands:
        return 0

    player_rows: list[tuple] = []
    label_rows: list[tuple] = []

    for hand in hands:
        positions = assign_positions(hand)
        flop_set = set(players_who_saw_flop(hand))
        investments = compute_investments(hand)
        vpip_pfr = compute_vpip_pfr(hand)
        bb = hand.blinds_or_straddles[1] if len(hand.blinds_or_straddles) > 1 else None
        date = hand.date_str if hand.year else None

        for seat_idx, player_id in enumerate(hand.players, start=1):
            i = seat_idx - 1
            gross = hand.winnings[i] if hand.winnings is not None else None
            invested = investments[i]
            net_won = (gross - invested) if gross is not None else None
            v, p = vpip_pfr[i]
            player_rows.append((
                player_id,
                hand.hand_id,
                filename,
                seat_idx,
                hand.n_players,
                positions.get(seat_idx),
                hand.starting_stacks[i],
                invested,
                gross,
                net_won,
                1 if seat_idx in flop_set else 0,
                1 if _player_went_to_sd(hand, seat_idx) else 0,
                1 if v else 0,
                1 if p else 0,
                venue,
                bb,
                date,
            ))

        for lr in label_hand(hand):
            label_rows.append((
                lr.hand_id, lr.file, lr.label, lr.street, lr.player_idx, lr.note,
            ))

    conn.executemany(
        "INSERT OR IGNORE INTO player_hands"
        "(player_id, hand_id, file, seat_idx, n_players, position, stack, invested,"
        " winnings, net_won, saw_flop, went_to_sd, vpip, pfr, venue, big_blind, date)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        player_rows,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO labels(hand_id, file, label, street, player_idx, note)"
        " VALUES (?,?,?,?,?,?)",
        label_rows,
    )
    conn.execute(
        "INSERT OR REPLACE INTO ingested_files(filename, hand_count) VALUES (?,?)",
        (filename, len(hands)),
    )
    conn.commit()
    return len(hands)


def _collect_sources(data_dir: Path) -> list[tuple[Path, str]]:
    """
    Return list of (path, venue) pairs from data_dir.
    Looks for .phhs files in data_dir/phhs files/ and .txt files in data_dir/888poker/.
    Falls back to scanning data_dir itself for .phhs if subdirs are absent.
    """
    sources: list[tuple[Path, str]] = []

    phhs_dir = data_dir / 'phhs files'
    if phhs_dir.is_dir():
        # rglob to handle files nested in subdirectories.
        # Deduplicate by basename — only the first path per name is ingested,
        # matching the DB's use of filename (not full path) as the primary key.
        seen: set[str] = set()
        for p in sorted(phhs_dir.rglob('*.phhs')):
            if p.name not in seen:
                seen.add(p.name)
                sources.append((p, 'absolute_poker'))
    else:
        sources.extend((p, 'absolute_poker') for p in sorted(data_dir.glob('*.phhs')))

    poker888_dir = data_dir / '888poker'
    if poker888_dir.is_dir():
        sources.extend(
            (p, '888poker')
            for p in sorted(poker888_dir.glob('*.txt'))
            if 'Summary' not in p.name
        )

    return sources


def main() -> None:
    ap = argparse.ArgumentParser(description='Ingest hand history files into db/poker.db')
    ap.add_argument(
        '--data-dir', default='data',
        help='Root data directory (default: data/). Scans data/phhs files/ and data/888poker/',
    )
    ap.add_argument('--reprocess', metavar='FILENAME',
                    help='Force re-ingest one specific file')
    ap.add_argument('--reprocess-all', action='store_true',
                    help='Remove all existing data and re-ingest every file')
    ap.add_argument('--reprocess-null-bb', action='store_true',
                    help='Re-ingest only files that have any row with NULL big_blind')
    ap.add_argument('--db', default=str(DB_PATH),
                    help='SQLite database path (default: db/poker.db)')
    args = ap.parse_args()

    conn = get_connection(Path(args.db))
    done = _ingested_files(conn)

    data_dir = Path(args.data_dir)
    sources = _collect_sources(data_dir)

    null_bb_files: set[str] = set()
    if args.reprocess_null_bb:
        # Identify 888poker files by venue (avoids a slow full-table scan).
        # Use a progress file so the run is resumable if interrupted.
        all_888 = {p.name for p, v in sources if v == '888poker'}
        done_progress = (
            set(PROGRESS_FILE.read_text().splitlines())
            if PROGRESS_FILE.exists() else set()
        )
        null_bb_files = all_888 - done_progress
        print(
            f'[ingest] --reprocess-null-bb: {len(null_bb_files)} files remaining'
            f' ({len(done_progress)} already done)'
        )

    if not sources:
        print(f'[ingest] No hand history files found under {data_dir.resolve()}')
        conn.close()
        return

    for path, venue in sources:
        filename = path.name
        force = (
            args.reprocess_all
            or (filename == args.reprocess)
            or (args.reprocess_null_bb and filename in null_bb_files)
        )

        if force and filename in done:
            print(f'[ingest] Re-processing {filename} (removing old data)...')
            _remove_file(conn, filename)
        elif filename in done:
            print(f'[ingest] Skipping {filename} (already ingested)')
            continue

        print(f'[ingest] Ingesting {filename} [{venue}]...')
        n = ingest_file(conn, path, venue=venue)
        print(f'[ingest] {filename}: {n} hands')

        if args.reprocess_null_bb and filename in null_bb_files:
            with open(PROGRESS_FILE, 'a') as pf:
                pf.write(filename + '\n')

    conn.close()

    if args.reprocess_null_bb:
        done_now = (
            set(PROGRESS_FILE.read_text().splitlines())
            if PROGRESS_FILE.exists() else set()
        )
        all_888 = {p.name for p, v in sources if v == '888poker'}
        if all_888.issubset(done_now):
            PROGRESS_FILE.unlink(missing_ok=True)
            print('[ingest] All 888poker files reprocessed — progress file removed.')

    print('[ingest] Done.')


if __name__ == '__main__':
    main()
