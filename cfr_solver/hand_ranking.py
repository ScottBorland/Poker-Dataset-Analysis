"""hand_ranking.py — Standard preflop starting-hand ranking via the Chen
Formula (Bill Chen, published in "The Mathematics of Poker"), used to turn a
position's range percentage (src/range_charts.py's OPEN_RAISE_PCT /
DEFEND_VS_RAISE_PCT) into an actual set of canonical starting hands, so the
CFR solver can deal each player's hole cards from a realistic range instead
of uniformly over the full deck.

The Chen formula:
  1. Score the higher card: A=10, K=8, Q=7, J=6, T=5, 9..2 = rank/2.
  2. Pairs: double the single-card score (minimum 5).
  3. Suited: +2.
  4. Gap penalty (non-pairs): 0-gap -0, 1-gap -1, 2-gap -2, 3-gap -4, 4+ -5.
  5. Straight bonus: +1 if gap <= 1 and the higher card is below a Queen.
  6. Round up to the nearest half point.
"""

from __future__ import annotations

import math

RANKS = 'AKQJT98765432'
SUITS = 'hdcs'
_RANK_VALUE = {
    'A': 10, 'K': 8, 'Q': 7, 'J': 6, 'T': 5,
    '9': 4.5, '8': 4, '7': 3.5, '6': 3, '5': 2.5, '4': 2, '3': 1.5, '2': 1,
}
# 0 = best (A) .. 12 = worst (2)
_RANK_ORDER = {r: i for i, r in enumerate(RANKS)}


def canonical_hands() -> list[str]:
    """All 169 canonical starting hands, e.g. 'AA', 'AKs', 'AKo', ..., '32o'."""
    hands: list[str] = []
    for i, r1 in enumerate(RANKS):
        for j, r2 in enumerate(RANKS):
            if i > j:
                continue
            if i == j:
                hands.append(r1 + r2)
            else:
                hands.append(r1 + r2 + 's')
                hands.append(r1 + r2 + 'o')
    return hands


def chen_score(hand: str) -> float:
    r1, r2 = hand[0], hand[1]
    pair = r1 == r2
    suited = len(hand) == 3 and hand[2] == 's'

    hi, lo = (r1, r2) if _RANK_ORDER[r1] <= _RANK_ORDER[r2] else (r2, r1)
    score = _RANK_VALUE[hi]

    if pair:
        score = max(score * 2, 5)
    if suited:
        score += 2

    if not pair:
        gap = _RANK_ORDER[lo] - _RANK_ORDER[hi] - 1
        if gap == 1:
            score -= 1
        elif gap == 2:
            score -= 2
        elif gap == 3:
            score -= 4
        elif gap >= 4:
            score -= 5
        if gap <= 1 and _RANK_ORDER[hi] > _RANK_ORDER['Q']:
            score += 1

    return math.ceil(score * 2) / 2


def ranked_hands() -> list[str]:
    """All 169 canonical hands sorted best-to-worst by Chen score.

    Ties are broken by a fixed, deterministic secondary key (the hand string
    itself) purely so the ordering is stable/reproducible — Chen doesn't
    define a tie-break, and this project's ranges are illustrative
    approximations, not a claim that the tie order itself is meaningful.
    """
    return sorted(canonical_hands(), key=lambda h: (-chen_score(h), h))


def top_pct_hands(pct: float) -> set[str]:
    """Canonical hands making up the top `pct` percent of hands by Chen score
    (e.g. pct=14 -> UTG's ~14% opening range)."""
    ranked = ranked_hands()
    n = max(1, round(len(ranked) * pct / 100))
    return set(ranked[:n])


def expand_to_combos(hand: str) -> list[tuple[str, str]]:
    """'AKs' -> the 4 suited combos, 'AKo' -> the 12 offsuit combos,
    'AA' -> the 6 pair combos. Card order within each tuple is arbitrary."""
    r1, r2 = hand[0], hand[1]
    if r1 == r2:
        return [(r1 + SUITS[i], r1 + SUITS[j]) for i in range(4) for j in range(i + 1, 4)]
    if hand.endswith('s'):
        return [(r1 + s, r2 + s) for s in SUITS]
    return [(r1 + s1, r2 + s2) for s1 in SUITS for s2 in SUITS if s1 != s2]


def range_combos(pct: float) -> list[tuple[str, str]]:
    """All raw 2-card combos making up the top `pct` percent of starting hands."""
    combos: list[tuple[str, str]] = []
    for hand in top_pct_hands(pct):
        combos.extend(expand_to_combos(hand))
    return combos
