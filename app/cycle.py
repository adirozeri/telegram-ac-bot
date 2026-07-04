"""Web-owned auto-cycle: hold ON for on_min, then OFF for off_min, repeat.

Starts with ON, driving the AC with explicit ON/OFF intents via set_ac (never
relying on device state). Single owner (the web app) so there's no split-brain
with the bot. Persists {on,off} to cycle_state.json and resume()s on startup.
Exposes phase + seconds-left for the dashboard. No notifications (the UI shows
status).
"""
import asyncio
import json
import logging
import time

from . import config
from .commands import set_ac

logger = logging.getLogger(__name__)

STATE_FILE = config.CYCLE_STATE_FILE


class CycleManager:
    def __init__(self, ac):
        self.ac = ac
        self.task = None
        self.on_min = None
        self.off_min = None
        self.phase = None          # "on" | "off"
        self.phase_ends_at = None  # epoch

    @property
    def running(self):
        return self.task is not None and not self.task.done()

    def start(self, on_min, off_min, persist=True):
        self.stop(clear_file=False)
        self.on_min, self.off_min = int(on_min), int(off_min)
        if persist:
            self._save()
        self.task = asyncio.create_task(self._run())

    def stop(self, clear_file=True):
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = None
        self.on_min = self.off_min = None
        self.phase = self.phase_ends_at = None
        if clear_file:
            self._clear()

    def status(self):
        if not self.running:
            return {"running": False}
        left = max(0, int((self.phase_ends_at or time.time()) - time.time()))
        return {
            "running": True,
            "on_min": self.on_min,
            "off_min": self.off_min,
            "phase": self.phase,
            "seconds_left": left,
        }

    def _save(self):
        try:
            STATE_FILE.write_text(json.dumps({"on": self.on_min, "off": self.off_min}))
        except Exception as e:
            logger.error(f"Could not save cycle state: {e}")

    def _clear(self):
        try:
            STATE_FILE.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Could not clear cycle state: {e}")

    def resume(self):
        """Resume a persisted cycle on startup. Returns True if one was restored."""
        try:
            if not STATE_FILE.exists():
                return False
            data = json.loads(STATE_FILE.read_text())
            on_min, off_min = int(data["on"]), int(data["off"])
        except Exception as e:
            logger.error(f"Could not read cycle state ({e}); discarding it")
            self._clear()
            return False
        logger.info(f"Resuming persisted cycle: {on_min}m on / {off_min}m off")
        self.start(on_min, off_min, persist=False)
        return True

    async def _run(self):
        intend_on = True  # start with ON
        try:
            while True:
                ok, err = await set_ac(self.ac, intend_on, source="cycle")
                self.phase = "on" if intend_on else "off"
                hold = self.on_min if intend_on else self.off_min
                self.phase_ends_at = time.time() + hold * 60
                logger.info(f"Cycle tick: {self.phase} (ok={ok}, err={err}) holding {hold} min")
                await asyncio.sleep(hold * 60)
                intend_on = not intend_on
        except asyncio.CancelledError:
            logger.info("Cycle stopped")
            raise
