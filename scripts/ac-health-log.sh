#!/bin/bash
# Records power + network health every minute so the NEXT crash leaves a trail
# right up to the moment it dies. Added while investigating the repeated
# under-voltage hangs (see PI_STABILITY_INVESTIGATION.md in the repo).
LOG=/var/log/ac-health.log
IFACE=$(ls /sys/class/net 2>/dev/null | grep -E '^wl' | head -1)
TH=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
TEMP=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2)
UP=$(cut -d' ' -f1 /proc/uptime); UP=${UP%.*}
LOAD=$(cut -d' ' -f1-3 /proc/loadavg)
MEM=$(awk '/MemAvailable/{printf "%dM", $2/1024}' /proc/meminfo)
IP=$(ip -4 -o addr show "$IFACE" 2>/dev/null | awk '{print $4}')
SIG=$(awk 'NR==3{gsub(/\./,"",$4); print $4}' /proc/net/wireless 2>/dev/null)
OPER=$(cat "/sys/class/net/$IFACE/operstate" 2>/dev/null)
GW=$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')
if [ -n "$GW" ] && ping -c1 -W2 "$GW" >/dev/null 2>&1; then GWP=ok; else GWP=FAIL; fi
printf '%s thr=%s temp=%s up=%ss load=%s avail=%s if=%s ip=%s sig=%sdBm oper=%s gw=%s\n' \
  "$(date -Is)" "${TH:-?}" "${TEMP:-?}" "$UP" "$LOAD" "${MEM:-?}" "${IFACE:-none}" \
  "${IP:-none}" "${SIG:-?}" "${OPER:-?}" "$GWP" >> "$LOG"
