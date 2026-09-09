"""solve_common_spots.py — Precompute TexasSolver solutions for the most
common heads-up postflop fingerprint spots in ScottyWotty's 888poker data.

Pipeline per spot (resumable — solved spots are skipped):
  1. spot_priority.rank_spots() ranks HU fingerprint types by
     count x avg_pot_bb.
  2. spot_spec_export.export_spot_spec() turns each type into a concrete
     spec (representative board, median pot/stack, observed bet fractions,
     ranges via the extended range_charts.infer_spot_roles).
  3. cfr_solver/texas_adapter.py runs the full 3-street DCFR solve.
  4. results/spot_index.json maps fingerprint types -> spot_ids for the
     API's /spots/lookup.

Solves take minutes each and ~1-6 GB RAM — run overnight for big batches:

    python src/solve_common_spots.py --top 10 --min-count 30
    python src/solve_common_spots.py --top 3 --min-count 50 --accuracy 0.5 --max-iteration 100
    python src/solve_common_spots.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from api import FP_TYPE_COLUMNS
from spot_priority import rank_spots
from spot_spec_export import export_spot_spec

CFR_DIR = Path(__file__).parent.parent / 'cfr_solver'
RESULTS_DIR = CFR_DIR / 'results'
INDEX_PATH = RESULTS_DIR / 'spot_index.json'


def refresh_spot_index() -> int:
    """Rebuild spot_index.json from every solved spot's spec on disk."""
    entries = []
    if RESULTS_DIR.is_dir():
        for spot_dir in sorted(RESULTS_DIR.iterdir()):
            spec_path = spot_dir / 'spot_spec.json'
            if not spot_dir.is_dir() or not spec_path.exists():
                continue
            solved = (spot_dir / 'texas_output.json').exists() or (spot_dir / 'strategy.json').exists()
            if not solved:
                continue
            spec = json.loads(spec_path.read_text())
            if spec.get('fingerprint_type'):
                entries.append({
                    'spot_id': spot_dir.name,
                    'fingerprint_type': spec['fingerprint_type'],
                })
    RESULTS_DIR.mkdir(exist_ok=True)
    INDEX_PATH.write_text(json.dumps(entries, indent=2))
    return len(entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=int, default=10, help='how many ranked spots to solve')
    parser.add_argument('--min-count', type=int, default=30)
    parser.add_argument('--venue', default='888poker')
    parser.add_argument('--accuracy', type=float, default=0.3)
    parser.add_argument('--max-iteration', type=int, default=200)
    parser.add_argument('--dry-run', action='store_true', help='rank + list, no solving')
    args = parser.parse_args()

    df = rank_spots(limit=args.top * 3, min_count=args.min_count, venue=args.venue)
    if df.empty:
        sys.exit("No fingerprint types matched the ranking filters.")

    postflop = df[df['street'] != 'preflop'].head(args.top)
    print(f"Top {len(postflop)} postflop HU spots by count x avg_pot_bb:")
    for rank, (_, row) in enumerate(postflop.iterrows(), start=1):
        print(f"  {rank}. {row['street']} {row['positions']} {row['pot_type']} "
              f"spr={row['spr_bucket']} {row['board_high_card']}-high "
              f"(n={row['count']}, avg pot {row['avg_pot_bb']} BB)")
    if args.dry_run:
        return

    for rank, (_, row) in enumerate(postflop.iterrows(), start=1):
        fp_type = {c: row[c] for c in FP_TYPE_COLUMNS}
        spot_id = f"common_{row['street']}_{str(row['positions']).lower()}_{rank}"
        out_dir = RESULTS_DIR / spot_id

        if (out_dir / 'texas_output.json').exists():
            print(f"[{rank}] {spot_id}: already solved, skipping")
            continue

        print(f"[{rank}] {spot_id}: exporting spec...")
        try:
            spec_path = export_spot_spec(fp_type, spot_id, venue=args.venue)
        except ValueError as e:
            print(f"    skip: {e}")
            continue

        print(f"[{rank}] {spot_id}: solving (this takes minutes)...")
        rc = subprocess.call(
            [sys.executable, '-u', 'texas_adapter.py', str(spec_path),
             '--accuracy', str(args.accuracy), '--max-iteration', str(args.max_iteration)],
            cwd=str(CFR_DIR),
        )
        if rc != 0:
            print(f"    solve FAILED (rc={rc}) — continuing with next spot")
            continue

        n = refresh_spot_index()
        print(f"[{rank}] {spot_id}: done ({n} spots in index)")

    n = refresh_spot_index()
    print(f"Finished. spot_index.json has {n} solved spots.")


if __name__ == '__main__':
    main()
