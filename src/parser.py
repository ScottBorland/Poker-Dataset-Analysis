"""
parser.py — Load .phhs hand history files into Hand dataclasses.

Usage:
    from parser import load_file, load_directory

    hands = load_file("data/abs NLH handhq_1-OBFUSCATED.phhs")
    all_hands = load_directory("data/")
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Hand:
    hand_id: int
    file: str                          # source filename (stem)
    variant: str
    ante_trimming_status: bool
    antes: list[float]
    blinds_or_straddles: list[float]
    min_bet: float
    starting_stacks: list[float]
    actions: list[str]
    venue: str
    time: str
    day: int
    month: int
    year: int
    seats: list[int]
    table: str
    players: list[str]
    winnings: list[float] | None       # may be absent
    currency_symbol: str
    time_zone_abbreviation: str

    @property
    def n_players(self) -> int:
        return len(self.players)

    @property
    def date_str(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

# Matches a section header like [1], [42], etc.
_SECTION_RE = re.compile(r'^\[(\d+)\]\s*$')


def _parse_value(raw: str):
    """
    Convert a raw string value from the .phhs format to a Python object.
    Handles: bool literals, lists, quoted strings, ints, floats.
    """
    raw = raw.strip()

    # Boolean literals (lowercase in the file)
    if raw == 'true':
        return True
    if raw == 'false':
        return False

    # Try ast.literal_eval for lists and quoted strings
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        pass

    # Bare time value like 00:00:01
    return raw


def _parse_block(lines: list[str], source_file: str) -> Hand | None:
    """Parse a single key=value block into a Hand. Returns None on failure."""
    kv: dict = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith('['):
            continue
        if '=' not in line:
            continue
        key, _, rest = line.partition('=')
        kv[key.strip()] = _parse_value(rest.strip())

    if not kv:
        return None

    try:
        return Hand(
            hand_id=int(kv['hand']),
            file=source_file,
            variant=kv.get('variant', 'NT'),
            ante_trimming_status=bool(kv.get('ante_trimming_status', False)),
            antes=[float(x) for x in kv.get('antes', [])],
            blinds_or_straddles=[float(x) for x in kv.get('blinds_or_straddles', [])],
            min_bet=float(kv.get('min_bet', 0.0)),
            starting_stacks=[float(x) for x in kv.get('starting_stacks', [])],
            actions=list(kv.get('actions', [])),
            venue=kv.get('venue', ''),
            time=str(kv.get('time', '')),
            day=int(kv.get('day', 0)),
            month=int(kv.get('month', 0)),
            year=int(kv.get('year', 0)),
            seats=[int(x) for x in kv.get('seats', [])],
            table=kv.get('table', ''),
            players=list(kv.get('players', [])),
            winnings=[float(x) for x in kv['winnings']] if 'winnings' in kv else None,
            currency_symbol=kv.get('currency_symbol', '$'),
            time_zone_abbreviation=kv.get('time_zone_abbreviation', 'ET'),
        )
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[parser] Skipping malformed hand in {source_file}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _iter_blocks(path: Path) -> Iterator[list[str]]:
    """Yield raw line-lists for each [N] section in a .phhs file."""
    current: list[str] = []
    with path.open(encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if _SECTION_RE.match(line):
                if current:
                    yield current
                current = [line]
            else:
                current.append(line)
    if current:
        yield current


def load_file(path: str | Path) -> list[Hand]:
    """Parse all hands from a single .phhs file."""
    path = Path(path)
    hands: list[Hand] = []
    for block in _iter_blocks(path):
        hand = _parse_block(block, path.name)
        if hand is not None:
            hands.append(hand)
    return hands


def load_directory(directory: str | Path, pattern: str = "*.phhs") -> list[Hand]:
    """Parse all .phhs files in a directory (non-recursive by default)."""
    directory = Path(directory)
    all_hands: list[Hand] = []
    for p in sorted(directory.glob(pattern)):
        file_hands = load_file(p)
        print(f"[parser] {p.name}: loaded {len(file_hands)} hands")
        all_hands.extend(file_hands)
    return all_hands


# ---------------------------------------------------------------------------
# CLI quick-check
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else '.'
    p = Path(target)
    if p.is_file():
        hands = load_file(p)
    else:
        hands = load_directory(p)

    print(f"\nTotal hands loaded: {len(hands)}")
    if hands:
        h = hands[0]
        print(f"First hand id={h.hand_id}  table={h.table!r}  players={h.n_players}  date={h.date_str}")
        print(f"  actions ({len(h.actions)}): {h.actions[:6]} ...")
