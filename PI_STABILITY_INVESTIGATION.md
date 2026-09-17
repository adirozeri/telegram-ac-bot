# Pi Stability Investigation — repeated network drops / forced power cycles

**Status:** root cause identified, fix deliberately NOT applied (see below).
**Last updated:** 2026-09-17 (first captured drop was a WiFi software failure — watchdog added)

---

## TL;DR

The Raspberry Pi 2 is in a **permanent under-voltage state**. Its 5V supply cannot
hold voltage under the load of the board plus the RT5370 USB WiFi dongle. This
causes the dongle's USB link to reset (network vanishes) and, when the sag is
deep enough, hangs the whole board — which is why it needs a physical power cycle.

**The fix is to replace the power supply.** This has *not* been done yet, by
choice: the failing configuration is being kept so the fault keeps reproducing
and we can capture it properly.

---

## The evidence

### 1. Under-voltage is constant, not transient

```
vcgencmd get_throttled  →  throttled=0x50005
```

| Bit | Meaning | Set? |
|----:|---------|:----:|
| 0 | Under-voltage **right now** | yes |
| 1 | ARM frequency capped | no |
| 2 | **Currently throttled** | yes |
| 16 | Under-voltage has occurred since boot | yes |
| 17 | Frequency capping has occurred | no |
| 18 | Throttling has occurred since boot | yes |

Sampled 12 times over 60s — identical every time, while **idle**, at **~50 C**.
Thermal throttling starts at 80 C, so temperature is not a factor. This is purely
the 5V rail.

Kernel logged it 16 seconds into boot and it has never cleared:

```
[Sat Sep 12 07:46:55 2026] usb 1-1.5: reset high-speed USB device number 4 using dwc_otg
[Sat Sep 12 07:46:56 2026] hwmon hwmon1: Undervoltage detected!
```

The USB reset one second before the under-voltage warning is the causal chain:
dongle radio powers up -> rail sags -> USB resets -> WiFi drops.

### 2. Hardware

- **Raspberry Pi 2 Model B Rev 1.1** — no onboard WiFi, so WiFi is a USB dongle
- **Ralink RT5370** USB WiFi dongle (`rt2800usb`), interface `wlx40a5ef05620a`
- Onboard ethernet `enxb827eba46df4` (smsc95xx) — currently unplugged
- SD card: SanDisk `SL16G`, manufactured **05/2015**
- `config.txt` does **not** set `max_usb_current=1` (USB budget limited to 600mA)

### 3. It has happened 57 times, and is accelerating

From `wtmp` (survives power loss, unlike the journal):

```
reboot records:   66
shutdown records:  9      ->  57 unclean power events (86%)
wtmp begins:  Tue May 13 01:17:51 2025
```

Restarts by month (2026):

| Month | Count | Dates |
|---|---:|---|
| July | 5 | 4, 5, 6, 17, 25 |
| August | 4 | 4, 18, 23, 27 |
| **September** | **7 in 8 days** | 5, 7, 8, 9, 9, 10, 12 |

The rate is climbing sharply — consistent with a **degrading** supply, not a
merely marginal one.

> **Timestamp caveat:** nearly every boot record reads `HH:16:57`. That is an
> artifact — the Pi has no RTC, so the clock is restored from a saved value
> before `wtmp` is written, and chrony steps it later. The **dates** are
> reliable; the **times** are not.

### 4. Live flaps captured

Two link drops observed directly on 2026-09-12, with nobody touching anything:

```
09:47:15  PI UP        (after manual power cycle)
09:48:28  PI DOWN      <- 73 seconds later
09:48:45  PI UP        <- recovered by itself, 17s

10:11:08  oper=up    gw=FAIL
10:12:10  oper=down  gw=FAIL  sig=?     <- wifi link down
10:13:12  oper=up    gw=ok              <- recovered by itself
```

So the link flaps often and usually self-heals. Occasionally the brownout is deep
enough to hang the board, and that is when a power cycle is needed.

---

## Why this was never diagnosed before

```
/etc/systemd/journald.conf  ->  Storage=volatile
/var/log/journal/           ->  empty
rsyslog                     ->  not installed
```

**Every power cycle destroyed all logs.** `journalctl --list-boots` showed exactly
one boot. 57 crashes, zero surviving evidence from any of them. Combined with no
RTC (so timestamps were wrong anyway), the fault was effectively invisible.

This is now fixed — see below.

---

## Ruled out

| Hypothesis | Verdict | Evidence |
|---|---|---|
| SD card wear | **No** | `Lifetime writes: 18 GB` total. Filesystem `clean`, root `rw`, no ext4/mmc errors. |
| Out of memory | **No** | 161MB used of 921MB; no OOM events. |
| Overheating | **No** | 48–50 C throughout. |
| ARM frequency capping | **No** | Throttle bits 1 and 17 clear. The 600MHz reading is just `ondemand` idling; max is 900MHz. |
| Services crashing | **No** | `telegram-ac-bot` and `ac-web` both `active`, `NRestarts=0`. |

---

## Changes applied on 2026-09-12

All backups are on the Pi next to the originals.

| # | Change | Why | Revert |
|---|---|---|---|
| 1 | Timezone -> `Asia/Jerusalem` (was `Europe/London`) | Logs were 2h off; also fixes an analytics bug (below) | `sudo timedatectl set-timezone Europe/London` |
| 2 | `journald Storage=persistent`, capped `SystemMaxUse=200M`, `SystemMaxFileSize=20M`, `MaxRetentionSec=6month` | **Logs now survive reboots** — the single most important change | restore `/etc/systemd/journald.conf.bak` |
| 3 | `ac-health.timer` + `/usr/local/bin/ac-health-log.sh` -> `/var/log/ac-health.log`, every 60s, logrotate weekly x12 | Leaves a breadcrumb trail right up to the moment of the next crash | `sudo systemctl disable --now ac-health.timer` |

### What the health log looks like

```
2026-09-12T10:12:10+03:00 thr=0x50005 temp=48.7'C up=1528s load=0.29 0.29 0.19 \
  avail=763M if=wlx40a5ef05620a ip=192.168.1.135/24 sig=?dBm oper=down gw=FAIL
```

Fields: `thr` = get_throttled bitmask, `oper` = wifi link state, `gw` = can we
ping the router, `sig` = signal strength.

---

## Deliberately NOT changed

- **The power supply.** Left in place on purpose so the fault keeps reproducing.
  This is the actual fix when we are ready to apply it.
- **`max_usb_current=1`** in `config.txt`. Would raise the USB budget from 600mA
  to 1.2A, but that removes the board's own protection while the supply is
  already failing. Do not set this until the PSU is replaced.
- **Static IP.** See open issue below — recommend a router-side DHCP
  reservation instead of changing config on the Pi remotely.

---

## Open issues (not the crash cause, but real)

### A. The "static IP" in CLAUDE.md does not exist

`/etc/dhcpcd.conf` configures `eth0` and `wlan0` — **neither interface exists**
(real names are `enxb827eba46df4` / `wlx40a5ef05620a`), and **`dhcpcd.service`
is not installed at all**. NetworkManager is in charge and `192.168.1.135` is a
plain **DHCP lease** (`proto dhcp`, `valid_lft 42828sec`).

**It can change at any time**, which is an independent second cause of "can't
reach the Pi". Safest fix: add a **DHCP reservation for the dongle's MAC
`40:a5:ef:05:62:0a` on the router** — no risk of locking ourselves out.

Related mess (harmless but untidy): `systemd-networkd` is enabled *alongside*
NetworkManager, `wpa_supplicant@wlan0.service` fails every boot (no `wlan0`), and
`systemd-networkd-wait-online.service` sits in `failed` state.

### B. Analytics day-buckets were computed in the wrong timezone

`app/analytics.py` buckets usage with `datetime.fromtimestamp()` — local time.
With the Pi on `Europe/London`, "today / this week / this month" on the dashboard
were computed on **London midnights**, 2–3h off from the real day. Fixed by
change #1, but **historical event data before 2026-09-12 is bucketed on the old
offset** and cannot be retroactively corrected without re-bucketing.

### C. `/api/status` re-reads the entire event log every 5 seconds

`web_app.py` `_current_state()` calls `db.get_events()`, which reads, JSON-parses
and sorts the **whole** `ac_data_events.jsonl` on **every** request — and the
dashboard polls it every 5s (`setInterval(refresh, 5000)`). The log is
append-only and never rotates, so this grows without bound on a 1GB Pi. Not a
crash cause today, but worth fixing (read the tail, or cache the last state).

### D. fsck has never been scheduled

`Maximum mount count: -1`, last checked May 2025, across 57 unclean mounts.
Hasn't caused corruption yet (`Filesystem state: clean`), but it is a loaded gun
on an 11-year-old card.

---

## Incident 2026-09-17 — WiFi gave up, board was fine

First drop captured with the new logging. **Not a board hang and not a power loss.**

- `ac-health.log` ran every minute for 5.3 days (`up=459431s`) with `oper=down
  ip=none` from **2026-09-14 18:07** until the manual power cycle at ~17:25 on
  09-17. The bot logged `Temporary failure in name resolution` throughout.
- Cause, from `journalctl -b -1` at 18:06: weak signal (−65…−75 dBm, ~1000
  `BEACON-LOSS` events over 3 days) → disconnect → on reconnect the WPA handshake
  timed out → wpa_supplicant: `4-Way Handshake failed - pre-shared key may be
  incorrect` (spurious — the key is correct) → NetworkManager asked for a new key
  → `no secrets: No agents were available` → connection `failed`. **NM never
  retried and logged nothing further for 3 days.**
- Under-voltage (`0x50005`) was present the whole time and the board survived it.
  Some of the 57 past "crashes" were probably this WiFi failure plus a power
  cycle, not a hang. The PSU is still bad and still the fix for real hangs.

**Fix applied: `wifi-watchdog`** (`scripts/wifi-watchdog.sh`, units in
`scripts/systemd/`). Runs every 60s; if the WiFi device has not been
`connected` for 3 min it runs `nmcli con up preconfigured`, retrying every 3 min.
Logs to `/var/log/wifi-watchdog.log` (`down:` / `reconnect attempt` /
`recovered:`). Tested live by `nmcli dev disconnect`: down 17:40:14, watchdog
reconnected at 17:43:32, `recovered ... after 253s down`.
Revert: `sudo systemctl disable --now wifi-watchdog.timer`.

**Lesson for the runbook:** the Telegram bot uses the same WiFi, so "bot is dead"
does *not* mean the board hung. Use `ac-health.log` to tell them apart.

---

## RUNBOOK — what to do next time it drops

The whole point of the changes above is that **the evidence now survives**. So:

### 1. Do NOT power cycle immediately

First check whether the board is actually dead or just off the network:

```bash
ping -c3 192.168.1.135                       # from the laptop
ssh -o ConnectTimeout=8 pi@192.168.1.135 uptime
```

Since 2026-09-17 `wifi-watchdog` should recover a WiFi-only drop within ~4
minutes, so **wait 5 minutes** first. If it is still down after that, suspect a
board hang (or the dongle vanishing from USB).

Messaging the bot does **not** distinguish the cases — it uses the same WiFi.
After recovery, `ac-health.log` does: entries continuing through the outage
mean the board was alive; a gap means it hung or lost power.

### 2. After it is back up, harvest before anything rotates

```bash
ssh pi@192.168.1.135 'bash -s' < scripts/pi-forensics.sh > forensics-$(date +%F-%H%M).txt
```

### 3. Read the two logs that now survive

```bash
# minute-by-minute health right up to the crash
ssh pi@192.168.1.135 'tail -200 /var/log/ac-health.log'

# THE KEY ONE - the previous boot's logs now actually exist
ssh pi@192.168.1.135 'journalctl --list-boots'
ssh pi@192.168.1.135 'journalctl -b -1 -n 200 --no-pager'
ssh pi@192.168.1.135 'journalctl -b -1 -p err --no-pager'
```

### 4. What to look for

| Observation | Means |
|---|---|
| `ac-health.log` stops abruptly, journal `-b -1` ends mid-sentence | Hard power loss / brownout hang -> **confirms the PSU diagnosis** |
| `ac-health.log` keeps running with `oper=down` / `gw=FAIL` for a long stretch | Board alive, dongle died and did not recover -> driver/USB side |
| `thr=` value changes (e.g. gains bit 1/17, frequency capping) | Supply degrading further |
| `EXT4-fs error` / `mmc` errors appear | Card starting to fail — take an image immediately |

### 5. When we have had enough data

Replace the power supply with a genuine **5V 2.5A** unit and a **short, thick**
micro-USB cable (thin cables drop meaningful voltage on their own). Then verify:

```bash
ssh pi@192.168.1.135 'vcgencmd get_throttled'
# want: throttled=0x0
```

Keep `ac-health.log` running afterwards to prove the drops actually stopped.

---

## Reference: files and where things live

| Thing | Path |
|---|---|
| Health log | `/var/log/ac-health.log` (on the Pi) |
| Health script | `/usr/local/bin/ac-health-log.sh` |
| Health timer | `/etc/systemd/system/ac-health.{service,timer}` |
| Journal (now persistent) | `/var/log/journal/` |
| Config backups | `/etc/systemd/journald.conf.bak`, `/etc/dhcpcd.conf.bak` |
| Forensics script | `scripts/pi-forensics.sh` (this repo) |
| WiFi watchdog | `/usr/local/bin/wifi-watchdog.sh`, `wifi-watchdog.{service,timer}`, log `/var/log/wifi-watchdog.log` (source: `scripts/`) |
| Dongle MAC (for DHCP reservation) | `40:a5:ef:05:62:0a` |
