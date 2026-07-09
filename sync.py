#!/usr/bin/env python3
"""Sync poly → locale: solo file mancanti, una sessione SSH, timestamp dal tar."""
import io
import os
import re
import subprocess
import sys
import tarfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HOST = "ticksaver"
REMOTE_CMD = "cd /opt/btc5min && venv/bin/python3 scripts/sync_pack.py"
SSH_BASE = ["ssh", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3"]
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def extract_tar(data: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
        members = [m for m in tar.getmembers() if m.name.endswith(".bin")]
        n = len(members)
        print(f"Estrazione {n} file .bin in data/ ...", flush=True)
        for i, member in enumerate(members, 1):
            tar.extract(member, DATA, filter="data")
            dest = DATA / member.name
            os.utime(dest, (member.mtime, member.mtime))
            if i == 1 or i == n or i % 20 == 0:
                print(f"  {i}/{n} {member.name}", flush=True)


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
        extract_tar(stdout_data)
    else:
        print("Nessun file da scaricare.", flush=True)

    print("Fatto.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERRORE: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
