# Strategy coded_rules Implementation Plan

> **For agentic workers:** implement task-by-task. Steps use checkbox syntax.

**Goal:** Dopo codegen strategy, generare e mostrare `coded_rules` schematiche (Apertura/Chiusura/Vincoli) in un box readonly separato da `rules`.

**Architecture:** Campo `coded_rules` nel JSON; `generate_coded_rules(source)` in `strategy_codegen.py`; server lo chiama dopo il Python; UI modal readonly.

**Tech Stack:** Python dashv2, Cursor `call_model`, Socket.IO, HTML/JS static.

## Global Constraints

- Schema output: solo sezioni Apertura / Chiusura / Vincoli (niente template Prudence).
- `rules` non viene sovrascritto.
- Fallimento reverse-pass non blocca il save del modulo.
- Codice sintetico (AGENTS D1–D2).

---

### Task 1: Persistenza `coded_rules`

**Files:** `dashv2/strategies.py`, `dashv2/tests/test_strategy_codegen.py`, `dashv2/tests/test_bot_live.py` se toccano summary

- [ ] Aggiungere `coded_rules` a create/update/clone/`strategy_summary`
- [ ] Test: create con coded_rules; clone copia coded_rules

### Task 2: Reverse-pass codegen

**Files:** `dashv2/strategy_codegen.py`, tests

- [ ] `build_coded_rules_prompt(source)` + `extract_coded_rules(text)` + `generate_coded_rules(...)`
- [ ] Validazione minima: deve contenere le tre heading
- [ ] Test con mock `call_model`

### Task 3: Server + engine IPC

**Files:** `dashv2/server.py`, `dashv2/engine/plugins/replay.py`

- [ ] Dopo codegen: emit “Writing coded rules…”, salva `coded_rules` (try/except → `""`)
- [ ] create/update payload e `_cmd_strategy_*` passano `coded_rules`

### Task 4: UI

**Files:** `dashv2/static/index.html`, `dashv2/static/js/app.js`, CSS se serve

- [ ] Textarea readonly Coded rules sotto Rules
- [ ] Populate/clear in openStrategyModal; hide se non deterministic

### Task 5: Verify

- [ ] `python -m unittest dashv2.tests.test_strategy_codegen dashv2.tests.test_bot_live`
- [ ] `data/restart` se backend cambiato
