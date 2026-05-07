"""Throwaway script: test pokerkit HandHistory.load_all() on sample .phhs file."""

from pathlib import Path
from pokerkit import HandHistory

SAMPLE = Path("abs NLH handhq_1-OBFUSCATED.phhs")

print(f"Loading: {SAMPLE}\n")

with SAMPLE.open("rb") as fh:
    hands = list(HandHistory.load_all(fh))

print(f"Total hands parsed: {len(hands)}\n")

for hh in hands[:5]:
    n_players = len(hh.players) if hh.players else 0
    # Pot = sum of blinds + antes collected (proxy before any actions)
    blinds = sum(hh.blinds_or_straddles) if hh.blinds_or_straddles else 0.0
    antes = sum(hh.antes) if hasattr(hh, 'antes') and hh.antes else 0.0
    pot_start = blinds + antes

    # Count state actions (generator, so materialise it)
    actions = list(hh.state_actions) if hasattr(hh, 'state_actions') else []
    n_actions = len(actions)

    print(
        f"Hand #{hh.hand}"
        f"  players={n_players}"
        f"  starting_pot=${pot_start:.2f}"
        f"  actions={n_actions}"
        f"  table={hh.table!r}"
    )
