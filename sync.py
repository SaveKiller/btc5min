#!/usr/bin/env python3
"""Sync poly → locale: solo file mancanti, una sessione SSH, timestamp dal tar."""
import io
import math
import os
import re
import subprocess
import sys
import tarfile
import threading
from pathlib import Path

from src.binary_format import read_round, txt_path_for_bin

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HOST = "ticksaver"
REMOTE_CMD = "cd /opt/btc5min && venv/bin/python3 scripts/sync_pack.py"
SSH_BASE = ["ssh", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3"]
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROUND_SEC = 300


def build_manifest() -> str:
    paths: set[str] = set()
    if DATA.is_dir():
        for day in sorted(DATA.iterdir()):
            if not day.is_dir() or not DAY_RE.match(day.name):
                continue
            bin_dir = day / "bin"
            if not bin_dir.is_dir():
                continue
            for f in bin_dir.iterdir():
                if f.is_file() and f.suffix == ".bin":
                    paths.add(f"{day.name}/bin/{f.name}")
    return "\n".join(sorted(paths)) + ("\n" if paths else "")


def drain_stderr(proc: subprocess.Popen, buf: list[bytes]) -> None:
    assert proc.stderr is not None
    for chunk in iter(proc.stderr.readline, b""):
        buf.append(chunk)


def read_stdout(proc: subprocess.Popen) -> bytes:
    assert proc.stdout is not None
    buf = bytearray()
    while True:
        chunk = proc.stdout.read(256 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        print(f"  ricevuti {len(buf)} byte", flush=True)
    return bytes(buf)


def extract_tar(data: bytes) -> list[Path]:
    downloaded: list[Path] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        members = [m for m in tar.getmembers() if m.name.endswith(".bin")]
        n = len(members)
        print(f"Estrazione {n} file .bin in data/ ...", flush=True)
        for i, member in enumerate(members, 1):
            tar.extract(member, DATA, filter="data")
            dest = DATA / member.name
            os.utime(dest, (member.mtime, member.mtime))
            downloaded.append(dest)
            if i == 1 or i == n or i % 20 == 0:
                print(f"  {i}/{n} {member.name}", flush=True)
    return downloaded


def start_ts_from_bin(path: Path) -> int:
    return int(path.stem.split("_")[1])


def find_bin_at_ts(start_ts: int) -> Path | None:
    matches = list(DATA.glob(f"**/bin/btc5m_{start_ts}_*.bin"))
    if not matches:
        return None
    if len(matches) > 1:
        raise Exception(f"multiple bins for start_ts {start_ts}: {matches}")
    return matches[0]


def trim_downloaded_nan_tail(downloaded: list[Path]) -> None:
    if not downloaded:
        return
    downloaded_ts = {start_ts_from_bin(p) for p in downloaded}
    ts = max(downloaded_ts)
    deleted = 0
    print("Tail trim final_gamma nan sui bin appena scaricati ...", flush=True)
    while True:
        path = find_bin_at_ts(ts)
        if path is None:
            print(f"tail trim: stop, bin assente per ts={ts}", flush=True)
            break
        header, _, _ = read_round(str(path))
        if not math.isnan(header["final_gamma"]):
            print(f"tail trim: anchor {path.name} final_gamma ok", flush=True)
            break
        if ts not in downloaded_ts:
            print(f"tail trim: stop a {path.name} (nan, non scaricato in questa sync)", flush=True)
            break
        txt = txt_path_for_bin(str(path))
        path.unlink()
        if txt.is_file():
            txt.unlink()
        deleted += 1
        print(f"tail trim: deleted {path.name}", flush=True)
        ts -= ROUND_SEC
    print(f"tail trim: deleted {deleted} bin", flush=True)


def main() -> None:
    print(f"Sync {HOST}:/opt/btc5min/data -> data/ (solo .bin mancanti)", flush=True)

    print("Scansione file locali ...", flush=True)
    manifest = build_manifest()
    local_count = len([ln for ln in manifest.splitlines() if ln.strip()])
    print(f"Locale: {local_count} bin gia presenti", flush=True)

    DATA.mkdir(exist_ok=True)
    print("Connessione a poly, trasferimento ...", flush=True)
    proc = subprocess.Popen(
        SSH_BASE + [HOST, REMOTE_CMD],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    proc.stdin.write(manifest.encode())
    proc.stdin.close()

    stderr_buf: list[bytes] = []
    err_thread = threading.Thread(target=drain_stderr, args=(proc, stderr_buf), daemon=True)
    err_thread.start()
    stdout_data = read_stdout(proc)
    proc.wait()
    err_thread.join()
    if proc.returncode != 0:
        raise RuntimeError(f"ssh sync failed, exit {proc.returncode}")

    for chunk in stderr_buf:
        print(chunk.decode(), end="", flush=True)

    if stdout_data:
        downloaded = extract_tar(stdout_data)
        trim_downloaded_nan_tail(downloaded)
    else:
        print("Nessun file da scaricare.", flush=True)

    print("Fatto.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERRORE: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
