from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import json
import re
import sqlite3
import subprocess
import os
import sys
import itertools
import random
from contextlib import asynccontextmanager
from pathlib import Path

# Works whether this module is run as `api` (cwd=src/) or `src.api`
# (cwd=repo root, e.g. `python -m uvicorn src.api:app`) — same pattern as
# src/spot_spec_export.py.
sys.path.insert(0, str(Path(__file__).parent))

from treys import Card as TreysCard, Evaluator

import fingerprint
import hand_utils
import range_charts
from hand_utils import assign_positions
from parser import Hand
from replayer.state import ReplaySession
from scripts import load_hands_by_id

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'poker.db')
CFR_RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'cfr_solver', 'results')

FP_TYPE_COLUMNS = [
    "street", "positions", "n_players_street", "pot_type", "in_position",
    "facing", "spr_bucket", "board_high_card", "board_paired",
    "board_monotone", "board_two_tone", "board_connectedness",
]

FP_BOOL_COLUMNS = ("in_position", "board_paired", "board_monotone", "board_two_tone")


def _ensure_covering_index() -> None:
    """Create covering index for stats queries. No-op if already exists; ~3–5 min first run."""
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_ph_hand_stats
            ON player_hands(hand_id, position, player_id, net_won, big_blind, invested)
        """)
        con.commit()
    finally:
        con.close()


def _ensure_fingerprint_type_index() -> None:
    """Covering index for the 12-column fingerprint-type GROUP BY. No-op if already exists."""
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_fp_type_full
            ON fingerprints({', '.join(FP_TYPE_COLUMNS)})
        """)
        con.commit()
    finally:
        con.close()


def _ensure_venue_index() -> None:
    """Covering index for filtering fingerprint queries down to one venue (e.g. 888poker)."""
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_ph_venue_hand
            ON player_hands(venue, hand_id, file, seat_idx)
        """)
        con.commit()
    finally:
        con.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_covering_index()
    _ensure_fingerprint_type_index()
    _ensure_venue_index()
    yield


app = FastAPI(title="Poker Analysis API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Filter(BaseModel):
    type: str
    value: Any = None


class QueryRequest(BaseModel):
    filters: list[Filter]


class FingerprintKey(BaseModel):
    street: Optional[str] = None
    positions: Optional[str] = None
    n_players_street: Optional[int] = None
    pot_type: Optional[str] = None
    in_position: Optional[bool] = None
    facing: Optional[str] = None
    spr_bucket: Optional[str] = None
    board_high_card: Optional[str] = None
    board_paired: Optional[bool] = None
    board_monotone: Optional[bool] = None
    board_two_tone: Optional[bool] = None
    board_connectedness: Optional[str] = None


class FingerprintDistributionRequest(BaseModel):
    street: Optional[str] = None
    limit: int = 30
    venue: Optional[str] = None


class FingerprintHandsRequest(BaseModel):
    types: list[FingerprintKey]
    limit: int = 500
    offset: int = 0
    venue: Optional[str] = None
    # Fuzzy relaxation-tier matching (uses types[0] only): rows matched at
    # progressively looser tiers, labeled match_tier 0..max_tier.
    fuzzy: bool = False
    max_tier: int = 4


def get_connection() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA cache_size = -262144")   # 256 MB page cache
    con.execute("PRAGMA mmap_size = 2147483648")  # 2 GB mmap
    con.execute("PRAGMA temp_store = MEMORY")     # keep temp tables in RAM
    return con


def build_filter_sql(filters: list[Filter]) -> tuple[str, list[Any]]:
    """Returns (sql, params) → SELECT hand_id for every hand matching all filters.

    Uses INTERSECT so SQLite can do index-only scans on both covering indexes:
      idx_label_hid(label, hand_id)           — labels side
      idx_ph_nplayers_hid(n_players, hand_id) — player_hands side
    """
    include_subqueries: list[str] = []
    exclude_subqueries: list[str] = []
    params: list[Any] = []

    for f in filters:
        if f.type == 'num_players' and f.value not in (None, 'any'):
            include_subqueries.append(
                "SELECT DISTINCT hand_id FROM player_hands WHERE n_players = ?"
            )
            params.append(int(f.value))

        elif f.type == 'hole_cards' and f.value and len(f.value) > 0:
            placeholders = ','.join('?' * len(f.value))
            include_subqueries.append(
                f"SELECT DISTINCT ph.hand_id FROM player_hands ph "
                f"JOIN labels l ON l.hand_id = ph.hand_id AND l.player_idx = ph.seat_idx "
                f"WHERE ph.player_id = 'ScottyWotty' AND l.label IN ({placeholders})"
            )
            params.extend(f'hand_{v}' for v in f.value)

        elif f.type == 'showdown':
            if f.value == 'yes':
                include_subqueries.append(
                    "SELECT DISTINCT hand_id FROM labels WHERE label = 'showdown'"
                )
            elif f.value == 'no':
                exclude_subqueries.append(
                    "SELECT DISTINCT hand_id FROM labels WHERE label = 'showdown'"
                )

        elif f.type == 'flop_type':
            values = f.value if isinstance(f.value, list) else (
                [f.value] if f.value not in (None, 'any') else []
            )
            for v in values:
                if v and v != 'any':
                    include_subqueries.append(
                        "SELECT DISTINCT hand_id FROM labels WHERE label = ?"
                    )
                    params.append(v)

        elif f.type == 'preflop_action':
            values = f.value if isinstance(f.value, list) else (
                [f.value] if f.value not in (None, 'any') else []
            )
            values = [v for v in values if v and v != 'any']
            if values:
                placeholders = ','.join('?' * len(values))
                include_subqueries.append(
                    f"SELECT DISTINCT hand_id FROM labels WHERE label IN ({placeholders})"
                )
                params.extend(values)

        elif f.type == 'player' and f.value and str(f.value).strip():
            include_subqueries.append(
                "SELECT DISTINCT hand_id FROM player_hands WHERE player_id = ?"
            )
            params.append(str(f.value).strip())

        elif f.type == 'player_position' and isinstance(f.value, dict):
            raw_positions = f.value.get('positions') or []
            if not raw_positions:
                single = f.value.get('position', 'any')
                raw_positions = [single] if single and single != 'any' else []
            positions = [p for p in raw_positions if p and p != 'any']
            player_id = (f.value.get('player_id') or '').strip()
            if positions:
                placeholders = ','.join('?' * len(positions))
                if player_id:
                    include_subqueries.append(
                        f"SELECT DISTINCT hand_id FROM player_hands WHERE player_id = ? AND position IN ({placeholders})"
                    )
                    params.extend([player_id, *positions])
                else:
                    include_subqueries.append(
                        f"SELECT DISTINCT hand_id FROM player_hands WHERE position IN ({placeholders})"
                    )
                    params.extend(positions)

        elif f.type == 'venue' and f.value not in (None, 'any'):
            include_subqueries.append(
                "SELECT DISTINCT hand_id FROM player_hands WHERE venue = ?"
            )
            params.append(f.value)

    if not include_subqueries and not exclude_subqueries:
        return "SELECT DISTINCT hand_id FROM player_hands LIMIT 500000", []

    sql = " INTERSECT ".join(include_subqueries) if include_subqueries else "SELECT DISTINCT hand_id FROM player_hands"
    for excl in exclude_subqueries:
        sql = f"{sql} EXCEPT {excl}"

    return sql, params


@app.post("/sql")
def get_sql(req: QueryRequest) -> dict:
    sql, params = build_filter_sql(req.filters)
    display_sql = sql
    for p in params:
        replacement = f"'{p}'" if isinstance(p, str) else str(p)
        display_sql = display_sql.replace('?', replacement, 1)
    return {'sql': display_sql}


def _fingerprint_key_predicate(key: FingerprintKey) -> tuple[str, list[Any]]:
    """Builds an equality/IS-NULL predicate over FP_TYPE_COLUMNS matching one fingerprint type."""
    data = key.model_dump()
    clauses: list[str] = []
    params: list[Any] = []
    for col in FP_TYPE_COLUMNS:
        val = data.get(col)
        if val is None:
            clauses.append(f"{col} IS NULL")
        else:
            if isinstance(val, bool):
                val = int(val)
            clauses.append(f"{col} = ?")
            params.append(val)
    return "(" + " AND ".join(clauses) + ")", params


def _cast_fp_bools(row: dict) -> dict:
    for col in FP_BOOL_COLUMNS:
        row[col] = bool(row[col]) if row[col] is not None else None
    return row


# ---------------------------------------------------------------------------
# Fuzzy fingerprint matching — relaxation tiers. Tier 0 is the exact
# 12-column key; each later tier widens/drops the least strategically
# significant remaining columns. Used by /fingerprints/hands, /stats
# (fuzzy=true) and /spots/lookup.
# ---------------------------------------------------------------------------

_SPR_ORDER = ['0-3', '3-6', '6-13', '13-20', '20+']

FUZZY_TIER_LABELS = [
    'exact',
    'any connectedness',
    'similar SPR',
    'similar board',
    'any position',
]


def _adjacent_sprs(bucket: Optional[str]) -> Optional[list[str]]:
    if bucket not in _SPR_ORDER:
        return None
    i = _SPR_ORDER.index(bucket)
    return _SPR_ORDER[max(0, i - 1):i + 2]


def _tier_predicate(key: FingerprintKey, tier: int) -> tuple[str, list[Any]]:
    """Predicate for fingerprint rows matching `key` at relaxation `tier`.

    Tier 0: exact on all 12 columns.
    Tier 1: drop board_connectedness.
    Tier 2: + spr_bucket widened to adjacent buckets.
    Tier 3: + drop facing; monotone/two_tone merged into flush-possible-ness.
    Tier 4: + any positions (street/n_players_street/pot_type still exact).
    """
    data = key.model_dump()
    clauses: list[str] = []
    params: list[Any] = []

    def eq(col: str) -> None:
        val = data.get(col)
        if val is None:
            clauses.append(f"{col} IS NULL")
        else:
            clauses.append(f"{col} = ?")
            params.append(int(val) if isinstance(val, bool) else val)

    for col in ('street', 'n_players_street', 'pot_type', 'in_position',
                'board_high_card', 'board_paired'):
        eq(col)

    if tier < 4:
        eq('positions')
    if tier < 3:
        eq('facing')
        eq('board_monotone')
        eq('board_two_tone')
    else:
        # Merge suit texture into "3-flush possible" vs not: monotone stays
        # meaningful (a made flush is possible), two-tone vs rainbow pools.
        mono = data.get('board_monotone')
        if mono is not None:
            clauses.append("board_monotone = ?")
            params.append(int(mono))
    if tier < 2:
        eq('spr_bucket')
    else:
        widened = _adjacent_sprs(data.get('spr_bucket'))
        if widened:
            clauses.append(f"spr_bucket IN ({','.join('?' * len(widened))})")
            params.extend(widened)
        elif data.get('spr_bucket') is None:
            clauses.append("spr_bucket IS NULL")
    if tier < 1:
        eq('board_connectedness')

    return "(" + " AND ".join(clauses) + ")", params


@app.post("/fingerprints/distribution")
def get_fingerprint_distribution(req: FingerprintDistributionRequest) -> dict:
    limit = max(1, min(req.limit, 100))
    con = get_connection()
    try:
        if req.venue:
            # venue lives only on player_hands, so start from the small venue-filtered
            # slice there (idx_ph_venue_hand) and probe into fingerprints by hand_id —
            # far cheaper than scanning fingerprints and checking venue per row.
            fp_cols_sql = ", ".join(f"fp.{c}" for c in FP_TYPE_COLUMNS)
            where_clauses = ["ph.venue = ?"]
            params: list[Any] = [req.venue]
            if req.street:
                where_clauses.append("fp.street = ?")
                params.append(req.street)

            from_sql = f"""
                FROM player_hands ph INDEXED BY idx_ph_venue_hand
                JOIN fingerprints fp
                    ON fp.hand_id = ph.hand_id AND fp.file = ph.file AND fp.player_idx = ph.seat_idx
                WHERE {' AND '.join(where_clauses)}
            """

            rows = con.execute(f"""
                SELECT {fp_cols_sql}, COUNT(*) AS n
                {from_sql}
                GROUP BY {fp_cols_sql}
                ORDER BY n DESC
                LIMIT ?
            """, [*params, limit]).fetchall()

            total_distinct_types = con.execute(f"""
                SELECT COUNT(*) FROM (SELECT 1 {from_sql} GROUP BY {fp_cols_sql})
            """, params).fetchone()[0]

            total_rows = con.execute(f"SELECT COUNT(*) {from_sql}", params).fetchone()[0]
        else:
            cols_sql = ", ".join(FP_TYPE_COLUMNS)
            where_sql = ""
            params = []
            if req.street:
                where_sql = "WHERE street = ?"
                params.append(req.street)

            rows = con.execute(f"""
                SELECT {cols_sql}, COUNT(*) AS n
                FROM fingerprints
                {where_sql}
                GROUP BY {cols_sql}
                ORDER BY n DESC
                LIMIT ?
            """, [*params, limit]).fetchall()

            total_distinct_types = con.execute(f"""
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM fingerprints {where_sql} GROUP BY {cols_sql}
                )
            """, params).fetchone()[0]

            total_rows = con.execute(
                f"SELECT COUNT(*) FROM fingerprints {where_sql}", params
            ).fetchone()[0]

        types = []
        for row in rows:
            d = dict(row)
            n = d.pop('n')
            types.append({'key': _cast_fp_bools(d), 'count': n})

        return {
            'types': types,
            'total_distinct_types': total_distinct_types,
            'total_rows': total_rows,
        }
    finally:
        con.close()


def _fuzzy_tier_sql(key: FingerprintKey, max_tier: int) -> tuple[str, list[Any], str, list[Any]]:
    """(case_sql, case_params, where_sql, where_params): tiers are nested
    supersets, so the widest tier's predicate is the WHERE and a CASE ranks
    each row by the tightest tier it matches. Params returned separately so
    callers can interleave other placeholders in SQL-text order."""
    max_tier = max(0, min(max_tier, len(FUZZY_TIER_LABELS) - 1))
    case_parts = []
    case_params: list[Any] = []
    for tier in range(max_tier):
        clause, p = _tier_predicate(key, tier)
        case_parts.append(f"WHEN {clause} THEN {tier}")
        case_params.extend(p)
    where, where_params = _tier_predicate(key, max_tier)
    case_sql = "CASE " + " ".join(case_parts) + f" ELSE {max_tier} END" if case_parts else str(max_tier)
    return case_sql, case_params, where, where_params


@app.post("/fingerprints/hands")
def get_fingerprint_hands(req: FingerprintHandsRequest) -> dict:
    types = req.types[:50]
    limit = max(1, min(req.limit, 1000))
    offset = max(0, req.offset)

    if not types:
        return {'hands': [], 'total': 0, 'limit': limit, 'offset': offset}

    if req.fuzzy:
        case_sql, case_params, where, where_params = _fuzzy_tier_sql(types[0], req.max_tier)
        tier_select = f", {case_sql} AS match_tier"
        order = "ORDER BY match_tier, fp.hand_id DESC"
    else:
        predicates: list[str] = []
        where_params = []
        case_params = []
        for t in types:
            clause, p = _fingerprint_key_predicate(t)
            predicates.append(clause)
            where_params.extend(p)
        where = "(" + " OR ".join(predicates) + ")"
        tier_select = ""
        order = "ORDER BY fp.hand_id DESC"

    # Venue-first join when a venue is set (see /fingerprints/stats): relaxed
    # tiers lose the columns the fingerprint situation index keys on.
    if req.venue:
        join_sql = """
            FROM player_hands ph INDEXED BY idx_ph_venue_hand
            JOIN fingerprints fp
                ON fp.hand_id = ph.hand_id AND fp.file = ph.file AND fp.player_idx = ph.seat_idx
        """
        where_full = f"ph.venue = ? AND {where}"
        venue_params = [req.venue]
    else:
        join_sql = """
            FROM fingerprints fp
            JOIN player_hands ph INDEXED BY idx_ph_hand
                ON ph.hand_id = fp.hand_id AND ph.file = fp.file AND ph.seat_idx = fp.player_idx
        """
        where_full = where
        venue_params = []

    con = get_connection()
    try:
        # COUNT has no tier CASE in its SQL text — venue param then WHERE's.
        total: int = con.execute(
            f"SELECT COUNT(*) {join_sql} WHERE {where_full}",
            [*venue_params, *where_params],
        ).fetchone()[0]

        # SQL-text placeholder order: CASE (select list) → venue → WHERE.
        rows = con.execute(f"""
            SELECT fp.hand_id, fp.file, fp.player_idx, fp.street, fp.positions,
                   fp.n_players_street, fp.pot_type, fp.in_position, fp.facing,
                   fp.spr_bucket, fp.board_high_card, fp.board_paired, fp.board_monotone,
                   fp.board_two_tone, fp.board_connectedness,
                   ph.player_id, ph.position, ph.n_players, ph.stack, ph.invested,
                   ph.winnings, ph.net_won, ph.venue, ph.big_blind, ph.date
                   {tier_select}
            {join_sql}
            WHERE {where_full}
            {order}
            LIMIT ? OFFSET ?
        """, [*case_params, *venue_params, *where_params, limit, offset]).fetchall()

        hands = [_cast_fp_bools(dict(row)) for row in rows]

        return {
            'hands': hands, 'total': total, 'limit': limit, 'offset': offset,
            'tier_labels': FUZZY_TIER_LABELS if req.fuzzy else None,
        }
    finally:
        con.close()


@app.post("/query")
def run_query(req: QueryRequest) -> dict:
    filter_sql, params = build_filter_sql(req.filters)
    show_scotty = not any(
        f.type == 'venue' and f.value not in (None, 'any', '888poker')
        for f in req.filters
    )

    if "LIMIT 500000" in filter_sql:
        return {
            'total_hands': -1,
            'showdown_pct': 0.0,
            'avg_pot_bb': 0.0,
            'message': 'Set at least one filter before running a query.',
        }

    con = get_connection()
    try:
        # Materialise filter results once; all stat queries reuse the in-memory temp table.
        # The covering index idx_ph_hand_stats means subsequent joins never touch the main
        # player_hands table pages — they read only the ~300 MB index.
        con.execute(f"CREATE TEMP TABLE _vh AS {filter_sql}", params)
        con.execute("CREATE UNIQUE INDEX _vh_idx ON _vh(hand_id)")

        total_hands: int = con.execute("SELECT COUNT(*) FROM _vh").fetchone()[0]

        if total_hands == 0:
            return {'total_hands': 0, 'showdown_pct': 0.0, 'avg_pot_bb': 0.0,
                    'scotty_hands': 0 if show_scotty else None,
                    'scotty_won_pct': None, 'scotty_bb_per_100': None}

        # Too many hands — skip expensive stats
        if total_hands > 1_000_000:
            return {
                'total_hands': total_hands,
                'showdown_pct': 0.0,
                'avg_pot_bb': 0.0,
                'scotty_hands': None,
                'scotty_won_pct': None,
                'scotty_bb_per_100': None,
                'message': f'{total_hands:,} matching hands — add more filters to see stats.',
            }

        # Showdown %
        showdown_count: int = con.execute("""
            SELECT COUNT(DISTINCT l.hand_id)
            FROM _vh JOIN labels l ON l.hand_id = _vh.hand_id AND l.label = 'showdown'
        """).fetchone()[0]
        showdown_pct = round(100.0 * showdown_count / total_hands, 1)

        # Avg pot in BB — aggregate per hand first to avoid multi-player row inflation
        avg_pot_val = con.execute("""
            SELECT AVG(pot_bb) FROM (
                SELECT ph.hand_id, SUM(ph.invested) / AVG(ph.big_blind) AS pot_bb
                FROM _vh JOIN player_hands ph ON ph.hand_id = _vh.hand_id
                WHERE ph.big_blind > 0
                GROUP BY ph.hand_id
            )
        """).fetchone()[0]
        avg_pot_bb = round(float(avg_pot_val), 1) if avg_pot_val else 0.0

        # ScottyWotty aggregate — only when venue includes 888poker
        if show_scotty:
            scotty_row = con.execute("""
                SELECT COUNT(*) AS hands,
                       COUNT(CASE WHEN ph.net_won > 0 THEN 1 END) AS wins,
                       AVG(ph.net_won / ph.big_blind) AS avg_net_bb
                FROM _vh JOIN player_hands ph ON ph.hand_id = _vh.hand_id
                WHERE ph.player_id = 'ScottyWotty'
                  AND ph.net_won IS NOT NULL AND ph.big_blind > 0
            """).fetchone()
            s_hands = scotty_row['hands']
            s_won_pct = round(100.0 * scotty_row['wins'] / s_hands, 1) if s_hands else None
            s_bb100 = (
                round(float(scotty_row['avg_net_bb']) * 100, 1)
                if scotty_row['avg_net_bb'] is not None else None
            )
        else:
            s_hands = None
            s_won_pct = None
            s_bb100 = None

        return {
            'total_hands': total_hands,
            'showdown_pct': showdown_pct,
            'avg_pot_bb': avg_pot_bb,
            'scotty_hands': s_hands,
            'scotty_won_pct': s_won_pct,
            'scotty_bb_per_100': s_bb100,
        }
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Solved Spot Explorer — reads cfr_solver/results/<spot_id>/{spot_spec,strategy}.json
# as plain JSON. No pyspiel/cfr_solver import here by design: src/ and cfr_solver/
# are separate venvs coupled only via these JSON files on disk.
# ---------------------------------------------------------------------------

def _spot_engine(spot_id: str) -> Optional[str]:
    """'texas' | None — whether a solved TexasSolver output exists."""
    base = os.path.join(CFR_RESULTS_DIR, spot_id)
    if os.path.exists(os.path.join(base, 'texas_output.json')):
        return 'texas'
    return None


def _spot_summary(spot_id: str, engine: str) -> dict:
    with open(os.path.join(CFR_RESULTS_DIR, spot_id, 'spot_spec.json')) as f:
        spec = json.load(f)
    bet_sizes: list[float] = []
    ranges = spec.get('ranges')
    oop_hands, ip_hands = _range_hands_from_spec(ranges)
    return {
        'spot_id': spot_id,
        'engine': engine,
        'positions': spec['positions'],
        'street': spec['street'],
        'board': spec['board'],
        'effective_stack_bb': spec['effective_stack_bb'],
        'pot_bb_at_street_start': spec['pot_bb_at_street_start'],
        'action_abstraction': spec.get('action_abstraction', 'bet_buckets'),
        'bet_sizes_bb': bet_sizes,
        'n_matching_hands': spec.get('n_matching_hands', 0),
        'fingerprint_type': spec.get('fingerprint_type'),
        'source': spec.get('source'),
        'ranges': ranges,
        'oop_range_hands': oop_hands,
        'ip_range_hands': ip_hands,
    }


def _range_hands_from_spec(ranges: Optional[dict]) -> tuple[Optional[list], Optional[list]]:
    """Canonical hands in each seat's assumed range, via cfr_solver's Chen
    ranking (dependency-free module, imported across the venv boundary)."""
    if not ranges:
        return None, None
    sys.path.insert(0, str(Path(__file__).parent.parent / 'cfr_solver'))
    import hand_ranking
    oop_pct = (ranges.get('oop') or {}).get('range_pct')
    ip_pct = (ranges.get('ip') or {}).get('range_pct')
    oop = sorted(hand_ranking.top_pct_hands(oop_pct)) if oop_pct is not None else None
    ip = sorted(hand_ranking.top_pct_hands(ip_pct)) if ip_pct is not None else None
    return oop, ip


@app.get("/spots")
def list_spots() -> list[dict]:
    if not os.path.isdir(CFR_RESULTS_DIR):
        return []
    summaries = []
    for spot_id in sorted(os.listdir(CFR_RESULTS_DIR)):
        engine = _spot_engine(spot_id)
        spec_path = os.path.join(CFR_RESULTS_DIR, spot_id, 'spot_spec.json')
        if engine is None or not os.path.exists(spec_path):
            continue
        summaries.append(_spot_summary(spot_id, engine))
    return summaries


@app.get("/spots/{spot_id}")
def get_spot_detail(spot_id: str) -> dict:
    engine = _spot_engine(spot_id)
    if engine is None:
        raise HTTPException(404, f"No solved spot found for spot_id={spot_id!r}")
    summary = _spot_summary(spot_id, engine)
    return {'summary': summary, 'nodes': []}


# ---------------------------------------------------------------------------
# TexasSolver strategy trees — texas_output.json is served directly (lazily
# loaded + cached), with per-exact-combo strategies pooled into canonical
# rank/suitedness classes at request time. Dump conventions (verified):
# action node {node_type:'action', player: 0=IP|1=OOP, actions,
# strategy:{actions,strategy:{combo:[probs]}}, childrens}; chance node
# {node_type:'chance', dealcards:{card: node}}.
# ---------------------------------------------------------------------------

_TEXAS_CACHE: dict[str, dict] = {}
_TEXAS_CACHE_MAX = 1   # dumps are ~124 MB JSON (~1 GB parsed) — cache one tree

_RANK_DISPLAY_ORDER = 'AKQJT98765432'


def _load_texas_tree(spot_id: str) -> dict:
    if spot_id in _TEXAS_CACHE:
        return _TEXAS_CACHE[spot_id]
    path = os.path.join(CFR_RESULTS_DIR, spot_id, 'texas_output.json')
    if not os.path.exists(path):
        raise HTTPException(404, f"No TexasSolver output for spot_id={spot_id!r}")
    with open(path) as f:
        tree = json.load(f)
    if len(_TEXAS_CACHE) >= _TEXAS_CACHE_MAX:
        _TEXAS_CACHE.pop(next(iter(_TEXAS_CACHE)))
    _TEXAS_CACHE[spot_id] = tree
    return tree


class TreePathStep(BaseModel):
    kind: str    # 'action' | 'chance'
    value: str   # action label (e.g. 'BET 2.750000') or card (e.g. 'Td')


class TreeNodeRequest(BaseModel):
    path: list[TreePathStep] = []
    hero_combo: Optional[str] = None   # e.g. 'AsKs' — exact frequencies returned if present


def _walk_texas(tree: dict, path: list[TreePathStep]) -> dict:
    node = tree
    for step in path:
        if step.kind == 'action':
            children = node.get('childrens') or {}
            if step.value not in children:
                raise HTTPException(404, f"No child action {step.value!r} at this node")
            node = children[step.value]
        elif step.kind == 'chance':
            cards = node.get('dealcards') or {}
            if step.value not in cards:
                raise HTTPException(404, f"No dealcard {step.value!r} at this node")
            node = cards[step.value]
        else:
            raise HTTPException(422, f"Unknown path step kind {step.kind!r}")
    return node


def _canonical_class(combo: str) -> tuple[str, str, str]:
    """'Ah5s' -> ('A5o', 'A', '5'); suited/pair aware. Combo is 4 chars."""
    r1, s1, r2, s2 = combo[0], combo[1], combo[2], combo[3]
    if _RANK_DISPLAY_ORDER.index(r1) > _RANK_DISPLAY_ORDER.index(r2):
        r1, s1, r2, s2 = r2, s2, r1, s1
    if r1 == r2:
        return r1 + r2, r1, r2
    return r1 + r2 + ('s' if s1 == s2 else 'o'), r1, r2


# ---------------------------------------------------------------------------
# Hand-category classification — buckets each combo into a GTO+-style made-
# hand / draw category relative to the board, for the range composition
# chart. Uses treys (already a project dependency) purely for made-hand rank
# class; pair sub-classing (top/middle/weak/overpair) and draw detection are
# done by hand since treys only exposes the coarse rank class.
# ---------------------------------------------------------------------------

_HAND_EVALUATOR = Evaluator()
_RANK_VALUE = {r: i for i, r in enumerate('23456789TJQKA', start=2)}

_MADE_HAND_ORDER = [
    'Straight Flush', 'Four of a Kind', 'Full House', 'Flush', 'Straight',
    'Three of a Kind', 'Two Pair', 'Overpair', 'Top Pair', 'Middle Pair',
    'Weak Pair', 'No Made Hand',
]
_DRAW_ORDER = ['Flush Draw', 'Open-Ended Straight Draw', 'Gutshot']


def _pair_subclass(hole_ranks: tuple[str, str], board_ranks: list[str]) -> str:
    """Only called when treys already classified the 7-card hand as exactly
    one pair (i.e. not two pair/trips+), so at most one hole rank matches a
    board rank."""
    uniq_board = sorted(set(board_ranks), key=lambda r: -_RANK_VALUE[r])
    r1, r2 = hole_ranks
    if r1 == r2:
        # Pocket pair not matching any board card (else treys would have
        # classified it as trips, not a pair).
        return 'Overpair' if _RANK_VALUE[r1] > _RANK_VALUE[uniq_board[0]] else 'Weak Pair'
    matched = r1 if r1 in uniq_board else r2
    idx = uniq_board.index(matched)
    if idx == 0:
        return 'Top Pair'
    if idx == 1:
        return 'Middle Pair'
    return 'Weak Pair'


def _straight_draw_kind(ranks: list[str]) -> Optional[str]:
    """'Open-Ended Straight Draw' | 'Gutshot' | None, from up to 7 ranks
    (hole + board). Aces count both high and low for wheel straights."""
    vals = {_RANK_VALUE[r] for r in ranks}
    if 14 in vals:
        vals.add(1)
    gutshot = None
    for low in range(1, 11):   # windows [low..low+4]: A-5 .. T-A
        window = set(range(low, low + 5))
        overlap = vals & window
        if len(overlap) == 4:
            missing = next(iter(window - overlap))
            if missing in (low, low + 4):
                return 'Open-Ended Straight Draw'
            gutshot = 'Gutshot'
    return gutshot


def _classify_combo(combo: str, board: str) -> dict:
    hole = [combo[0:2], combo[2:4]]
    board_cards = [board[i:i + 2] for i in range(0, len(board), 2)]
    score = _HAND_EVALUATOR.evaluate(
        [TreysCard.new(c) for c in board_cards], [TreysCard.new(c) for c in hole])
    class_name = _HAND_EVALUATOR.class_to_string(_HAND_EVALUATOR.get_rank_class(score))

    if class_name == 'Pair':
        made = _pair_subclass((hole[0][0], hole[1][0]), [c[0] for c in board_cards])
    elif class_name == 'High Card':
        made = 'No Made Hand'
    else:
        made = class_name

    draws = []
    all_cards = hole + board_cards
    suit_counts: dict[str, int] = {}
    for c in all_cards:
        suit_counts[c[1]] = suit_counts.get(c[1], 0) + 1
    if any(n == 4 for n in suit_counts.values()):
        draws.append('Flush Draw')
    sd = _straight_draw_kind([c[0] for c in all_cards])
    if sd:
        draws.append(sd)

    return {'made': made, 'draws': draws}


def _pool_texas_by_category(node: dict, board: str) -> list[dict]:
    """Same per-combo strategy dict as _pool_texas_strategy, aggregated by
    hand category instead of canonical rank/suit class. 'frequencies' here
    are raw summed action-probabilities (i.e. weighted combo counts) rather
    than an average — they sum to n_combos, matching GTO+'s convention of
    showing e.g. "73.2 (18/55.3)" per category."""
    strat = (node.get('strategy') or {}).get('strategy') or {}
    n_actions = len((node.get('strategy') or {}).get('actions') or [])
    made_groups: dict[str, dict] = {}
    draw_groups: dict[str, dict] = {}

    for combo, probs in strat.items():
        cls = _classify_combo(combo, board)
        g = made_groups.setdefault(cls['made'], {'totals': [0.0] * n_actions, 'n': 0})
        g['n'] += 1
        for i, p in enumerate(probs):
            g['totals'][i] += p
        for d in cls['draws']:
            gd = draw_groups.setdefault(d, {'totals': [0.0] * n_actions, 'n': 0})
            gd['n'] += 1
            for i, p in enumerate(probs):
                gd['totals'][i] += p

    def _finalize(groups: dict[str, dict], order: list[str]) -> list[dict]:
        return [
            {
                'category': name,
                'n_combos': groups[name]['n'],
                'frequencies': {str(i): t for i, t in enumerate(groups[name]['totals'])},
            }
            for name in order if name in groups
        ]

    return _finalize(made_groups, _MADE_HAND_ORDER) + _finalize(draw_groups, _DRAW_ORDER)


def _pool_texas_strategy(node: dict) -> tuple[list[dict], dict]:
    """Pool per-exact-combo strategies into rank/suitedness classes, in the
    canonical_groups shape the frontend's RangeBreakdownTable renders (BIG/
    OTHER suit tags unused here — all cards tagged OTHER, which routes the
    display through the plain suited/offsuit labels)."""
    strat = (node.get('strategy') or {}).get('strategy') or {}
    groups: dict[str, dict] = {}
    n_actions = len((node.get('strategy') or {}).get('actions') or [])
    agg_totals = [0.0] * n_actions
    total_n = 0

    for combo, probs in strat.items():
        cls, hi, lo = _canonical_class(combo)
        g = groups.setdefault(cls, {
            'canonical_key': [[hi, 'OTHER'], [lo, 'OTHER']],
            'members': [], 'totals': [0.0] * n_actions,
        })
        g['members'].append(combo)
        for i, p in enumerate(probs):
            g['totals'][i] += p
            agg_totals[i] += p
        total_n += 1

    canonical_groups = []
    for g in groups.values():
        n = len(g['members'])
        canonical_groups.append({
            'canonical_key': g['canonical_key'],
            'members': g['members'],
            'frequencies': {str(i): t / n for i, t in enumerate(g['totals'])},
        })
    aggregate = {str(i): (t / total_n if total_n else 0.0) for i, t in enumerate(agg_totals)}
    return canonical_groups, aggregate


@app.post("/spots/{spot_id}/tree-node")
def get_texas_tree_node(spot_id: str, req: TreeNodeRequest) -> dict:
    tree = _load_texas_tree(spot_id)
    node = _walk_texas(tree, req.path)

    # Chance nodes carry 'dealcards' (node_type is 'chance_node' in the dump,
    # but structural detection is more robust than string matching).
    if 'dealcards' in node:
        return {
            'node_type': 'chance',
            'cards': sorted((node.get('dealcards') or {}).keys()),
        }

    actions = (node.get('strategy') or {}).get('actions') or node.get('actions') or []
    children = node.get('childrens') or {}
    options = []
    for i, label in enumerate(actions):
        child = children.get(label)
        if child is None:
            nxt = 'terminal'
            chance_cards = None
        elif 'dealcards' in child:
            nxt = 'chance'
            chance_cards = sorted((child.get('dealcards') or {}).keys())
        else:
            nxt = 'action'
            chance_cards = None
        options.append({'action': i, 'label': label, 'next': nxt, 'chance_cards': chance_cards})

    canonical_groups, aggregate = _pool_texas_strategy(node)

    hero_frequencies = None
    if req.hero_combo:
        strat = (node.get('strategy') or {}).get('strategy') or {}
        for candidate in (req.hero_combo, req.hero_combo[2:] + req.hero_combo[:2]):
            if candidate in strat:
                hero_frequencies = {str(i): p for i, p in enumerate(strat[candidate])}
                break

    # Board at this node = the spec's starting board plus any turn/river
    # cards dealt along the walked path. Category classification needs a
    # real board (>=3 cards) — omitted (empty list) for preflop nodes.
    with open(os.path.join(CFR_RESULTS_DIR, spot_id, 'spot_spec.json')) as f:
        board = (json.load(f).get('board') or '')
    board += ''.join(step.value for step in req.path if step.kind == 'chance')
    category_groups = _pool_texas_by_category(node, board) if len(board) >= 6 else []

    return {
        'node_type': 'action',
        # Dump convention: player 1 = OOP, 0 = IP. Normalize to a role string.
        'acting_role': 'oop' if node.get('player') == 1 else 'ip',
        'options': options,
        'canonical_groups': canonical_groups,
        'category_groups': category_groups,
        'aggregate': aggregate,
        'hero_frequencies': hero_frequencies,
        'board': board,
    }


# ---------------------------------------------------------------------------
# Line EV — walks a solved TexasSolver tree range-vs-range to score the EV of
# the hero's chosen line against the solver's own strategy. The solver
# strategy is held fixed for BOTH players: villain combos are reach-weighted
# by that strategy plus card removal, and at each hero decision node every
# legal action's EV for the hero's exact combo is expanded so "your line" can
# be compared to the solver's best action.
#
# walk() returns (num, den) where num = Σ_c vreach(c)·payoff_hero(c) and
# den = Σ_c vreach(c); EV = num/den. This composes cleanly through chance
# nodes (uniform average over listed runouts) and villain nodes (each child
# takes vreach·strat[c][i]).
#
# Terminals: FOLD -> folder loses only their invested chips; a river
# check/call -> showdown via treys; an action whose subtree the depth-limited
# dump pruned (dump_rounds) is scored by assuming the hero realises raw
# equity for the rest of the hand — flagged `approx` on that row.
# ---------------------------------------------------------------------------

_SUITS = 'cdhs'
_ALL_CARDS = [r + s for r in _RANK_DISPLAY_ORDER for s in _SUITS]


def _parse_cmd_range(text: str, key: str) -> Optional[list[str]]:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(key):
            return [h.strip() for h in line[len(key):].strip().split(',') if h.strip()]
    return None


def _spec_range_combos(spot_id: str, spec: dict, dead: set[str]):
    """(oop, ip) each as {('Ah','Kh'): weight}. Prefers the exact ranges in
    solver_commands.txt; falls back to Chen top-pct from the spec."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'cfr_solver'))
    import hand_ranking

    cmd_path = os.path.join(CFR_RESULTS_DIR, spot_id, 'solver_commands.txt')
    oop_hands = ip_hands = None
    if os.path.exists(cmd_path):
        txt = open(cmd_path).read()
        oop_hands = _parse_cmd_range(txt, 'set_range_oop')
        ip_hands = _parse_cmd_range(txt, 'set_range_ip')

    ranges = spec.get('ranges') or {}
    if oop_hands is None:
        pct = (ranges.get('oop') or {}).get('range_pct')
        oop_hands = sorted(hand_ranking.top_pct_hands(pct)) if pct else []
    if ip_hands is None:
        pct = (ranges.get('ip') or {}).get('range_pct')
        ip_hands = sorted(hand_ranking.top_pct_hands(pct)) if pct else []

    def to_combos(hands: list[str]) -> dict:
        out: dict[tuple[str, str], float] = {}
        for h in hands:
            w = 1.0
            if ':' in h:
                h, wtxt = h.split(':', 1)
                try:
                    w = float(wtxt)
                except ValueError:
                    w = 1.0
            h = h.strip().rstrip('+')
            try:
                combos = hand_ranking.expand_to_combos(h)
            except Exception:
                continue
            for a, b in combos:
                if a in dead or b in dead:
                    continue
                out[(a, b)] = w
        return out

    return to_combos(oop_hands), to_combos(ip_hands)


def _bet_total_after(label: str, role: str, sbet: dict) -> float:
    """New street-bet total for `role` after playing `label` (TexasSolver
    labels carry the absolute street total: 'BET 3.0', 'RAISE 9.0')."""
    m = re.match(r'^(?:BET|RAISE)\s+([\d.]+)', label)
    if m:
        return float(m.group(1))
    if label == 'CALL':
        other = 'ip' if role == 'oop' else 'oop'
        return sbet[other]
    return sbet[role]  # CHECK / FOLD


def _showdown_num_den(hero, hero_role, vreach, board, pot0, inv):
    total = pot0 + inv['oop'] + inv['ip']
    bcards = [TreysCard.new(c) for c in board]
    hs = _HAND_EVALUATOR.evaluate(bcards, [TreysCard.new(hero[0]), TreysCard.new(hero[1])])
    blockers = {hero[0], hero[1], *board}
    num = den = 0.0
    for (a, b), w in vreach.items():
        if a in blockers or b in blockers:
            continue
        vs = _HAND_EVALUATOR.evaluate(bcards, [TreysCard.new(a), TreysCard.new(b)])
        share = total if hs < vs else total / 2 if hs == vs else 0.0
        num += w * share
        den += w
    return num - inv[hero_role] * den, den


def _equity_vs_range(hero, vreach, board, dead) -> float:
    """Hero combo equity against the reach-weighted villain range, enumerating
    (capped) runouts when the board is short."""
    need = 5 - len(board)
    used_deck = [c for c in _ALL_CARDS
                 if c not in dead and c not in board and c not in hero]
    runouts = list(itertools.combinations(used_deck, need)) if need else [()]
    if len(runouts) > 300:
        runouts = random.Random(0).sample(runouts, 300)
    hcards = [TreysCard.new(hero[0]), TreysCard.new(hero[1])]
    num = den = 0.0
    for (a, b), w in vreach.items():
        if a in hero or b in hero or a in board or b in board:
            continue
        vcards = [TreysCard.new(a), TreysCard.new(b)]
        won = seen = 0.0
        for ro in runouts:
            if a in ro or b in ro:
                continue
            full = [TreysCard.new(c) for c in board] + [TreysCard.new(c) for c in ro]
            hs = _HAND_EVALUATOR.evaluate(full, hcards)
            vs = _HAND_EVALUATOR.evaluate(full, vcards)
            won += 1.0 if hs < vs else 0.5 if hs == vs else 0.0
            seen += 1
        if seen:
            num += w * (won / seen)
            den += w
    return num / den if den else 0.0


def _hero_probs(strat: dict, hero_combo: str, n_actions: int) -> list[float]:
    for cand in (hero_combo, hero_combo[2:] + hero_combo[:2]):
        if cand in strat:
            return list(strat[cand])
    return [1.0 / n_actions] * n_actions   # combo outside assumed range


class LineEvRequest(BaseModel):
    path: list[TreePathStep] = []
    hero_combo: str   # e.g. 'QhJh'


@app.post("/spots/{spot_id}/line-ev")
def get_line_ev(spot_id: str, req: LineEvRequest) -> dict:
    tree = _load_texas_tree(spot_id)
    with open(os.path.join(CFR_RESULTS_DIR, spot_id, 'spot_spec.json')) as f:
        spec = json.load(f)

    start_board = spec.get('board') or ''
    start_board_cards = [start_board[i:i + 2] for i in range(0, len(start_board), 2)]
    pot0 = float(spec['pot_bb_at_street_start'])
    fp = spec.get('fingerprint_type') or {}
    hero_role = 'ip' if fp.get('in_position') else 'oop'
    villain_role = 'oop' if hero_role == 'ip' else 'ip'

    hero = (req.hero_combo[:2], req.hero_combo[2:4])
    path_cards = [s.value for s in req.path if s.kind == 'chance']
    dead = set(start_board_cards) | set(hero) | set(path_cards)
    oop_combos, ip_combos = _spec_range_combos(spot_id, spec, set(start_board_cards) | set(hero))
    vreach = dict(ip_combos if villain_role == 'ip' else oop_combos)

    NA = 'not available in the depth-limited dump'

    def node_role(node: dict) -> str:
        return 'oop' if node.get('player') == 1 else 'ip'

    def _combo_probs(strat: dict, c: tuple, n: int) -> Optional[list]:
        return strat.get(c[0] + c[1]) or strat.get(c[1] + c[0])

    def _after(label, role, inv, sbet):
        nt = _bet_total_after(label, role, sbet)
        add = max(0.0, nt - sbet[role])
        inv2 = dict(inv); inv2[role] += add
        sbet2 = dict(sbet); sbet2[role] = nt
        return inv2, sbet2

    def _terminal(label, role, board, inv2, reach):
        """(num, den) for an action with no stored child — a real terminal,
        or a subtree the depth-limited dump pruned (equity realisation)."""
        d = sum(reach.values())
        if label == 'FOLD':
            if role == hero_role:
                return -inv2[hero_role] * d, d
            pot = pot0 + inv2['oop'] + inv2['ip']
            return (pot - inv2[hero_role]) * d, d
        if len(board) >= 5:
            return _showdown_num_den(hero, hero_role, reach, board, pot0, inv2)
        eq = _equity_vs_range(hero, reach, board, dead)
        pot = pot0 + inv2['oop'] + inv2['ip']
        return (eq * pot - inv2[hero_role]) * d, d

    def _branch(children, label, role, board, inv, sbet, reach):
        inv2, sbet2 = _after(label, role, inv, sbet)
        child = children.get(label)
        if child is None:
            return _terminal(label, role, board, inv2, reach)
        return walk(child, board, inv2, sbet2, reach)

    def walk(node, board, inv, sbet, reach):
        """(num, den) where num = Σ vreach·payoff_hero, den = Σ vreach."""
        den0 = sum(reach.values())
        if den0 <= 0:
            return 0.0, 0.0
        if 'dealcards' in node:
            cards = [c for c in node['dealcards']
                     if c not in board and c not in hero and c not in dead]
            if not cards:
                cards = list(node['dealcards'])
            tn = td = 0.0
            for c in cards:
                sub = {k: v for k, v in reach.items() if c not in k}
                n, d = walk(node['dealcards'][c], board + [c], inv,
                            {'oop': 0.0, 'ip': 0.0}, sub)
                tn += n; td += d
            return tn / len(cards), td / len(cards)

        role = node_role(node)
        actions = (node.get('strategy') or {}).get('actions') or node.get('actions') or []
        strat = (node.get('strategy') or {}).get('strategy') or {}
        children = node.get('childrens') or {}

        if role == hero_role:
            probs = _hero_probs(strat, req.hero_combo, len(actions))
            num = 0.0
            for i, label in enumerate(actions):
                cn, _ = _branch(children, label, role, board, inv, sbet, reach)
                num += probs[i] * cn
            return num, den0

        num = 0.0
        for i, label in enumerate(actions):
            sub = {}
            for c, w in reach.items():
                p = _combo_probs(strat, c, len(actions))
                pi = p[i] if p is not None else 1.0 / len(actions)
                if pi > 0:
                    sub[c] = w * pi
            if not sub:
                continue
            cn, _ = _branch(children, label, role, board, inv, sbet, sub)
            num += cn
        return num, den0

    def hero_option_evs(node, board, inv, sbet, reach):
        """Per-action EV for the hero combo at a hero decision node."""
        role = node_role(node)
        actions = (node.get('strategy') or {}).get('actions') or node.get('actions') or []
        strat = (node.get('strategy') or {}).get('strategy') or {}
        children = node.get('childrens') or {}
        probs = _hero_probs(strat, req.hero_combo, len(actions))
        out = []
        for i, label in enumerate(actions):
            inv2, sbet2 = _after(label, role, inv, sbet)
            child = children.get(label)
            approx = False
            if child is not None:
                cn, cd = walk(child, board, inv2, sbet2, reach)
                ev = cn / cd if cd else 0.0
            else:
                cn, cd = _terminal(label, role, board, inv2, reach)
                ev = cn / cd if cd else 0.0
                approx = label != 'FOLD' and len(board) < 5
            out.append({
                'action': i, 'label': label, 'pretty': _pretty_ev_label(label),
                'ev': round(ev, 3), 'solver_freq': round(probs[i], 4), 'approx': approx,
            })
        return out

    # --- walk the requested path, scoring every hero decision on the way ---
    node = tree
    board = list(start_board_cards)
    inv = {'oop': 0.0, 'ip': 0.0}
    sbet = {'oop': 0.0, 'ip': 0.0}
    reach = dict(vreach)
    rows: list[dict] = []

    for step in req.path:
        if 'dealcards' in node:
            reach = {k: v for k, v in reach.items() if step.value not in k}
            node = node['dealcards'].get(step.value)
            if node is None:
                raise HTTPException(404, f"No dealcard {step.value!r} on the walked path")
            board = board + [step.value]
            sbet = {'oop': 0.0, 'ip': 0.0}
            continue

        role = node_role(node)
        actions = (node.get('strategy') or {}).get('actions') or node.get('actions') or []
        strat = (node.get('strategy') or {}).get('strategy') or {}
        children = node.get('childrens') or {}
        street = ('preflop', 'flop', 'turn', 'river')[max(0, len(board) - 2)] if board else 'preflop'

        if role == hero_role and step.kind == 'action':
            opts = hero_option_evs(node, board, inv, sbet, reach)
            best = max(opts, key=lambda o: o['ev'])
            chosen = next((o for o in opts if o['label'] == step.value), None)
            if chosen is not None:
                rows.append({
                    'street': street, 'actor': 'hero',
                    'chosen_label': chosen['label'], 'chosen_pretty': chosen['pretty'],
                    'chosen_ev': chosen['ev'], 'solver_freq': chosen['solver_freq'],
                    'best_label': best['label'], 'best_pretty': best['pretty'],
                    'best_ev': best['ev'],
                    'ev_delta': round(chosen['ev'] - best['ev'], 3),
                    'approx': chosen['approx'], 'options': opts,
                })
        elif step.kind == 'action':
            rows.append({
                'street': street, 'actor': 'villain',
                'chosen_label': step.value, 'chosen_pretty': _pretty_ev_label(step.value),
                'chosen_ev': None, 'solver_freq': None,
                'best_label': None, 'best_pretty': None, 'best_ev': None,
                'ev_delta': None, 'approx': False, 'options': [],
            })
            # Bayes-update villain reach on the observed action
            if actions and step.value in actions:
                i = actions.index(step.value)
                nr = {}
                for c, w in reach.items():
                    p = _combo_probs(strat, c, len(actions))
                    pi = p[i] if p is not None else 1.0 / len(actions)
                    if pi > 0:
                        nr[c] = w * pi
                reach = nr or reach

        # advance state past this step
        role = node_role(node)
        new_total = _bet_total_after(step.value, role, sbet)
        add = max(0.0, new_total - sbet[role])
        inv[role] += add
        sbet[role] = new_total
        node = children.get(step.value)
        if node is None:
            break

    # --- current node summary (action mix / combo panel) ---
    current = None
    if node is not None and 'dealcards' not in node:
        role = node_role(node)
        actions = (node.get('strategy') or {}).get('actions') or node.get('actions') or []
        strat = (node.get('strategy') or {}).get('strategy') or {}
        agg = [0.0] * len(actions)
        for probs in strat.values():
            for i, p in enumerate(probs):
                agg[i] += p
        n = len(strat) or 1
        hero_probs = _hero_probs(strat, req.hero_combo, len(actions)) if strat else []
        combo_actions = []
        if role == hero_role:
            combo_actions = [
                {'action': o['action'], 'label': o['label'], 'pretty': o['pretty'],
                 'ev': o['ev'], 'solver_freq': o['solver_freq']}
                for o in hero_option_evs(node, board, inv, sbet, reach)
            ]
        current = {
            'actor': 'hero' if role == hero_role else 'villain',
            'acting_role': role,
            'action_mix': [
                {'action': i, 'label': l, 'pretty': _pretty_ev_label(l),
                 'freq': round(agg[i] / n, 4)}
                for i, l in enumerate(actions)
            ],
            'hero_action_mix': [
                {'action': i, 'label': l, 'pretty': _pretty_ev_label(l),
                 'freq': round(hero_probs[i], 4)}
                for i, l in enumerate(actions)
            ] if hero_probs else None,
            'combo_actions': combo_actions,
        }

    losses = [r['ev_delta'] for r in rows if r['ev_delta'] is not None and r['ev_delta'] < -1e-6]
    hero_rows = [r for r in rows if r['actor'] == 'hero' and r['ev_delta'] is not None]
    leak = min(hero_rows, key=lambda r: r['ev_delta']) if hero_rows else None

    combo_equity = _equity_vs_range(hero, reach, board, dead)
    cls = _classify_combo(req.hero_combo, ''.join(board)) if len(board) >= 3 else {'made': None, 'draws': []}
    hand_class = ' + '.join([p for p in ([cls['made']] + cls['draws']) if p and p != 'No Made Hand']) \
        or (cls['made'] or 'High card')

    return {
        'spot_id': spot_id,
        'hero_role': hero_role,
        'hero_combo': req.hero_combo,
        'board': ''.join(board),
        'pot_bb': pot0,
        'line': rows,
        'total_ev_loss': round(sum(losses), 3),
        'largest_leak': None if leak is None or leak['ev_delta'] > -1e-6 else {
            'street': leak['street'],
            'chosen_pretty': leak['chosen_pretty'],
            'best_pretty': leak['best_pretty'],
            'ev_delta': leak['ev_delta'],
            'solver_best_freq': leak.get('solver_freq'),
            'approx': leak['approx'],
        },
        'current_node': current,
        'combo': {
            'combo': req.hero_combo,
            'hand_class': hand_class,
            'equity_vs_range': round(combo_equity, 4),
            'actions': current['combo_actions'] if current else [],
        },
        'notes': NA,
    }


def _pretty_ev_label(label: str) -> str:
    m = re.match(r'^(BET|RAISE)\s+([\d.]+)$', label)
    if m:
        amt = float(m.group(2))
        return f"{'Bet' if m.group(1) == 'BET' else 'Raise to'} {amt:g} BB"
    return label.capitalize()


class SpotLookupRequest(BaseModel):
    fingerprint_type: FingerprintKey
    max_tier: int = 4


def _key_matches_at_tier(key: dict, cand: dict, tier: int) -> bool:
    """Python-side mirror of _tier_predicate for in-memory spot_index lookup."""
    def eq(col: str) -> bool:
        return key.get(col) == cand.get(col)

    for col in ('street', 'n_players_street', 'pot_type', 'in_position',
                'board_high_card', 'board_paired'):
        if not eq(col):
            return False
    if tier < 4 and not eq('positions'):
        return False
    if tier < 3:
        if not (eq('facing') and eq('board_monotone') and eq('board_two_tone')):
            return False
    else:
        if key.get('board_monotone') is not None and not eq('board_monotone'):
            return False
    if tier < 2:
        if not eq('spr_bucket'):
            return False
    else:
        widened = _adjacent_sprs(key.get('spr_bucket'))
        if widened is not None and cand.get('spr_bucket') not in widened:
            return False
        if widened is None and key.get('spr_bucket') != cand.get('spr_bucket'):
            return False
    if tier < 1 and not eq('board_connectedness'):
        return False
    return True


@app.post("/spots/lookup")
def lookup_solved_spot(req: SpotLookupRequest) -> dict:
    """Best stored solution for a fingerprint: every solved spot's
    fingerprint_type is checked against the same relaxation ladder used for
    fuzzy hand matching; the tightest-tier match wins."""
    key = req.fingerprint_type.model_dump()
    max_tier = max(0, min(req.max_tier, len(FUZZY_TIER_LABELS) - 1))

    candidates = []
    if os.path.isdir(CFR_RESULTS_DIR):
        for spot_id in sorted(os.listdir(CFR_RESULTS_DIR)):
            engine = _spot_engine(spot_id)
            spec_path = os.path.join(CFR_RESULTS_DIR, spot_id, 'spot_spec.json')
            if engine is None or not os.path.exists(spec_path):
                continue
            with open(spec_path) as f:
                spec = json.load(f)
            fp = spec.get('fingerprint_type')
            if fp:
                candidates.append((spot_id, engine, fp, spec))

    for tier in range(max_tier + 1):
        for spot_id, engine, fp, spec in candidates:
            if _key_matches_at_tier(key, fp, tier):
                return {
                    'spot_id': spot_id,
                    'engine': engine,
                    'match_tier': tier,
                    'match_label': FUZZY_TIER_LABELS[tier],
                    # Fingerprints identify texture classes, not exact cards —
                    # surface which concrete board the stored solve used.
                    'board': spec.get('board'),
                    'street': spec.get('street'),
                }
    return {'spot_id': None, 'engine': None, 'match_tier': None, 'match_label': None,
            'board': None, 'street': None}


# ---------------------------------------------------------------------------
# Fingerprint hand replay — precomputes every step's HandState snapshot
# server-side via the existing pygame replayer's (pygame-free) state machine.
# ---------------------------------------------------------------------------

class ReplayRequest(BaseModel):
    file: str
    venue: str


@app.post("/hands/{hand_id}/replay")
def get_hand_replay(hand_id: int, req: ReplayRequest) -> dict:
    hands = load_hands_by_id([(hand_id, req.file, req.venue)])
    if not hands:
        raise HTTPException(404, f"Hand {hand_id} not found in file {req.file!r}")
    hand = hands[0]

    session = ReplaySession(hand)
    steps = []
    while True:
        s = session.state
        steps.append({
            'step': s.step,
            'display_step': session.display_step,
            'stacks': s.stacks,
            'street_bets': s.street_bets,
            'pot': s.pot,
            'total_pot': s.total_pot,
            'board': s.board,
            'hole_cards': {str(k): v for k, v in s.hole_cards.items()},
            'shown_cards': {str(k): v for k, v in s.shown_cards.items()},
            'folded': sorted(s.folded),
            'street': s.street,
            'action_log': list(s.action_log),
            'current_actor': s.current_actor,
            'hand_over': s.hand_over,
        })
        if not session.can_advance():
            break
        session.advance()

    big_blind = hand.blinds_or_straddles[1] if len(hand.blinds_or_straddles) > 1 else None
    return {
        'hand_id': hand.hand_id,
        'players': hand.players,
        'positions': assign_positions(hand),
        'big_blind': big_blind,
        'steps': steps,
    }


# ---------------------------------------------------------------------------
# Hand Builder — construct a from-scratch table situation (2-6 players), run
# it through the same fingerprint.py/hand_utils.py logic real hands go
# through (via a synthetic in-memory Hand), so "this situation" means the
# same thing here as it does everywhere else in the app. Actions use the
# same .phhs action grammar as everything else (e.g. 'p3 cbr 3.5', 'p4 f'),
# with the DB's seat convention: p1=SB, p2=BB, ..., pN=BTN
# (hand_utils.assign_positions). Stacks/blinds are expressed directly in BB
# units (blinds fixed at [0.5, 1.0]) so every derived pot/stack number is
# already "in BB", matching the rest of the app's convention.
# ---------------------------------------------------------------------------

_HB_STREET_ORDER = ['preflop', 'flop', 'turn', 'river']
_SPOT_ID_RE = re.compile(r'^[A-Za-z0-9_-]+$')
_HB_SPOTS_DIR = Path(__file__).parent.parent / 'cfr_solver' / 'spots'


class TableDeriveRequest(BaseModel):
    n_players: int
    stacks_bb: list[float]
    hero_seat: int                      # 1-based; p1=SB ... pN=BTN
    preflop_actions: list[str] = []
    flop_actions: list[str] = []
    flop_board: Optional[str] = None
    turn_actions: list[str] = []
    turn_board: Optional[str] = None
    river_actions: list[str] = []
    river_board: Optional[str] = None
    current_street: str


def _build_synthetic_hand(req: TableDeriveRequest) -> Hand:
    cur_idx = _HB_STREET_ORDER.index(req.current_street)
    actions: list[str] = list(req.preflop_actions)

    for idx, (street, board, street_actions) in enumerate([
        ('flop', req.flop_board, req.flop_actions),
        ('turn', req.turn_board, req.turn_actions),
        ('river', req.river_board, req.river_actions),
    ], start=1):
        if cur_idx < idx:
            break
        if not board:
            raise HTTPException(422, f"{street}_board is required when current_street is {req.current_street}")
        actions.append(f"d db {board}")
        actions.extend(street_actions)

    return Hand(
        hand_id=0, file='hand_builder', variant='NT', ante_trimming_status=False,
        antes=[], blinds_or_straddles=[0.5, 1.0], min_bet=1.0,
        starting_stacks=list(req.stacks_bb),
        actions=actions, venue='hand_builder', time='',
        day=1, month=1, year=2000, seats=list(range(1, req.n_players + 1)),
        table='hand_builder',
        players=[f'P{i}' for i in range(1, req.n_players + 1)],
        winnings=None, currency_symbol='$', time_zone_abbreviation='ET',
    )


def _board_through(req: TableDeriveRequest, street: str) -> Optional[str]:
    if street == 'preflop':
        return None
    parts = [req.flop_board]
    if street in ('turn', 'river'):
        parts.append(req.turn_board)
    if street == 'river':
        parts.append(req.river_board)
    return ''.join(p for p in parts if p) or None


@app.post("/hand-builder/derive")
def derive_hand_builder(req: TableDeriveRequest) -> dict:
    if req.current_street not in _HB_STREET_ORDER:
        raise HTTPException(422, "current_street must be preflop, flop, turn, or river")
    if not (2 <= req.n_players <= 6):
        raise HTTPException(422, "n_players must be 2-6")
    if len(req.stacks_bb) != req.n_players:
        raise HTTPException(422, "stacks_bb must have one entry per player")
    if not (1 <= req.hero_seat <= req.n_players):
        raise HTTPException(422, "hero_seat out of range")

    hand = _build_synthetic_hand(req)
    fps = fingerprint.compute_fingerprints(hand)
    by_key = {(fp.player_idx, fp.street): fp for fp in fps}

    hero_fp = by_key.get((req.hero_seat, req.current_street))
    if hero_fp is None:
        raise HTTPException(422, "Hero is not in the hand at the current street (folded earlier?)")

    fp_dict = hero_fp.as_dict()
    fingerprint_type = {c: fp_dict[c] for c in FP_TYPE_COLUMNS}

    positions = fingerprint._resolve_positions(hand, hand_utils.split_streets(hand.actions)[0])

    cur_idx = _HB_STREET_ORDER.index(req.current_street)
    street_progression = []
    for s in _HB_STREET_ORDER[:cur_idx + 1]:
        s_stacks, s_pot, s_in = hand_utils.street_start_state(hand, s)
        street_progression.append({
            'street': s,
            'pot_bb': round(s_pot, 2),
            'stacks_bb': [round(x, 2) for x in s_stacks],
            'players_in': sorted(s_in),
        })

    # Streets the CFR solver can handle: postflop, exactly 2 players in at
    # street start, hero one of them. Each entry is a ready-made payload for
    # POST /hand-builder/export-spot.
    solvable_streets = []
    for s in _HB_STREET_ORDER[1:cur_idx + 1]:
        s_stacks, s_pot, s_in = hand_utils.street_start_state(hand, s)
        if len(s_in) != 2 or req.hero_seat not in s_in:
            continue
        s_fp = by_key.get((req.hero_seat, s))
        if s_fp is None or s_pot <= 0:
            continue
        s_fp_dict = s_fp.as_dict()
        solvable_streets.append({
            'street': s,
            'positions': s_fp_dict['positions'],
            'pot_bb': round(s_pot, 2),
            'effective_stack_bb': round(min(s_stacks[p - 1] for p in s_in), 2),
            'board': _board_through(req, s),
            'fingerprint_type': {c: s_fp_dict[c] for c in FP_TYPE_COLUMNS},
            'hero_is_oop': not s_fp_dict['in_position'],
        })

    return {
        'fingerprint_type': fingerprint_type,
        'positions': {str(k): v for k, v in positions.items()},
        'pot_bb_at_street_start': street_progression[-1]['pot_bb'],
        'effective_stack_bb': round(
            min(street_progression[-1]['stacks_bb'][p - 1] for p in street_progression[-1]['players_in']), 2
        ) if street_progression[-1]['players_in'] else 0.0,
        'street_progression': street_progression,
        'solvable_streets': solvable_streets,
    }


class HandBuilderExportRequest(BaseModel):
    spot_id: str
    fingerprint_type: dict
    street: str
    positions: str
    effective_stack_bb: float
    pot_bb_at_street_start: float
    board: Optional[str] = None
    bet_size_fractions: list[float] = []
    n_matching_hands: int = 0
    overwrite: bool = False


@app.post("/hand-builder/export-spot")
def export_hand_builder_spot(req: HandBuilderExportRequest) -> dict:
    if not _SPOT_ID_RE.match(req.spot_id):
        raise HTTPException(422, "spot_id must contain only letters, digits, underscores, and hyphens")

    action_abstraction = 'bet_buckets' if req.bet_size_fractions else 'push_fold'
    ranges = range_charts.infer_spot_roles(req.positions, req.fingerprint_type.get('pot_type'))

    spec = {
        'spot_id': req.spot_id,
        'fingerprint_type': req.fingerprint_type,
        'street': req.street,
        'positions': req.positions,
        'n_matching_hands': req.n_matching_hands,
        'effective_stack_bb': req.effective_stack_bb,
        'pot_bb_at_street_start': req.pot_bb_at_street_start,
        'action_abstraction': action_abstraction,
        'bet_size_fractions': req.bet_size_fractions or None,
        'board': req.board,
        'ranges': ranges,
        'source': {'venue': 'hand_builder', 'generator': 'frontend hand builder'},
    }

    _HB_SPOTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _HB_SPOTS_DIR / f"{req.spot_id}.json"
    if out_path.exists() and not req.overwrite:
        raise HTTPException(409, f"Spot spec {req.spot_id!r} already exists — pass overwrite=true to replace it")
    out_path.write_text(json.dumps(spec, indent=2))

    return {'path': str(out_path), 'spec': spec}


# ---------------------------------------------------------------------------
# Fingerprint aggregate stats — "how did these situations go" for the Hand
# Builder's similar-hands panel. Same fingerprints ⋈ player_hands join as
# /fingerprints/hands; the ScottyWotty aggregate is restricted to rows where
# the fingerprint-matching player IS ScottyWotty (he faced this situation),
# mirroring /query's Scotty block.
# ---------------------------------------------------------------------------

class FingerprintStatsRequest(BaseModel):
    types: list[FingerprintKey]
    venue: Optional[str] = '888poker'
    fuzzy: bool = False
    max_tier: int = 4


def _stats_from_matches(con, tier_where: str = "1=1") -> dict:
    """Aggregate stats over the _fp_matches temp table (optionally a tier slice)."""
    total_hands = con.execute(
        f"SELECT COUNT(DISTINCT hand_id) FROM _fp_matches WHERE {tier_where}"
    ).fetchone()[0]

    # CROSS JOIN pins the join order (matches first, then indexed probes into
    # player_hands) — without it SQLite sometimes flips to scanning the 62M-row
    # table and probing the temp table, which takes minutes instead of ms.
    avg_pot = con.execute(f"""
        SELECT AVG(pot_bb) FROM (
            SELECT ph.hand_id, SUM(ph.invested) / AVG(ph.big_blind) AS pot_bb
            FROM (SELECT DISTINCT hand_id FROM _fp_matches WHERE {tier_where}) m
            CROSS JOIN player_hands ph INDEXED BY idx_ph_hand
                ON ph.hand_id = m.hand_id
            WHERE ph.big_blind > 0
            GROUP BY ph.hand_id
        )
    """).fetchone()[0]

    scotty_row = con.execute(f"""
        SELECT COUNT(*) AS hands,
               SUM(CASE WHEN net_won > 0 THEN 1 ELSE 0 END) AS wins,
               AVG(net_won / big_blind) AS avg_net_bb,
               SUM(net_won / big_blind) AS net_bb
        FROM _fp_matches
        WHERE {tier_where}
          AND player_id = 'ScottyWotty' AND net_won IS NOT NULL AND big_blind > 0
    """).fetchone()

    scotty = None
    if scotty_row['hands']:
        scotty = {
            'hands': scotty_row['hands'],
            'won_pct': round(100.0 * scotty_row['wins'] / scotty_row['hands'], 1),
            'bb_per_100': round(float(scotty_row['avg_net_bb']) * 100, 1),
            'net_bb': round(float(scotty_row['net_bb']), 1),
        }

    return {
        'total_hands': total_hands,
        'avg_pot_bb': round(float(avg_pot), 1) if avg_pot is not None else None,
        'scotty': scotty,
    }


@app.post("/fingerprints/stats")
def get_fingerprint_stats(req: FingerprintStatsRequest) -> dict:
    types = req.types[:50]
    if not types:
        return {'total_hands': 0, 'avg_pot_bb': None, 'scotty': None, 'tiers': None}

    if req.fuzzy:
        case_sql, case_params, where, where_params = _fuzzy_tier_sql(types[0], req.max_tier)
        tier_col = f", {case_sql} AS match_tier"
    else:
        predicates: list[str] = []
        where_params = []
        case_params = []
        for t in types:
            clause, p = _fingerprint_key_predicate(t)
            predicates.append(clause)
            where_params.extend(p)
        where = "(" + " OR ".join(predicates) + ")"
        tier_col = ", 0 AS match_tier"

    con = get_connection()
    try:
        if req.venue:
            # Venue-first join (same pattern as /fingerprints/distribution):
            # relaxed-tier predicates lose the selective columns the
            # fingerprint situation index needs, so start from the small
            # venue slice and probe fingerprints by hand_id instead.
            # Placeholder order in SQL text: CASE (select list) → venue → WHERE.
            con.execute(f"""
                CREATE TEMP TABLE _fp_matches AS
                SELECT fp.hand_id, ph.player_id, ph.net_won, ph.big_blind {tier_col}
                FROM player_hands ph INDEXED BY idx_ph_venue_hand
                JOIN fingerprints fp
                    ON fp.hand_id = ph.hand_id AND fp.file = ph.file AND fp.player_idx = ph.seat_idx
                WHERE ph.venue = ? AND {where}
            """, [*case_params, req.venue, *where_params])
        else:
            con.execute(f"""
                CREATE TEMP TABLE _fp_matches AS
                SELECT fp.hand_id, ph.player_id, ph.net_won, ph.big_blind {tier_col}
                FROM fingerprints fp
                JOIN player_hands ph INDEXED BY idx_ph_hand
                    ON ph.hand_id = fp.hand_id AND ph.file = fp.file AND ph.seat_idx = fp.player_idx
                WHERE {where}
            """, [*case_params, *where_params])

        overall = _stats_from_matches(con)

        tiers = None
        if req.fuzzy:
            max_tier = max(0, min(req.max_tier, len(FUZZY_TIER_LABELS) - 1))
            tiers = []
            for tier in range(max_tier + 1):
                # Cumulative: tiers nest, so "tier <= k" = everything at
                # least as close as tier k.
                s = _stats_from_matches(con, f"match_tier <= {tier}")
                tiers.append({'tier': tier, 'label': FUZZY_TIER_LABELS[tier], **s})

        return {**overall, 'tiers': tiers}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Solve jobs — launch cfr_solver/texas_adapter.py as a subprocess (stdlib-only,
# runs with the API's own python — no separate venv). Progress comes from
# TexasSolver's own "Iter: N" / "Total exploitability" log lines, captured in
# a log file. The adapter writes texas_output.json itself when done.
# NOTE: jobs live in module state — a uvicorn reload forgets them (the
# subprocess keeps running; status falls back to checking texas_output.json).
# ---------------------------------------------------------------------------

_CFR_DIR = Path(__file__).parent.parent / 'cfr_solver'
_SOLVE_JOBS: dict[str, dict] = {}
_TEXAS_ITER_RE = re.compile(r'Iter:\s*(\d+)')
_TEXAS_EXPL_RE = re.compile(r'Total exploitability\s+([\d.]+)')


class SolveRequest(BaseModel):
    accuracy: float = 0.3            # target exploitability, % of pot
    max_iteration: int = 200         # DCFR iteration cap


def _log_tail(log_path: Path, n: int = 10) -> list[str]:
    try:
        return log_path.read_text(errors='replace').strip().splitlines()[-n:]
    except OSError:
        return []


@app.post("/solve/{spot_id}")
def start_solve(spot_id: str, req: SolveRequest) -> dict:
    if not _SPOT_ID_RE.match(spot_id):
        raise HTTPException(422, "invalid spot_id")
    spec_path = _HB_SPOTS_DIR / f"{spot_id}.json"
    if not spec_path.exists():
        raise HTTPException(404, f"No spot spec at cfr_solver/spots/{spot_id}.json — export it first")

    job = _SOLVE_JOBS.get(spot_id)
    if job and job['proc'].poll() is None:
        raise HTTPException(409, f"A solve for {spot_id!r} is already running")

    results_dir = _CFR_DIR / 'results'
    results_dir.mkdir(exist_ok=True)
    log_path = results_dir / f"{spot_id}.solve.log"

    max_iteration = max(10, min(req.max_iteration, 5000))
    cmd = [sys.executable, '-u', 'texas_adapter.py', str(spec_path),
           '--accuracy', str(req.accuracy), '--max-iteration', str(max_iteration)]

    with open(log_path, 'w') as log_f:
        # -u: unbuffered child stdout so progress lines land in the log live.
        proc = subprocess.Popen(cmd, cwd=str(_CFR_DIR), stdout=log_f, stderr=subprocess.STDOUT)
    _SOLVE_JOBS[spot_id] = {
        'phase': 'solving', 'proc': proc, 'log': log_path,
        'iterations': max_iteration,
    }
    return {'status': 'running', 'iterations': max_iteration, 'engine': 'texas'}


@app.get("/solve/{spot_id}/status")
def solve_status(spot_id: str) -> dict:
    texas_path = _CFR_DIR / 'results' / spot_id / 'texas_output.json'
    job = _SOLVE_JOBS.get(spot_id)

    if job is None:
        if texas_path.exists():
            return {'status': 'done'}
        return {'status': 'not_started'}

    tail = _log_tail(job['log'], n=20)
    iters_done = 0
    exploitability = None
    for line in reversed(tail):
        m = _TEXAS_ITER_RE.search(line)
        if m:
            iters_done = int(m.group(1))
            break
    for line in reversed(tail):
        m = _TEXAS_EXPL_RE.search(line)
        if m:
            exploitability = float(m.group(1))
            break

    base = {
        'iterations_done': iters_done,
        'iterations_total': job['iterations'],
        'exploitability_pct': exploitability,
        'engine': 'texas',
        'log_tail': tail[-3:],
    }

    rc = job['proc'].poll()
    if rc is None:
        return {'status': 'running', **base}
    if rc != 0 or not texas_path.exists():
        return {'status': 'failed', 'error': '\n'.join(tail), **base}
    _TEXAS_CACHE.pop(spot_id, None)
    del _SOLVE_JOBS[spot_id]
    return {'status': 'done', **base}
