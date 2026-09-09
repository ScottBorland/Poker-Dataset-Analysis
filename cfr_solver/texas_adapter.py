"""texas_adapter.py — Drive the TexasSolver console binary from a spot spec.

Converts a cfr_solver/spots/*.json spot spec (the same file-based contract
the OpenSpiel MCCFR path uses, see spot_spec.schema.json) into a TexasSolver
command file, runs console_solver.exe, and leaves results in
results/<spot_id>/:

    solver_commands.txt   — the generated command file (reproducibility)
    texas_output.json     — TexasSolver's strategy dump (full game tree up
                            to `--dump-rounds` betting rounds deep; action
                            nodes carry per-exact-combo strategies, chance
                            nodes carry per-card children)
    spot_spec.json        — copy of the input spec (same convention as
                            solve.py)

Output JSON conventions (verified against the v0.2.0 sample run):
  - action node: {node_type:'action', player: 0|1, actions: [...],
    strategy: {actions: [...], strategy: {comboStr: [probs]}},
    childrens: {actionLabel: node}}
  - chance node: {node_type:'chance', deal_number, dealcards: {card: node}}
  - player 1 = OOP, player 0 = IP (root is always OOP's decision)
  - bet/raise amounts in action labels are absolute amounts in the same
    units as set_pot / set_effective_stack (we pass BB).

Usage:
    python texas_adapter.py spots/<spot_id>.json [--dump-rounds 3]
        [--accuracy 0.3] [--max-iteration 200]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import hand_ranking

CFR_DIR = Path(__file__).parent
RESULTS_DIR = CFR_DIR / "results"
_STREETS = ("flop", "turn", "river")


def find_solver_exe() -> Path:
    override = os.environ.get("TEXAS_SOLVER_EXE")
    if override:
        p = Path(override)
        if p.exists():
            return p
        sys.exit(f"TEXAS_SOLVER_EXE={override} does not exist")
    matches = list((CFR_DIR / "bin").rglob("console_solver.exe"))
    if not matches:
        sys.exit("console_solver.exe not found under cfr_solver/bin/ — run python fetch_solver.py")
    return matches[0]


def _board_to_commas(board: str) -> str:
    """'Qs7s2d' -> 'Qs,7s,2d'."""
    return ",".join(board[i:i + 2] for i in range(0, len(board), 2))


def _range_string(pct: float) -> str:
    """Top pct% of canonical hands (Chen-ordered), TexasSolver notation."""
    hands = sorted(hand_ranking.top_pct_hands(pct))
    return ",".join(hands)


def spec_to_commands(
    spec: dict,
    out_json: Path,
    dump_rounds: int = 2,
    accuracy: float = 0.3,
    max_iteration: int = 200,
    thread_num: int | None = None,
    raise_pct: int = 60,
) -> str:
    board = spec.get("board")
    if not board:
        raise ValueError("spec has no board — TexasSolver solves postflop spots only")
    n_board = len(board) // 2
    if n_board not in (3, 4, 5):
        raise ValueError(f"board must be 3-5 cards, got {n_board}")

    ranges = spec.get("ranges") or {}
    oop_pct = (ranges.get("oop") or {}).get("range_pct") or 100.0
    ip_pct = (ranges.get("ip") or {}).get("range_pct") or 100.0

    # Tree-size control: memory grows multiplicatively with bet sizes across
    # streets (an unconstrained 2-size/3-street run measured >10 GB on this
    # 15 GB machine). Standard solver practice: richer sizing on the spot's
    # first street, a single size on later streets. How many of the spec's
    # sizes the first street keeps depends on how many streets remain — a
    # river-start spot has no future subtrees so it can afford them all:
    #   flop start: 2 sizes, turn start: 3, river start: all (up to 8).
    # Later streets always get the single middle-most size.
    fractions = sorted(spec.get("bet_size_fractions") or [0.5, 1.0])
    _FIRST_STREET_CAP = {"flop": 2, "turn": 3, "river": 8}

    def pick(n: int) -> list[int]:
        take = fractions[:]
        while len(take) > n:
            take.pop(0 if len(take) % 2 == 0 else -1)  # trim extremes inward
        return [max(1, round(f * 100)) for f in take]

    spot_street = spec.get("street", "flop")
    first_street_idx = _STREETS.index(spot_street) if spot_street in _STREETS else 0
    street_sizes: dict[str, list[int]] = {}
    for i, street in enumerate(_STREETS):
        if i < first_street_idx:
            continue
        cap = _FIRST_STREET_CAP.get(spot_street, 2) if i == first_street_idx else 1
        street_sizes[street] = pick(cap)

    if thread_num is None:
        thread_num = max(1, (os.cpu_count() or 4) - 1)

    lines = [
        f"set_pot {spec['pot_bb_at_street_start']}",
        f"set_effective_stack {spec['effective_stack_bb']}",
        f"set_board {_board_to_commas(board)}",
        f"set_range_oop {_range_string(oop_pct)}",
        f"set_range_ip {_range_string(ip_pct)}",
    ]
    for who in ("oop", "ip"):
        for street, pcts in street_sizes.items():
            lines.append(f"set_bet_sizes {who},{street},bet,{','.join(map(str, pcts))}")
            lines.append(f"set_bet_sizes {who},{street},raise,{raise_pct}")
            lines.append(f"set_bet_sizes {who},{street},allin")
    lines += [
        "set_allin_threshold 0.67",
        "build_tree",
        f"set_thread_num {thread_num}",
        f"set_accuracy {accuracy}",
        f"set_max_iteration {max_iteration}",
        "set_print_interval 10",
        "set_use_isomorphism 1",
        "start_solve",
        f"set_dump_rounds {dump_rounds}",
        # Relative to the exe's cwd — its command parser can't handle spaces,
        # so the caller passes a bare filename and moves the result after.
        f"dump_result {out_json}",
    ]
    return "\n".join(lines) + "\n"


def run(
    spec_path: Path,
    dump_rounds: int = 2,
    accuracy: float = 0.3,
    max_iteration: int = 200,
) -> Path:
    spec = json.loads(spec_path.read_text())
    spot_id = spec["spot_id"]
    out_dir = RESULTS_DIR / spot_id
    out_dir.mkdir(parents=True, exist_ok=True)

    exe = find_solver_exe()
    # TexasSolver's command parser can't handle paths with spaces, so dump to
    # a bare filename in the exe's cwd and move it into results/ afterwards.
    tmp_name = f"_dump_{spot_id}.json"
    out_json = out_dir / "texas_output.json"
    commands = spec_to_commands(
        spec, Path(tmp_name),
        dump_rounds=dump_rounds, accuracy=accuracy, max_iteration=max_iteration,
    )
    cmd_file_name = f"_cmds_{spot_id}.txt"
    (exe.parent / cmd_file_name).write_text(commands)
    (out_dir / "solver_commands.txt").write_text(commands)
    (out_dir / "spot_spec.json").write_text(json.dumps(spec, indent=2))

    print(f"Solving {spot_id} with TexasSolver ({exe.name}, accuracy {accuracy}%, "
          f"max {max_iteration} iters, dump_rounds {dump_rounds})...", flush=True)
    # cwd = the exe's own directory: it loads resources/ relative to cwd.
    try:
        proc = subprocess.Popen(
            [str(exe), "-i", cmd_file_name],
            cwd=str(exe.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        for line in proc.stdout:
            print(line.rstrip(), flush=True)
        rc = proc.wait()
        if rc != 0:
            sys.exit(f"console_solver.exe exited with {rc}")
        tmp_out = exe.parent / tmp_name
        if not tmp_out.exists():
            sys.exit(f"Solver finished but {tmp_out} was not written")
        shutil.move(str(tmp_out), str(out_json))
    finally:
        (exe.parent / cmd_file_name).unlink(missing_ok=True)
    size_mb = out_json.stat().st_size / 1024 / 1024
    print(f"Done: {out_json} ({size_mb:.1f} MB)", flush=True)
    return out_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spot_spec", type=Path)
    # 2 betting rounds deep ≈ 124 MB for a flop spot (measured); 3 explodes.
    parser.add_argument("--dump-rounds", type=int, default=2)
    parser.add_argument("--accuracy", type=float, default=0.3,
                        help="target exploitability as %% of pot")
    parser.add_argument("--max-iteration", type=int, default=200)
    args = parser.parse_args()
    run(args.spot_spec, dump_rounds=args.dump_rounds,
        accuracy=args.accuracy, max_iteration=args.max_iteration)
