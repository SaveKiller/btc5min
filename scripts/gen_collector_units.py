#!/usr/bin/env python3
"""Genera unit systemd collector per asset×interval (stdout o --write DIR)."""
from __future__ import annotations

import argparse
from pathlib import Path

TEMPLATE = """[Unit]
Description=BTC5MIN Polymarket collector ({ASSET_UP} Up/Down {INTERVAL})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/btc5min
ExecStart=/opt/btc5min/venv/bin/python3 -m src.main --asset {ASSET} --interval {INTERVAL}
Restart=always
RestartSec=5
StandardOutput=append:/opt/btc5min/data/collector-{NAME}.log
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--assets", default="eth,sol,xrp,doge,bnb,hype")
    p.add_argument("--intervals", default="5m,15m")
    p.add_argument("--write", default="")
    args = p.parse_args()
    assets = [a.strip() for a in args.assets.split(",") if a.strip()]
    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]
    out_dir = Path(args.write) if args.write else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        for interval in intervals:
            name = f"{asset}{interval}"
            text = TEMPLATE.format(
                ASSET=asset, INTERVAL=interval, NAME=name, ASSET_UP=asset.upper())
            if out_dir:
                path = out_dir / f"{name}.service"
                path.write_text(text, encoding="utf-8", newline="\n")
                print(f"wrote {path}")
            else:
                print(f"=== {name}.service ===")
                print(text)


if __name__ == "__main__":
    main()
