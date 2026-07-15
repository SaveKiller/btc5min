"""Test che le response IPC viaggiano sulla pipe evt (unidirezionale)."""

import multiprocessing as mp
import unittest

from dashv2 import ipc


def _data_echo(cmd_conn, evt_conn):
    msg = cmd_conn.recv()
    evt_conn.send(ipc.make_response(msg["request_id"], {"echo": msg["cmd"]}))


class TestIpcPipeDirection(unittest.TestCase):
    def test_response_on_evt_pipe(self):
        mp.set_start_method("spawn", force=True)
        data_recv, server_send = mp.Pipe(duplex=False)
        server_recv, data_send = mp.Pipe(duplex=False)
        p = mp.Process(target=_data_echo, args=(data_recv, data_send))
        p.start()
        req = ipc.make_request("test.cmd", {"x": 1})
        server_send.send(req)
        deadline = 5.0
        import time
        t0 = time.monotonic()
        res = None
        while time.monotonic() - t0 < deadline:
            if server_recv.poll(0.05):
                msg = server_recv.recv()
                if ipc.is_response(msg):
                    res = msg
                    break
        p.terminate()
        p.join(timeout=2)
        self.assertIsNotNone(res)
        self.assertEqual(res["payload"]["echo"], "test.cmd")


if __name__ == "__main__":
    unittest.main()
