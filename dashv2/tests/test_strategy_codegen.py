"""Test codegen extract/validate + strategy runner (senza Cursor)."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from dashv2.bots.runner import StrategyRunner
from dashv2.config import reload_common_prompt, reload_strategy_codegen_system_prompt
from dashv2.strategies import (
    clone_strategy, create_strategy, delete_strategy,
    load_strategy, module_path, strategies_dir, update_strategy, write_module,
)
from dashv2.agents.strategy_codegen import (
    build_coded_rules_prompt, build_codegen_prompt, extract_python_source, validate_module_source,
)


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

_STUB2 = '''
def on_round_start(ctx):
    return []

def on_tick(ctx):
    return [{"cmd": "order.place", "side": "Down", "size_usd": 5.0}]

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
        self.assertIn("zona bianca", text)
        self.assertIn("Up_ask + Down_ask", text)
        self.assertIn("mark-to-market", text)

    def test_common_prompt_shared(self):
        common = reload_common_prompt()
        self.assertIn("Mercato Polymarket", common)
        self.assertIn("Coded rules", common)
        self.assertIn("Rispondi SEMPRE in italiano", common)
        agentish = reload_strategy_codegen_system_prompt()
        self.assertTrue(agentish.startswith(common[:40]))
        coded = build_coded_rules_prompt("def on_tick(ctx):\n    return []\n")
        self.assertIn("Reverse-pass", coded)
        self.assertIn("Up_ask + Down_ask", coded)
        self.assertIn("Apertura:", coded)

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

        with unittest.mock.patch("dashv2.agents.strategy_codegen.call_model", side_effect=fake_call):
            from dashv2.agents.strategy_codegen import generate_strategy_module
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

        with unittest.mock.patch("dashv2.agents.strategy_codegen.call_model", side_effect=fake_call):
            from dashv2.agents.strategy_codegen import generate_strategy_module
            with self.assertRaises(Exception):
                generate_strategy_module(
                    "buy", model_id="m", params={}, system_prompt="INDENTAZIONE note",
                    max_attempts=2,
                )

    def test_generate_coded_rules_shape(self):
        with unittest.mock.patch(
            "dashv2.agents.strategy_codegen.call_model",
            return_value="Apertura:\n- place Up\n\nChiusura:\n- y\n\nVincoli:\n- z\n",
        ):
            from dashv2.agents.strategy_codegen import generate_coded_rules
            out = generate_coded_rules(
                _STUB, model_id="m", params={}, max_attempts=1,
            )
        self.assertIn("Apertura:", out)
        self.assertIn("place Up", out)

    def test_create_and_clone_coded_rules(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            mf = write_module(root, "srcid000001", _STUB, 1)
            src = create_strategy(
                root, "Alpha", "deterministic", "d", rules="buy",
                module_file=mf, strategy_id="srcid000001",
                coded_rules="Apertura:\n- x\n\nChiusura:\n- y\n\nVincoli:\n- z\n",
            )
            self.assertEqual(src["version"], 1)
            self.assertIn("Apertura:", src["coded_rules"])
            c1 = clone_strategy(root, src["id"])
            self.assertEqual(c1["coded_rules"], src["coded_rules"])
            self.assertEqual(c1["version"], 1)


class TestStrategyVersioning(unittest.TestCase):
    def test_create_version_1(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            mf = write_module(root, "abc123def456", _STUB, 1)
            data = create_strategy(
                root, "Stub", "deterministic", "d", rules="buy",
                coded_rules="", module_file=mf, strategy_id="abc123def456")
            self.assertEqual(data["version"], 1)
            self.assertEqual(len(data["versions"]), 1)
            self.assertTrue(module_path(root, data["id"], 1).is_file())

    def test_bump_keeps_old_module(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            sid = "abc123def456"
            mf1 = write_module(root, sid, _STUB, 1)
            create_strategy(
                root, "Stub", "deterministic", "d", rules="r1",
                coded_rules="c1", module_file=mf1, strategy_id=sid)
            mf2 = write_module(root, sid, _STUB2, 2)
            updated = update_strategy(
                root, sid, "Stub", "d", module_rebuilt=True,
                rules="r2", module_file=mf2, coded_rules="c2")
            self.assertEqual(updated["version"], 2)
            self.assertEqual(len(updated["versions"]), 2)
            self.assertTrue(module_path(root, sid, 1).is_file())
            self.assertTrue(module_path(root, sid, 2).is_file())
            self.assertIn("Up", module_path(root, sid, 1).read_text(encoding="utf-8"))
            self.assertIn("Down", module_path(root, sid, 2).read_text(encoding="utf-8"))

    def test_desc_only_no_bump(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            sid = "abc123def456"
            mf = write_module(root, sid, _STUB, 1)
            create_strategy(
                root, "Stub", "deterministic", "d", rules="r1",
                coded_rules="", module_file=mf, strategy_id=sid)
            updated = update_strategy(
                root, sid, "Stub", "new desc", module_rebuilt=False)
            self.assertEqual(updated["version"], 1)
            self.assertEqual(updated["description"], "new desc")

    def test_rename_in_place(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            sid = "abc123def456"
            mf = write_module(root, sid, _STUB, 1)
            create_strategy(
                root, "Stub", "deterministic", "d", rules="r1",
                coded_rules="", module_file=mf, strategy_id=sid)
            mf2 = write_module(root, sid, _STUB2, 2)
            update_strategy(
                root, sid, "Stub", "d", module_rebuilt=True,
                rules="r2", module_file=mf2, coded_rules="c2")
            renamed = update_strategy(
                root, sid, "Renamed", "new desc", module_rebuilt=False)
            self.assertEqual(renamed["id"], sid)
            self.assertEqual(renamed["name"], "Renamed")
            self.assertEqual(renamed["version"], 2)
            self.assertEqual(len(renamed["versions"]), 2)
            self.assertEqual(renamed["description"], "new desc")
            loaded = load_strategy(root, sid)
            self.assertEqual(loaded["name"], "Renamed")

    def test_edit_from_past_bumps_tip(self):
        """Simula tip=2: rebuild → tip=3, v1/v2 intatti."""
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            sid = "abc123def456"
            mf1 = write_module(root, sid, _STUB, 1)
            create_strategy(
                root, "Stub", "deterministic", "d", rules="r1",
                coded_rules="", module_file=mf1, strategy_id=sid)
            mf2 = write_module(root, sid, _STUB, 2)
            update_strategy(
                root, sid, "Stub", "d", module_rebuilt=True,
                rules="r2", module_file=mf2, coded_rules="")
            mf3 = write_module(root, sid, _STUB2, 3)
            updated = update_strategy(
                root, sid, "Stub", "d", module_rebuilt=True,
                rules="r1-edited", module_file=mf3, coded_rules="c3")
            self.assertEqual(updated["version"], 3)
            self.assertEqual(updated["versions"][0]["rules"], "r1")
            self.assertEqual(updated["versions"][2]["rules"], "r1-edited")
            self.assertTrue(module_path(root, sid, 1).is_file())
            self.assertTrue(module_path(root, sid, 2).is_file())


class TestStrategyRunner(unittest.TestCase):
    def test_dispatch_place(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            mf = write_module(root, "abc123def456", _STUB, 1)
            data = create_strategy(
                root, "Stub", "deterministic", "d", rules="buy at 200",
                coded_rules="", module_file=mf, strategy_id="abc123def456")
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
            mf = write_module(root, "deadbeefcafe", _STUB, 1)
            data = create_strategy(
                root, "Stub", "deterministic", "", rules="r",
                coded_rules="", module_file=mf, strategy_id="deadbeefcafe")
            py = module_path(root, data["id"], 1)
            self.assertTrue(py.is_file())
            delete_strategy(root, data["id"])
            self.assertFalse(py.is_file())
            self.assertFalse((root / f"strategy_{data['id']}.json").is_file())

    def test_clone_copies_module_and_name(self):
        with tempfile.TemporaryDirectory() as td:
            root = strategies_dir(Path(td))
            mf = write_module(root, "srcid000001", _STUB, 1)
            src = create_strategy(
                root, "Alpha", "deterministic", "desc", rules="buy up",
                coded_rules="", module_file=mf, strategy_id="srcid000001")
            c1 = clone_strategy(root, src["id"])
            self.assertEqual(c1["name"], "Alpha (copy)")
            self.assertEqual(c1["rules"], "buy up")
            self.assertEqual(c1["version"], 1)
            self.assertNotEqual(c1["id"], src["id"])
            self.assertTrue(module_path(root, c1["id"], 1).is_file())
            self.assertEqual(
                module_path(root, c1["id"], 1).read_text(encoding="utf-8"),
                module_path(root, src["id"], 1).read_text(encoding="utf-8"),
            )
            c2 = clone_strategy(root, src["id"])
            self.assertEqual(c2["name"], "Alpha (copy 2)")


if __name__ == "__main__":
    unittest.main()
