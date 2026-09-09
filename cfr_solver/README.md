# cfr_solver

Solving engine for specific heads-up poker spots. Deliberately separate
from the rest of this repo (`src/`): no shared imports, no shared venv. The
two sides talk only through JSON files — `src/spot_spec_export.py` writes a
spot spec into `spots/`, this module reads it and writes results into
`results/`.

**TexasSolver** — full 3-street flop→river DCFR via the external
`console_solver.exe` (github.com/bupticybee/TexasSolver, AGPL v3).
`texas_adapter.py` converts a spot spec into its command file, runs it, and
stores the strategy dump. Setup (one-time, ~39 MB download):

```
python fetch_solver.py
```

No venv needed — the adapter is stdlib-only. Memory note: tree size is
controlled by limiting bet sizes per street (2 on the spot's street, 1
later); an unconstrained config measured >10 GB.

## Running a solve

```
python texas_adapter.py spots/<spot_id>.json
```

## Layout

- `spot_spec.schema.json` — documented shape of the input contract (produced
  by `src/spot_spec_export.py` on the other side of the boundary).
- `spots/` — input spot specs (JSON).
- `results/` — output strategies + exploitability logs (gitignored).
- `fetch_solver.py` — one-time download of `console_solver.exe`.
- `texas_adapter.py` — spot spec -> TexasSolver command file, runs the
  solve, stores `texas_output.json`.
- `hand_ranking.py` — Chen-formula range ranking, shared with
  `src/range_charts.py`/`src/spot_spec_export.py` across the venv boundary.
