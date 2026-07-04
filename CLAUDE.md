# CLAUDE.md — telegram-ac-bot

Telegram bot that toggles an AC unit. Runs as a systemd service on a Raspberry Pi 2.

## Raspberry Pi access

Passwordless key-based SSH is set up (laptop `~/.ssh/id_ed25519`, comment `railway-freeslot`, is in the Pi's `authorized_keys`).

- **WiFi (primary):** `ssh pi@192.168.1.135` (static IP)
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

## Known issues (as of 2026-07-04)

1. **AC controller offline (device-side, not code):** The Switcher Breeze is unreachable. IP `192.168.1.126` answers ping, but the device broadcasts no Switcher discovery packets (`SwitcherBridge` finds 0 devices in 15s) and refuses its control port — i.e. the Switcher's service is down even though something holds the `.126` lease. Almost certainly the unit is powered off / fell off WiFi / crashed. **Fix is physical: power-cycle the Switcher.** Since Phase 1, the bot auto-discovers the device by `DEVICE_ID` and will reconnect automatically once it's back; failures now report "device not found on the network" instead of Errno 111.

## Resolved (ops)

- **Pi clock drift (2026-07-04):** `systemd-timesyncd` never synced (`Server: n/a`, 0 packets) — the recurring cause of `git fetch` TLS failures and wrong log timestamps. Replaced it with **chrony**, which now syncs (`System clock synchronized: yes`) and steps the clock on every boot. Manual fallback if ever needed: `L=$(date -u '+%Y-%m-%d %H:%M:%S'); ssh pi@192.168.1.135 "sudo date -u -s '$L'"`.

## Resolved

- **Divergence / dirty Pi tree (2026-07-04):** Pi, GitHub, and this clone are now all in sync at `f06952f`. The Pi's uncommitted running code was GitHub's toggle bot plus one small "Bot IP" enhancement (`host_ip` in `get_system_info` / startup message) — that was committed and pushed as `f06952f`; the Pi was then `reset --hard` to `origin/main`, dropping the 5 gitignore-churn commits and the stale merge conflict.

## Next task

Fresh feature work on the bot (a new "latest" is coming). AC endpoint (issue #1) still needs a valid address before control commands will work.
