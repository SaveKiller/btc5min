#!/bin/bash
# Campiona risorse ogni 120s per 30 iterazioni (~1h)
OUT=/opt/btc5min/data/reports/resource_btc15m.jsonl
mkdir -p /opt/btc5min/data/reports
for i in $(seq 1 30); do
  /opt/btc5min/venv/bin/python3 /opt/btc5min/scripts/poly_resource_snapshot.py >> "$OUT"
  sleep 120
done
