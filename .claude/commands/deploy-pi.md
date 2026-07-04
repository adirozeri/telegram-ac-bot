---
description: Pull latest main on the Raspberry Pi and restart the telegram-ac-bot service
allowed-tools: Bash(ssh:*)
---

Deploy the latest `main` to the Raspberry Pi and restart the bot.

Connection (see CLAUDE.md): `ssh -o ConnectTimeout=8 pi@192.168.1.135` (WiFi, static). Passwordless key-based SSH and passwordless `sudo` are set up. Install path: `/home/pi/telegram-ac-bot/`, venv `telegram-bot-env/`, service `telegram-ac-bot`.

Run this as a single SSH command and report the result:

```bash
ssh -o ConnectTimeout=8 pi@192.168.1.135 'cd /home/pi/telegram-ac-bot && \
  OLD=$(git rev-parse HEAD) && \
  git fetch origin -q && git reset --hard origin/main && \
  NEW=$(git rev-parse HEAD) && \
  if ! git diff --quiet "$OLD" "$NEW" -- requirements.txt; then \
    echo "requirements changed -> reinstalling"; telegram-bot-env/bin/pip install -q -r requirements.txt; \
  fi && \
  sudo systemctl restart telegram-ac-bot && sleep 2 && \
  echo "deployed: $(git rev-parse --short HEAD)  active: $(systemctl is-active telegram-ac-bot)" && \
  journalctl -u telegram-ac-bot -n 15 --no-pager'
```

Then tell the user: the deployed commit hash, whether the service is `active`, and flag anything abnormal in the log tail (ignore the known `192.168.1.126:10000` Errno 111 AC-unreachable errors unless the user is working on that).

If `git fetch` fails with `server certificate verification failed`, the Pi's clock has drifted — fix it first:
`L=$(date -u '+%Y-%m-%d %H:%M:%S'); ssh -o ConnectTimeout=8 pi@192.168.1.135 "sudo date -u -s '$L' && sudo systemctl restart systemd-timesyncd"` — then retry.
