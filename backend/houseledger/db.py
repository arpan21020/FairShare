"""SQLite connection and schema. Amounts are stored as integer paise."""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "houseledger.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS household (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY,
    payer_id INTEGER NOT NULL REFERENCES members(id),
    total_paise INTEGER NOT NULL CHECK (total_paise > 0),
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    split_json TEXT NOT NULL,
    created_by INTEGER NOT NULL REFERENCES members(id),
    created_at TEXT NOT NULL,
    request_id TEXT UNIQUE,
    deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS expense_shares (
    expense_id INTEGER NOT NULL REFERENCES expenses(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    share_paise INTEGER NOT NULL CHECK (share_paise >= 0),
    PRIMARY KEY (expense_id, member_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY,
    from_id INTEGER NOT NULL REFERENCES members(id),
    to_id INTEGER NOT NULL REFERENCES members(id),
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL REFERENCES members(id),
    created_at TEXT NOT NULL,
    request_id TEXT UNIQUE,
    deleted INTEGER NOT NULL DEFAULT 0
);

-- Every change, who made it, and the entity before/after (JSON), so balances are
-- traceable and the last action can be undone.
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES members(id),
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    before_json TEXT,
    after_json TEXT,
    at TEXT NOT NULL,
    undoable INTEGER NOT NULL DEFAULT 1,
    undone INTEGER NOT NULL DEFAULT 0
);
"""


def db_path_from_env() -> Path:
    return Path(os.environ.get("HOUSELEDGER_DB", DEFAULT_DB_PATH))


def connect(path: str | Path) -> sqlite3.Connection:
    """Open (and if needed create) a ledger database. Use ':memory:' for tests."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
