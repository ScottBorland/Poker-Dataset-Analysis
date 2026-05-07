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
from hand_utils import (
    assign_positions, players_who_saw_flop, went_to_showdown, compute_investments,
)
from labeller import label_hand

DB_PATH = Path(__file__).parent.parent / 'db' / 'poker.db'

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
    position    TEXT,
    stack       REAL,
    winnings    REAL,
    net_won     REAL,
    saw_flop    INTEGER NOT NULL DEFAULT 0,
    went_to_sd  INTEGER NOT NULL DEFAULT 0,
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
CREATE INDEX IF NOT EXISTS idx_player     ON player_hands(player_id);
CREATE INDEX IF NOT EXISTS idx_ph_hand    ON player_hands(hand_id);
CREATE INDEX IF NOT EXISTS idx_label      ON labels(label);
CREATE INDEX IF NOT EXISTS idx_label_hand ON labels(hand_id);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    # migrate: add net_won column if this is an older database
    try:
        conn.execute("ALTER TABLE player_hands ADD COLUMN net_won REAL")
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


def ingest_file(conn: sqlite3.Connection, path: Path) -> int:
    """Parse one .phhs file and upsert its data. Returns number of hands ingested."""
    filename = path.name
    hands = load_file(path)
    if not hands:
        return 0

    player_rows: list[tuple] = []
    label_rows: list[tuple] = []

    for hand in hands:
        positions = assign_positions(hand)
        flop_set = set(players_who_saw_flop(hand))
        investments = compute_investments(hand)

        for seat_idx, player_id in enumerate(hand.players, start=1):
            i = seat_idx - 1
            gross = hand.winnings[i] if hand.winnings is not None else None
            invested = investments[i]
            net_won = (gross - invested) if gross is not None else None
            player_rows.append((
                player_id,
                hand.hand_id,
                filename,
                seat_idx,
                positions.get(seat_idx),
                hand.starting_stacks[i],
                gross,
                net_won,
                1 if seat_idx in flop_set else 0,
                1 if _player_went_to_sd(hand, seat_idx) else 0,
            ))

        for lr in label_hand(hand):
            label_rows.append((
                lr.hand_id, lr.file, lr.label, lr.street, lr.player_idx, lr.note,
            ))

    conn.executemany(
        "INSERT OR IGNORE INTO player_hands"
        "(player_id, hand_id, file, seat_idx, position, stack, winnings, net_won, saw_flop, went_to_sd)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
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


def main() -> None:
    ap = argparse.ArgumentParser(description='Ingest .phhs files into db/poker.db')
    ap.add_argument(
        '--data-dir', default='.',
        help='Directory containing .phhs files (default: project root)',
    )
    ap.add_argument('--reprocess', metavar='FILENAME',
                    help='Force re-ingest one specific file')
    ap.add_argument('--reprocess-all', action='store_true',
                    help='Remove all existing data and re-ingest every file')
    ap.add_argument('--db', default=str(DB_PATH),
                    help='SQLite database path (default: db/poker.db)')
    args = ap.parse_args()

    conn = get_connection(Path(args.db))
    done = _ingested_files(conn)

    data_dir = Path(args.data_dir)
    phhs_files = sorted(data_dir.glob('*.phhs'))

    if not phhs_files:
        print(f'[ingest] No .phhs files found in {data_dir.resolve()}')
        conn.close()
        return

    for path in phhs_files:
        filename = path.name
        force = args.reprocess_all or (filename == args.reprocess)

        if force and filename in done:
            print(f'[ingest] Re-processing {filename} (removing old data)...')
            _remove_file(conn, filename)
        elif filename in done:
            print(f'[ingest] Skipping {filename} (already ingested)')
            continue

        print(f'[ingest] Ingesting {filename}...')
        n = ingest_file(conn, path)
        print(f'[ingest] {filename}: {n} hands')

    conn.close()
    print('[ingest] Done.')


if __name__ == '__main__':
    main()
