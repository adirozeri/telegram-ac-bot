# Transition Plan — From Telegram Bot to Web Dashboard (+ Bot)

_Last updated: 2026-07-04_

## Why we're doing this

The Pi is always on, so it can host a proper web app. A single-page dashboard on
the local network gives a much better UI, richer information, and analytics that
Telegram buttons can't. The Telegram bot stays — but only as the **free remote
control** for when you're outside the house.

## Decisions (from our Q&A)

| Question | Your choice | What it means |
|---|---|---|
| Where to access the dashboard | **Home network only** | Dashboard is LAN-only, e.g. `http://192.168.1.135:8080`. Never exposed to the internet — no port-forwarding, no paid tunnel. |
| Remote control from outside | **Keep Telegram** | The bot relays commands through Telegram's servers for free, so you can turn the AC on/off from anywhere without exposing the Pi. |
| Login on the dashboard | **No login** | Anyone on your home network can open it. Fine because it's LAN-only. |
| Existing Telegram bot | **Keep both** | Bot and web app run side by side, sharing code + data. |
| Usage/cost tracking basis | **Commanded on-time** | We count ON minutes from the ON/OFF commands the app issues (honest & reliable). Physical-remote use isn't counted, since the Switcher's own state can't be trusted. |
| Currency | **₪ (default)** | Editable — tell me if it should be something else. |

## Architecture

Two small services on the Pi, **sharing one codebase and one SQLite database**:

```
                 ┌─────────────────────────┐
   at home  ───▶ │  Web dashboard (FastAPI) │  LAN only, port 8080
                 │  control • cycle • stats  │  ── owns the auto-cycle
                 └───────────┬─────────────┘
                             │  both read/write
                             ▼
                 ┌─────────────────────────┐
                 │   SQLite  (ac_data.db)   │  event log + settings
                 └───────────▲─────────────┘
                             │
   outside  ───▶ ┌───────────┴─────────────┐
   (Telegram)    │  Telegram bot            │  remote ON / OFF / Flip
                 │  (existing service)      │  ── logs commands to the DB
                 └─────────────────────────┘
```

- **Shared `app/` package** — one copy of the AC logic (auto-discovery by
  `DEVICE_ID`, resilient `_send` with timeout + retry), the SQLite layer, and the
  command helpers. Both services import it.
- **Flip state** lives in the DB (a setting), so a "Flip" from either the bot or
  the dashboard applies to both and survives restarts.
- **Auto-cycle** lives only in the web app (single owner → no split-brain), with
  the same persistence we already built (resumes after a restart).
- The Telegram bot is trimmed to remote **ON / OFF / Flip** (no cycle from
  Telegram — you said remote just needs to start the AC).

## Features in the dashboard

- **Live status** — current commanded state (ON/OFF), whether a cycle is running,
  which phase and time left, the device's discovered IP, last command result.
- **Actions** — big ON / OFF buttons, Flip, and Auto-Cycle start/stop with
  separate ON and OFF durations (the feature we just built).
- **Usage analytics** — total ON-time today / this week / this month, number of
  on-periods, average on-duration, and a per-day bar chart.
- **Cost** — ON-time × your per-minute rate, shown per day/week/month. The rate
  and currency are editable in a settings panel.
- Self-contained page (no external CDNs) so it renders even if the Pi is offline
  from the internet; responsive + dark mode.

## Data model (SQLite)

- **`events`** — one row per command: `ts`, `action` (`ON`/`OFF`, the *intent*),
  `source` (`web` / `telegram` / `cycle`), `success`.
  On-time is derived by pairing successful ON→OFF transitions over the timeline
  (an open interval runs to "now" while the AC is commanded ON).
- **`settings`** — key/value: `cost_per_min`, `currency`, `buttons_flipped`.

## Cost tracking — what's honest

Cost/usage = **what the app told the AC to do**, not what the Switcher reports
(you've established that state is unreliable). If you use the physical remote,
that time won't be counted. The Flip control exists so "ON" reliably means the AC
is on, which is what the analytics assume.

## Deployment

- New systemd service **`ac-web.service`** runs the dashboard; the existing
  **`telegram-ac-bot.service`** keeps running the bot. Same venv.
- New Python deps: **FastAPI + uvicorn** (need to confirm they install on the
  Pi's 32-bit ARM venv via piwheels; fallback is Flask/aiohttp if not).
- The **`/deploy-pi`** command gets updated to pull + restart **both** services.
- New files gitignored: `ac_data.db`, `cycle_state.json`.

## What I still need from you

- **Per-minute cost of the AC** (you said you'll measure it) — plug into the
  settings; until then cost shows 0 / "not set."
- Confirm **currency** (default ₪) and the **port** (default 8080).

## Status / not yet built

Nothing of the web app is built yet — this doc is the agreed plan. Already done
earlier and unaffected: reliability/auto-discovery, chrony clock fix, and the
Telegram auto-cycle with restart persistence.
