"""
player_main.py — Player-filtered hand replayer.

Loads hands from a .phhs file, filters to those containing a chosen player,
and opens a step-through replayer.  The player's seat is highlighted in teal.
A strip at the top shows aggregate stats and hand-navigation buttons.

Usage (CLI):
    python src/replayer/player_main.py --file "abs NLH handhq_1-OBFUSCATED.phhs" --player Qt5Yyd/Y121jtIk37c7TSg
    python src/replayer/player_main.py --file "..." --list-players
    python src/replayer/player_main.py --file "..." --search "Qt5"   # search player IDs

Usage (programmatic):
    import sys; sys.path.insert(0, 'src')
    from parser import load_file
    from replayer.player_main import replay_player

    hands = load_file("abs NLH handhq_1-OBFUSCATED.phhs")
    replay_player(hands, player_id="Qt5Yyd/Y121jtIk37c7TSg")

Keyboard controls:
    Right / Space  — next action
    Left           — previous action
    R              — reset to start of hand
    N              — next player hand
    P              — previous player hand
    Q / Escape     — quit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).parent.parent
sys.path.insert(0, str(_SRC))

import pygame

from parser import Hand, load_file, load_directory
from hand_utils import assign_positions
from player_analysis import find_players, get_player_hands, player_stats
from replayer.state import ReplaySession
from replayer.renderer import (
    Renderer, _font,
    BG, PANEL_BG, TEXT_MAIN, TEXT_DIM,
    BTN_NORMAL, BTN_HOVER, BTN_TEXT, PLAYER_HL,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_W = 1000
WINDOW_H = 720
STRIP_H  = 40
FPS      = 60

_HB_W = 95   # hand-nav button width
_HB_H = 26   # hand-nav button height


# ---------------------------------------------------------------------------
# Strip drawing
# ---------------------------------------------------------------------------

def _draw_strip(
    surf: pygame.Surface,
    player_id: str,
    hand: Hand,
    seat: int,
    hand_idx: int,
    total_hands: int,
    stats: dict,
    fonts: dict,
    btn_prev: pygame.Rect,
    btn_next: pygame.Rect,
    mouse_pos: tuple[int, int],
) -> None:
    """Draw the player-info strip at the top of *surf* (full screen width)."""
    W = surf.get_width()
    cy = STRIP_H // 2

    # Background + bottom divider
    pygame.draw.rect(surf, PANEL_BG, (0, 0, W, STRIP_H))
    pygame.draw.line(surf, (70, 70, 70), (0, STRIP_H - 1), (W, STRIP_H - 1))

    # ── Hand-nav buttons ────────────────────────────────────────────────────
    for btn, label in ((btn_prev, '◀ Prev Hand'), (btn_next, 'Next Hand ▶')):
        color = BTN_HOVER if btn.collidepoint(mouse_pos) else BTN_NORMAL
        pygame.draw.rect(surf, color, btn, border_radius=4)
        lbl = fonts['small'].render(label, True, BTN_TEXT)
        surf.blit(lbl, lbl.get_rect(center=btn.center))

    # ── Single centred info block between the two buttons ───────────────────
    pos = assign_positions(hand).get(seat, f'p{seat}')
    stack = (hand.starting_stacks[seat - 1]
             if (seat - 1) < len(hand.starting_stacks) else 0.0)

    segments = [
        (f"Hand {hand_idx + 1}/{total_hands}", TEXT_MAIN),
        (f"Pos: {pos}", PLAYER_HL),
        (f"Stack: ${stack:.2f}", PLAYER_HL),
    ]
    if stats:
        nw = stats['net_won']
        segments += [
            (f"VPIP {stats['vpip_pct']}%", TEXT_DIM),
            (f"PFR {stats['pfr_pct']}%", TEXT_DIM),
            (f"Net {'+'if nw>=0 else ''}${nw:.2f}", TEXT_DIM),
        ]

    sep = fonts['small'].render("  ·  ", True, (80, 80, 80))
    sep_w = sep.get_width()

    # Measure total width so we can centre the block
    rendered = [(fonts['small'].render(txt, True, col), col) for txt, col in segments]
    total_w = sum(s.get_width() for s, _ in rendered) + sep_w * (len(rendered) - 1)

    # Available space between the two buttons (with 8px padding each side)
    left_bound  = btn_prev.right + 8
    right_bound = btn_next.left  - 8
    available   = right_bound - left_bound
    x = left_bound + max(0, (available - total_w) // 2)

    for idx, (surf_lbl, _) in enumerate(rendered):
        surf.blit(surf_lbl, surf_lbl.get_rect(left=x, centery=cy))
        x += surf_lbl.get_width()
        if idx < len(rendered) - 1:
            surf.blit(sep, sep.get_rect(left=x, centery=cy))
            x += sep_w


# ---------------------------------------------------------------------------
# Main replay loop
# ---------------------------------------------------------------------------

def replay_player(
    hands: list[Hand],
    player_id: str,
    start_index: int = 0,
) -> None:
    """
    Open a step-through replayer filtered to *player_id*'s hands.

    The player's seat is highlighted in teal. A strip at the top shows
    aggregate stats. Use ◀/▶ buttons or N/P keys to switch hands.
    """
    player_hands = get_player_hands(hands, player_id)
    if not player_hands:
        print(f"[player_replayer] '{player_id}' not found in any of the {len(hands)} hands.")
        return

    stats = player_stats(hands, player_id)
    print(
        f"[player_replayer] {player_id!r}  "
        f"{stats['hands_played']} hands  "
        f"VPIP {stats['vpip_pct']}%  PFR {stats['pfr_pct']}%  "
        f"Net ${stats['net_won']:+.2f}  BB/100 {stats['bb_per_100']:+.1f}"
    )

    pygame.init()
    short_id = (player_id[:24] + '…') if len(player_id) > 25 else player_id
    pygame.display.set_caption(f"Player: {short_id}")

    screen     = pygame.display.set_mode((WINDOW_W, WINDOW_H + STRIP_H))
    table_surf = screen.subsurface(pygame.Rect(0, STRIP_H, WINDOW_W, WINDOW_H))
    clock      = pygame.time.Clock()
    renderer   = Renderer(table_surf)
    fonts      = {'small': _font(14), 'medium': _font(17), 'large': _font(22, bold=True)}

    # Hand-nav button positions (in screen coords, inside the strip)
    _btn_y   = (STRIP_H - _HB_H) // 2
    btn_prev = pygame.Rect(10,                    _btn_y, _HB_W, _HB_H)
    btn_next = pygame.Rect(WINDOW_W - 10 - _HB_W, _btn_y, _HB_W, _HB_H)

    hand_idx = max(0, min(start_index, len(player_hands) - 1))
    show_bb  = False

    def _load(idx: int) -> tuple[ReplaySession, int]:
        h, s = player_hands[idx]
        return ReplaySession(h), s

    session, seat = _load(hand_idx)

    running = True
    while running:
        clock.tick(FPS)

        hand, _ = player_hands[hand_idx]
        screen_mouse = pygame.mouse.get_pos()
        table_mouse  = (screen_mouse[0], screen_mouse[1] - STRIP_H)

        # Draw table area (no flip — we do it after the strip)
        renderer.draw(
            session.state,
            session.display_step,
            session.display_total_steps,
            highlight_seat=seat,
            mouse_pos=table_mouse,
            known_cards=session.known_cards,
            show_bb=show_bb,
        )

        # Draw player strip on top of the screen
        _draw_strip(
            screen, player_id, hand, seat,
            hand_idx, len(player_hands), stats,
            fonts, btn_prev, btn_next, screen_mouse,
        )

        pygame.display.flip()

        # ── Events ────────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                k = event.key
                if k in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif k in (pygame.K_RIGHT, pygame.K_SPACE):
                    session.advance()
                elif k == pygame.K_LEFT:
                    session.rewind()
                elif k == pygame.K_r:
                    session.reset()
                elif k == pygame.K_n:
                    hand_idx = (hand_idx + 1) % len(player_hands)
                    session, seat = _load(hand_idx)
                elif k == pygame.K_p:
                    hand_idx = (hand_idx - 1) % len(player_hands)
                    session, seat = _load(hand_idx)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Strip hand-nav buttons (screen coords)
                if btn_prev.collidepoint(screen_mouse):
                    hand_idx = (hand_idx - 1) % len(player_hands)
                    session, seat = _load(hand_idx)
                elif btn_next.collidepoint(screen_mouse):
                    hand_idx = (hand_idx + 1) % len(player_hands)
                    session, seat = _load(hand_idx)
                # Table step buttons (table coords)
                elif renderer.btn_next.rect.collidepoint(table_mouse):
                    session.advance()
                elif renderer.btn_prev.rect.collidepoint(table_mouse):
                    session.rewind()
                elif renderer.btn_reset.rect.collidepoint(table_mouse):
                    session.reset()
                elif renderer.btn_bb_toggle.rect.collidepoint(table_mouse):
                    show_bb = not show_bb

    pygame.quit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Player-filtered poker hand replayer',
        formatter_class=argparse.RawTextHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--file', help='Path to a .phhs file')
    src.add_argument('--dir',  help='Directory of .phhs files')

    parser.add_argument('--player', help='Exact player ID to track')
    parser.add_argument('--list-players', action='store_true',
                        help='Print all player IDs and hand counts, then exit')
    parser.add_argument('--search', default='',
                        help='Partial-match filter for --list-players')
    parser.add_argument('--index', type=int, default=0,
                        help="Starting hand index within the player's hands (default: 0)")
    args = parser.parse_args()

    # Load hands
    if args.file:
        p = Path(args.file)
        if not p.exists():
            p = Path(__file__).parent.parent.parent / args.file
        hands = load_file(p)
    else:
        hands = load_directory(args.dir)

    if not hands:
        print("No hands loaded — check your file path.")
        sys.exit(1)

    if args.list_players:
        players = find_players(hands, args.search)
        print(f"\n{len(players)} player(s) in {len(hands)} hands:\n")
        for pid in players:
            n = len(get_player_hands(hands, pid))
            print(f"  {pid}  ({n} hands)")
        return

    if not args.player:
        parser.error("--player is required unless --list-players is set")

    replay_player(hands, args.player, start_index=args.index)


if __name__ == '__main__':
    main()
