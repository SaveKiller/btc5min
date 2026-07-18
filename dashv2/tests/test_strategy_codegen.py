"""Test codegen extract/validate + strategy runner (senza Cursor)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dashv2.bots.runner import StrategyRunner
from dashv2.config import reload_strategy_codegen_system_prompt
from dashv2.strategies import create_strategy, delete_strategy, strategies_dir, write_module
from dashv2.strategy_codegen import build_codegen_prompt, extract_python_source, validate_module_source


_STUB = '''
def on_round_start(ctx):
    return []

def on_tick(ctx):
    if ctx.get("sec") == 200 and ctx.get("tradable"):
        return [{"cmd": "order.place", "side": "Up", "size_usd": 10.0}]
    return []

def on_round_end(ctx):
    return []
'''


class TestCodegenParse(unittest.TestCase):
    def test_extract_fence(self):
        raw = "Here is the module:\n```python\ndef on_tick(ctx):\n    return []\n```\n"
        src = extract_python_source(raw)
        self.assertIn("def on_tick", src)
        validate_module_source(src)

    def test_validate_requires_on_tick(self):
        with self.assertRaises(RuntimeError):
            validate_module_source("def foo():\n    pass\n")

    def test_system_prompt_in_build(self):
        prompt = build_codegen_prompt("buy Up", "usa il campo mtm_usd dell'ordine aperto")
        self.assertIn("mtm_usd", prompt)
        self.assertIn("buy Up", prompt)
        self.assertIn("PRE-PROMPT", prompt)

    def test_contract_documents_per_order_size(self):
        prompt = build_codegen_prompt("size piccola poi grande", "SIZE: ogni order.place DEVE includere size_usd")
        self.assertIn("size_usd", prompt)
        self.assertIn("può essere diversa tra un ordine e l'altro", prompt)
        self.assertIn("SIZE", prompt)

    def test_reload_system_prompt_from_md(self):
        text = reload_strategy_codegen_system_prompt()
        self.assertIn("COUNTDOWN", text)
        self.assertIn("QUOTA SENZA ASK/BID", text)


class TestStrategyRunner(unittest.TestCase):
    def test_dispatch_place(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            data = create_strategy(
                root, "Stub", "deterministic", "d", rules="buy at 200",
                module_file="x.py", strategy_id="abc123def456")
            write_module(root, data["id"], _STUB)
            runner = StrategyRunner(root)
            runner.sync([data["id"]])
            pairs = runner.dispatch("on_tick", [data["id"]], {
                "sec": 200, "tradable": True, "open_orders": [], "bot_active": True,
            })
            self.assertEqual(len(pairs), 1)
            sid, act = pairs[0]
            self.assertEqual(sid, data["id"])
            self.assertEqual(act["cmd"], "order.place")
            self.assertEqual(act["side"], "Up")

    def test_delete_removes_py(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            data = create_strategy(
                root, "Stub", "deterministic", "", rules="r",
                module_file="strategy_x.py", strategy_id="deadbeefcafe")
            write_module(root, data["id"], _STUB)
            py = root / f"strategy_{data['id']}.py"
            self.assertTrue(py.is_file())
            delete_strategy(root, data["id"])
            self.assertFalse(py.is_file())
            self.assertFalse((root / f"strategy_{data['id']}.json").is_file())


if __name__ == "__main__":
    unittest.main()
