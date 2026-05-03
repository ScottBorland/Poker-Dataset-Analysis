"""
analyser.py — Query and aggregate labelled hands from labels.db.

Usage (module):
    from analyser import Analyser

    an = Analyser()
    df = an.hands_with_label('3bet_pot')
    print(an.label_counts())

CLI:
    python analyser.py --counts
    python analyser.py --label 3bet_pot --limit 20
    python analyser.py --stats
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'labels' / 'labels.db'

try:
    import pandas as pd
    _PANDAS = True
except ImportError:
    _PANDAS = False


class Analyser:
    def __init__(self, db_path: Path = DB_PATH):
        if not db_path.exists():
            raise FileNotFoundError(
                f"labels.db not found at {db_path}. "
                "Run labeller.py first to generate labels."
            )
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    # Basic queries
    # ------------------------------------------------------------------

    def label_counts(self) -> list[tuple[str, int]]:
        """Return [(label, count)] sorted by count descending."""
        rows = self.conn.execute(
            "SELECT label, COUNT(*) as cnt FROM labels GROUP BY label ORDER BY cnt DESC"
        ).fetchall()
        return [(r['label'], r['cnt']) for r in rows]

    def hands_with_label(self, label: str, limit: int = 500) -> list[dict]:
        """Return list of label rows matching the given label."""
        rows = self.conn.execute(
            "SELECT * FROM labels WHERE label=? ORDER BY hand_id LIMIT ?",
            (label, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def hand_labels(self, hand_id: int) -> list[str]:
        """Return all labels applied to a specific hand."""
        rows = self.conn.execute(
            "SELECT label FROM labels WHERE hand_id=? ORDER BY label",
            (hand_id,),
        ).fetchall()
        return [r['label'] for r in rows]

    def label_overlap(self, label_a: str, label_b: str) -> int:
        """Count hands that have both label_a and label_b."""
        row = self.conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT hand_id FROM labels WHERE label=?
                INTERSECT
                SELECT hand_id FROM labels WHERE label=?
            )
            """,
            (label_a, label_b),
        ).fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Pandas helpers (only available if pandas is installed)
    # ------------------------------------------------------------------

    def to_dataframe(self, query: str, params: tuple = ()) -> 'pd.DataFrame':
        if not _PANDAS:
            raise ImportError("pandas is required for to_dataframe()")
        import pandas as pd
        return pd.read_sql_query(query, self.conn, params=params)

    def label_counts_df(self) -> 'pd.DataFrame':
        return self.to_dataframe(
            "SELECT label, COUNT(*) as count FROM labels GROUP BY label ORDER BY count DESC"
        )

    def hands_with_label_df(self, label: str, limit: int = 500) -> 'pd.DataFrame':
        return self.to_dataframe(
            "SELECT * FROM labels WHERE label=? ORDER BY hand_id LIMIT ?",
            (label, limit),
        )

    def player_stats_df(self, label: str | None = None) -> 'pd.DataFrame':
        """
        Aggregate per-player stats from labels.
        If label is given, restrict to hands with that label.
        """
        base = "SELECT player_idx, label, COUNT(*) as cnt FROM labels"
        if label:
            base += f" WHERE label='{label}'"
        base += " GROUP BY player_idx, label ORDER BY cnt DESC"
        return self.to_dataframe(base)

    # ------------------------------------------------------------------
    # Summary / stats
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        total_hands = self.conn.execute(
            "SELECT COUNT(DISTINCT hand_id) FROM labels"
        ).fetchone()[0]
        total_labels = self.conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        unique_labels = self.conn.execute(
            "SELECT COUNT(DISTINCT label) FROM labels"
        ).fetchone()[0]
        return {
            'total_labelled_hands': total_hands,
            'total_label_rows': total_labels,
            'unique_labels': unique_labels,
        }

    def close(self):
        self.conn.close()


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Query poker hand labels')
    parser.add_argument('--db', default=str(DB_PATH))
    parser.add_argument('--counts', action='store_true', help='Show label counts')
    parser.add_argument('--label', help='Show hands with this label')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--stats', action='store_true', help='Show summary stats')
    parser.add_argument('--hand-id', type=int, help='Show labels for a hand')
    args = parser.parse_args()

    an = Analyser(Path(args.db))

    if args.stats:
        s = an.summary()
        for k, v in s.items():
            print(f"  {k}: {v}")

    if args.counts:
        print("\nLabel counts:")
        for label, cnt in an.label_counts():
            print(f"  {label:<25} {cnt:>8,}")

    if args.label:
        rows = an.hands_with_label(args.label, limit=args.limit)
        print(f"\nFirst {len(rows)} hands with label '{args.label}':")
        for r in rows:
            print(f"  hand_id={r['hand_id']}  file={r['file']}  street={r['street']}")

    if args.hand_id:
        labels = an.hand_labels(args.hand_id)
        print(f"\nLabels for hand {args.hand_id}: {labels}")

    an.close()


if __name__ == '__main__':
    main()
