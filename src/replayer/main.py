"""
main.py — pygame entry point for the hand replayer.

Usage:
    python src/replayer/main.py --file "abs NLH handhq_1-OBFUSCATED.phhs" --hand 3017235114
    python src/replayer/main.py --file "abs NLH handhq_1-OBFUSCATED.phhs" --index 0
    python src/replayer/main.py --dir data/ --index 5

Keyboard shortcuts:
    RIGHT / Space — advance one action
    LEFT          — rewind one action
    R             — reset to start
    N             — next hand (if multiple loaded)
    P             — previous hand
    Q / Escape    — quit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from any directory
_SRC = Path(__file__).parent.parent
sys.path.insert(0, str(_SRC))

import pygame

from parser import Hand, load_file, load_directory
from replayer.state import ReplaySession
from replayer.renderer import Renderer


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_W   = 1000
WINDOW_H   = 720
FPS        = 60
WINDOW_TITLE = "Poker Hand Replayer"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(hands: list[Hand], start_index: int = 0):
    if not hands:
        print("[replayer] No hands to display.")
        return

    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)
    screen  = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    clock   = pygame.time.Clock()
    renderer = Renderer(screen)

    hand_idx = max(0, min(start_index, len(hands) - 1))
    session  = ReplaySession(hands[hand_idx])
    show_bb  = False

    running = True
    while running:
        clock.tick(FPS)
        mouse = pygame.mouse.get_pos()
        state = session.state

        # Draw
        pygame.display.set_caption(
            f"{WINDOW_TITLE}  |  Hand {hand_idx+1}/{len(hands)}"
            f"  id={hands[hand_idx].hand_id}  table={hands[hand_idx].table}"
        )
        renderer.draw(state, session.display_step, session.display_total_steps,
                      known_cards=session.known_cards, show_bb=show_bb)
        pygame.display.flip()

        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key in (pygame.K_RIGHT, pygame.K_SPACE):
                    session.advance()
                elif event.key == pygame.K_LEFT:
                    session.rewind()
                elif event.key == pygame.K_r:
                    session.reset()
                elif event.key == pygame.K_n:
                    hand_idx = (hand_idx + 1) % len(hands)
                    session = ReplaySession(hands[hand_idx])
                elif event.key == pygame.K_p:
                    hand_idx = (hand_idx - 1) % len(hands)
                    session = ReplaySession(hands[hand_idx])

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if renderer.btn_next.is_clicked(event):
                    session.advance()
                elif renderer.btn_prev.is_clicked(event):
                    session.rewind()
                elif renderer.btn_reset.is_clicked(event):
                    session.reset()
                elif renderer.btn_bb_toggle.is_clicked(event):
                    show_bb = not show_bb

    pygame.quit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Step-through poker hand replayer')
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--file', help='Path to a .phhs file')
    src.add_argument('--dir',  help='Directory of .phhs files')

    parser.add_argument('--hand',  type=int, help='Specific hand_id to start on')
    parser.add_argument('--index', type=int, default=0,
                        help='0-based index of hand to start on (default: 0)')
    args = parser.parse_args()

    if args.file:
        # Resolve relative to CWD or as absolute
        p = Path(args.file)
        if not p.exists():
            # Try relative to project root
            p = Path(__file__).parent.parent.parent / args.file
        hands = load_file(p)
    else:
        hands = load_directory(args.dir)

    if not hands:
        print("No hands loaded — check your file path.")
        sys.exit(1)

    start = args.index
    if args.hand is not None:
        ids = [h.hand_id for h in hands]
        if args.hand in ids:
            start = ids.index(args.hand)
        else:
            print(f"[replayer] hand_id {args.hand} not found; starting at index 0")
            start = 0

    print(f"[replayer] Loaded {len(hands)} hands. Starting at index {start}.")
    run(hands, start_index=start)


if __name__ == '__main__':
    main()
