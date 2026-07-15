"""Test envelope IPC."""

import unittest

from dashv2 import ipc


class TestIpc(unittest.TestCase):
    def test_request_response(self):
        req = ipc.make_request("replay.play", {}, "rid1")
        self.assertEqual(req["kind"], "request")
        res = ipc.make_response("rid1", {"ok": True})
        self.assertTrue(ipc.is_response(res))
        err = ipc.make_error("rid1", "fail")
        self.assertIn("error", err)

    def test_event(self):
        ev = ipc.make_event("tick", {"sec": 100})
        self.assertTrue(ipc.is_event(ev))
