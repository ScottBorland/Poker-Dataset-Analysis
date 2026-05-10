"""
renderer.py — pygame drawing routines for the hand replayer.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from replayer.state import HandState


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

BG          = (30,  80,  30)   # felt green
TABLE_FELT  = (20,  60,  20)
TABLE_RAIL  = (80,  40,  10)
TEXT_MAIN   = (255, 255, 255)
TEXT_DIM    = (180, 180, 180)
TEXT_FOLDED = (120, 120, 120)
CARD_BG     = (255, 255, 255)
CARD_RED    = (200,  20,  20)
CARD_BLACK  = (10,   10,  10)
CARD_HIDDEN = (50,   80, 160)
BTN_NORMAL  = (60,  100, 160)
BTN_HOVER   = (80,  130, 200)
BTN_TEXT    = (255, 255, 255)
ACTIVE_HL   = (255, 215,   0)
PLAYER_HL   = (0,   210, 185)   # teal: tracked player's seat
PLAYER_HL_BG = (0,   55,  50)   # dark teal fill for tracked player's box
PANEL_BG    = (20,   20,  20)
LOG_BG      = (15,   15,  15)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont('consolas', size, bold=bold)


def draw_text(surf: pygame.Surface, text: str, pos: tuple, font: pygame.font.Font,
              color=TEXT_MAIN, center: bool = False):
    rendered = font.render(text, True, color)
    rect = rendered.get_rect()
    if center:
        rect.center = pos
    else:
        rect.topleft = pos
    surf.blit(rendered, rect)


def draw_card(surf: pygame.Surface, card: str, cx: int, cy: int,
              w: int = 36, h: int = 50):
    """Draw a single card centred at (cx, cy)."""
    rect = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
    pygame.draw.rect(surf, CARD_BG, rect, border_radius=4)
    pygame.draw.rect(surf, (0, 0, 0), rect, 1, border_radius=4)

    if card == '??' or len(card) < 2:
        # Hidden card
        inner = rect.inflate(-6, -6)
        pygame.draw.rect(surf, CARD_HIDDEN, inner, border_radius=3)
        return

    rank, suit = card[0], card[1]
    suit_sym = {'h': '♥', 'd': '♦', 'c': '♣', 's': '♠'}.get(suit, suit)
    color = CARD_RED if suit in ('h', 'd') else CARD_BLACK
    label = rank + suit_sym

    if w >= 34:
        # Large card (community): label top-left + mirrored bottom-right
        font = _font(16, bold=True)
        draw_text(surf, label, (rect.left + 3, rect.top + 2), font, color)
        draw_text(surf, label, (rect.right - 22, rect.bottom - 18), font, color)
    else:
        # Small card (hole cards): single centred label with smaller font
        font = _font(11, bold=True)
        lbl = font.render(label, True, color)
        surf.blit(lbl, lbl.get_rect(center=rect.center))


# ---------------------------------------------------------------------------
# Table layout
# ---------------------------------------------------------------------------

def _seat_positions(n: int, cx: int, cy: int, rx: int, ry: int) -> list[tuple[int, int]]:
    """
    Return (x, y) positions evenly distributed around an ellipse.
    Seat 0 is at the bottom (SB), seats go clockwise.
    """
    positions = []
    for i in range(n):
        # Start from bottom (SB), rotate clockwise
        angle = math.pi / 2 + 2 * math.pi * i / n
        x = int(cx - rx * math.cos(angle))
        y = int(cy - ry * math.sin(angle))
        positions.append((x, y))
    return positions


def draw_table(surf: pygame.Surface, state: HandState,
               positions: list[tuple[int, int]],
               cx: int, cy: int, rx: int, ry: int,
               fonts: dict, active_player: int | None,
               highlight_seat: int | None = None,
               known_cards: dict | None = None):
    """Draw the oval table, community cards, pot, and player seats."""

    # Table oval
    table_rect = pygame.Rect(cx - rx, cy - ry, rx * 2, ry * 2)
    pygame.draw.ellipse(surf, TABLE_RAIL, table_rect)
    felt_rect = table_rect.inflate(-16, -16)
    pygame.draw.ellipse(surf, TABLE_FELT, felt_rect)

    # Community cards
    board_cards = state.board + [''] * (5 - len(state.board))
    card_w, card_h = 38, 54
    start_x = cx - (5 * (card_w + 6)) // 2
    for i, card in enumerate(board_cards):
        bx = start_x + i * (card_w + 6) + card_w // 2
        by = cy - 10
        if card:
            draw_card(surf, card, bx, by, card_w, card_h)
        else:
            # Empty placeholder
            ph = pygame.Rect(bx - card_w // 2, by - card_h // 2, card_w, card_h)
            pygame.draw.rect(surf, (30, 60, 30), ph, border_radius=4)
            pygame.draw.rect(surf, (50, 90, 50), ph, 1, border_radius=4)

    # Pot
    pot_text = f"Pot: {state.display_pot()}"
    draw_text(surf, pot_text, (cx, cy + 38), fonts['medium'], TEXT_MAIN, center=True)

    # Last action banner — always shows what just happened
    if state.action_log:
        last = state.action_log[-1]
        # Strip the dashes from street headers so they render cleanly
        banner = last.strip('- ').strip()
        draw_text(surf, banner, (cx, cy + 60), fonts['medium'], ACTIVE_HL, center=True)

    # Street indicator
    draw_text(surf, state.street.upper(), (cx, cy - 55),
              fonts['small'], TEXT_DIM, center=True)

    # Players
    n = len(state.stacks)
    for i, (px, py) in enumerate(positions):
        pidx = i + 1   # 1-based
        is_folded  = pidx in state.folded
        is_active  = (pidx == active_player)

        is_tracked = (pidx == highlight_seat)
        name_color = (TEXT_FOLDED if is_folded
                      else ACTIVE_HL if is_active
                      else PLAYER_HL if is_tracked
                      else TEXT_MAIN)
        box_w, box_h = 110, 66
        box = pygame.Rect(px - box_w // 2, py - box_h // 2, box_w, box_h)

        # Outer glow / highlight ring
        if is_active:
            pygame.draw.rect(surf, ACTIVE_HL,  box.inflate(8, 8), 2, border_radius=7)
        elif is_tracked:
            pygame.draw.rect(surf, PLAYER_HL, box.inflate(8, 8), 3, border_radius=7)

        # Box fill — tinted for tracked player
        box_bg = PLAYER_HL_BG if is_tracked else PANEL_BG
        pygame.draw.rect(surf, box_bg, box, border_radius=6)
        pygame.draw.rect(surf, (80, 80, 80), box, 1, border_radius=6)

        label = f"p{pidx}"
        draw_text(surf, label, (px, py - 24), fonts['small'], name_color, center=True)

        stack_str = f"${state.stacks[i]:.2f}"
        draw_text(surf, stack_str, (px, py - 8), fonts['small'],
                  TEXT_FOLDED if is_folded else TEXT_DIM, center=True)

        bet = state.street_bets[i] if i < len(state.street_bets) else 0.0
        if bet > 0:
            draw_text(surf, f"bet: ${bet:.2f}", (px, py + 8),
                      fonts['small'], ACTIVE_HL, center=True)

        # Hole cards — prefer known_cards (lookahead) over current state
        actual = (known_cards or {}).get(pidx)
        state_cards = state.hole_cards.get(pidx, [])
        # Pick the best available cards to display
        if actual:
            display_cards = actual
        elif state_cards and state_cards[0] != '??':
            display_cards = state_cards
        else:
            display_cards = None

        if display_cards:
            for j, card in enumerate(display_cards[:2]):
                draw_card(surf, card, px - 12 + j * 24, py + 30, 20, 28)
        elif not is_folded:
            for j in range(2):
                draw_card(surf, '??', px - 12 + j * 24, py + 30, 20, 28)


# ---------------------------------------------------------------------------
# Action log panel
# ---------------------------------------------------------------------------

def draw_log_panel(surf: pygame.Surface, state: HandState,
                   rect: pygame.Rect, fonts: dict):
    pygame.draw.rect(surf, LOG_BG, rect)
    pygame.draw.rect(surf, (60, 60, 60), rect, 1)

    # Show last N lines of log
    line_h = 18
    max_lines = rect.height // line_h - 1
    log = state.action_log[-max_lines:] if len(state.action_log) > max_lines else state.action_log

    y = rect.top + 4
    for line in log:
        draw_text(surf, line, (rect.left + 6, y), fonts['small'], TEXT_MAIN)
        y += line_h


# ---------------------------------------------------------------------------
# Navigation bar
# ---------------------------------------------------------------------------

class Button:
    def __init__(self, label: str, rect: pygame.Rect):
        self.label = label
        self.rect  = rect

    def draw(self, surf: pygame.Surface, fonts: dict, hovered: bool = False):
        color = BTN_HOVER if hovered else BTN_NORMAL
        pygame.draw.rect(surf, color, self.rect, border_radius=6)
        draw_text(surf, self.label, self.rect.center, fonts['medium'],
                  BTN_TEXT, center=True)

    def is_hovered(self, mouse_pos: tuple) -> bool:
        return self.rect.collidepoint(mouse_pos)

    def is_clicked(self, event: pygame.event.Event) -> bool:
        return (event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos))


def draw_nav_bar(surf: pygame.Surface, rect: pygame.Rect,
                 step: int, total: int, buttons: list[Button],
                 mouse_pos: tuple, fonts: dict):
    pygame.draw.rect(surf, PANEL_BG, rect)
    for btn in buttons:
        btn.draw(surf, fonts, hovered=btn.is_hovered(mouse_pos))
    step_text = f"Step {step} / {total}"
    cx = rect.centerx
    cy = rect.centery
    draw_text(surf, step_text, (cx, cy), fonts['medium'], TEXT_DIM, center=True)


# ---------------------------------------------------------------------------
# Full screen renderer
# ---------------------------------------------------------------------------

class Renderer:
    """Owns all pygame drawing for one frame."""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.W, self.H = screen.get_size()
        self.fonts = {
            'large':  _font(22, bold=True),
            'medium': _font(17),
            'small':  _font(14),
        }

        # Layout constants — panels first, then fit the table in the remaining space
        nav_h = 44
        log_h = int(self.H * 0.28)
        self.nav_rect = pygame.Rect(0, self.H - nav_h, self.W, nav_h)
        self.log_rect = pygame.Rect(0, self.H - nav_h - log_h, self.W, log_h)

        # Usable area for the table: from a top margin to just above the log panel
        TOP_MARGIN = 50  # enough room for the topmost seat box + label
        SEAT_BOX_HALF_H = 33 + 30 + 10  # half seat-box height + hole-cards + clearance
        table_area_top = TOP_MARGIN
        table_area_bot = self.log_rect.top - SEAT_BOX_HALF_H
        table_area_h   = table_area_bot - table_area_top

        self.table_cx = self.W // 2
        self.table_cy = table_area_top + table_area_h // 2
        self.table_rx = int(self.W * 0.36)
        self.table_ry = int(table_area_h * 0.42)   # fits within the usable height

        bw, bh = 110, 32
        by = self.nav_rect.centery - bh // 2
        self.btn_prev  = Button("← Prev",  pygame.Rect(20,           by, bw, bh))
        self.btn_next  = Button("Next →",  pygame.Rect(self.W - 130, by, bw, bh))
        self.btn_reset = Button("Reset",   pygame.Rect(self.W // 2 + 90, by, 80, bh))
        self.buttons   = [self.btn_prev, self.btn_next, self.btn_reset]

    def seat_positions(self, n: int) -> list[tuple[int, int]]:
        return _seat_positions(
            n, self.table_cx, self.table_cy,
            self.table_rx + 30, self.table_ry + 30,
        )

    def draw(self, state: HandState, step: int, total: int,
             highlight_seat: int | None = None,
             mouse_pos: tuple | None = None,
             known_cards: dict | None = None):
        self.screen.fill(BG)
        mouse = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()
        n = len(state.stacks)
        positions = self.seat_positions(n)

        draw_table(
            self.screen, state, positions,
            self.table_cx, self.table_cy,
            self.table_rx, self.table_ry,
            self.fonts, state.current_actor,
            highlight_seat=highlight_seat,
            known_cards=known_cards,
        )
        draw_log_panel(self.screen, state, self.log_rect, self.fonts)
        draw_nav_bar(
            self.screen, self.nav_rect,
            step, total, self.buttons, mouse, self.fonts,
        )
        # Caller is responsible for pygame.display.flip()
