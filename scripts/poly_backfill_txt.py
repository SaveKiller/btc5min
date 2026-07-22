from pathlib import Path
from src.binary_format import read_round, txt_path_for_bin
from src.convert import warnings_from_header, write_round_txt

bins = [
    "/opt/btc5min/data/2026-07-22/bin/btc5m_1784716500_1035.bin",
    "/opt/btc5min/data/2026-07-22/bin/btc5m_1784716800_1040.bin",
]
for bp in bins:
    h, _, _ = read_round(bp)
    write_round_txt(bp, warnings_from_header(h))
    tp = txt_path_for_bin(bp)
    print(tp, tp.exists(), tp.stat().st_size)
