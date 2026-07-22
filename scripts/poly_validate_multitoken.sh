#!/bin/bash
set -e
DAY=$(date -u +%Y-%m-%d)
echo "UTC $(date -u)"
echo "=== done 5m ==="
for f in eth5m sol5m xrp5m doge5m bnb5m hype5m; do
  echo -n "$f: "
  grep ' done ' /opt/btc5min/data/collector-$f.log | tail -1 || echo none
done
echo "=== bins new ==="
ls /opt/btc5min/data/$DAY/bin/ | grep -E '^(eth|sol|xrp|doge|bnb|hype)' | sort || true
echo "=== btc ==="
systemctl is-active btc5min btc15min
grep ' done ' /opt/btc5min/data/collector.log | tail -2
free -m
PYTHONPATH=/opt/btc5min /opt/btc5min/venv/bin/python3 /opt/btc5min/scripts/poly_resource_snapshot.py > /tmp/snap.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/snap.json"))
print("units", d["unit_count"], "rss_mb", round(d["rss_sum_kb"]/1024,1),
      "estab", d["estab_sum"],
      "avail_mb", int(d["meminfo"]["MemAvailable"].split()[0])//1024)
active=sum(1 for u,v in d["units"].items() if v.get("active")=="active")
print("active_units", active)
PY
