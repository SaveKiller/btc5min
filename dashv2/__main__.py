"""Launcher dashv2: tre processi spawn + fail-fast server/engine + bot soft + restart."""

from __future__ import annotations

import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path

from dashv2.bots.bot_process import run_bot_process
from dashv2.config import load_config
from dashv2.engine import run_engine_process
from dashv2.server import run_server_process


def main() -> None:
    mp.set_start_method("spawn", force=True)
    cfg = load_config()
    sentinel = Path(cfg["data_dir"]) / "restart"
    if sentinel.exists():
        sentinel.unlink()
        print("cleared leftover restart sentinel", flush=True)
    eng_recv_cmd, server_send_cmd = mp.Pipe(duplex=False)
    server_recv_evt, eng_send_evt = mp.Pipe(duplex=False)
    engine_proc = mp.Process(
        target=run_engine_process, args=(cfg, eng_recv_cmd, eng_send_evt), name="dashv2-engine")
    server_proc = mp.Process(
        target=run_server_process, args=(cfg, server_send_cmd, server_recv_evt), name="dashv2-server")
    bot_proc = mp.Process(target=run_bot_process, args=(cfg,), name="dashv2-bot")
    engine_proc.start()
    server_proc.start()
    bot_proc.start()
    url = f"http://{cfg['host']}:{cfg['port']}/"
    print(f"Dashboard V2: {url}")
    print(f"engine plugin: {cfg['engine_plugin']}")
    print(f"restart watch: {sentinel}")
    print("Ctrl+C to stop")

    def _kill_children() -> None:
        for p in (server_proc, engine_proc, bot_proc):
            if p.is_alive():
                p.terminate()
        for p in (server_proc, engine_proc, bot_proc):
            p.join(timeout=3)

    def _shutdown(*_args):
        _kill_children()
        sys.exit(0)

    def _restart() -> None:
        print("restart sentinel found, reloading...", flush=True)
        sentinel.unlink()
        _kill_children()
        os.execv(sys.executable, [sys.executable, "-m", "dashv2"])

    def _respawn_bot() -> mp.Process:
        p = mp.Process(target=run_bot_process, args=(cfg,), name="dashv2-bot")
        p.start()
        print(f"bot process respawned pid={p.pid}", flush=True)
        return p

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    try:
        while True:
            if sentinel.exists():
                _restart()
            if not engine_proc.is_alive() or not server_proc.is_alive():
                dead = "dashv2-engine" if not engine_proc.is_alive() else "dashv2-server"
                code = engine_proc.exitcode if dead == "dashv2-engine" else server_proc.exitcode
                print(f"process {dead} exited with code {code}")
                _shutdown()
            if not bot_proc.is_alive():
                print(f"process dashv2-bot exited with code {bot_proc.exitcode} (soft, respawning)", flush=True)
                bot_proc = _respawn_bot()
            time.sleep(2.0)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
