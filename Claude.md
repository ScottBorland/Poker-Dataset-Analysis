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
poker-analysis/
├── claude.md                  # This file
├── data/
│   └── *.phhs                 # Raw hand history files
├── labels/
│   └── labels.db              # SQLite label store (see Labelling System)
├── src/
│   ├── parser.py              # .phhs parser → Hand dataclass
│   ├── hand_utils.py          # Derived features (street detection, pot sizes, positions)
│   ├── labeller.py            # CLI tool for tagging hands
│   ├── analyser.py            # Query & aggregate labelled hands
│   └── replayer/
│       ├── main.py            # pygame entry point
│       ├── renderer.py        # Drawing logic
│       └── state.py           # Hand state machine for step-through replay
├── notebooks/
│   └── exploration.ipynb      # Exploratory analysis
└── requirements.txt
```

---

## Labelling System

### Recommended Storage: SQLite

Use a single `labels/labels.db` SQLite database. This allows:
- Fast filtered queries across millions of labels
- Multiple labels per hand
- Metadata (notes, confidence, analyst)
- Easy export to pandas via `pd.read_sql`

### Schema

```sql
CREATE TABLE labels (
    hand_id     INTEGER NOT NULL,   -- matches hand field in .phhs
    file        TEXT NOT NULL,      -- source .phhs filename
    label       TEXT NOT NULL,      -- e.g. '3bet_pot', 'squeeze'
    street      TEXT,               -- 'preflop' | 'flop' | 'turn' | 'river' | NULL
    player_idx  INTEGER,            -- 1-indexed player, NULL if hand-level label
    note        TEXT,               -- optional free-text annotation
    created_at  TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (hand_id, label, player_idx)
);

CREATE INDEX idx_label ON labels(label);
CREATE INDEX idx_hand  ON labels(hand_id);
```

### Label Taxonomy (starting suggestions)

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

Labels can be auto-detected via `labeller.py` or manually assigned.

---

## Key Concepts for Implementation

### Pot Size Tracking

The pot is not stored directly — reconstruct it from actions:
1. Start with sum of blinds/antes
2. For each `cbr X` action: the raise amount is `X - player_current_bet_this_street`
3. Track per-player street contributions separately; reset each street

### Position Assignment (6-max example)

With `blinds_or_straddles = [0.25, 0.50, 0, 0, 0, 0]`:
- p1 = SB
- p2 = BB
- p3 = UTG (first to act preflop)
- p6 = BTN (last to act preflop, first postflop... except SB/BB)

Button is the player with the highest index before p1/p2, i.e. `N_players` in a full orbit.

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
2. **Explore** — use a Jupyter notebook to sanity-check counts, stack distributions, action frequencies
3. **Label** — build auto-labellers for common spots; add a simple CLI (`labeller.py`) for manual review
4. **Analyse** — query `labels.db` to pull hand subsets; compute stats with pandas
5. **Replay** — build pygame replayer last, feeding it parsed `Hand` objects

---

## Notes & Gotchas

- **`winnings` can be absent** — some hands (especially all-ins where opponent cards aren't shown) have no `winnings` field. Handle with `.get()`.
- **Cards use two-char notation** — rank then suit: `Ah` = Ace of hearts, `Tc` = Ten of clubs. Valid suits: `h d c s`.
- **`????` means unknown cards** — hole cards are only revealed at showdown via `sm` actions. Most hands never reveal cards.
- **`cbr` amounts are absolute** — the amount is the total bet/raise size facing opponents, not the additional chips going in.
- **Multi-file dataset** — write the parser to accept a directory glob, not a single file path.
- **Obfuscated player IDs** — cross-file player tracking is possible via the base64 ID strings, but treat them as opaque keys.

## Git Workflow

After completing any code change, run:
  git add -A
  git commit -m "<type>: <description>"

Commit message format: conventional commits — feat:, fix:, refactor:, docs:, chore:
Be specific: `feat: add 3bet detection to labeller` not `update labeller.py`

Branch strategy:
- Default: commit to current branch
- Create a new branch only if explicitly asked, using kebab-case: feat/squeeze-detection

Never commit: .pyc files, __pycache__, .db files, .env, large data files (*.phhs)
Add a .gitignore covering the above before the first commit.