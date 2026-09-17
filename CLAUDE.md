# CLAUDE.md — telegram-ac-bot

Telegram bot that toggles an AC unit. Runs as a systemd service on a Raspberry Pi 2.

## Raspberry Pi access

Passwordless key-based SSH is set up (laptop `~/.ssh/id_ed25519`, comment `railway-freeslot`, is in the Pi's `authorized_keys`).

- **WiFi (primary):** `ssh pi@192.168.1.135` — this is a **DHCP lease, not a static IP** (the `dhcpcd.conf` static config is inert; see `PI_STABILITY_INVESTIGATION.md`). It can change; dongle MAC is `40:a5:ef:05:62:0a`.
- **Ethernet (direct cable):** `ssh pi@10.1.0.50` — first run `sudo ip addr add 10.1.0.1/16 dev enp0s25`
- Run remote commands: `ssh -o ConnectTimeout=8 pi@192.168.1.135 '<cmd>'`
- User `pi`, Raspbian 12 Bookworm, kernel 6.12.34, ARMv7 32-bit
- No password is stored anywhere (by design).

## Deployment on the Pi

- systemd service: `telegram-ac-bot.service` (enabled, runs as user `pi`)
  - `systemctl status telegram-ac-bot` / `journalctl -u telegram-ac-bot -f`
- Install path: `/home/pi/telegram-ac-bot/`
- Python venv: `telegram-bot-env/`
- Entrypoint: `telegram_bot_cloud.py`
- `.env` holds the bot token / secrets — **gitignored, not in the repo**

## Git

- Remote: `https://github.com/adirozeri/telegram-ac-bot.git`, branch `main`
- This local clone: `/home/adir/projects/telegram-ac-bot`

## Known issues (as of 2026-09-12)

1. **Pi keeps dropping off the network / needs repeated power cycles — ROOT CAUSE FOUND (2026-09-12):** the Pi is in a **permanent under-voltage state** (`vcgencmd get_throttled` = `0x50005` — under-voltage + throttled, constantly, at idle, ~50°C). The 5V supply cannot carry the Pi 2 plus its RT5370 USB WiFi dongle, so the dongle's USB link resets (network vanishes) and deep sags hang the board. `wtmp` shows **66 boots vs 9 clean shutdowns = 57 unclean power events**, accelerating (7 in the first 8 days of September vs 4 in all of August). **Fix = replace the power supply (5V 2.5A, short thick cable).** Deliberately NOT done yet — the failing setup is being kept so the fault reproduces and we can capture it. Full write-up, evidence and a runbook for the next occurrence: **`PI_STABILITY_INVESTIGATION.md`**. Logs now survive reboots (journald was `Storage=volatile` — that's why this went undiagnosed for 57 crashes) and `/var/log/ac-health.log` records power/network health every 60s.
2. **AC controller offline (device-side, not code):** The Switcher Breeze is unreachable. IP `192.168.1.126` answers ping, but the device broadcasts no Switcher discovery packets (`SwitcherBridge` finds 0 devices in 15s) and refuses its control port — i.e. the Switcher's service is down even though something holds the `.126` lease. Almost certainly the unit is powered off / fell off WiFi / crashed. **Fix is physical: power-cycle the Switcher.** Since Phase 1, the bot auto-discovers the device by `DEVICE_ID` and will reconnect automatically once it's back; failures now report "device not found on the network" instead of Errno 111. **Update 2026-09-12:** it no longer answers ping at all (previously it did), and it stayed dark across the whole session — including while the Pi was up. Worth checking whether it shares a power strip with the Pi.

## Resolved (ops)

- **Pi clock drift (2026-07-04):** `systemd-timesyncd` never synced (`Server: n/a`, 0 packets) — the recurring cause of `git fetch` TLS failures and wrong log timestamps. Replaced it with **chrony**, which now syncs (`System clock synchronized: yes`) and steps the clock on every boot. Manual fallback if ever needed: `L=$(date -u '+%Y-%m-%d %H:%M:%S'); ssh pi@192.168.1.135 "sudo date -u -s '$L'"`.

## Resolved

- **Divergence / dirty Pi tree (2026-07-04):** Pi, GitHub, and this clone are now all in sync at `f06952f`. The Pi's uncommitted running code was GitHub's toggle bot plus one small "Bot IP" enhancement (`host_ip` in `get_system_info` / startup message) — that was committed and pushed as `f06952f`; the Pi was then `reset --hard` to `origin/main`, dropping the 5 gitignore-churn commits and the stale merge conflict.

## Next task

**2026-09-17: first captured drop was NOT the PSU** — NetworkManager gave up on
WiFi after a spurious "wrong key" handshake failure (weak signal) and never
retried; the board ran fine offline for 3 days. Fixed with `wifi-watchdog`
(reconnects after 3 min down; tested live). Still waiting on a drop the watchdog
*can't* heal — that would be a real hang and would point back at the PSU. Wait 5
min before power-cycling, then follow the runbook in
`PI_STABILITY_INVESTIGATION.md` (the bot shares the WiFi, so it can't tell a
hang from a WiFi drop — `ac-health.log` can).

Also open, independent of the crash work:
- Switcher Breeze still unreachable (issue #2) — blocks all AC control commands.
- `app/analytics.py` day-buckets used the wrong timezone until 2026-09-12; data
  before that date is bucketed on London midnights.
- `web_app.py` re-reads the entire event log on every `/api/status` (polled every
  5s) — unbounded growth on a 1GB Pi.
