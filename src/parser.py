"""
parser.py — Load .phhs hand history files into Hand dataclasses.

Uses pokerkit's HandHistory.load_all() (Absolute Poker format) as the parsing
backend. The Hand dataclass is preserved for downstream compatibility.

Usage:
    from parser import load_file, load_directory

    hands = load_file("data/abs NLH handhq_1-OBFUSCATED.phhs")
    all_hands = load_directory("data/")
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

from pokerkit import HandHistory


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
# Conversion helper
# ---------------------------------------------------------------------------

def _hh_to_hand(hh: HandHistory, source_file: str) -> Hand:
    """Map a pokerkit HandHistory to our Hand dataclass."""
    udf = hh.user_defined_fields or {}
    return Hand(
        hand_id=hh.hand,
        file=source_file,
        variant=hh.variant or 'NT',
        ante_trimming_status=bool(hh.ante_trimming_status),
        antes=[float(a) for a in hh.antes] if hh.antes else [],
        blinds_or_straddles=[float(b) for b in hh.blinds_or_straddles] if hh.blinds_or_straddles else [],
        min_bet=float(hh.min_bet) if hh.min_bet is not None else 0.0,
        starting_stacks=[float(s) for s in hh.starting_stacks] if hh.starting_stacks else [],
        actions=list(hh.actions) if hh.actions else [],
        venue=hh.venue or '',
        time=str(hh.time) if hh.time is not None else '',
        day=hh.day or 0,
        month=hh.month or 0,
        year=hh.year or 0,
        seats=[int(s) for s in hh.seats] if hh.seats else [],
        table=hh.table or '',
        players=list(hh.players) if hh.players else [],
        winnings=[float(w) for w in hh.winnings] if hh.winnings else None,
        currency_symbol=hh.currency_symbol or '$',
        time_zone_abbreviation=udf.get('time_zone_abbreviation', 'ET'),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_file(path: str | Path) -> list[Hand]:
    """Parse all hands from a single .phhs file using pokerkit."""
    path = Path(path)
    # Suppress pokerkit warnings for unknown fields and benign state warnings
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=UserWarning, module='pokerkit')
        with path.open('rb') as fh:
            hh_list = list(HandHistory.load_all(fh))

    hands: list[Hand] = []
    for hh in hh_list:
        try:
            hands.append(_hh_to_hand(hh, path.name))
        except Exception as exc:
            print(f"[parser] Skipping malformed hand in {path.name}: {exc}")
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
