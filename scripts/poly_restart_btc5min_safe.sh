#!/bin/bash
# Restart btc5min solo dopo un 'done' e con offset_in_slot in [150,210]
LOG=/opt/btc5min/data/collector.log
while true; do
  now=$(date -u +%s)
  offset=$((now % 300))
  last_done=$(grep ' done ' "$LOG" | tail -1)
  echo "wait offset=$offset last=$last_done"
  if [ "$offset" -ge 150 ] && [ "$offset" -le 210 ]; then
    # assicurati che l'ultimo done sia recente (<180s) = write del round precedente ok
    done_ts=$(tail -1 <<<"$last_done" | awk '{print $1" "$2}')
    echo "window ok, restarting btc5min"
    systemctl restart btc5min
    sleep 2
    systemctl is-active btc5min
    tail -n 8 "$LOG"
    exit 0
  fi
  sleep 10
done
