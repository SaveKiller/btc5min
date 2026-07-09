#!/usr/bin/env python3
"""Server: stdin = path relativi già presenti in locale; stdout = tar dei file mancanti."""
import re
import sys
import tarfile
from pathlib import Path

DATA = Path("/opt/btc5min/data")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main() -> None:
    if not DATA.is_dir():
        raise FileNotFoundError(f"remote data dir missing: {DATA}")

    have = {line.strip().replace("\\", "/") for line in sys.stdin if line.strip()}
    to_pack: list[tuple[Path, str]] = []

    for day in sorted(DATA.iterdir()):
        if not day.is_dir() or not DAY_RE.match(day.name):
            continue
        for sub in ("bin", "txt"):
            subdir = day / sub
            if not subdir.is_dir():
                continue
            for f in sorted(subdir.iterdir()):
                if not f.is_file():
                    continue
                rel = f"{day.name}/{sub}/{f.name}"
                if rel not in have:
                    to_pack.append((f, rel))

    clog = DATA / "collector.log"
    if clog.is_file() and "collector-poly.log" not in have:
        to_pack.append((clog, "collector-poly.log"))

    total_bytes = sum(p.stat().st_size for p, _ in to_pack)
    print(f"sync: {len(to_pack)} files, {total_bytes} bytes", file=sys.stderr)

    if not to_pack:
        return

    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tar:
        for path, arcname in to_pack:
            tar.add(path, arcname=arcname)


if __name__ == "__main__":
    main()
