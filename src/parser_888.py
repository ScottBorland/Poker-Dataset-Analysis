"""
parser_888.py — Parse 888poker plain-text hand history files into Hand dataclasses.

Hand IDs are stored as HAND_ID_888_OFFSET + game_number to avoid collisions with
Absolute Poker hand IDs in the same database.

Action lines are converted to the same format used by .phhs files so all downstream
code (hand_utils, labeller) works without modification:
    pN f          fold
    pN cc         call or check
    pN cbr X.XX   bet or raise TO X.XX (total this street)
    d dh pN XrYr  hole cards dealt
    d db XrYr...  board cards dealt
    pN sm XrYr    showdown cards shown
"""

from __future__ import annotations

import re
from pathlib import Path

from parser import Hand

HAND_ID_888_OFFSET = 1_000_000_000_000

# Patterns compiled once
_RE_GAME_NO    = re.compile(r'#Game No\s*:\s*(\d+)')
_RE_BLINDS     = re.compile(r'\$([0-9.]+)/\$([0-9.]+)\s+Blinds')
_RE_DATETIME   = re.compile(r'\*\*\*\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+:\d+:\d+)')
_RE_TABLE      = re.compile(r'Table\s+(\S+)')
_RE_BUTTON     = re.compile(r'Seat\s+(\d+)\s+is\s+the\s+button')
_RE_N_PLAYERS  = re.compile(r'Total number of players\s*:\s*(\d+)')
_RE_SEAT       = re.compile(r'Seat\s+(\d+):\s+(\S+)\s+\(\s+\$([0-9.]+)\s+\)')
_RE_SB_POST    = re.compile(r'(\S+)\s+posts\s+small\s+blind')
_RE_BB_POST    = re.compile(r'(\S+)\s+posts\s+big\s+blind')
_RE_DEALT      = re.compile(r'Dealt\s+to\s+(\S+)\s+\[\s+(.+?)\s+\]')
_RE_FLOP       = re.compile(r'\*\* Dealing flop \*\*\s+\[\s+(.+?)\s+\]')
_RE_TURN       = re.compile(r'\*\* Dealing turn \*\*\s+\[\s+(.+?)\s+\]')
_RE_RIVER      = re.compile(r'\*\* Dealing river \*\*\s+\[\s+(.+?)\s+\]')
_RE_FOLD       = re.compile(r'(\S+)\s+folds')
_RE_CHECK      = re.compile(r'(\S+)\s+checks')
_RE_CALL       = re.compile(r'(\S+)\s+calls\s+\[\$([0-9.]+)\]')
_RE_RAISE      = re.compile(r'(\S+)\s+raises\s+\[\$([0-9.]+)\]')
_RE_BET        = re.compile(r'(\S+)\s+bets\s+\[\$([0-9.]+)\]')
_RE_SHOWS      = re.compile(r'(\S+)\s+shows\s+\[\s+(.+?)\s+\]')
_RE_COLLECTED  = re.compile(r'(\S+)\s+collected\s+\[\s+\$([0-9.]+)\s+\]')


def _cards(raw: str) -> str:
    """Convert '7d, 2s, 7h' → '7d2s7h'."""
    return raw.replace(', ', '').replace(' ', '')


def _parse_hand(block: str, filename: str) -> Hand | None:
    lines = [l.rstrip() for l in block.splitlines()]
    lines = [l for l in lines if l.strip()]
    if not lines:
        return None

    game_no_m = _RE_GAME_NO.search(lines[0])
    if not game_no_m:
        return None
    hand_id = HAND_ID_888_OFFSET + int(game_no_m.group(1))

    sb_blind = bb_blind = 0.0
    day = month = year = 0
    time_str = ''
    table = ''
    button_seat = -1
    seat_data: dict[int, tuple[str, float]] = {}
    name_to_idx: dict[str, int] = {}

    actions: list[str] = []
    winnings_map: dict[int, float] = {}
    in_summary = False
    skip_runout = False   # True after ** Second runout ** — ignore duplicate boards
    n = 0

    for line in lines[1:]:
        # --- Summary section ---
        if line.strip() == '** Summary **':
            in_summary = True
            continue

        if in_summary:
            m = _RE_SHOWS.search(line)
            if m:
                pidx = name_to_idx.get(m.group(1))
                if pidx:
                    actions.append(f'p{pidx} sm {_cards(m.group(2))}')
            m = _RE_COLLECTED.search(line)
            if m:
                pidx = name_to_idx.get(m.group(1))
                if pidx:
                    winnings_map[pidx] = winnings_map.get(pidx, 0.0) + float(m.group(2))
            continue

        # --- Header lines (before action starts) ---
        if not name_to_idx:
            m = _RE_BLINDS.search(line)
            if m:
                sb_blind, bb_blind = float(m.group(1)), float(m.group(2))
                dt_m = _RE_DATETIME.search(line)
                if dt_m:
                    day = int(dt_m.group(1))
                    month = int(dt_m.group(2))
                    year = int(dt_m.group(3))
                    time_str = dt_m.group(4)
                continue

            m = _RE_TABLE.match(line)
            if m:
                table = m.group(1)
                continue

            m = _RE_BUTTON.search(line)
            if m:
                button_seat = int(m.group(1))
                continue

            m = _RE_N_PLAYERS.search(line)
            if m:
                continue  # n_players derived from seat_data

            m = _RE_SEAT.match(line)
            if m:
                seat_data[int(m.group(1))] = (m.group(2), float(m.group(3)))
                continue

            # Build name→idx once we see blind posts (seat_data now complete)
            if seat_data and button_seat != -1 and _RE_SB_POST.match(line):
                sorted_seats = sorted(seat_data)
                if button_seat not in sorted_seats:
                    return None
                btn_idx = sorted_seats.index(button_seat)
                start = (btn_idx + 1) % len(sorted_seats)
                rotated = sorted_seats[start:] + sorted_seats[:start]
                players_ordered = [seat_data[s][0] for s in rotated]
                name_to_idx = {name: i + 1 for i, name in enumerate(players_ordered)}
                n = len(players_ordered)
            continue  # skip blind post / other header lines before name_to_idx is built

        # Skip meta lines once in action section
        if _RE_SB_POST.match(line) or _RE_BB_POST.match(line):
            continue
        if 'posts ante' in line:
            continue
        if line == '** Dealing down cards **' or line == '** First runout **':
            continue
        if line == '** Second runout **':
            skip_runout = True
            continue

        # Hole cards
        m = _RE_DEALT.match(line)
        if m:
            pidx = name_to_idx.get(m.group(1))
            if pidx:
                actions.append(f'd dh p{pidx} {_cards(m.group(2))}')
            continue

        # Board cards (skip second runout to avoid duplicate d db actions)
        m = _RE_FLOP.match(line)
        if m:
            if not skip_runout:
                actions.append(f'd db {_cards(m.group(1))}')
            continue
        m = _RE_TURN.match(line)
        if m:
            if not skip_runout:
                actions.append(f'd db {_cards(m.group(1))}')
            continue
        m = _RE_RIVER.match(line)
        if m:
            if not skip_runout:
                actions.append(f'd db {_cards(m.group(1))}')
            continue

        # Folds, checks, calls
        m = _RE_FOLD.match(line)
        if m:
            pidx = name_to_idx.get(m.group(1))
            if pidx:
                actions.append(f'p{pidx} f')
            continue

        m = _RE_CHECK.match(line)
        if m:
            pidx = name_to_idx.get(m.group(1))
            if pidx:
                actions.append(f'p{pidx} cc')
            continue

        m = _RE_CALL.match(line)
        if m:
            pidx = name_to_idx.get(m.group(1))
            if pidx:
                actions.append(f'p{pidx} cc')
            continue

        # raises [$X] = raise TO X total (same semantics as phhs cbr)
        m = _RE_RAISE.match(line)
        if m:
            pidx = name_to_idx.get(m.group(1))
            if pidx:
                actions.append(f'p{pidx} cbr {float(m.group(2)):.2f}')
            continue

        # bets [$X] = first bet this street (total = X since no prior bet)
        m = _RE_BET.match(line)
        if m:
            pidx = name_to_idx.get(m.group(1))
            if pidx:
                actions.append(f'p{pidx} cbr {float(m.group(2)):.2f}')
            continue

    if not name_to_idx or n == 0:
        return None

    sorted_seats = sorted(seat_data)
    btn_idx = sorted_seats.index(button_seat) if button_seat in sorted_seats else 0
    start = (btn_idx + 1) % len(sorted_seats)
    rotated = sorted_seats[start:] + sorted_seats[:start]
    players = [seat_data[s][0] for s in rotated]
    starting_stacks = [seat_data[s][1] for s in rotated]
    blinds_or_straddles = [sb_blind, bb_blind] + [0.0] * (n - 2)
    winnings = [winnings_map.get(i + 1, 0.0) for i in range(n)]
    has_winnings = any(w > 0.0 for w in winnings)

    return Hand(
        hand_id=hand_id,
        file=filename,
        variant='NT',
        ante_trimming_status=False,
        antes=[0.0] * n,
        blinds_or_straddles=blinds_or_straddles,
        min_bet=bb_blind,
        starting_stacks=starting_stacks,
        actions=actions,
        venue='888poker',
        time=time_str,
        day=day,
        month=month,
        year=year,
        seats=rotated,
        table=table,
        players=players,
        winnings=winnings if has_winnings else None,
        currency_symbol='$',
        time_zone_abbreviation='',
    )


def load_file_888(path: str | Path) -> list[Hand]:
    """Parse all hands from a single 888poker .txt hand history file."""
    path = Path(path)
    text = path.read_text(encoding='utf-8', errors='replace')

    # Split on hand boundaries — each hand starts with "#Game No"
    raw_blocks = re.split(r'(?=#Game No\s*:)', text)

    hands: list[Hand] = []
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
        try:
            hand = _parse_hand(block, path.name)
            if hand is not None:
                hands.append(hand)
        except Exception as exc:
            first_line = block.splitlines()[0] if block else ''
            print(f'[parser_888] Skipping malformed hand in {path.name}: {exc} ({first_line!r})')

    return hands
