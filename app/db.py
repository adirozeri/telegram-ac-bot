"""SQLite layer shared by the bot and the web app.

One database (ac_data.db) with an event log (ON/OFF intents) and a key/value
settings table. WAL + busy_timeout so both processes can read/write safely.
Connections are opened per call (cheap; commands are infrequent).
"""
import logging
import time
from contextlib import contextmanager

try:  # stdlib on normal builds
    import sqlite3
except ModuleNotFoundError:  # Pi's /usr/local Python was built without _sqlite3
    from pysqlite3 import dbapi2 as sqlite3

from . import config

logger = logging.getLogger(__name__)

_DEFAULT_SETTINGS = {
    "cost_per_min": "0",
    "currency": "₪",  # ₪
    "buttons_flipped": "0",
}


@contextmanager
def _connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                action TEXT NOT NULL,
                source TEXT NOT NULL,
                success INTEGER NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        for k, v in _DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    logger.info("DB initialized at %s", config.DB_PATH)


def log_event(action, source, success):
    """Record an ON/OFF intent. action in {'ON','OFF'}, source in {web,telegram,cycle}."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO events (ts, action, source, success) VALUES (?, ?, ?, ?)",
            (time.time(), action, source, 1 if success else 0),
        )


def get_setting(key, default=None):
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key, value):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def get_flip():
    """Whether the ON/OFF button logic is flipped (a shared setting)."""
    return get_setting("buttons_flipped", "0") == "1"


def set_flip(flipped):
    set_setting("buttons_flipped", "1" if flipped else "0")
    return flipped


def get_events(since=None):
    """Return event dicts ordered by ts. `since` is an epoch lower bound."""
    with _connect() as conn:
        if since is None:
            rows = conn.execute(
                "SELECT ts, action, source, success FROM events ORDER BY ts"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts, action, source, success FROM events WHERE ts>=? ORDER BY ts",
                (since,),
            ).fetchall()
    return [dict(ts=r[0], action=r[1], source=r[2], success=r[3]) for r in rows]
