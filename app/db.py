"""SQLite storage for cached lookups. One generic table keeps the demo small."""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS lookups (
    kind       TEXT NOT NULL,          -- 'cnpj' or 'cep'
    key        TEXT NOT NULL,          -- normalised CNPJ / CEP
    payload    TEXT NOT NULL,          -- raw JSON returned by BrasilAPI
    fetched_at TEXT NOT NULL,          -- ISO-8601 UTC timestamp
    PRIMARY KEY (kind, key)
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def get(conn: sqlite3.Connection, kind: str, key: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT payload, fetched_at FROM lookups WHERE kind = ? AND key = ?", (kind, key)
    ).fetchone()
    if row is None:
        return None
    return {"payload": json.loads(row["payload"]), "fetched_at": datetime.fromisoformat(row["fetched_at"])}


def save(conn: sqlite3.Connection, kind: str, key: str, payload: dict, now: Optional[datetime] = None) -> datetime:
    fetched_at = now or datetime.now(timezone.utc)
    conn.execute(
        """INSERT INTO lookups (kind, key, payload, fetched_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(kind, key) DO UPDATE SET payload = excluded.payload, fetched_at = excluded.fetched_at""",
        (kind, key, json.dumps(payload, ensure_ascii=False), fetched_at.isoformat()),
    )
    conn.commit()
    return fetched_at


def list_kind(conn: sqlite3.Connection, kind: str, limit: int = 20, offset: int = 0) -> list:
    rows = conn.execute(
        "SELECT key, payload, fetched_at FROM lookups WHERE kind = ? ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
        (kind, limit, offset),
    ).fetchall()
    return [
        {"key": r["key"], "payload": json.loads(r["payload"]), "fetched_at": datetime.fromisoformat(r["fetched_at"])}
        for r in rows
    ]
