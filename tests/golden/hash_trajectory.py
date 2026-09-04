"""Full-trajectory hash used by the golden-run comparison.

The web app's backend and this library must produce the same trajectory
for the same fixture, seed and dt. Both sides hash their SQLite output
with this function and compare the digests.

Agent ids are normalised before hashing: jupedsim numbers agents with a
process-global counter, so the same run yields ids 1..N in a fresh
process and K+1..K+N in a long-lived one (the app's backend). Ids are
therefore replaced by their rank in order of first appearance
(``ORDER BY frame, id``), starting at 0.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3


def hash_trajectory(sqlite_path: str | pathlib.Path) -> str:
    """SHA-256 over ``(frame, rank, round(x, 4), round(y, 4))`` rows ordered by frame, id."""
    con = sqlite3.connect(str(sqlite_path))
    try:
        rows = con.execute("SELECT frame, id, pos_x, pos_y FROM trajectory_data ORDER BY frame, id")
        ranks: dict[int, int] = {}
        digest = hashlib.sha256()
        for frame, agent_id, x, y in rows:
            rank = ranks.setdefault(int(agent_id), len(ranks))
            digest.update(f"{int(frame)},{rank},{round(x, 4):.4f},{round(y, 4):.4f}\n".encode())
    finally:
        con.close()
    return digest.hexdigest()
