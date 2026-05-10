"""
player_analysis.py — Per-player analysis on in-memory Hand objects.

Complements scripts.py (which queries poker.db) by working directly on a
list[Hand] loaded from .phhs files — no database required.

Usage:
    import sys; sys.path.insert(0, 'src')
    from parser import load_file
    from player_analysis import find_players, get_player_hands, player_stats, player_summary_df

    hands = load_file("abs NLH handhq_1-OBFUSCATED.phhs")

    # Who is in these hands?
    print(find_players(hands))

    # Filter to one player
    ph = get_player_hands(hands, player_id)   # → list[(Hand, seat_1based)]

    # Aggregate stats
    stats = player_stats(hands, player_id)
    print(stats)

    # Hand-by-hand breakdown
    df = player_summary_df(hands, player_id)
    print(df.head())
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from hand_utils import (
    assign_positions,
    compute_investments,
    compute_vpip_pfr,
    count_preflop_raises,
    final_pot,
    players_who_saw_flop,
)

if TYPE_CHECKING:
    from parser import Hand


# ---------------------------------------------------------------------------
# Player lookup helpers
# ---------------------------------------------------------------------------

def find_players(hands: list[Hand], partial: str = '') -> list[str]:
    """
    Return all unique player IDs present in *hands*, sorted.
    Pass *partial* to filter by a case-insensitive substring.
    """
    seen: set[str] = set()
    needle = partial.lower()
    for hand in hands:
        for pid in hand.players:
            if needle in pid.lower():
                seen.add(pid)
    return sorted(seen)


def get_player_hands(hands: list[Hand], player_id: str) -> list[tuple[Hand, int]]:
    """
    Return (hand, seat) for every hand in *hands* where *player_id* is seated.
    *seat* is 1-based and matches the pN notation used in actions.
    """
    result = []
    for hand in hands:
        if player_id in hand.players:
            seat = hand.players.index(player_id) + 1
            result.append((hand, seat))
    return result


def _player_at_showdown(hand: Hand, seat: int) -> bool:
    """True if this player showed their cards (explicit sm action)."""
    prefix = f'p{seat} sm'
    return any(a.startswith(prefix) for a in hand.actions)


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------

def player_stats(hands: list[Hand], player_id: str) -> dict:
    """
    Aggregate stats for one player across all hands in *hands*.

    Returned keys:
        player_id, hands_played,
        vpip_pct, pfr_pct, flop_seen_pct, showdown_pct,
        net_won, bb_per_100, avg_bb_size,
        positions  (dict: position → hand count)
    """
    player_hands = get_player_hands(hands, player_id)
    n = len(player_hands)
    if not n:
        return {}

    vpip_count = pfr_count = flop_count = sd_count = 0
    net_won_total = 0.0
    total_bb = 0.0
    positions_count: dict[str, int] = {}

    for hand, seat in player_hands:
        pidx = seat - 1

        # VPIP / PFR
        vp_pfr = compute_vpip_pfr(hand)
        if pidx < len(vp_pfr):
            v, p = vp_pfr[pidx]
            vpip_count += v
            pfr_count += p

        # Flop
        if seat in players_who_saw_flop(hand):
            flop_count += 1

        # Showdown (player-specific)
        if _player_at_showdown(hand, seat):
            sd_count += 1

        # Net P&L: gross receipts minus total invested
        invested_list = compute_investments(hand)
        invested = invested_list[pidx] if pidx < len(invested_list) else 0.0
        gross = (hand.winnings[pidx]
                 if hand.winnings and pidx < len(hand.winnings) else 0.0)
        net_won_total += gross - invested

        # BB size for BB/100 denominator
        bb = (hand.blinds_or_straddles[1]
              if len(hand.blinds_or_straddles) > 1 else 1.0)
        total_bb += bb

        # Position
        pos = assign_positions(hand).get(seat, f'p{seat}')
        positions_count[pos] = positions_count.get(pos, 0) + 1

    return {
        'player_id':     player_id,
        'hands_played':  n,
        'vpip_pct':      round(vpip_count / n * 100, 1),
        'pfr_pct':       round(pfr_count / n * 100, 1),
        'flop_seen_pct': round(flop_count / n * 100, 1),
        'showdown_pct':  round(sd_count / n * 100, 1),
        'net_won':       round(net_won_total, 2),
        'bb_per_100':    round(net_won_total / total_bb * 100, 2) if total_bb else 0.0,
        'avg_bb_size':   round(total_bb / n, 2),
        'positions':     positions_count,
    }


# ---------------------------------------------------------------------------
# Per-hand breakdown
# ---------------------------------------------------------------------------

def player_summary_df(hands: list[Hand], player_id: str) -> pd.DataFrame:
    """
    Return a DataFrame with one row per hand the player appeared in.

    Columns:
        hand_id, date, table, n_players, seat, position,
        stack, invested, gross_winnings, net_won,
        vpip, pfr, saw_flop, at_showdown,
        n_preflop_raises, pot_final
    """
    rows = []
    for hand, seat in get_player_hands(hands, player_id):
        pidx = seat - 1

        pos = assign_positions(hand).get(seat, f'p{seat}')

        vp_pfr = compute_vpip_pfr(hand)
        vpip, pfr = vp_pfr[pidx] if pidx < len(vp_pfr) else (False, False)

        invested_list = compute_investments(hand)
        invested = invested_list[pidx] if pidx < len(invested_list) else 0.0

        gross = (hand.winnings[pidx]
                 if hand.winnings and pidx < len(hand.winnings) else None)

        stack = (hand.starting_stacks[pidx]
                 if pidx < len(hand.starting_stacks) else None)

        rows.append({
            'hand_id':           hand.hand_id,
            'date':              hand.date_str,
            'table':             hand.table,
            'n_players':         hand.n_players,
            'seat':              seat,
            'position':          pos,
            'stack':             round(stack, 2) if stack is not None else None,
            'invested':          round(invested, 2),
            'gross_winnings':    round(gross, 2) if gross is not None else None,
            'net_won':           round(gross - invested, 2) if gross is not None else None,
            'vpip':              vpip,
            'pfr':               pfr,
            'saw_flop':          seat in players_who_saw_flop(hand),
            'at_showdown':       _player_at_showdown(hand, seat),
            'n_preflop_raises':  count_preflop_raises(hand),
            'pot_final':         round(final_pot(hand), 2),
        })

    return pd.DataFrame(rows)
