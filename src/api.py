from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any
import sqlite3
import os
from contextlib import asynccontextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'poker.db')


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_covering_index()
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
