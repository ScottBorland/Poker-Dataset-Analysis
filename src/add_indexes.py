"""
One-time migration: adds indexes that make the frontend API fast.

Missing indexes that cause slow queries:
  labels(label, hand_id)     -- covering index; makes label→hand_id lookups index-only
  player_hands(n_players)    -- allows fast filtering by table size

Run once before starting the API:
    python src/add_indexes.py
"""

import sqlite3, os, time

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'poker.db')
con = sqlite3.connect(DB_PATH, timeout=600)

INDEXES = [
    ("idx_label_hid",       "labels",       "label, hand_id"),
    ("idx_ph_nplayers",     "player_hands",  "n_players"),
    ("idx_ph_nplayers_hid", "player_hands",  "n_players, hand_id"),
]

for name, tbl, cols in INDEXES:
    exists = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    if exists:
        print(f"  {name} already exists, skipping")
        continue
    print(f"  Building {name} on {tbl}({cols}) …", flush=True)
    t0 = time.time()
    con.execute(f"CREATE INDEX {name} ON {tbl}({cols})")
    con.commit()
    print(f"    done in {time.time()-t0:.1f}s")

con.close()
print("All indexes ready.")
