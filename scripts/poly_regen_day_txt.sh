#!/bin/bash
# Rigenera .txt del giorno per tutti i .bin (usa price_decimals nuovi)
DAY=${1:-$(date -u +%Y-%m-%d)}
BIN_DIR=/opt/btc5min/data/$DAY/bin
cd /opt/btc5min
export PYTHONPATH=/opt/btc5min
n=0
for bp in "$BIN_DIR"/*.bin; do
  [ -f "$bp" ] || continue
  /opt/btc5min/venv/bin/python3 -m src.convert "$bp" -o /tmp/_cvt_out.txt >/dev/null
  # convert with -o writes only that path; use write_round_txt via python
  /opt/btc5min/venv/bin/python3 - <<PY
from src.convert import write_round_txt, read_txt_warnings
from src.binary_format import txt_path_for_bin
bp = "$bp"
write_round_txt(bp, read_txt_warnings(str(txt_path_for_bin(bp))))
print("ok", bp)
PY
  n=$((n+1))
done
echo "regenerated $n txt for $DAY"
