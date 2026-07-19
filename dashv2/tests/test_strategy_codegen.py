"""Test codegen extract/validate + strategy runner (senza Cursor)."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from dashv2.bots.runner import StrategyRunner
from dashv2.config import reload_strategy_codegen_system_prompt
from dashv2.strategies import clone_strategy, create_strategy, delete_strategy, module_path, strategies_dir, write_module
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
        self.assertIn("INDENTAZIONE", text)
        self.assertIn("LESSICO DASHBOARD", text)
        self.assertIn("Model A", text)
        self.assertIn("p_win_pct", text)
        self.assertIn("dwin_pct_for_side", text)
        self.assertIn("Rq", text)
        self.assertIn("LIQ2", text)
        self.assertIn("terminologia ufficiale", text)
        self.assertIn("zona bianca", text)

    def test_contract_documents_dwin_shapes(self):
        prompt = build_codegen_prompt("Model A >= 75%", "usa dwin_a")
        self.assertIn("p_win_pct", prompt)
        self.assertIn("MAI float(dwin_a)", prompt)
        self.assertIn("liq2_ask_usd", prompt)
        self.assertIn("ptb_chainlink", prompt)
        self.assertIn("Model A", prompt)

    def test_codegen_retries_syntax_error_silently(self):
        bad = "```python\ndef on_tick(ctx):\n  return []\n    return []\n```\n"
        good = "```python\ndef on_tick(ctx):\n    return []\n```\n"
        calls = {"n": 0}

        def fake_call(prompt, model_id, params, cwd):
            calls["n"] += 1
            return bad if calls["n"] == 1 else good

        with unittest.mock.patch("dashv2.strategy_codegen.call_model", side_effect=fake_call):
            from dashv2.strategy_codegen import generate_strategy_module
            src = generate_strategy_module(
                "buy", model_id="m", params={}, system_prompt="INDENTAZIONE note",
                max_attempts=3,
            )
        self.assertIn("def on_tick", src)
        self.assertEqual(calls["n"], 2)

    def test_codegen_raises_after_exhausted_retries(self):
        bad = "```python\ndef on_tick(ctx):\n  return []\n    return []\n```\n"

        def fake_call(prompt, model_id, params, cwd):
            return bad

        with unittest.mock.patch("dashv2.strategy_codegen.call_model", side_effect=fake_call):
            from dashv2.strategy_codegen import generate_strategy_module
            with self.assertRaises(SyntaxError):
                generate_strategy_module(
                    "buy", model_id="m", params={}, system_prompt="x", max_attempts=2,
                )


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

    def test_clone_copies_module_and_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            src = create_strategy(
                root, "Alpha", "deterministic", "desc", rules="buy up",
                module_file="strategy_srcid000001.py", strategy_id="srcid000001")
            write_module(root, src["id"], _STUB)
            c1 = clone_strategy(root, src["id"])
            self.assertEqual(c1["name"], "Alpha (copy)")
            self.assertEqual(c1["rules"], "buy up")
            self.assertNotEqual(c1["id"], src["id"])
            self.assertTrue(module_path(root, c1["id"]).is_file())
            self.assertEqual(
                module_path(root, c1["id"]).read_text(encoding="utf-8"),
                module_path(root, src["id"]).read_text(encoding="utf-8"),
            )
            c2 = clone_strategy(root, src["id"])
            self.assertEqual(c2["name"], "Alpha (copy 2)")


if __name__ == "__main__":
    unittest.main()
