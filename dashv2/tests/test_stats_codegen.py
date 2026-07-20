"""Test codegen extract/validate + CRUD analyze (senza Cursor)."""

from __future__ import annotations

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from dashv2.config import reload_stats_codegen_system_prompt
from dashv2.agents.stats_codegen import (
    build_codegen_prompt,
    extract_python_source,
    validate_analyze_source,
)
from dashv2.stats_modules import (
    create_analyze,
    delete_analyze,
    list_analyzes,
    module_path,
    stats_dir,
    write_analyze_module,
)


_STUB = '''
def analyze_round(round_view):
    return {"n_ticks": len(round_view["ticks"])}

def reduce_results(per_round):
    return f"# Stats\\n\\nrounds_ok: {sum(1 for r in per_round if r.get('ok'))}\\n"
'''


class TestStatsCodegenParse(unittest.TestCase):
    def test_extract_fence(self):
        raw = "Here:\n```python\ndef analyze_round(round_view):\n    return {}\n```\n"
        src = extract_python_source(raw)
        self.assertIn("def analyze_round", src)
        validate_analyze_source(src)

    def test_validate_requires_analyze_round(self):
        with self.assertRaises(RuntimeError):
            validate_analyze_source("def foo():\n    pass\n")

    def test_validate_accepts_optional_reduce(self):
        validate_analyze_source(_STUB)

    def test_system_prompt_in_build(self):
        prompt = build_codegen_prompt("conta majority flips", "usa round_view['ticks']")
        self.assertIn("round_view", prompt)
        self.assertIn("conta majority flips", prompt)
        self.assertIn("PRE-PROMPT", prompt)

    def test_contract_documents_round_view_and_reduce(self):
        prompt = build_codegen_prompt("stats", "x")
        self.assertIn("market_start_ts", prompt)
        self.assertIn("hour_utc", prompt)
        self.assertIn("outcome", prompt)
        self.assertIn("ptb_chainlink", prompt)
        self.assertIn("final_chainlink", prompt)
        self.assertIn("fee_rate", prompt)
        self.assertIn("ticks", prompt)
        self.assertIn("secs", prompt)
        self.assertIn("analyze_round", prompt)
        self.assertIn("reduce_results", prompt)
        self.assertIn("orders", prompt)
        self.assertIn("strategy", prompt)
        self.assertIn("Vietato", prompt)
        self.assertIn("rete", prompt)
        self.assertIn("disco", prompt)

    def test_reload_system_prompt_from_md(self):
        text = reload_stats_codegen_system_prompt()
        self.assertIn("Rispondi SEMPRE in italiano", text)
        self.assertIn("analyze_round", text)
        self.assertIn("round_view", text)
        self.assertIn("reduce_results", text)
        self.assertIn("market_start_ts", text)
        self.assertIn("INDENTAZIONE", text)

    def test_codegen_retries_syntax_error_silently(self):
        bad = "```python\ndef analyze_round(round_view):\n  return {}\n    return {}\n```\n"
        good = "```python\ndef analyze_round(round_view):\n    return {}\n```\n"
        calls = {"n": 0}

        def fake_call(prompt, model_id, params, cwd):
            calls["n"] += 1
            return bad if calls["n"] == 1 else good

        with unittest.mock.patch("dashv2.agents.stats_codegen.call_model", side_effect=fake_call):
            from dashv2.agents.stats_codegen import generate_analyze_module
            src = generate_analyze_module(
                "stats", model_id="m", params={}, system_prompt="INDENTAZIONE note",
                max_attempts=3,
            )
        self.assertIn("def analyze_round", src)
        self.assertEqual(calls["n"], 2)

    def test_codegen_raises_after_exhausted_retries(self):
        bad = "```python\ndef analyze_round(round_view):\n  return {}\n    return {}\n```\n"

        def fake_call(prompt, model_id, params, cwd):
            return bad

        with unittest.mock.patch("dashv2.agents.stats_codegen.call_model", side_effect=fake_call):
            from dashv2.agents.stats_codegen import generate_analyze_module
            with self.assertRaises(SyntaxError):
                generate_analyze_module(
                    "stats", model_id="m", params={}, system_prompt="x", max_attempts=2,
                )


class TestStatsModulesCrud(unittest.TestCase):
    def test_create_write_list_delete(self):
        with tempfile.TemporaryDirectory() as td:
            history = Path(td)
            root = stats_dir(history)
            self.assertTrue(root.is_dir())
            data = create_analyze(history, "Inv flips", "conta inversioni")
            self.assertEqual(data["name"], "Inv flips")
            self.assertEqual(data["rules"], "conta inversioni")
            self.assertTrue(data["id"])
            py = write_analyze_module(history, data["id"], _STUB)
            self.assertEqual(py, module_path(history, data["id"]))
            self.assertTrue(py.is_file())
            listed = list_analyzes(history)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], data["id"])
            self.assertEqual(listed[0]["name"], "Inv flips")
            delete_analyze(history, data["id"])
            self.assertFalse(py.is_file())
            self.assertFalse((root / f"analyze_{data['id']}.json").is_file())
            self.assertEqual(list_analyzes(history), [])


if __name__ == "__main__":
    unittest.main()
