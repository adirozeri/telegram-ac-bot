"""Async Switcher Breeze controller: discovery + resilient send.

Locates the device by DEVICE_ID (its DHCP IP drifts) and drives it with
explicit ON/OFF commands, retrying with a fresh discovery on failure. Returns
(ok, err) so callers can surface a real reason. Flip logic lives in the DB now,
not here — this class only speaks to the hardware.
"""
import asyncio
import logging

from aioswitcher.api import SwitcherApi
from aioswitcher.api.remotes import SwitcherBreezeRemoteManager
from aioswitcher.bridge import SwitcherBridge
from aioswitcher.device import (
    DeviceType,
    DeviceState,
    ThermostatFanLevel,
    ThermostatMode,
    ThermostatSwing,
)

from . import config

logger = logging.getLogger(__name__)

DEVICE_TYPE = DeviceType.BREEZE


class ACController:
    def __init__(self):
        self.remote_manager = SwitcherBreezeRemoteManager()
        # Last-known IP. DEVICE_IP from .env is only a starting hint — the
        # device is located by DEVICE_ID via discovery.
        self._ip = config.DEVICE_IP or None
        self._key = config.DEVICE_KEY

    @property
    def ip(self):
        return self._ip

    async def discover(self, timeout=None):
        """Find the device's current IP by listening for its UDP broadcast.

        Matches on the stable DEVICE_ID rather than a hardcoded IP. Returns the
        IP, or None on timeout.
        """
        timeout = timeout or config.DISCOVERY_TIMEOUT
        loop = asyncio.get_event_loop()
        found = loop.create_future()

        def on_device(device):
            if device.device_id == config.DEVICE_ID and not found.done():
                found.set_result(device)

        try:
            async with SwitcherBridge(on_device):
                device = await asyncio.wait_for(found, timeout)
            self._ip = device.ip_address
            if getattr(device, "device_key", None):
                self._key = device.device_key
            logger.info(f"Discovered device {config.DEVICE_ID} at {self._ip}")
            return self._ip
        except asyncio.TimeoutError:
            logger.warning(
                f"Discovery timed out after {timeout}s (device {config.DEVICE_ID} not heard on LAN)"
            )
            return None
        except Exception as e:
            logger.error(f"Discovery error: {e}")
            return None

    async def _send(self, *args, label="command"):
        """Send a Breeze control command, (re)discovering the IP and retrying.

        Returns (ok: bool, error: str|None).
        """
        last_err = None
        for attempt in range(1, config.MAX_ATTEMPTS + 1):
            if not self._ip:
                await self.discover()
            if not self._ip:
                last_err = "device not found on the network"
                continue
            try:
                async with asyncio.timeout(config.COMMAND_TIMEOUT):
                    async with SwitcherApi(
                        DEVICE_TYPE, self._ip, config.DEVICE_ID, self._key, token=config.SWITCHER_TOKEN
                    ) as api:
                        remote = self.remote_manager.get_remote(config.REMOTE_ID)
                        await api.control_breeze_device(remote, *args)
                logger.info(f"{label} sent successfully to {self._ip}")
                return True, None
            except (asyncio.TimeoutError, OSError) as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(
                    f"{label} attempt {attempt}/{config.MAX_ATTEMPTS} failed ({last_err}); re-discovering"
                )
                self._ip = None  # force fresh discovery on the next attempt
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.error(f"{label} attempt {attempt}/{config.MAX_ATTEMPTS} error: {last_err}")
                self._ip = None
        return False, last_err

    async def turn_on_ac(self):
        """Send an explicit ON command (COOL, last temperature, medium fan)."""
        return await self._send(
            DeviceState.ON,
            ThermostatMode.COOL,
            0,
            ThermostatFanLevel.MEDIUM,
            ThermostatSwing.OFF,
            label="ON",
        )

    async def turn_off_ac(self):
        """Send an explicit OFF command."""
        return await self._send(DeviceState.OFF, label="OFF")
