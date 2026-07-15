"""Launcher dashv2: due processi spawn + fail-fast."""

from __future__ import annotations

import multiprocessing as mp
import signal
import sys
import time

from dashv2.config import load_config
from dashv2.engine import run_data_process
from dashv2.server import run_server_process


def main() -> None:
    mp.set_start_method("spawn", force=True)
    cfg = load_config()
    data_recv_cmd, server_send_cmd = mp.Pipe(duplex=False)
    server_recv_evt, data_send_evt = mp.Pipe(duplex=False)
    data_proc = mp.Process(target=run_data_process, args=(cfg, data_recv_cmd, data_send_evt), name="dashv2-data")
    server_proc = mp.Process(target=run_server_process, args=(cfg, server_send_cmd, server_recv_evt), name="dashv2-server")
    data_proc.start()
    server_proc.start()
    url = f"http://{cfg['host']}:{cfg['port']}/"
    print(f"Dashboard V2: {url}")
    print("Ctrl+C to stop")

    def _shutdown(*_args):
        for p in (server_proc, data_proc):
            if p.is_alive(): p.terminate()
        for p in (server_proc, data_proc):
            p.join(timeout=3)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    try:
        while True:
            for p in (data_proc, server_proc):
                if not p.is_alive():
                    print(f"process {p.name} exited with code {p.exitcode}")
                    _shutdown()
            time.sleep(0.5)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
