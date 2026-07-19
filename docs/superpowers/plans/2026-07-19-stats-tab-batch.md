# Tab Stats + RoundBatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere la tab STATS in dashv2 con backtest headless parallelo delle strategy (tabella 24h UTC) e analyze agent-generated (Markdown), orchestrati dal server.

**Architecture:** Modulo `dashv2/batch/` con `ProcessPoolExecutor` (~10 worker) sul processo server; job `strategy` riusa `OrderEngine` + moduli `strategy_*.py`; job `analyze` chiama `analyze_round` generato; UI segmented Backtest|Analyze; comandi `stats.*` gestiti **solo dal server** (come `agent.*`, non passano dall’engine).

**Tech Stack:** Python 3, `concurrent.futures.ProcessPoolExecutor`, Flask-SocketIO (server esistente), unittest, HTML/CSS/JS statici dashv2.

**Spec:** [`docs/superpowers/specs/2026-07-19-stats-tab-batch-design.md`](../specs/2026-07-19-stats-tab-batch-design.md)

## Global Constraints

- Commenti/docstring in italiano; nomi codice in inglese; log strings in inglese (`AGENTS.global.md`)
- Codice sintetico (D1); no default/fallback che nascondono errori (D2); no retrocompatibilità firme (D3)
- Dopo modifiche backend: creare file vuoto `data/restart`; solo static → refresh browser
- Un solo job batch alla volta; cancel non emette `stats.job.done` con risultati parziali
- Batch non scrive `history/accounts/`
- Test runner: `python -m unittest …` (non pytest)
- Commit solo se l’utente lo richiede in sessione; negli step Commit sotto, preparare lo staging ma chiedere conferma se la regola utente vieta commit automatici — altrimenti eseguire il commit dello step

---

## File map

| File | Responsabilità |
|------|----------------|
| `dashv2/batch/__init__.py` | Package vuoto / export pubblici |
| `dashv2/batch/markets.py` | `UTC_HOUR_MARKETS` (24 stringhe, allineate al picker JS) |
| `dashv2/batch/reduce.py` | `reduce_strategy_rows` → tabella 24h; `reduce_analyze_fallback` Markdown |
| `dashv2/batch/listing.py` | `list_batch_rounds(repo, day_from, day_to)` → path validi |
| `dashv2/batch/ctx.py` | `build_strategy_ctx` da LoadedRound + open orders (mirror `bot_process._ctx`) |
| `dashv2/batch/strategy_job.py` | `run_strategy_round(...)` → dict per-round |
| `dashv2/batch/analyze_job.py` | `run_analyze_round(...)` + load `reduce_results` |
| `dashv2/batch/worker.py` | Entry top-level pickleable `process_task(task: dict) -> dict` |
| `dashv2/batch/runner.py` | `RoundBatchRunner` pool + progress + cancel |
| `dashv2/stats_modules.py` | CRUD `history/stats/analyze_{id}.*` |
| `dashv2/stats_codegen.py` | extract/validate/generate analyze modules |
| `dashv2/stats_system_prompt.md` | Contratto analyze per Cursor |
| `dashv2/stats_service.py` | Chat thread Stats + apply rules + auto-run hook |
| `dashv2/server.py` | `_STATS_CMDS`, handler locali, job lock |
| `dashv2/setup.json` | `stats_workers: 10` |
| `dashv2/config.py` | Carica `stats_workers` + prompt stats |
| `dashv2/static/index.html` | Tab STATS + pane |
| `dashv2/static/js/app.js` | Comandi/eventi stats, stato UI |
| `dashv2/static/js/render.js` | `renderStats*` tabella/markdown/chat |
| `dashv2/static/css/dashboard.css` | Stili minimi tab |
| `dashv2/tests/test_batch_reduce.py` | Reduce 24h |
| `dashv2/tests/test_batch_listing.py` | Filtro giorni |
| `dashv2/tests/test_strategy_job.py` | Job strategy su round sintetico |
| `dashv2/tests/test_analyze_job.py` | Analyze + reduce |
| `dashv2/tests/test_batch_runner.py` | Pool workers=2 su task fake |
| `docs/dashv2-architecture.md` | Sezione Stats / protocollo `stats.*` |

---

### Task 1: Reduce tabella 24h

**Files:**
- Create: `dashv2/batch/__init__.py`
- Create: `dashv2/batch/markets.py`
- Create: `dashv2/batch/reduce.py`
- Test: `dashv2/tests/test_batch_reduce.py`

**Interfaces:**
- Consumes: nessuno
- Produces:
  - `UTC_HOUR_MARKETS: list[str]` len 24
  - `reduce_strategy_rows(rows: list[dict]) -> dict` con chiavi `hours: list[dict]`, `total: dict`
  - ogni hour dict: `hour`, `market`, `rounds`, `traded`, `pos`, `neg`, `flat`, `pnl_sum`, `pnl_avg`

- [ ] **Step 1: Write the failing test**

```python
# dashv2/tests/test_batch_reduce.py
from __future__ import annotations
import unittest
from dashv2.batch.reduce import reduce_strategy_rows
from dashv2.batch.markets import UTC_HOUR_MARKETS

class TestReduceStrategy(unittest.TestCase):
    def test_markets_len_24(self):
        self.assertEqual(len(UTC_HOUR_MARKETS), 24)
        self.assertEqual(UTC_HOUR_MARKETS[14], "Londra, New York")

    def test_bucket_and_total(self):
        rows = [
            {"hour_utc": 14, "ok": True, "pnl_usd": 2.0, "traded": True},
            {"hour_utc": 14, "ok": True, "pnl_usd": -1.0, "traded": True},
            {"hour_utc": 14, "ok": True, "pnl_usd": 0.0, "traded": False},
            {"hour_utc": 9, "ok": True, "pnl_usd": 5.0, "traded": True},
            {"hour_utc": 9, "ok": False, "pnl_usd": 0.0, "traded": False},  # ignored in agg
        ]
        out = reduce_strategy_rows(rows)
        self.assertEqual(len(out["hours"]), 24)
        h14 = out["hours"][14]
        self.assertEqual(h14["hour"], "14:00")
        self.assertEqual(h14["market"], "Londra, New York")
        self.assertEqual(h14["rounds"], 3)
        self.assertEqual(h14["traded"], 2)
        self.assertEqual(h14["pos"], 1)
        self.assertEqual(h14["neg"], 1)
        self.assertEqual(h14["flat"], 1)
        self.assertEqual(h14["pnl_sum"], 1.0)
        self.assertAlmostEqual(h14["pnl_avg"], 1.0 / 3)
        self.assertEqual(out["total"]["rounds"], 4)  # solo ok=True
        self.assertEqual(out["total"]["pnl_sum"], 6.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest dashv2.tests.test_batch_reduce -v`  
Expected: FAIL (ImportError o module not found)

- [ ] **Step 3: Write minimal implementation**

Copia esatta da `dashv2/static/js/render.js` `UTC_HOUR_MARKETS` in `markets.py`.

```python
# dashv2/batch/reduce.py
from __future__ import annotations
from dashv2.batch.markets import UTC_HOUR_MARKETS

def reduce_strategy_rows(rows: list[dict]) -> dict:
    buckets = [
        {"hour": f"{h:02d}:00", "market": UTC_HOUR_MARKETS[h], "rounds": 0, "traded": 0,
         "pos": 0, "neg": 0, "flat": 0, "pnl_sum": 0.0, "pnl_avg": 0.0}
        for h in range(24)
    ]
    for r in rows:
        if not r["ok"]:
            continue
        b = buckets[int(r["hour_utc"])]
        b["rounds"] += 1
        if r["traded"]:
            b["traded"] += 1
        pnl = float(r["pnl_usd"])
        b["pnl_sum"] += pnl
        if pnl > 0:
            b["pos"] += 1
        elif pnl < 0:
            b["neg"] += 1
        else:
            b["flat"] += 1
    for b in buckets:
        if b["rounds"]:
            b["pnl_avg"] = b["pnl_sum"] / b["rounds"]
    total = {"rounds": 0, "traded": 0, "pos": 0, "neg": 0, "flat": 0, "pnl_sum": 0.0, "pnl_avg": 0.0}
    for b in buckets:
        for k in ("rounds", "traded", "pos", "neg", "flat"):
            total[k] += b[k]
        total["pnl_sum"] += b["pnl_sum"]
    if total["rounds"]:
        total["pnl_avg"] = total["pnl_sum"] / total["rounds"]
    return {"hours": buckets, "total": total}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest dashv2.tests.test_batch_reduce -v`  
Expected: OK

- [ ] **Step 5: Commit** (se richiesto dall’utente)

```bash
git add dashv2/batch/__init__.py dashv2/batch/markets.py dashv2/batch/reduce.py dashv2/tests/test_batch_reduce.py
git commit -m "feat(stats): add 24h UTC reduce for strategy backtest"
```

---

### Task 2: Listing round per range giorni

**Files:**
- Create: `dashv2/batch/listing.py`
- Modify: nessuno obbligatorio su `rounds.py` (usa API esistenti)
- Test: `dashv2/tests/test_batch_listing.py`

**Interfaces:**
- Consumes: `RoundRepository` (`list_picker`, `_bins` via path pubblici — usare solo `list_picker` + `data_dir` glob o aggiungere metodo `bin_path_for(mts)`)
- Produces: `list_batch_rounds(repo: RoundRepository, day_from: str, day_to: str) -> tuple[list[dict], int]`  
  - lista item: `{"market_start_ts": int, "bin_path": str, "hour_utc": int, "day_utc": str}`  
  - secondo valore: `skipped` (invalidi nel range)

Aggiungere su `RoundRepository`:

```python
def bin_path(self, market_start_ts: int) -> Path:
    return self._bins[market_start_ts]
```

- [ ] **Step 1: Write the failing test**

Usa temp dir con un fake index: più semplice mockare un oggetto con `list_picker` e `bin_path`.

```python
# dashv2/tests/test_batch_listing.py
from __future__ import annotations
import unittest
from pathlib import Path
from dashv2.batch.listing import list_batch_rounds

class FakeRepo:
    def __init__(self):
        self._items = [
            {"market_start_ts": 1784419200, "day_utc": "2026-07-19", "valid": True},   # 00:00
            {"market_start_ts": 1784469600, "day_utc": "2026-07-19", "valid": True},   # 14:00
            {"market_start_ts": 1784469600 + 300, "day_utc": "2026-07-19", "valid": False},
            {"market_start_ts": 1784332800, "day_utc": "2026-07-18", "valid": True},
        ]
        self._bins = {i["market_start_ts"]: Path(f"/tmp/{i['market_start_ts']}.bin") for i in self._items if i["valid"]}

    def list_picker(self):
        return list(self._items)

    def bin_path(self, mts: int) -> Path:
        return self._bins[mts]

class TestListing(unittest.TestCase):
    def test_range_inclusive(self):
        paths, skipped = list_batch_rounds(FakeRepo(), "2026-07-19", "2026-07-19")
        self.assertEqual(len(paths), 2)
        self.assertEqual(skipped, 1)
        hours = {p["hour_utc"] for p in paths}
        self.assertEqual(hours, {0, 14})
```

Nota: calcola `hour_utc` con `datetime.utcfromtimestamp(mts).hour` (o `datetime.fromtimestamp(mts, timezone.utc).hour`).

- [ ] **Step 2: Run test — expect FAIL**

`python -m unittest dashv2.tests.test_batch_listing -v`

- [ ] **Step 3: Implement `listing.py` + `RoundRepository.bin_path`**

```python
# dashv2/batch/listing.py
from __future__ import annotations
from datetime import datetime, timezone

def list_batch_rounds(repo, day_from: str, day_to: str) -> tuple[list[dict], int]:
    out: list[dict] = []
    skipped = 0
    for e in repo.list_picker():
        day = e["day_utc"]
        if day < day_from or day > day_to:
            continue
        if not e["valid"]:
            skipped += 1
            continue
        mts = int(e["market_start_ts"])
        hour = datetime.fromtimestamp(mts, timezone.utc).hour
        out.append({
            "market_start_ts": mts,
            "bin_path": str(repo.bin_path(mts)),
            "hour_utc": hour,
            "day_utc": day,
        })
    out.sort(key=lambda x: x["market_start_ts"])
    return out, skipped
```

In `dashv2/rounds.py` aggiungere metodo `bin_path` come sopra.

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit** (se richiesto)

```bash
git add dashv2/batch/listing.py dashv2/rounds.py dashv2/tests/test_batch_listing.py
git commit -m "feat(stats): list valid rounds by UTC day range"
```

---

### Task 3: Strategy job headless

**Files:**
- Create: `dashv2/batch/ctx.py`
- Create: `dashv2/batch/strategy_job.py`
- Test: `dashv2/tests/test_strategy_job.py`

**Interfaces:**
- Consumes: `OrderEngine`, `LoadedRound`, `StrategyRunner` pattern (importlib diretto ok)
- Produces:
  - `build_strategy_ctx(tick_public: dict, session: dict, open_orders: list, bot_active: bool=True) -> dict`
  - `run_strategy_round(*, loaded: LoadedRound, module_path: Path, strategy_id: str, size_up: float, size_down: float) -> dict`  
    return: `market_start_ts, hour_utc, ok, error, pnl_usd, n_orders, n_wins, n_losses, traded`

Usa `from dashv2.engine.plugins.replay import _public_tick` per allineare il tick pubblico (evita drift vs live).

Loop:

```python
for sec in range(300, -1, -1):
    # sec 0: solo settlement + on_round_end (come engine)
```

Per sec 300..1: costruisci public tick, applica azioni. A sec==300 chiama anche `on_round_start` prima di `on_tick`.

Apply action:

```python
def _apply(engine, act, sid, sec, tick, book, fee, account_id="batch"):
    cmd = act["cmd"]
    try:
        if cmd == "order.place":
            engine.place(act["side"], float(act["size_usd"]), sec, tick, book, fee, account_id, "bot", sid, act.get("reason"))
        elif cmd == "order.close":
            engine.close(act["order_id"], sec, tick, book, fee, reason=act.get("reason"))
        elif cmd == "order.cancel":
            engine.cancel(act["order_id"])
        else:
            raise Exception(f"unknown cmd {cmd}")
    except Exception as e:
        # loggata: appendi a action_errors; NON abort round
        action_errors.append(str(e))
```

Settlement: `engine.settle_open(loaded.outcome_name, 0, loaded.final_chainlink)`.

PnL: `sum(o["pnl_usd"] for o in engine.closed_orders)`.

`hour_utc` da `datetime.fromtimestamp(loaded.market_start_ts, timezone.utc).hour`.

- [ ] **Step 1: Write failing test** con LoadedRound sintetico minimo

Costruisci tick tradable a sec 200 con book ask superficiale (riusa pattern da `test_clob_walk.py` se utile). Stub module su tempfile:

```python
_STUB = '''
def on_round_start(ctx): return []
def on_tick(ctx):
    if ctx.get("sec") == 200 and ctx.get("tradable"):
        return [{"cmd": "order.place", "side": "Up", "size_usd": 10.0}]
    return []
def on_round_end(ctx): return []
'''
```

Outcome `"Up"` → pnl positivo atteso se place riesce.

Se costruire LoadedRound completo è troppo pesante: mocka `loaded.ticks_by_sec` / `books_by_sec` / fee / outcome come dataclass fields.

- [ ] **Step 2: Run — expect FAIL**

`python -m unittest dashv2.tests.test_strategy_job -v`

- [ ] **Step 3: Implement `ctx.py` + `strategy_job.py`**

`build_strategy_ctx` deve includere gli stessi campi di `bot_process._ctx` (`sec`, `tradable`, `vol`, `risk`, `dwin_*`, `open_orders`, `ptb_chainlink`, `market_start_ts`, `bot_active`, quote cents, `majority_side`, `liq2_ask_usd`, …). Mappa `risk` da tick interno: il public tick usa `risk` via `_public_tick` (già calcolato).

Nota: tick interno ha `side_risk`; `_public_tick` espone `risk`. Passa sempre dal public tick.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit** (se richiesto)

```bash
git add dashv2/batch/ctx.py dashv2/batch/strategy_job.py dashv2/tests/test_strategy_job.py
git commit -m "feat(stats): headless strategy backtest job per round"
```

---

### Task 4: Analyze job + reduce Markdown

**Files:**
- Create: `dashv2/batch/analyze_job.py`
- Modify: `dashv2/batch/reduce.py` (aggiungere `reduce_analyze_fallback`)
- Test: `dashv2/tests/test_analyze_job.py`

**Interfaces:**
- Produces:
  - `build_round_view(loaded: LoadedRound) -> dict` con almeno: `market_start_ts`, `hour_utc`, `outcome`, `ptb_chainlink`, `final_chainlink`, `fee_rate`, `ticks` (lista dict sec ordinati), `secs`
  - `run_analyze_round(loaded, module_path: Path) -> dict` (`ok`, `error`, metriche mergeate)
  - `load_reduce_results(module_path: Path)` → callable | None
  - `reduce_analyze_fallback(per_round: list[dict]) -> str`

- [ ] **Step 1: Failing test**

```python
_MOD = '''
def analyze_round(round_view):
    return {"n_ticks": len(round_view["ticks"]), "outcome": round_view["outcome"]}

def reduce_results(per_round):
    n = sum(1 for r in per_round if r.get("ok"))
    return f"# Stats\\n\\nrounds_ok: {n}\\n"
'''
```

Assert `reduce_results` output e fallback se modulo senza `reduce_results`.

- [ ] **Step 2–4:** implement + green

- [ ] **Step 5: Commit** (se richiesto)

```bash
git commit -m "feat(stats): analyze_round job and markdown reduce"
```

---

### Task 5: Worker entry + RoundBatchRunner

**Files:**
- Create: `dashv2/batch/worker.py`
- Create: `dashv2/batch/runner.py`
- Test: `dashv2/tests/test_batch_runner.py`

**Interfaces:**

```python
# worker.py — top-level per Windows spawn
def process_task(task: dict) -> dict:
    """task keys: job, bin_path|market_start_ts, data_dir, stall_reconnect_sec,
       module_path, strategy_id?, size_up?, size_down?, hour_utc"""
    ...

# runner.py
class RoundBatchRunner:
    def __init__(self, workers: int): ...
    def run(self, tasks: list[dict], on_progress) -> list[dict]:
        """on_progress(done: int, total: int, errors: int). Ritorna lista risultati."""
    def cancel(self) -> None: ...
```

Implementazione `run`:
- `ProcessPoolExecutor(max_workers=self.workers)`
- `as_completed`; incrementa progress
- se `_cancel` set: `executor.shutdown(wait=False, cancel_futures=True)` e raise `BatchCancelled` (o ritorna status cancelled al caller senza reduce)

Worker strategy: dentro il child crea `RoundRepository(Path(data_dir), stall)`, `load(mts)`, chiama `run_strategy_round`.

**Test:** senza ProcessPool pesante — testare `process_task` con job fake in-process, e runner con `workers=1` su 3 task echo (puoi aggiungere branch `job=="echo"` solo nei test tramite monkeypatch, oppure testare `run` con mock di `ProcessPoolExecutor`). Preferisci: unit test di `process_task` su strategy stub tempfile + 1 round sintetico **senza** pool; unit test cancel flag su runner con executor mockato.

- [ ] **Step 1–4:** TDD come sopra
- [ ] **Step 5: Commit** `feat(stats): parallel RoundBatchRunner`

---

### Task 6: Persistenza analyze + codegen

**Files:**
- Create: `dashv2/stats_modules.py` (specchio snello di `strategies.py`)
- Create: `dashv2/stats_codegen.py`
- Create: `dashv2/stats_system_prompt.md`
- Modify: `dashv2/config.py` (load prompt path)
- Test: `dashv2/tests/test_stats_codegen.py`

**Interfaces:**

```python
# stats_modules.py
def stats_dir(history_dir: Path) -> Path  # history/stats
def create_analyze(history_dir, name: str, rules: str) -> dict
def write_analyze_module(history_dir, analyze_id: str, source: str) -> Path
def list_analyzes(history_dir) -> list[dict]
def delete_analyze(history_dir, analyze_id: str) -> None
def module_path(history_dir, analyze_id: str) -> Path

# stats_codegen.py
def extract_python_source(raw: str) -> str
def validate_analyze_source(source: str) -> None  # richiede analyze_round
def generate_analyze_module(rules: str, ...) -> str  # Cursor, retry syntax come strategy
```

Prompt: documenta `round_view` keys e `reduce_results` opzionale; vieta rete/disk write.

- [ ] **Step 1:** test extract/validate (senza Cursor), come `test_strategy_codegen.py`
- [ ] **Step 2–4:** implement
- [ ] **Step 5: Commit** `feat(stats): analyze module CRUD and codegen contract`

---

### Task 7: Server — comandi `stats.*` + job orchestration

**Files:**
- Create: `dashv2/stats_service.py` (chat thread + apply)
- Modify: `dashv2/server.py` (`_STATS_CMDS`, handlers, non forward all’engine)
- Modify: `dashv2/setup.json` (`"stats_workers": 10`)
- Modify: `dashv2/config.py` se carica setup keys
- Modify: `docs/dashv2-architecture.md` (tabella comandi/eventi)
- Test: `dashv2/tests/test_bot_live.py` — assert `stats.backtest.start` in `_HUMAN_CMDS` e non in bot cmds; oppure nuovo `test_stats_acl.py`

**Comandi (payload):**

| cmd | payload |
|-----|---------|
| `stats.backtest.start` | `strategy_id`, `day_from`, `day_to` |
| `stats.analyze.start` | `analyze_id`, `day_from`, `day_to` |
| `stats.job.cancel` | `{}` |
| `stats.chat.send` | `text` |
| `stats.chat.history` | `{}` |
| `stats.rules.apply` | `rules`, `analyze_id?` / create |
| `stats.analyze.list` | `{}` |
| `stats.analyze.delete` | `analyze_id` |

**Eventi:** `stats.job.progress`, `stats.job.done`, `stats.job.error`, `stats.job.cancelled`, `stats.chat.message`, `stats.chat.status`, `stats.analyzes`

**Flusso backtest.start (thread OS, come agent):**

1. Se job running → emit error return  
2. `list_batch_rounds` → tasks  
3. `RoundBatchRunner(cfg["stats_workers"]).run(..., on_progress=emit)`  
4. `reduce_strategy_rows` → emit `stats.job.done` `{kind:"backtest", table, summary}`  
5. Lock released in `finally`

**Flusso rules.apply:** codegen → save module → emit analyzes → **auto** `analyze.start` stesso range (range tenuto in stato server `_stats_day_from/to` aggiornato da start o da chat context; v1: payload di apply include `day_from`/`day_to` obbligatori dal client).

Size: `cfg["default_order_size_usd"]` per up e down.

- [ ] **Step 1:** test ACL inclusion
- [ ] **Step 2–4:** wire server (sintetico: pochi metodi `_stats_*`)
- [ ] **Step 5:** `data/restart` sentinel dopo deploy locale; commit `feat(stats): server batch job commands`

---

### Task 8: UI tab STATS

**Files:**
- Modify: `dashv2/static/index.html` — tab + pane segmented
- Modify: `dashv2/static/js/app.js` — `LEFT_TAB_IDS`, state, emit/listen
- Modify: `dashv2/static/js/render.js` — `UTC_HOUR_MARKETS` già presente; `renderStatsBacktest`, `renderStatsAnalyze`
- Modify: `dashv2/static/css/dashboard.css`

**UI Backtest:**
- input date `day_from` / `day_to` (default da `round_days` min/max)
- `<select>` strategie da `state.strategies`
- Run / Cancel
- progress bar
- `<table>` 24 rows + total

**UI Analyze:**
- stesso range (condiviso nello state `statsDayFrom/To`)
- chat box + Applica rules
- select analyze modules
- `<pre>` o div markdown (v1: `textContent` del markdown grezzo; opzionale marked.js solo se già in vendor — **non** aggiungere vendor in v1, mostra `<pre class="stats-md">`)

- [ ] **Step 1:** HTML structure tab dopo BOT
- [ ] **Step 2:** wire `stats.backtest.start` + render table on `stats.job.done`
- [ ] **Step 3:** wire analyze chat/apply/markdown
- [ ] **Step 4:** smoke manuale browser (refresh; se solo static: **refresh browser**; se Task 7 già deployato: restart già fatto)
- [ ] **Step 5: Commit** `feat(stats): Stats tab UI backtest and analyze`

---

### Task 9: Docs + smoke checklist

**Files:**
- Modify: `docs/dashv2-architecture.md` — sezione Stats (processi, `stats.*`, file map)
- Optionally link spec/plan from architecture

- [ ] **Step 1:** Documentare che i job vivono nel server, non nell’engine
- [ ] **Step 2:** Checklist smoke in coda al doc o nel plan:

```
1. Avvia dashv2, apri STATS → Backtest
2. Range 1 giorno con round, seleziona strategy, Run
3. Progress avanza; tabella 24h popolata; totale coerente
4. Analyze: chiedi "conteggio inversioni majority_side ultimo minuto"; Applica; Markdown appare
5. Secondo Run mentre gira → errore
6. Cancel durante run → cancelled, no tabella parziale
```

- [ ] **Step 3: Commit** `docs: document Stats tab and batch protocol`

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Headless B + OrderEngine | Task 3 |
| ProcessPool ~10 dal server | Task 5, 7 |
| Tabella 24h + UTC_HOUR_MARKETS | Task 1, 8 |
| Range giorni | Task 2, 7, 8 |
| Analyze rules→codegen→Markdown | Task 4, 6, 7, 8 |
| Un job alla volta / cancel | Task 5, 7 |
| No ledger write | Task 3 (nessuna chiamata history) |
| UI segmented A | Task 8 |
| Test reduce/strategy/analyze | Task 1, 3, 4 |
| Fuori scope CSV/multi-strategy/CLI | non pianificato |

Placeholder scan: nessuno TBD lasciato nei task.  
Type consistency: `list_batch_rounds` → tasks usano `market_start_ts`/`bin_path`/`hour_utc`; reduce usa `ok`/`pnl_usd`/`traded`/`hour_utc`.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-19-stats-tab-batch.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — un subagent fresco per task, review tra i task  
2. **Inline Execution** — eseguo i task in questa sessione con checkpoint  

Which approach?
