#!/bin/bash
# Restart tutti i collector dopo un 'done' e con offset 5m in [150,210]
UNITS="btc5min btc15min eth5m eth15m sol5m sol15m xrp5m xrp15m doge5m doge15m bnb5m bnb15m hype5m hype15m"
LOG=/opt/btc5min/data/collector.log
while true; do
  now=$(date -u +%s)
  offset=$((now % 300))
  last=$(grep ' done ' "$LOG" | tail -1)
  echo "wait offset=$offset last=$last"
  if [ "$offset" -ge 150 ] && [ "$offset" -le 210 ]; then
    echo "restarting all collectors"
    systemctl restart $UNITS
    sleep 3
    for u in $UNITS; do
      printf '%-10s %s\n' "$u" "$(systemctl is-active "$u")"
    done
    exit 0
  fi
  sleep 5
done
