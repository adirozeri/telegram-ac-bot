"""Tiny stdlib-only storage shared by the bot and the web app.

Deliberately not SQLite: the Pi's hand-built Python lacks the _sqlite3
extension, and the data is tiny. Events are an append-only JSONL log; settings
are a small JSON object. Cross-process access (bot + web) is guarded with
fcntl file locks. No third-party deps, nothing to compile.
"""
import fcntl
import json
import logging
import os
import time
from contextlib import contextmanager

from . import config

logger = logging.getLogger(__name__)

_BASE = config.DB_PATH
EVENTS_FILE = _BASE.with_name(_BASE.stem + "_events.jsonl")
SETTINGS_FILE = _BASE.with_name(_BASE.stem + "_settings.json")

_DEFAULT_SETTINGS = {
    "cost_per_min": "0",
    "currency": "₪",  # ₪
    "buttons_flipped": "0",
}


@contextmanager
def _settings_rw():
    """Open the settings file under an exclusive lock for read-modify-write."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    f = open(SETTINGS_FILE, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        raw = f.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        yield data
        f.seek(0)
        f.truncate()
        f.write(json.dumps(data))
        f.flush()
        os.fsync(f.fileno())
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _read_settings():
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE) as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                raw = f.read()
                return json.loads(raw) if raw.strip() else {}
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return {}


def init_db():
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_FILE.touch(exist_ok=True)
    with _settings_rw() as data:
        for k, v in _DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
    logger.info("Storage initialized (events=%s, settings=%s)", EVENTS_FILE, SETTINGS_FILE)


def log_event(action, source, success, ts=None):
    """Append an ON/OFF intent. action in {'ON','OFF'}, source in {web,telegram,cycle}."""
    rec = {
        "ts": time.time() if ts is None else ts,
        "action": action,
        "source": source,
        "success": 1 if success else 0,
    }
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_FILE, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(rec) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def get_setting(key, default=None):
    return _read_settings().get(key, default)


def set_setting(key, value):
    with _settings_rw() as data:
        data[key] = str(value)


def get_flip():
    """Whether the ON/OFF button logic is flipped (a shared setting)."""
    return get_setting("buttons_flipped", "0") == "1"


def set_flip(flipped):
    set_setting("buttons_flipped", "1" if flipped else "0")
    return flipped


def get_events(since=None):
    """Return event dicts ordered by ts. `since` is an epoch lower bound."""
    if not EVENTS_FILE.exists():
        return []
    events = []
    with open(EVENTS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None and e.get("ts", 0) < since:
                continue
            events.append(e)
    events.sort(key=lambda e: e.get("ts", 0))
    return events
