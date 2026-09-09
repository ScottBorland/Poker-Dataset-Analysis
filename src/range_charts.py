"""range_charts.py — Static, hand-coded preflop range percentages.

v1 range model (per the plan): a simple static chart, not empirically
calibrated from this dataset's VPIP/PFR stats.

These percentages ARE fed into the CFR solver as a soft constraint: each
spot spec's `ranges` block (built by `infer_spot_roles`) tells
cfr_solver/game_def.py what percentage of hands (by Chen-formula rank, see
cfr_solver/hand_ranking.py) each seat is dealt from, instead of the full
uniform deck. See infer_spot_roles()'s docstring for how a spot's two named
positions get mapped to (a) which one is OOP/IP — needed because postflop
seating order is NOT the same as preflop "position" — and (b) which
percentage chart applies to each, given the preflop pot type.

Percentages are illustrative, standard-ish 100bb 6-max approximations —
not derived from this dataset. Good enough for a sniff test; not a claim
of precision.
"""

from __future__ import annotations

from typing import Optional

# Mirrors src/fingerprint.py's POSITION_RANK — higher rank acts later
# postflop (BTN always last; the blinds act first, then the field in
# preflop-position order). Duplicated here (rather than imported) since
# it's a tiny, stable constant and range_charts.py is meant to stay a
# light, dependency-free module.
_POSITION_RANK: dict[str, int] = {'BTN': 6, 'CO': 5, 'HJ': 4, 'UTG': 3, 'SB': 2, 'BB': 1}
_BLINDS = {'SB', 'BB'}

# % of hands opened first-in, by position (6-max, ~100bb).
OPEN_RAISE_PCT: dict[str, float] = {
    'UTG': 14,
    'HJ': 18,
    'CO': 26,
    'BTN': 45,
    'SB': 35,   # SB raise-first-in over folded BTN
}

# % of hands defended (call or 3bet) facing a single open-raise, by position.
DEFEND_VS_RAISE_PCT: dict[str, float] = {
    'BB': 60,
    'SB': 25,
    'BTN': 30,
    'CO': 15,
    'HJ': 12,
    'UTG': 10,
}

# % of hands continuing (call or 4bet) facing a 3bet, by position.
DEFEND_VS_3BET_PCT: dict[str, float] = {
    'BB': 35,
    'SB': 20,
    'BTN': 25,
    'CO': 15,
    'HJ': 12,
    'UTG': 10,
}

# % of hands that limp/over-limp into an unraised pot, by position. Wider
# than open-raising ranges (limping selects for speculative hands) and very
# wide in the blinds (SB completes cheaply, BB checks everything).
LIMP_PCT: dict[str, float] = {
    'UTG': 20,
    'HJ': 24,
    'CO': 30,
    'BTN': 40,
    'SB': 55,
    'BB': 90,
}

# % of hands 3-betting against a single open-raise, by position.
THREEBET_PCT: dict[str, float] = {
    'UTG': 5,
    'HJ': 6,
    'CO': 7,
    'BTN': 9,
    'SB': 8,
    'BB': 8,
}

# 4bet-pot ranges: the 4bettor's range and the caller's continue range are
# both very tight regardless of position.
FOURBET_PCT: float = 4
DEFEND_VS_4BET_PCT: float = 6

_POT_TYPE_CHARTS = {
    'unopened': OPEN_RAISE_PCT,
    'facing_raise': DEFEND_VS_RAISE_PCT,
    'facing_3bet': DEFEND_VS_3BET_PCT,
}


def get_range_pct(position: str, facing: str) -> Optional[float]:
    """Look up the static range percentage for a position given what they're facing.

    `facing` should be a fingerprint `facing`/`pot_type`-style value: one of
    'unopened' (opening), 'facing_raise' (defending vs open), 'facing_3bet'
    (defending vs 3bet). Returns None if there's no chart entry.
    """
    chart = _POT_TYPE_CHARTS.get(facing)
    if chart is None:
        return None
    return chart.get(position)


# Preflop acting order (earlier = acts first preflop): UTG..BTN, then blinds
# already posted so SB/BB act LAST preflop. Used to infer who the preflop
# aggressor was when neither/both seats are blinds.
_PREFLOP_ORDER = {'UTG': 0, 'HJ': 1, 'CO': 2, 'BTN': 3, 'SB': 4, 'BB': 5}


def _infer_aggressor(pos_x: str, pos_y: str) -> tuple[str, str]:
    """(aggressor, caller) for a raised pot between two positions.

    Approximation: exactly one blind → the non-blind raised, the blind
    defended. Neither a blind → the earlier preflop position opened, the
    later one called. Both blinds → SB is the aggressor (SB raise / BB
    defend is the dominant blind-vs-blind raised line).
    """
    x_blind, y_blind = pos_x in _BLINDS, pos_y in _BLINDS
    if x_blind and not y_blind:
        return pos_y, pos_x
    if y_blind and not x_blind:
        return pos_x, pos_y
    if x_blind and y_blind:
        return ('SB', 'BB') if pos_x == 'BB' else (pos_x, pos_y)
    # Neither a blind: earlier preflop position opened.
    return (pos_x, pos_y) if _PREFLOP_ORDER[pos_x] < _PREFLOP_ORDER[pos_y] else (pos_y, pos_x)


def infer_spot_roles(positions: str, pot_type: Optional[str]) -> Optional[dict]:
    """Build the `ranges` block for a spot spec, given e.g. positions='UTG_vs_BB'.

    Two things are inferred that are NOT explicit in a fingerprint's
    `positions` string:

    1. Which named position is OOP vs IP *postflop*. This is NOT the same
       as preflop "position" — postflop action starts left of the button,
       so e.g. UTG acts AFTER BB heads-up. Determined via _POSITION_RANK
       (mirrors src/fingerprint.py's in_position logic): lower rank = OOP.

    2. Who the preflop aggressor was (see _infer_aggressor) — a documented
       approximation covering every matchup, including non-blind pairs
       (earlier position opened) and blind-vs-blind (SB opened).

    Charts by pot type:
      unopened/limped → LIMP_PCT both seats (no aggressor asymmetry)
      srp             → OPEN_RAISE_PCT aggressor / DEFEND_VS_RAISE_PCT caller
      3bet            → THREEBET_PCT 3bettor / DEFEND_VS_3BET_PCT caller
                        (in a 3bet pot the preflop CALLER of the 3bet is the
                        original opener; the 3bettor is the srp defender —
                        so the aggressor/caller roles are swapped vs srp)
      4bet/5bet+      → flat tight percentages both seats

    Always returns a ranges dict for a recognized 'X_vs_Y' positions string;
    None only for unparseable/multiway positions.

    Returns e.g. {'oop': {'position': 'BB', 'range_pct': 60},
                   'ip': {'position': 'UTG', 'range_pct': 14}}.
    """
    parts = positions.split('_vs_') if '_vs_' in positions else []
    if len(parts) != 2:
        return None
    a, b = parts
    rank_a, rank_b = _POSITION_RANK.get(a), _POSITION_RANK.get(b)
    if rank_a is None or rank_b is None:
        return None
    oop_pos, ip_pos = (a, b) if rank_a < rank_b else (b, a)

    if pot_type in ('unopened', 'limped', None):
        pct_by_pos = {
            oop_pos: LIMP_PCT.get(oop_pos, 40),
            ip_pos: LIMP_PCT.get(ip_pos, 40),
        }
    elif pot_type == 'srp':
        opener, defender = _infer_aggressor(oop_pos, ip_pos)
        pct_by_pos = {
            opener: OPEN_RAISE_PCT.get(opener, DEFEND_VS_RAISE_PCT.get(opener, 25)),
            defender: DEFEND_VS_RAISE_PCT.get(defender, 25),
        }
    elif pot_type == '3bet':
        # The srp "defender" seat is the 3bettor; the original opener calls.
        opener, threebettor = _infer_aggressor(oop_pos, ip_pos)
        pct_by_pos = {
            threebettor: THREEBET_PCT.get(threebettor, 7),
            opener: DEFEND_VS_3BET_PCT.get(opener, 15),
        }
    else:  # 4bet / 5bet+
        opener, defender = _infer_aggressor(oop_pos, ip_pos)
        pct_by_pos = {opener: FOURBET_PCT, defender: DEFEND_VS_4BET_PCT}

    return {
        'oop': {'position': oop_pos, 'range_pct': pct_by_pos[oop_pos]},
        'ip': {'position': ip_pos, 'range_pct': pct_by_pos[ip_pos]},
    }
