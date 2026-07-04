"""High-level AC commands shared by the bot and web app.

set_ac() applies the flip setting, sends the physical command, and logs the
*intent* (ON/OFF) to the DB so analytics reflect what the user asked for — not
the post-flip physical command.
"""
import logging

from . import db

logger = logging.getLogger(__name__)


async def set_ac(ac, intent_on, source):
    """Command the AC to the intended logical state. Returns (ok, err).

    The flip setting corrects which physical IR command an intent maps to (the
    Breeze's reported state is unreliable). We log the intent, not the physical
    command, so on-time analytics track what the user wanted.
    """
    flipped = db.get_flip()
    physical_on = intent_on ^ flipped
    if physical_on:
        ok, err = await ac.turn_on_ac()
    else:
        ok, err = await ac.turn_off_ac()
    db.log_event("ON" if intent_on else "OFF", source, ok)
    return ok, err


def toggle_flip(source="?"):
    """Flip the ON/OFF button logic (a shared DB setting). Returns the new state.

    Not logged as an event, so on-time interval pairing stays clean.
    """
    new = not db.get_flip()
    db.set_flip(new)
    logger.info("Button logic flipped -> flipped=%s (source=%s)", new, source)
    return new
