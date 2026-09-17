#!/bin/bash
# Reconnects WiFi when NetworkManager has given up on it.
#
# On a weak signal the WPA handshake can time out; wpa_supplicant reports that as
# "pre-shared key may be incorrect", NM asks for a new key, nobody answers on a
# headless Pi, and NM marks the connection failed and never retries. That kept
# the Pi offline for 3 days on 2026-09-14 (see PI_STABILITY_INVESTIGATION.md).
# Run every minute by wifi-watchdog.timer.
LOG=/var/log/wifi-watchdog.log
STATE=/run/wifi-watchdog.down   # tmpfs: "<down-since> <last-attempt>" epochs
CON=preconfigured
GRACE=180                       # give NM's own reconnect a chance first
RETRY=180                       # minimum seconds between our attempts

log() { echo "$(date -Is) $*" >> "$LOG"; }

DEV=$(nmcli -t -f DEVICE,TYPE dev 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}')
if [ -n "$DEV" ]; then
  DEVSTATE=$(nmcli -t -f DEVICE,STATE dev | awk -F: -v d="$DEV" '$1==d{print $2}')
else
  DEVSTATE=absent             # dongle missing from USB
fi
NOW=$(date +%s)

if [ "$DEVSTATE" = connected ]; then
  if [ -f "$STATE" ]; then
    read -r SINCE _ < "$STATE"
    log "recovered: $DEV connected after $((NOW - SINCE))s down"
    rm -f "$STATE"
  fi
  exit 0
fi

if [ ! -f "$STATE" ]; then
  echo "$NOW 0" > "$STATE"
  log "down: dev=${DEV:-none} state=$DEVSTATE"
  exit 0
fi

read -r SINCE LAST < "$STATE"
[ $((NOW - SINCE)) -lt $GRACE ] && exit 0
[ $((NOW - LAST)) -lt $RETRY ] && exit 0

echo "$SINCE $NOW" > "$STATE"
OUT=$(timeout 90 nmcli --wait 60 con up "$CON" 2>&1)
RC=$?
log "reconnect attempt after $((NOW - SINCE))s down (state=$DEVSTATE): rc=$RC $(echo "$OUT" | tail -1)"
