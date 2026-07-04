# Poker Dataset Analysis — Project Guide

## Project Overview

This project analyses a large dataset of No-Limit Texas Hold'em cash game hands from two sources:

1. **Absolute Poker (2009)** — ~777k hands stored in `.phhs` files across multiple stake levels ($0.50/$1.00, $1/$2, $5/$10 NL). Player IDs are obfuscated base64 strings.
2. **888poker** — ~118k hands stored in plain-text hand history files. Includes the user's own sessions (player ID `ScottyWotty`) where hole cards are visible at showdown.

There is no fixed "hero" — the Absolute Poker portion is a population study. The 888poker portion includes ScottyWotty's sessions, enabling starting-hand and positional analysis from a first-person perspective.

The goals are:
1. **Parse & ingest** hand histories into a SQLite database
2. **Auto-label** hands by situation type (pot type, flop texture, hole cards, etc.)
3. **Analyse** labelled subsets via SQL + pandas
4. **Replay** individual hands step-by-step in a pygame visualiser

---

## Project Structure

```
Poker Analysis/
├── Claude.md                        # This file
├── data/
│   ├── phhs files/
│   │   └── phh-dataset-main/
│   │       └── data/handhq/
│   │           └── ABS-*/           # stake-level subdirs, e.g. ABS-2009-..._1000NLH
│   │               └── *.phhs       # ~780 ingested files, ~1000 hands each
│   ├── 888poker/                    # 888poker text hand histories (~1056 files)
│   └── ScottyWotty/                 # ScottyWotty's personal 888poker sessions
├── db/
│   └── poker.db                     # Primary SQLite DB — NOT committed to git
├── labels/
│   └── labels.db                    # Manual-label store — NOT committed to git
├── src/
│   ├── parser.py                    # .phhs → Hand dataclass (uses pokerkit)
│   ├── parser_888.py                # 888poker text → Hand dataclass
│   ├── hand_utils.py                # Street segmentation, pot reconstruction, positions
│   ├── ingest.py                    # Populates db/poker.db (incremental)
│   ├── labeller.py                  # Auto-label engine + CLI for manual labels
│   ├── analyser.py                  # CLI query tool for labels.db
│   ├── player_analysis.py           # In-memory per-player stats (no DB required)
│   ├── scripts.py                   # High-level API for notebooks / REPL
│   └── replayer/
│       ├── main.py                  # pygame entry point (all hands)
│       ├── player_main.py           # pygame entry point (player-filtered view)
│       ├── renderer.py              # Drawing logic
│       └── state.py                 # Hand state machine
├── notebooks/
│   └── exploration.ipynb
├── commands.txt                     # Example CLI commands
└── requirements.txt
```

---

## File Formats

### `.phhs` (Absolute Poker)

The `.phhs` format is pokerkit's native TOML-based hand history format. Files contain many hands separated by numbered sections `[1]`, `[2]`, etc.

**Key fields on the `Hand` dataclass** (produced by `parser.py`):

| Field | Type | Notes |
|---|---|---|
| `hand_id` | int | Unique hand ID |
| `players` | list[str] | Obfuscated player IDs (1-indexed: players[0] = p1) |
| `blinds_or_straddles` | list[float] | Index 0 = SB, index 1 = BB |
| `starting_stacks` | list[float] | Per player, 0-indexed |
| `actions` | list[str] | Ordered action sequence (see below) |
| `winnings` | list[float] \| None | Gross chips received; absent on some all-ins |
| `day` / `month` / `year` | int | Hand date |
| `table` | str | Table name |
| `venue` | str | `'Absolute Poker'` |
| `n_players` | int (property) | `len(players)` |
| `date_str` | str (property) | `'YYYY-MM-DD'` |

**Action encoding:**

| Pattern | Meaning |
|---|---|
| `d dh pN ????` | Deal hole cards to player N — unknown |
| `d dh pN XxYy` | Deal hole cards to player N — revealed at showdown |
| `d db XxYy[Zz]` | Deal board cards (flop = 3 cards, turn/river = 1) |
| `pN f` | Player N folds |
| `pN cc` | Player N calls or checks |
| `pN cbr X.XX` | Player N raises/bets to X.XX (absolute total, not increment) |
| `pN sm XxYy` | Player N shows/mucks at showdown |

Street boundaries: first `d db` = flop, second = turn, third = river. Players are 1-indexed; p1 = SB, p2 = BB, last player = BTN.

### 888poker text format

Parsed by `parser_888.py` into the same `Hand` dataclass. Hole cards are visible for all players who reached showdown, making it suitable for starting-hand analysis. ScottyWotty's sessions are in `data/ScottyWotty/`.

---

## Database (`db/poker.db`)

Populated by `src/ingest.py`. Contains ~10M hands, ~62M player_hands rows, ~53M label rows (208 label types) across ~11,941 ingested files. The DB is ~30 GB on disk — queries against `player_hands` or `labels` without a covering index will be slow; see `src/add_indexes.py`.

### Schema

```sql
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
    seat_idx    INTEGER NOT NULL,     -- 1-indexed
    n_players   INTEGER NOT NULL,     -- players at the table
    position    TEXT,                 -- 'BTN'|'SB'|'BB'|'UTG'|'HJ'|'CO' (NULL for 7+)
    stack       REAL,                 -- starting stack
    invested    REAL,                 -- total chips put in (uncalled bets returned)
    winnings    REAL,                 -- gross chips received; NULL when unknown
    net_won     REAL,                 -- winnings - invested; NULL when winnings NULL
    saw_flop    INTEGER DEFAULT 0,
    went_to_sd  INTEGER DEFAULT 0,
    vpip        INTEGER DEFAULT 0,    -- 1 if voluntarily put money in preflop
    pfr         INTEGER DEFAULT 0,    -- 1 if raised preflop
    venue       TEXT DEFAULT 'absolute_poker',
    big_blind   REAL,                 -- BB size in $, e.g. 0.50 for $0.25/$0.50
    date        TEXT,                 -- 'YYYY-MM-DD'
    PRIMARY KEY (player_id, hand_id)
);

-- Auto-labels (and manual labels added via labeller.py --add)
CREATE TABLE labels (
    hand_id     INTEGER NOT NULL,
    file        TEXT NOT NULL,
    label       TEXT NOT NULL,
    street      TEXT,                 -- 'preflop'|'flop'|'turn'|'river'|NULL
    player_idx  INTEGER,              -- 1-indexed seat; NULL = hand-level label
    note        TEXT,                 -- e.g. raw flop string for flop texture labels
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

# Net P&L leaderboard (net_won = winnings - invested, not raw winnings)
pd.read_sql("""
    SELECT player_id, COUNT(*) hands, ROUND(SUM(net_won), 2) net_won
    FROM player_hands WHERE net_won IS NOT NULL
    GROUP BY player_id HAVING hands >= 5
    ORDER BY net_won DESC
""", con)

# BB-normalised P&L — useful for comparing players across stakes
pd.read_sql("""
    SELECT player_id,
           COUNT(*)                                   hands,
           ROUND(SUM(net_won / big_blind), 2)         net_won_bb,
           ROUND(AVG(net_won / big_blind) * 100, 2)   bb_per_100
    FROM player_hands
    WHERE net_won IS NOT NULL AND big_blind > 0
    GROUP BY player_id HAVING hands >= 5
    ORDER BY net_won_bb DESC
""", con)

# Positional P&L — always filter n_players for fair comparison
pd.read_sql("""
    SELECT position, COUNT(*) hands,
           ROUND(SUM(net_won), 2) net_won,
           ROUND(100.0 * SUM(saw_flop) / COUNT(*), 1) flop_seen_pct
    FROM player_hands
    WHERE n_players = 6
    GROUP BY position ORDER BY net_won DESC
""", con)

# Player stats in 3bet pots
pd.read_sql("""
    SELECT ph.player_id, COUNT(*) hands, ROUND(SUM(ph.net_won), 2) net_won
    FROM player_hands ph
    JOIN labels l ON ph.hand_id = l.hand_id
    WHERE l.label = '3bet_pot' AND ph.net_won IS NOT NULL
    GROUP BY ph.player_id ORDER BY net_won DESC
""", con)

# Filter to a specific stake
pd.read_sql("SELECT * FROM player_hands WHERE big_blind = 1.00 LIMIT 20", con)

# Monthly P&L trend
pd.read_sql("""
    SELECT strftime('%Y-%m', date) month,
           COUNT(DISTINCT hand_id) hands,
           ROUND(SUM(net_won), 2) net_won
    FROM player_hands WHERE net_won IS NOT NULL
    GROUP BY month ORDER BY month
""", con)

# Rake analysis (proportional to chips invested)
pd.read_sql("""
    WITH hand_rake AS (
        SELECT hand_id,
               SUM(invested)                 total_invested,
               SUM(invested) - SUM(winnings) rake
        FROM player_hands GROUP BY hand_id
        HAVING SUM(CASE WHEN winnings IS NULL THEN 1 ELSE 0 END) = 0
          AND SUM(invested) - SUM(winnings) >= 0
    )
    SELECT ph.player_id, COUNT(*) hands,
           ROUND(SUM(hr.rake * ph.invested / hr.total_invested), 2) rake_paid,
           ROUND(SUM(ph.net_won), 2) net_won,
           ROUND(SUM(ph.net_won) + SUM(hr.rake * ph.invested / hr.total_invested), 2) net_won_pre_rake
    FROM player_hands ph
    JOIN hand_rake hr ON ph.hand_id = hr.hand_id
    WHERE ph.net_won IS NOT NULL
    GROUP BY ph.player_id HAVING hands >= 5
    ORDER BY net_won_pre_rake DESC
""", con)
```

---

## Ingestion (`src/ingest.py`)

Incremental by default — files in `ingested_files` are skipped unless forced.

```bash
python src/ingest.py                          # ingest new files from data/
python src/ingest.py --data-dir data/         # explicit data dir (same as default)
python src/ingest.py --reprocess file.phhs    # force re-ingest one file
python src/ingest.py --reprocess-all          # wipe and re-ingest everything
```

**Directory layout expected under `--data-dir`:**
- `data/phhs files/` — recursively scanned for `*.phhs` (Absolute Poker)
- `data/888poker/` — scanned for `*.txt` excluding `*Summary*` (888poker)

Per hand, ingest writes:
- One `player_hands` row per seated player (position, stack, invested, winnings, net_won, saw_flop, went_to_sd, vpip, pfr, big_blind, date)
- All auto-labels from `label_hand()` into the `labels` table

**Note:** `poker.db` holds auto-labels only. Manual labels (`labeller.py --add`) go to `labels/labels.db`.

---

## Scripts API (`src/scripts.py`)

```python
import sys; sys.path.insert(0, 'src')
from scripts import *
```

All DB functions accept an optional `con=` keyword to reuse an open connection.

### Overview & stats

| Function | Returns | Description |
|---|---|---|
| `summary()` | — | Print hands, players, label counts, rake |
| `label_counts()` | DataFrame | Count per label type |
| `rake_stats()` | dict | Total/avg rake |
| `pot_type_stats(pot_types)` | DataFrame | P&L by preflop pot type |
| `positional_stats(n_players=6)` | DataFrame | P&L by position; `None` = all sizes |

### Player analysis

| Function | Returns | Description |
|---|---|---|
| `top_players(n=10, by='net_won', min_hands=5)` | DataFrame | Includes vpip_pct, pfr_pct; `by` also accepts `'net_won_pre_rake'` |
| `bottom_players(n=10, by='net_won', min_hands=5)` | DataFrame | Biggest losers |
| `vpip_pfr_stats(min_hands=100)` | DataFrame | VPIP%, PFR%, AF, net_won |
| `player_stats(player_id)` | dict | P&L + vpip/pfr + breakdown by position and label |
| `player_hand_history(player_id, label=None)` | DataFrame | All hands for a player |

### Hand lookup & replay

| Function | Returns | Description |
|---|---|---|
| `hand_details(hand_id)` | dict | `{'players': DataFrame, 'labels': list}` |
| `hands_with_label(label, limit=20)` | DataFrame | Player rows for hands with a label |
| `hand_replay(hand, position=None, label=None, player_id='ScottyWotty')` | dict | Stats + replayer for a specific starting hand (e.g. `'AQs'`, `'KK'`). 888poker only — requires visible hole cards. |
| `label_replay(labels, player_id=None, position=None, n_players=None, max_hands=500, replay=True)` | dict | Filter by one or more labels (AND logic if list), print avg pot in BB + P&L stats, open replayer. Works on all hands. |

### Data loading

| Function | Returns | Description |
|---|---|---|
| `load(path)` | list[Hand] | Load one `.phhs` file |
| `load_all(folder='.')` | list[Hand] | Load all `.phhs` files in a folder |
| `connect(db_path)` | Connection | Open poker.db (caller closes) |

### Example session

```python
from scripts import *

summary()

top_players(10)
top_players(10, by='net_won_pre_rake')
bottom_players(10)
vpip_pfr_stats(min_hands=100)

positional_stats(6)       # 6-max
positional_stats(None)    # all sizes

stats = player_stats('gaItR0R1G3KUo6rFvO7WSA')
stats['overall']          # dict
stats['by_position']      # DataFrame
stats['by_label']         # DataFrame

player_hand_history('gaItR0R1G3KUo6rFvO7WSA', label='3bet_pot')
hand_details(3017235114)
hands_with_label('squeeze')

# Starting-hand replay (888poker / ScottyWotty hands only)
hand_replay('AQs')
hand_replay('AQs', position='BTN')
hand_replay('KK', label='3bet_pot')

# Label-based replay (all hands)
label_replay('3bet_pot')                          # P&L by position + avg pot BB
label_replay(['3bet_pot', 'flop_monotone'])       # AND logic
label_replay('squeeze', n_players=6)
label_replay('flop_dry', replay=False)            # stats only
label_replay('all_in_preflop', player_id='ScottyWotty')
label_replay('blind_vs_blind', player_id='ScottyWotty', position='SB')
```

---

## Labelling System

Labels live in the `labels` table of `poker.db` (auto, written at ingest) and optionally in `labels/labels.db` (manual, via `labeller.py --add`). The schema is identical in both databases.

The `label_hand(hand)` function in `labeller.py` returns all applicable `LabelRow` objects for a hand. It is called during ingest and can also be run standalone.

### Label Taxonomy

**Preflop:**
- `rfi` — raise first in (open raise, no action before)
- `single_raised_pot` — exactly one preflop raise
- `3bet_pot` — two preflop raises
- `4bet_pot` — three preflop raises
- `5bet_pot` — four or more raises (also tagged `4bet_pot`)
- `squeeze` — 3-bet after a raise + ≥1 caller
- `limp_pot` — at least one limp, no raise
- `blind_vs_blind` — only SB and BB reach flop (in a 3+-handed game)
- `all_in_preflop` — a player committed all-in before the flop

**Postflop:**
- `heads_up_flop` — exactly 2 players see the flop
- `3way_flop` — exactly 3 players see the flop
- `multi_way` — 3+ players see the flop
- `cbet_flop` — preflop aggressor bets flop (`player_idx` = aggressor)
- `donk_bet_flop` — non-aggressor leads flop (`player_idx` = bettor)
- `check_raise_flop` / `check_raise_turn` / `check_raise_river`
- `showdown` — hand reached showdown

**Flop texture** (`street='flop'`, raw flop string in `note`, e.g. `'Ah5s2c'`):
- `flop_rainbow` / `flop_two_tone` / `flop_monotone` — suit texture
- `flop_paired` — board pair
- `flop_ace_high` / `flop_king_high` / `flop_low` (all ≤9) — high card
- `flop_two_broadway` — two or more T–A cards
- `flop_connected` — all 3 unique ranks within a 5-card window
- `flop_dry` — rainbow + no straight draw + unpaired

**Hole cards** (`street='preflop'`, `player_idx` = seat — only when cards are revealed at showdown):
- `hand_AA`, `hand_AKs`, `hand_AKo`, … — specific canonical hand
- `pocket_pair`, `premium_pair` (TT+)
- `suited`, `offsuit`
- `suited_connector`, `connector`, `suited_one_gapper`, `one_gapper`
- `broadway` (both cards T–A, non-pair)
- `ace_x`, `ace_x_suited`

---

## Pygame Replayer

Two entry points in `src/replayer/`:

- **`main.py`** — loads any list of `Hand` objects; navigate with N/P
- **`player_main.py`** — player-filtered view, highlights the player's seat in teal, shows only that player's hands

Both are launched automatically by `label_replay()` and `hand_replay()` in `scripts.py`, or directly from the command line (see `commands.txt`).

Keyboard controls: `Right`/`Space` = next action, `Left` = previous, `R` = reset, `N`/`P` = next/prev hand, `Q`/`Esc` = quit.

---

## Key Implementation Notes

### Position assignment

p1 = SB, p2 = BB, last player = BTN. Named positions only assigned for 2–6 players; 7+ get `p1`–`pN`. Always filter `WHERE n_players = 6` when comparing 6-max positions.

| Players | Positions |
|---|---|
| 2 | BTN, BB |
| 3 | BTN, SB, BB |
| 4 | BTN, UTG, SB, BB |
| 5 | BTN, CO, UTG, SB, BB |
| 6 | BTN, CO, HJ, UTG, SB, BB |

### Pot size

`invested` in `player_hands` = total chips each player put in, with uncalled bets correctly returned. `SUM(invested)` per hand = actual pot (pre-rake). Use this, not `final_pot()` from `hand_utils.py`, which doesn't return uncalled bets.

For BB-normalised pot size: `SUM(invested) / big_blind`.

### Street segmentation

```python
# from hand_utils.split_streets(hand.actions)
# returns: streets dict + boards dict
# boards['flop'] = 'Ah5s2c', boards['turn'] = 'Td', etc.
```

### cbr amounts are absolute

`p3 cbr 5.00` means player 3's total bet this street is $5.00, not an increment. To get the raise size: `5.00 - player_current_street_bet`.

---

## Python Dependencies

```
pokerkit>=0.7    # .phhs parser
pygame-ce        # replayer (use pygame-ce, not pygame)
pandas>=2.0
numpy>=1.25
treys            # hand evaluator
jupyter
matplotlib
```

---

## Notes & Gotchas

- **Never read `.phhs` files directly** — they are large. Always use `load_file()` / `load_directory()` from `parser.py`, or `load()` / `load_all()` from `scripts.py`. Do not grep or cat them.
- **`winnings` can be absent** — all-ins where opponent cards aren't shown have no `winnings` field. Always use `.get('winnings')` and handle `None`.
- **`big_blind` can be NULL** — abs poker hands ingested before the column was added will have NULL. Re-ingest with `--reprocess-all` to populate.
- **Hole cards are mostly unknown** — abs poker hands show `????` for hole cards. Cards are only revealed at showdown via `d dh pN XxYy` or `pN sm XxYy`. Hole card labels only apply to showdown hands.
- **Cards use two-char notation** — `Ah` = Ace of hearts, `Tc` = Ten of clubs. Suits: `h d c s`.
- **Abs poker files are nested** — files live deep under `data/phhs files/phh-dataset-main/data/handhq/`. The DB stores only the basename. `scripts.py` uses `rglob` to resolve them.
- **`ingest.py` deduplicates by filename** — the same basename may exist in multiple stake-level subdirectories. Only the first path found by `rglob` is ingested per basename.
- **`poker.db` and `labels.db` are not committed to git.**
