#!/bin/bash
# Runs ON the Pi. Harvests everything needed to explain repeated network drops / hangs.
echo "######## HARVEST AT $(date -Is) ########"

echo "=== [1] MODEL / HARDWARE ==="
tr -d '\0' < /proc/device-tree/model 2>/dev/null; echo
grep -E 'Revision|Hardware|model name' /proc/cpuinfo 2>/dev/null | head -5
echo "RAM:"; free -m

echo "=== [2] POWER: UNDER-VOLTAGE / THROTTLING (bit0=UV now, bit16=UV since boot) ==="
for c in get_throttled measure_temp measure_volts; do
  echo -n "$c: "; vcgencmd $c 2>/dev/null || echo "vcgencmd unavailable"
done

echo "=== [3] UPTIME / BOOT HISTORY (how often is it actually restarting?) ==="
uptime -p; echo "booted: $(uptime -s)"
journalctl --list-boots --no-pager 2>/dev/null | tail -25

echo "=== [4] WAS THE LAST SHUTDOWN CLEAN? (abrupt tail = power loss / hard hang) ==="
echo "--- last 40 lines of PREVIOUS boot (-b -1) ---"
journalctl -b -1 -n 40 --no-pager 2>/dev/null || echo "no previous boot retained (persistent journal off?)"
echo "--- clean-shutdown markers in previous boot ---"
journalctl -b -1 --no-pager 2>/dev/null | grep -Ei 'Reached target.*(Shutdown|Reboot|Power-Off)|systemd-shutdown|Unmounting|watchdog|kernel panic|Oops|BUG:' | tail -20
echo "--- journal persistence ---"
ls -d /var/log/journal 2>/dev/null && echo "persistent journal: YES" || echo "persistent journal: NO (logs lost on reboot!)"

echo "=== [5] UNDER-VOLTAGE / THERMAL IN KERNEL LOG ==="
dmesg -T 2>/dev/null | grep -Ei 'under-?voltage|voltage normal|throttl|temperature' | tail -30

echo "=== [6] NETWORK HARDWARE: onboard vs USB dongle ==="
echo "--- links ---"; ip -br link
echo "--- lsusb ---"; lsusb 2>/dev/null
echo "--- wifi driver in use ---"
for n in /sys/class/net/*; do
  d=$(basename "$n"); [ "$d" = lo ] && continue
  echo "$d -> driver: $(basename "$(readlink -f "$n/device/driver" 2>/dev/null)" 2>/dev/null)  path: $(readlink -f "$n/device" 2>/dev/null)"
done
echo "--- iw info ---"; iw dev 2>/dev/null

echo "=== [7] WIFI POWER SAVE (a classic silent-drop cause) ==="
for w in $(ls /sys/class/net | grep -E '^wl'); do
  echo -n "$w power_save: "; iw dev "$w" get power_save 2>/dev/null || echo unknown
  echo "  link: $(iw dev "$w" link 2>/dev/null | tr '\n' ' ')"
done

echo "=== [8] USB RESETS / DONGLE DISCONNECTS / DRIVER CRASHES ==="
dmesg -T 2>/dev/null | grep -Ei 'usb .*(disconnect|reset|new .* device)|rtl[0-9]|8192|8188|brcmfmac|cfg80211|ieee80211|firmware|deauth|beacon loss|link is not ready' | tail -40

echo "=== [9] SD CARD / FILESYSTEM HEALTH (read-only root = needs power cycle) ==="
mount | grep -E ' / | /boot' 
dmesg -T 2>/dev/null | grep -Ei 'mmc|ext4|EXT4-fs error|I/O error|read-only|remount' | tail -30
echo "--- disk usage (full disk hangs services) ---"; df -h /
echo "--- inode usage ---"; df -i /

echo "=== [10] OOM KILLER (1GB Pi running two python services) ==="
dmesg -T 2>/dev/null | grep -Ei 'Out of memory|oom-kill|Killed process' | tail -20
journalctl -b -1 --no-pager 2>/dev/null | grep -Ei 'Out of memory|oom-kill' | tail -10
echo "--- current memory ---"; free -m; echo "--- swap ---"; swapon --show 2>/dev/null

echo "=== [11] NETWORK STACK EVENTS THIS BOOT ==="
journalctl -b 0 --no-pager 2>/dev/null | grep -Ei 'dhcpcd|wpa_supplicant|NetworkManager|networkd|carrier|link (up|down)|associated|disassoc|CTRL-EVENT' | tail -40

echo "=== [12] NETWORK CONFIG (static IP setup, conflicts) ==="
ip -4 addr; echo "--- routes ---"; ip route
echo "--- dhcpcd.conf (non-comment) ---"; grep -vE '^\s*#|^\s*$' /etc/dhcpcd.conf 2>/dev/null
echo "--- NetworkManager conns ---"; nmcli -t con show 2>/dev/null
echo "--- wpa_supplicant nets (SSIDs only) ---"; grep -E 'ssid=' /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null

echo "=== [13] SERVICES ==="
for s in telegram-ac-bot ac-web; do
  echo "--- $s: $(systemctl is-active $s 2>/dev/null) / $(systemctl is-enabled $s 2>/dev/null) ---"
  systemctl show $s -p NRestarts 2>/dev/null
done
echo "--- failed units ---"; systemctl --failed --no-pager 2>/dev/null

echo "=== [14] CLOCK (chrony) ==="
timedatectl 2>/dev/null | head -8
chronyc tracking 2>/dev/null | head -6

echo "######## END HARVEST ########"
