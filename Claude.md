# Poker Dataset Analysis — Project Guide

## Project Overview

This project analyses a large dataset of No-Limit Texas Hold'em cash game hands from Absolute Poker (2009), stored in `.phhs` files. The goals are:

1. **Parse & explore** the dataset with Python scripts
2. **Label hands** by situation type (e.g. 3-bet pot, squeeze, single-raised pot)
3. **Analyse labelled subsets** to study population tendencies, player stats, and equity/range scenarios
4. **Visualise individual hands** step-by-step using a pygame replayer

There is no "hero" player — this is a population study across all obfuscated players.

---

## File Format: `.phhs`

Each file contains multiple hands separated by numbered sections `[1]`, `[2]`, etc. Each hand is a flat key-value block.

### Field Reference

| Field | Type | Description |
|---|---|---|
| `variant` | str | Always `'NT'` (No-Limit Texas Hold'em) |
| `ante_trimming_status` | bool | Ante handling rule |
| `antes` | list[float] | Ante posted by each player (usually all 0) |
| `blinds_or_straddles` | list[float] | Blinds per seat — index 0 = SB, index 1 = BB |
| `min_bet` | float | Minimum bet size |
| `starting_stacks` | list[float] | Stack sizes at start of hand, per player |
| `actions` | list[str] | Ordered action sequence (see Action Encoding below) |
| `venue` | str | Always `'Absolute Poker'` |
| `time` | str | Time of hand (HH:MM:SS) |
| `day/month/year` | int | Date of hand |
| `hand` | int | Unique hand ID |
| `seats` | list[int] | Physical seat numbers occupied |
| `table` | str | Table name |
| `players` | list[str] | Obfuscated player IDs (base64-like strings) |
| `winnings` | list[float] | Net winnings per player (may be absent if all zero / hand incomplete) |
| `currency_symbol` | str | Always `'$'` |
| `time_zone_abbreviation` | str | Always `'ET'` |

**Note:** `winnings` is sometimes absent (e.g. all-in run-outs with unknown cards). Always use `.get('winnings')` defensively.

### Action Encoding

Actions in the `actions` list follow this pattern:

| Prefix | Meaning |
|---|---|
| `d dh pN ????` | Deal hole cards to player N (cards hidden/unknown) |
| `d dh pN XxYy` | Deal hole cards to player N (cards revealed at showdown) |
| `d db XxYy[Zz]` | Deal board cards (flop = 3 cards, turn/river = 1 card) |
| `pN f` | Player N folds |
| `pN cc` | Player N calls or checks |
| `pN cbr X.XX` | Player N raises/bets to X.XX (total, not raise size) |
| `pN sm XxYy` | Player N shows mucked cards at showdown |

**Street boundaries** are inferred from `d db` actions:
- First `d db` = flop (3 cards)
- Second `d db` = turn (1 card)
- Third `d db` = river (1 card)

**Player indexing:** Players are 1-indexed (`p1`, `p2`, …). Index maps to `players[N-1]` and `starting_stacks[N-1]`.

**Positions:** p1 = SB, p2 = BB. Button is the last player to act preflop (just before SB).

### Example Hand (annotated)

```
[6]
variant = 'NT'
blinds_or_straddles = [0.25, 0.50, 0, 0, 0, 0]   # 6-handed, SB=0.25 BB=0.50
starting_stacks = [49.50, 70.69, 12, 18.50, 26.15, 117.05]
actions = [
  'd dh p1 ????', ..., 'd dh p6 ????',             # deal
  'p3 cc', 'p4 cc', 'p5 f', 'p6 f', 'p1 f',        # preflop: limp, limp, folds
  'p2 cbr 1.50',                                    # BB raises (iso)
  'p3 cc', 'p4 cc',                                 # two callers
  'd db 5h2s8h',                                    # flop
  'p2 cc', 'p3 cc', 'p4 cbr 1.50',                 # p4 bets
  'p2 f', 'p3 f'                                    # folds
]
winnings = [0, 0, 0, 4.55, 0, 0]
```

---

## Project Structure

```
Poker Analysis/
├── Claude.md                  # This file
├── *.phhs                     # Raw hand history files (not committed to git)
├── db/
│   └── poker.db               # Primary SQLite database (not committed to git)
├── labels/
│   └── labels.db              # Manual label store for labeller.py / analyser.py
├── src/
│   ├── ingest.py              # One-time (incremental) ingestion script
│   ├── parser.py              # .phhs parser → Hand dataclass
│   ├── hand_utils.py          # Derived features (street detection, pot sizes, positions)
│   ├── labeller.py            # CLI tool for tagging hands (writes to labels.db)
│   ├── analyser.py            # Query & aggregate labelled hands (reads labels.db)
│   ├── scripts.py             # High-level convenience API for notebooks/REPL
│   └── replayer/
│       ├── main.py            # pygame entry point
│       ├── renderer.py        # Drawing logic
│       └── state.py           # Hand state machine for step-through replay
├── commands.txt               # Example CLI commands
├── notebooks/
│   └── exploration.ipynb      # Exploratory analysis
└── requirements.txt
```

---

## Database (`db/poker.db`)

The primary database is `db/poker.db`. It is populated by `src/ingest.py` and is the main source for player-level analysis. Do not commit it to git.

### Schema

```sql
-- Tracks which files have been ingested (enables incremental re-runs)
CREATE TABLE ingested_files (
    filename    TEXT PRIMARY KEY,
    ingested_at TEXT DEFAULT (datetime('now')),
    hand_count  INTEGER
);

-- One row per player per hand
CREATE TABLE player_hands (
    player_id   TEXT NOT NULL,
    hand_id     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    seat_idx    INTEGER NOT NULL,   -- 1-indexed
    n_players   INTEGER NOT NULL,   -- total players seated in this hand
    position    TEXT,               -- 'BTN' | 'SB' | 'BB' | 'UTG' | 'HJ' | 'CO'
    stack       REAL,
    invested    REAL,               -- total chips put into pot (blinds + all bets/calls, uncalled bets returned)
    winnings    REAL,               -- gross chips received from pot; NULL when absent from source
    net_won     REAL,               -- winnings - invested; NULL when winnings is NULL
    saw_flop    INTEGER NOT NULL DEFAULT 0,
    went_to_sd  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, hand_id)
);

-- Auto-labels applied at ingest time (mirrors labels.db schema)
CREATE TABLE labels (
    hand_id     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    label       TEXT NOT NULL,
    street      TEXT,
    player_idx  INTEGER,
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_unique_label ON labels(hand_id, label, COALESCE(player_idx, -1));
CREATE INDEX idx_player     ON player_hands(player_id);
CREATE INDEX idx_ph_hand    ON player_hands(hand_id);
CREATE INDEX idx_label      ON labels(label);
CREATE INDEX idx_label_hand ON labels(hand_id);
```

### Common Queries

```python
import sqlite3, pandas as pd
con = sqlite3.connect('db/poker.db')

# Net P&L leaderboard (use net_won, not winnings — winnings is gross chips received)
pd.read_sql("""
    SELECT player_id, COUNT(*) hands, ROUND(SUM(net_won), 2) net_won
    FROM player_hands WHERE net_won IS NOT NULL
    GROUP BY player_id HAVING hands >= 5
    ORDER BY net_won DESC
""", con)

# All hands for a specific player
pd.read_sql("SELECT * FROM player_hands WHERE player_id = ?", con, params=[player_id])

# Hands where player saw the flop
pd.read_sql("""
    SELECT * FROM player_hands WHERE player_id = ? AND saw_flop = 1
""", con, params=[player_id])

# Player stats in 3bet pots only
pd.read_sql("""
    SELECT ph.player_id, COUNT(*) hands, ROUND(SUM(ph.net_won), 2) net_won
    FROM player_hands ph
    JOIN labels l ON ph.hand_id = l.hand_id
    WHERE l.label = '3bet_pot' AND ph.net_won IS NOT NULL
    GROUP BY ph.player_id ORDER BY net_won DESC
""", con)

# Positional net P&L — filter by n_players to compare like-for-like
pd.read_sql("""
    SELECT position, n_players, COUNT(*) hands,
           ROUND(SUM(net_won), 2) net_won,
           ROUND(100.0 * SUM(saw_flop) / COUNT(*), 1) flop_seen_pct,
           ROUND(100.0 * SUM(went_to_sd) / COUNT(*), 1) showdown_pct
    FROM player_hands
    WHERE n_players = 6
    GROUP BY position ORDER BY net_won DESC
""", con)

# Rake analysis — rake = sum(invested) - sum(winnings) per hand, split proportionally
# Only valid for hands where all players have known winnings
pd.read_sql("""
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
           ROUND(SUM(hr.rake * ph.invested / hr.total_invested), 2)   rake_paid,
           ROUND(SUM(ph.net_won), 2)                                   net_won,
           ROUND(SUM(ph.net_won)
               + SUM(hr.rake * ph.invested / hr.total_invested), 2)   net_won_pre_rake
    FROM player_hands ph
    JOIN hand_rake hr ON ph.hand_id = hr.hand_id
    WHERE ph.net_won IS NOT NULL
    GROUP BY ph.player_id HAVING hands >= 5
    ORDER BY net_won_pre_rake DESC
""", con)
```

---

## Ingestion System (`src/ingest.py`)

`src/ingest.py` parses `.phhs` files and populates `db/poker.db`. It is incremental by design — files already recorded in `ingested_files` are skipped unless a reprocess flag is given.

### Usage

```bash
# Ingest all .phhs files in the project root (default)
python src/ingest.py

# Ingest from a specific directory
python src/ingest.py --data-dir data/

# Force re-ingest one file (removes its old rows first)
python src/ingest.py --reprocess "abs NLH handhq_1-OBFUSCATED.phhs"

# Wipe and re-ingest everything from scratch
python src/ingest.py --reprocess-all
```

### What gets written per hand

- One `player_hands` row per seated player, with position, stack, winnings, `saw_flop`, `went_to_sd`
- All auto-labels from `label_hand()` (same logic as `labeller.py`)
- One `ingested_files` row recording the filename and hand count

**Note:** `poker.db` contains auto-labels only. Manual labels added via `labeller.py --add` live in `labels/labels.db` and are never touched by re-ingestion.

---

## Scripts API (`src/scripts.py`)

High-level convenience functions for interactive use in notebooks or a REPL. All database functions accept an optional `con` keyword — pass an existing connection to avoid repeated open/close in loops; omit it and a fresh connection is opened and closed automatically.

```python
import sys; sys.path.insert(0, 'src')
from scripts import *
```

### Data loading

| Function | Returns | Description |
|---|---|---|
| `load(path)` | `list[Hand]` | Load all hands from a single `.phhs` file |
| `load_all(folder='.')` | `list[Hand]` | Load all `.phhs` files in a folder |
| `connect(db_path)` | `Connection` | Open a connection to `poker.db` (caller closes) |

### Ingestion & labelling

| Function | Description |
|---|---|
| `ingest(folder='.', reprocess=None, reprocess_all=False)` | Ingest `.phhs` files into `poker.db` |
| `add_labels(path_or_folder)` | Run auto-labeller and write to `labels/labels.db` |

### Overview

| Function | Returns | Description |
|---|---|---|
| `summary()` | — | Print hands, players, label counts, and rake totals |
| `label_counts()` | `DataFrame` | Count of each label type |
| `rake_stats()` | `dict` | Total/avg rake over hands with known winnings |
| `pot_type_stats(pot_types)` | `DataFrame` | P&L and showdown % by preflop situation |
| `positional_stats(n_players=6)` | `DataFrame` | P&L by position; pass `None` for all sizes |

### Player analysis

| Function | Returns | Description |
|---|---|---|
| `top_players(n=10, by='net_won', min_hands=5)` | `DataFrame` | Best players; `by` also accepts `'net_won_pre_rake'` |
| `bottom_players(n=10, by='net_won', min_hands=5)` | `DataFrame` | Biggest losers |
| `player_stats(player_id)` | `dict` | Overall P&L + breakdown by position and label |
| `player_hand_history(player_id, label=None)` | `DataFrame` | Every hand for a player, optionally filtered to a label |

### Hand lookup & labels

| Function | Returns | Description |
|---|---|---|
| `hand_details(hand_id)` | `dict` | Player rows and label list for one hand |
| `hands_with_label(label, limit=20)` | `DataFrame` | Player rows for hands carrying a label |

### Example session

```python
from scripts import *

summary()
# Files ingested : 1 | Hands : 1,000 | Players : 151 | Rake : $168.55

top_players(5)
top_players(5, by='net_won_pre_rake')
bottom_players(5)

positional_stats(6)          # 6-max only
positional_stats(2)          # heads-up only
positional_stats(None)       # all sizes

stats = player_stats('gaItR0R1G3KUo6rFvO7WSA')
stats['overall']             # dict: hands, net_won, flop_seen_pct, ...
stats['by_position']         # DataFrame
stats['by_label']            # DataFrame

player_hand_history('gaItR0R1G3KUo6rFvO7WSA', label='3bet_pot')

hand_details(3017235114)     # {'hand_id': ..., 'players': DataFrame, 'labels': [...]}
hands_with_label('squeeze')

pot_type_stats()
rake_stats()                 # {'raked_hands': 596, 'total_rake': 168.55, ...}
```

---

## Labelling System

### Storage

Labels from manual review live in `labels/labels.db` (SQLite). Use `src/labeller.py` to populate it and `src/analyser.py` to query it. Auto-labels are also written to `db/poker.db` during ingestion.

### Schema

```sql
CREATE TABLE labels (
    hand_id     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    label       TEXT NOT NULL,      -- e.g. '3bet_pot', 'squeeze'
    street      TEXT,               -- 'preflop' | 'flop' | 'turn' | 'river' | NULL
    player_idx  INTEGER,            -- 1-indexed, NULL if hand-level label
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_unique_label ON labels(hand_id, label, COALESCE(player_idx, -1));
CREATE INDEX idx_label ON labels(label);
CREATE INDEX idx_hand  ON labels(hand_id);
```

### Common Queries

```python
import sqlite3, pandas as pd
con = sqlite3.connect('labels/labels.db')

# Count of each label type
pd.read_sql("SELECT label, COUNT(*) cnt FROM labels GROUP BY label ORDER BY cnt DESC", con)

# All hands with a given label
pd.read_sql("SELECT * FROM labels WHERE label = ?", con, params=['3bet_pot'])

# All labels applied to a specific hand
pd.read_sql("SELECT label, street FROM labels WHERE hand_id = ?", con, params=[hand_id])

# Hands with both 3bet_pot and squeeze
pd.read_sql("""
    SELECT hand_id FROM labels WHERE label = '3bet_pot'
    INTERSECT
    SELECT hand_id FROM labels WHERE label = 'squeeze'
""", con)
```

### Label Taxonomy

**Preflop situation:**
- `rfi` — raise first in
- `3bet_pot` — hand includes a 3-bet preflop
- `4bet_pot` — hand includes a 4-bet preflop
- `squeeze` — 3-bet after a raise + one or more callers
- `limp_pot` — at least one limp, no raise preflop
- `single_raised_pot` — exactly one raise preflop

**Postflop situation:**
- `cbet_flop` — preflop aggressor bets flop
- `check_raise_flop` — flop check-raise occurs
- `multi_way` — 3+ players see the flop

**Outcome:**
- `showdown` — hand goes to showdown
- `all_in_preflop` — all-in committed before flop

Auto-labels are written to both `labels.db` (via `labeller.py --file` / `--dir`) and `poker.db` (via `ingest.py`). Manual labels can be added to `labels.db` only with `labeller.py --add`.

---

## Key Concepts for Implementation

### Pot Size Tracking

The pot is not stored directly — reconstruct it from actions:
1. Start with sum of blinds/antes
2. For each `cbr X` action: the raise amount is `X - player_current_bet_this_street`
3. Track per-player street contributions separately; reset each street

### Position Assignment

Positions are assigned by `assign_positions()` in `hand_utils.py` based on player count:

| Players | Labels assigned |
|---------|----------------|
| 2 | BTN, BB |
| 3 | BTN, SB, BB |
| 4 | BTN, UTG, SB, BB |
| 5 | BTN, CO, UTG, SB, BB |
| 6 | BTN, CO, HJ, UTG, SB, BB |
| 7+ | p1–pN (no named positions) |

In heads-up, p1 is the BTN (posts SB, acts last postflop). `n_players` is stored in `player_hands` so positional stats can be filtered by game size — always filter `WHERE n_players = 6` when comparing 6-max positions.

### Detecting 3-Bets

```python
def is_3bet_pot(actions: list[str]) -> bool:
    preflop_raises = 0
    for a in actions:
        if a.startswith('d db'):       # flop dealt — stop
            break
        if 'cbr' in a:
            preflop_raises += 1
        if preflop_raises >= 2:        # open + 3bet
            return True
    return False
```

### Street Segmentation

```python
def split_streets(actions):
    streets = {'preflop': [], 'flop': [], 'turn': [], 'river': []}
    boards  = {'flop': None, 'turn': None, 'river': None}
    current, db_count = 'preflop', 0
    street_order = ['flop', 'turn', 'river']
    for a in actions:
        if a.startswith('d db'):
            current = street_order[db_count]
            boards[current] = a.split()[-1]   # card string
            db_count += 1
        else:
            streets[current].append(a)
    return streets, boards
```

---

## Pygame Replayer

### Concept

Step-through replay of a single hand, showing:
- Table layout with seat positions
- Player stacks and current bet
- Community cards (revealed as they appear)
- Action log / history panel
- Current pot size
- Navigation: **Next action**, **Prev action**, **Reset**

### State Machine

Each "frame" in the replayer corresponds to processing one more action from the list. Maintain a `HandState` object:

```python
@dataclass
class HandState:
    step: int
    stacks: list[float]
    bets: list[float]          # current street bets per player
    pot: float
    board: list[str]           # cards dealt so far
    hole_cards: dict           # {player_idx: [card1, card2]}
    folded: set[int]
    street: str
    action_log: list[str]      # human-readable history
    current_actor: int | None
```

Advance state by calling `apply_action(state, action_str) -> HandState`.

### Layout Sketch

```
┌─────────────────────────────────┐
│  [Table oval]                   │
│     p6         p5               │
│  p1               p4            │
│     p2         p3               │
│                                 │
│  Board: [Ah][Kd][5s] [Tc] [ ]  │
│  Pot: $14.50                    │
├─────────────────────────────────┤
│  Action log                     │
│  > p3 raises to $3.50           │
│  > p1 folds                     │
│  [← Prev]  Step 7/19  [Next →] │
└─────────────────────────────────┘
```

---

## Python Dependencies

```
# requirements.txt
pygame>=2.5
pandas>=2.0
numpy>=1.25
sqlite3          # stdlib
pokerkit         # optional: hand evaluation / equity calc
treys            # fast hand evaluator (Cactus Kev)
jupyter
matplotlib
```

**`pokerkit`** is worth investigating — the `.phhs` format appears to be its native format, so a parser may already exist.

---

## Development Workflow

1. **Parse** — build `parser.py` to load all hands from a `.phhs` file into a list of `Hand` dataclasses
2. **Ingest** — run `ingest.py` to populate `db/poker.db` from all `.phhs` files; auto-labels applied here
3. **Explore** — use a Jupyter notebook to sanity-check counts, stack distributions, action frequencies
4. **Label** — add manual labels via `labeller.py`; add new auto-label rules to `ingest.py` and re-run
5. **Analyse** — query `poker.db` via pandas to study player stats, earnings, labelled subsets
6. **Replay** — build pygame replayer last, feeding it parsed `Hand` objects

---

## Notes & Gotchas

- **Never read `.phhs` files directly** — they are large (thousands of hands each). Always use `load()` / `load_all()` from `scripts.py` or `load_file()` / `load_directory()` from `parser.py`. The folder `phhs files/` may contain the full dataset and must not be grepped, catted, or read line-by-line.
- **`winnings` can be absent** — some hands (especially all-ins where opponent cards aren't shown) have no `winnings` field. Handle with `.get()`.
- **Cards use two-char notation** — rank then suit: `Ah` = Ace of hearts, `Tc` = Ten of clubs. Valid suits: `h d c s`.
- **`????` means unknown cards** — hole cards are only revealed at showdown via `sm` actions. Most hands never reveal cards.
- **`cbr` amounts are absolute** — the amount is the total bet/raise size facing opponents, not the additional chips going in.
- **Multi-file dataset** — write the parser to accept a directory glob, not a single file path.
- **`.gitignore`** — must exclude `data/*.phhs`, `db/poker.db`, `__pycache__`, `*.pyc`, `.env`.
