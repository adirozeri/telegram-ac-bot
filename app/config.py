"""Shared configuration: loads .env and exposes device/bot settings and paths.

Both the Telegram bot and the web dashboard import from here, so there is one
source of truth for credentials, timeouts, and file locations. Validation is
done via explicit functions (not at import) so importing this module never
crashes — the bot validates Telegram+device vars in main(), the web app
validates device vars at startup.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

# --- Switcher Breeze device (needed by both services) ---
DEVICE_IP = os.getenv("DEVICE_IP")          # starting hint only; discovery uses DEVICE_ID
DEVICE_ID = os.getenv("DEVICE_ID")
DEVICE_KEY = os.getenv("DEVICE_KEY")
SWITCHER_TOKEN = os.getenv("SWITCHER_TOKEN")
REMOTE_ID = os.getenv("REMOTE_ID")

# --- Telegram (needed only by the bot) ---
BOT_TOKEN = os.getenv("BOT_TOKEN")


def _chat_ids():
    ids = []
    for key in ("CHAT_ID_1", "CHAT_ID_2"):
        v = os.getenv(key)
        if v:
            try:
                ids.append(int(v))
            except ValueError:
                pass
    return ids


AUTHORIZED_CHAT_IDS = _chat_ids()

# --- Reliability tuning (env-overridable so tests can shorten them) ---
# The Breeze broadcasts its presence only every ~20-30s, so discovery must be
# long enough to catch a broadcast. It only runs when the cached IP fails.
DISCOVERY_TIMEOUT = int(os.getenv("DISCOVERY_TIMEOUT", "35"))
COMMAND_TIMEOUT = int(os.getenv("COMMAND_TIMEOUT", "12"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "2"))

# --- Paths (AC_DB_PATH override lets tests use a scratch DB) ---
DB_PATH = Path(os.getenv("AC_DB_PATH", str(BASE_DIR / "ac_data.db")))
CYCLE_STATE_FILE = BASE_DIR / "cycle_state.json"

# --- Web ---
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

REQUIRED_DEVICE_VARS = {
    "DEVICE_ID": DEVICE_ID,
    "DEVICE_KEY": DEVICE_KEY,
    "SWITCHER_TOKEN": SWITCHER_TOKEN,
    "REMOTE_ID": REMOTE_ID,
}


def validate_device():
    """Raise SystemExit if any device credential needed to control the AC is missing."""
    missing = [k for k, v in REQUIRED_DEVICE_VARS.items() if not v]
    if missing:
        raise SystemExit(f"Missing required device env vars: {missing}")


def validate_telegram():
    """Raise SystemExit if Telegram bot credentials are missing."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not AUTHORIZED_CHAT_IDS:
        missing.append("CHAT_ID_1/CHAT_ID_2")
    if missing:
        raise SystemExit(f"Missing required Telegram env vars: {missing}")
