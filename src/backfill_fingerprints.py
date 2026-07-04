"""
backfill_fingerprints.py — Compute fingerprints for hands already in the DB.

Uses `ingested_files` as the file list and skips any file whose fingerprints
have already been generated (idempotent, resumable). Re-parses each source
file to reconstruct actions (actions aren't stored in the DB).

Usage:
    python src/backfill_fingerprints.py                 # backfill everything
    python src/backfill_fingerprints.py --data-dir data/
    python src/backfill_fingerprints.py --limit 100     # first N files only
    python src/backfill_fingerprints.py --force         # re-do even completed files
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parser import load_file
from parser_888 import load_file_888
from fingerprint import compute_fingerprints
from ingest import DB_PATH, SCHEMA, _collect_sources


def _get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    return conn


def _files_with_fingerprints(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT file FROM fingerprints").fetchall()}


def _insert_fingerprints_for_file(conn: sqlite3.Connection, path: Path, venue: str) -> int:
    """Parse `path`, compute fingerprints, insert. Returns rows inserted."""
    hands = load_file_888(path) if venue == '888poker' else load_file(path)
    if not hands:
        return 0

    rows: list[tuple] = []
    for hand in hands:
        for fp in compute_fingerprints(hand):
            rows.append((
                fp.hand_id, fp.file, fp.player_idx, fp.street,
                fp.positions, fp.n_players_street, fp.pot_type,
                int(fp.in_position),
                fp.facing, fp.spr_bucket,
                fp.board_high_card,
                None if fp.board_paired is None else int(fp.board_paired),
                None if fp.board_monotone is None else int(fp.board_monotone),
                None if fp.board_two_tone is None else int(fp.board_two_tone),
                fp.board_connectedness,
            ))

    conn.executemany(
        "INSERT OR IGNORE INTO fingerprints"
        "(hand_id, file, player_idx, street, positions, n_players_street, pot_type,"
        " in_position, facing, spr_bucket, board_high_card, board_paired,"
        " board_monotone, board_two_tone, board_connectedness)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description='Backfill fingerprints for hands in the DB')
    ap.add_argument('--data-dir', default='data',
                    help='Root data dir (scans data/phhs files/ and data/888poker/)')
    ap.add_argument('--db', default=str(DB_PATH), help='Path to poker.db')
    ap.add_argument('--limit', type=int, help='Process at most N files')
    ap.add_argument('--force', action='store_true',
                    help='Re-do files that already have fingerprints')
    args = ap.parse_args()

    conn = _get_connection(Path(args.db))
    sources = _collect_sources(Path(args.data_dir))
    if not sources:
        print(f'[backfill] No hand history files found under {args.data_dir}')
        return

    done = set() if args.force else _files_with_fingerprints(conn)
    todo = [(p, v) for p, v in sources if p.name not in done]
    if args.limit:
        todo = todo[: args.limit]

    print(f'[backfill] {len(todo)} files to process ({len(done)} already done)')
    started = time.time()

    for i, (path, venue) in enumerate(todo, start=1):
        if args.force and path.name in _files_with_fingerprints(conn):
            conn.execute("DELETE FROM fingerprints WHERE file = ?", (path.name,))
            conn.commit()

        t0 = time.time()
        n_rows = _insert_fingerprints_for_file(conn, path, venue)
        rate = n_rows / max(time.time() - t0, 1e-6)
        elapsed = time.time() - started
        eta = elapsed / i * (len(todo) - i) if i else 0
        print(
            f'[backfill] [{i}/{len(todo)}] {path.name}: {n_rows:>7} rows '
            f'({rate:>7.0f}/s) | elapsed {elapsed:>6.0f}s | eta {eta:>6.0f}s'
        )

    conn.close()
    print('[backfill] Done.')


if __name__ == '__main__':
    main()
