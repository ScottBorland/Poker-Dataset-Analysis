# Handoff: Poker Flow — dark Modernist hand builder + solver split view

## Overview

Two screens for Poker Flow, a hand-analysis web app:

1. **Hand Builder** (option `1b`) — the existing builder screen restyled: dark ground, diagrammatic seat grid instead of a felt oval, street tabs, right rail for Situation / Similar real hands / Solve Spot.
2. **Solver view** (option `1c`) — a new screen: the user's line and the solver's line side by side, EV loss called out, a 13×13 range grid coloured by action, and a combo detail panel that ties the solve back to real 888poker hands.

Both are drawn against the **Modernist** design system (flat, architectural, Archivo throughout, zero corner radius, strong 2px rules, one red accent), inverted onto a dark ground.

## About the design files

`Poker Flow.dc.html` in this bundle is a **design reference created in HTML** — a prototype showing intended look and structure, not production code to copy. It opens directly in a browser (keep `support.js` next to it).

The task is to **recreate these designs in the existing frontend**: React 18 + TypeScript + Vite + Tailwind, in `frontend/src/`. Use the codebase's existing components and data flow — `PokerTable.tsx`, `HandBuilderPage.tsx`, `TexasStrategyViewer.tsx`, `HandRangeHeatmap.tsx`, `RangeBreakdownTable.tsx`, `utils/tableEngine.ts`, `utils/api.ts`. Do not port the HTML file itself.

The prototype file also contains an option `1a` (light chrome, dark table inset). **Ignore `1a`** — it was not selected.

## Fidelity

**High fidelity.** Colours, type, spacing and rules are final; recreate them exactly. All numbers shown (pot sizes, frequencies, EV, hand counts) are placeholder data standing in for real API responses — wire them to the real endpoints, don't hard-code them.

---

## Design tokens

Modernist, inverted for a dark ground. Add these as Tailwind theme extensions rather than sprinkling arbitrary values.

### Colour

| Role | Hex | Use |
| --- | --- | --- |
| Ground | `#201e1d` | page background, folded/empty seat cells |
| Surface | `#2d2b2b` | raised cells: hero seat, board cell, to-act seat, inset notes |
| Surface deep | `#444141` | muted card backs, "not in range" grid cells |
| Text | `#f3f2f2` | primary text, card faces |
| Text muted | `#9b9797` | labels, secondary numbers |
| Text dim | `#605d5d` | folded seats, disabled |
| Accent | `#ff563c` | primary action, hero ring, active tab, running state (accent-500 — the correct accent step on a dark ground) |
| Accent light | `#ff9783` | accent hover, secondary bar segment, positive-ish emphasis |
| Accent deep | `#ae1800` | pressed state |
| Accent tint (dark) | `#471d16` | selected table row fill |
| Card red | `#ec3013` | hearts and diamonds on white card faces |
| Divider strong | `rgba(243,242,242,.35)` | 2px rules between major sections |
| Divider mid | `rgba(243,242,242,.2)` | 1px seat-grid gaps, sub-rules |
| Divider light | `rgba(243,242,242,.12)` | 1px table row rules |

### Type

Archivo only (400 / 600 / 800), weights already loaded via Google Fonts.

| Token | Spec | Use |
| --- | --- | --- |
| Section label | 800 · 11px · `letter-spacing:.14em` · uppercase | panel headings ("Situation", "Solve spot") |
| Seat label | 800 · 11px · `.1em` | UTG / HJ / CO / BTN / SB / BB |
| Badge | 800 · 9–10px · `.1em` · uppercase | HERO, TO ACT, RUNNING, D |
| Button | 800 · 11–12px · `.06–.08em` · uppercase · **flush left** | all buttons |
| Body | 400 · 12.5px | situation values, log lines, notes |
| Data | 600 · 12px · `font-variant-numeric: tabular-nums` | table cells |
| Pot display | 800 · 26px · `letter-spacing:-.02em` | POT 7.00 BB |
| Card rank | 800 · 22px (board) / 15px (hole) | card faces |

### Spacing / geometry

4 / 8 / 12 / 16 / 24 / 32px scale. **Border radius is 0 everywhere.** Section dividers are 2px; row rules 1px. No shadows except `inset 0 0 0 2px <colour>` used as a selection ring. Screen width in the mock is 1360px; both screens should be fluid with the right rail fixed at 432px (hand builder) / 400px (solver combo panel).

---

## Screen 1 — Hand Builder (`1b`)

Replaces the current `HandBuilderPage.tsx` layout. Same state, same API calls; new visual structure.

### Layout

```
┌─ header bar (2px bottom rule) ──────────────────────────────────┐
│ POKERFLOW │ Hand builder │ Explorer │ Query │ …controls right   │
├──────────────────────────────┬──────────────────────────────────┤
│ table column (2px right rule)│ right rail — 432px               │
│  · street tabs + table grid  │  · Situation                     │
│  · action bar (2px rules)    │  · Similar real hands            │
│  · action log                │  · Solve spot                    │
└──────────────────────────────┴──────────────────────────────────┘
```

Grid: `grid-template-columns: minmax(0,1fr) 432px`.

### Header bar

- Brand: `POKER` in text colour + `FLOW` in accent, 800/15px, `.12em`, uppercase, 20px horizontal padding, 2px right rule.
- Tabs: 16px/22px padding, 800/11px `.1em` uppercase when active, 600 + `#9b9797` when not; 1px right rule between each; active tab carries a **3px accent bottom border**. Tabs map to the existing routes in `App.tsx`.
- Right cluster: `Players` label + select (1px border `rgba(243,242,242,.35)`, `#2d2b2b` fill, 6px/10px padding), `Stacks BB` label + 64px number input, then `Undo` and `Reset hand` as outlined buttons (7px/12px, hover `rgba(243,242,242,.1)`). These bind to the existing `nPlayers` / `stackBB` / `setEvents` / `resetHand`.

### Table

**No felt oval.** Seats sit on a 3×3 CSS grid with 2px gaps showing the ground through as rules, wrapped in a 2px `rgba(243,242,242,.2)` border:

```
UTG   HJ    CO(hero)
BB    BOARD BTN
—     SB    —
```

Map seats to cells by position so the ring order stays readable as `nPlayers` changes; empty cells are plain ground-coloured divs.

Above the grid: `TABLE · 6-MAX · 100 BB DEEP` on the left (800/11px `.14em` `#9b9797`), street tabs on the right — Preflop / Flop / Turn / River as a joined segmented control, active = accent fill with `#201e1d` label, past streets `#9b9797`, future streets `#605d5d`. Clicking a past street should scrub the table to that street's state (currently the app has no scrubber — treat as a follow-up if `street_progression` doesn't already cover it).

**Seat cell** (14px/16px padding):
- Row 1: position label · optional badge (`HERO` = accent fill / `TO ACT` = `#f3f2f2` fill, both with `#201e1d` text, 2px/5px padding; `D` = 1px outlined box for the button) · stack right-aligned, 600/11px.
- Row 2: two 30×42px cards, 3px gap. Face-down = `#2d2b2b` (folded) or `#444141` (live, unknown). Face-up = `#f8f4f4` fill, rank 800/15px top-left with the suit glyph directly beneath at 13px; red suits `#ec3013`, black `#201e1d`. Folded players' revealed cards drop to `#605d5d` fill with `#2d2b2b` ink.
- Row 3: status — `BET 3.00 BB` in `#ff9783` 800/10px when the seat has chips in, `FACING 3.00 BB` in `#9b9797`, `FOLDED` in `#605d5d`.
- Hero cell: `#2d2b2b` fill + `inset 0 0 0 2px #ff563c`. To-act cell: `#2d2b2b` fill + `inset 0 0 0 2px #f3f2f2`. Clicking a cell sets hero (existing `onSeatClick`); clicking the cards opens the card picker (`onSeatCardsClick`).

**Board cell** (centre, `#2d2b2b`, 20px/16px padding, flex column, 12px gap, flush left):
- `BOARD · K-HIGH RAINBOW` label (texture string from `derive`).
- Board cards: 44×62px, same face treatment, undealt streets as 2px dashed `#444141` placeholders. Clicking a placeholder opens the board picker.
- `POT 7.00 BB` at 800/26px.
- `LAST: BB FOLDS` at 600/10px `#9b9797`.

### Action bar

Full-width strip, 2px rules top and bottom, 14px/24px padding, 10px gap, wraps.

`SB TO ACT` label · `Fold` (outlined; hover turns border and label accent) · `Call 3.00` / `Check` (outlined; hover `rgba(243,242,242,.1)`) · bet amount input (92px, `#2d2b2b` fill, placeholder = min raise) · `Raise to` / `Bet` (accent fill, `#201e1d` label, hover `#ff9783`) · joined size buttons `⅓ pot ½ pot ⅔ pot pot all-in` (8px/11px, 1px shared borders, `#9b9797` labels) · right-aligned hint `Hero: CO — click a seat to change`.

All of this maps 1:1 to the current `legalActions()` output; keep the existing `quickSize()` maths.

### Action log

Two columns, one per street, 28px gutter. Each column starts with a header row (street name left, pot or board right, `#9b9797`, 1px bottom rule `rgba(243,242,242,.2)`), then one line per action at 400/12.5px with 1px `rgba(243,242,242,.1)` rules. The hero's actions render 800 weight in accent. Pending action shows as `SB to act…` in `#9b9797`.

### Right rail

2px rule between each section, 18px/20px padding.

**Situation** — a 2-column grid (`88px minmax(0,1fr)`, 6px/12px gap): Hero / Facing / Texture / Pot & eff., labels `#9b9797`, values `#f3f2f2`, pot value 800 weight. Values come straight from `deriveHandBuilderApi`.

**Similar real hands** — heading + `888poker` in `#9b9797`. Tier filter as a joined segmented control (Exact / +Board / +SPR / +Facing / Any position, 6px/9px, 600/10.5px); active tier = accent fill. Table: `minmax(0,1.5fr) repeat(4, minmax(0,1fr))` grid, header row 800/10px `.1em` uppercase `#9b9797` with a 2px bottom rule, body rows 7px vertical padding with 1px rules, numerics right-aligned and tabular. Rows with zero hands drop to `#605d5d`. The currently-selected tier row gets a `#471d16` fill. Negative bb/100 renders `#ff9783` 800; positive renders `#f3f2f2` 800. Below: full-width accent button `FIND MATCHING REAL HANDS` with a **flush-left label**, then the hint `Select a hand row to replay it on the table.`

**Solve spot** — heading with a status badge right-aligned (accent fill, `#201e1d` label: `RUNNING` / `DONE` / `FAILED`). Mode as two half-width joined buttons (`Final state only` / `Every decision`), active = `#f3f2f2` fill with `#201e1d` label, labels flush left. `BET SIZES IN THE TREE` label, then the eight fractions as toggle chips — selected `#f3f2f2` fill / `#201e1d` text, unselected 1px `rgba(243,242,242,.25)` border with `#9b9797` text. `ITERATIONS` label + 76px input + hint `Full 3-street solve — minutes`. Then a 2px rule and the job row: `Flop · CO (hero, IP) vs SB` left, `51 / 200 · expl. 5.07%` right in `#9b9797`, above an 8px progress bar — track `rgba(243,242,242,.18)`, fill accent, square ends, width = `iterations_done / iterations_total`.

---

## Screen 2 — Solver view (`1c`)

New screen. Reached from a solved job in the rail, or by selecting a stored solution. Replaces / wraps `TexasStrategyViewer`.

### Layout

```
┌─ solution header (2px bottom rule) ─────────────────────────────┐
├────────────────────────┬────────────────────────────────────────┤
│ Your line              │ Solver line          (2px bottom rule) │
├────────────────────────┴───────────────┬────────────────────────┤
│ Hero range · 13×13                     │ Combo panel — 400px    │
└────────────────────────────────────────┴────────────────────────┘
```

Top band: two equal columns split by a 2px rule. Bottom band: `minmax(0,1fr) 400px`.

### Solution header

14px/20px padding. `SOLUTION · CO VS SB · SRP` at 800/13px `.12em` uppercase. Then a breadcrumb of the walked tree path: nodes at 600/11px, `›` separators in `#9b9797`, past nodes `#f3f2f2`, the current node an accent chip (`#201e1d` label, 800, 2px/6px). This is the existing `TreePathStep[]` — clicking a crumb walks back up the tree. Right: `expl. 0.41%` (value 800 `#f3f2f2`), `200 iters`, and an outlined `RE-SOLVE` button.

### Your line (left)

Heading `YOUR LINE` + right-aligned total, `−1.84 BB TOTAL EV` in `#ff9783` 800/12px (accent tint only when EV loss is negative; use `#f3f2f2` when the line matches the solver).

Rows: grid `64px minmax(0,1fr) 78px`, 11px vertical padding, 1px `rgba(243,242,242,.12)` rules — street label (800/10px `.12em` uppercase `#9b9797`), action text (600/13px), EV delta right-aligned 800/12px, coloured accent when it's the losing action and `#f3f2f2` otherwise.

Below, the leak callout: `#2d2b2b` fill, **3px left accent border**, 12px/14px padding. Kicker `LARGEST LEAK` in `#ff9783` 800/10px `.12em`, then one sentence of plain-language explanation at 400/12.5px. Generate this from the largest EV drop in the walked line.

### Solver line (right)

Same row grid, but the third column shows the solver's frequency at that node in 600/12px `#9b9797`, not EV.

Below, the node action mix: `#2d2b2b` panel with a 26px stacked horizontal bar — segments in `#9b9797` (check), `#ff9783` (small bet), `#ff563c` (large bet), widths = frequencies, no gaps, square. Legend beneath: 9px square swatch + `Check 64%` etc. at 600/10.5px `#9b9797`. Segment colours must match the range grid legend exactly.

### Hero range grid

Heading `HERO RANGE · 13×13` plus a caption `Cell fill = action frequency · QJs highlighted`.

- 13×13 of 34×26px cells, 2px gaps, plus a 22px header row/column of rank labels in 600/10px `#605d5d`.
- Cell fill = the hand's dominant action colour: `#444141` not in range, `#9b9797` check, `#ff9783` bet 33%, `#ff563c` bet 75%. Label centred, 600/9.5px — `#9b9797` on the dark not-in-range fill, `#201e1d` on the rest.
- **In the real app, keep the existing per-cell proportional split** from `HandRangeHeatmap.tsx` (a mini stacked bar of the full action mix inside each cell) rather than the flat fill used in the mock — that's strictly more information. Apply this palette to `utils/categoricalColors.ts` so the grid, the mix bar and the combo panel all agree.
- The hero's actual combo gets `inset 0 0 0 2px #f3f2f2`. Hover a cell → tooltip with the full mix; click → loads that combo into the panel on the right.
- Legend below at 600/10.5px `#9b9797` with 10px swatches, in the same order as the mix bar.

### Combo panel (400px)

- Heading `QJ♥♥ — YOUR COMBO`, then the two 44×62px card faces, and beside them the hand class (`Backdoor flush + gutshot`, 400/11px `#9b9797`) over the equity (`31.4% equity vs SB range`, 800/13px).
- One block per action: label left, `21% · EV +1.94` right in `#9b9797`, above a 10px bar — track `rgba(243,242,242,.14)`, fill in the action colour, width = frequency.
- 2px rule, then `REAL HANDS IN THIS SPOT`: a sentence comparing the population's actual frequency to the solver's (`bet here 68% of the time — 46 points above the solver`), computed from the fingerprint stats already fetched by `getFingerprintStatsApi`. Ends with a full-width accent button `REPLAY THOSE HANDS`, label flush left, which loads those hands into the table's replay mode.

---

## Interactions & behaviour

- **Hover**: outlined controls tint `rgba(243,242,242,.1)`; accent fills go `#ff9783`; pressed goes `#ae1800`. Fold hovers to accent border + accent label. No transitions longer than 120ms; no easing flourishes — the system is flat.
- **Focus**: `:focus-visible { outline: 2px solid #ff563c; outline-offset: 2px; }` on every interactive element. Never the browser default.
- **Selection rings** are `inset 0 0 0 2px`, never an outer glow or shadow.
- **Loading**: the solve progress bar is the only spinner-equivalent; while stats are loading, show the table skeleton rows at `#605d5d` rather than a spinner.
- **Empty**: zero-hand tiers stay in the table as dim rows with `—`, matching current behaviour.
- **Responsive**: below ~1200px the right rail should drop under the table column; the range grid scrolls horizontally rather than shrinking cells below 26px.

## State

No new state beyond what `HandBuilderPage.tsx` already holds. The solver view needs: the walked `TreePathStep[]`, the selected combo (default = hero's actual hole cards), the selected street/node, and the EV deltas for the user's line, which can be derived by evaluating the user's chosen actions against the solved strategy at each node.

## Assets

None. Card suits are Unicode glyphs (`♠ ♥ ♦ ♣`). Icons, if added, should come from Lucide per the Modernist guide.

## Files in this bundle

- `Poker Flow.dc.html` — the design reference (options `1a`, `1b`, `1c`; build `1b` and `1c`).
- `support.js` — runtime needed to open the HTML file in a browser. Not part of the implementation.
- `screenshots/1b-hand-builder.png` — screen 1 as rendered (2× scale).
- `screenshots/1c-solver-view.png` — screen 2 as rendered (2× scale).
