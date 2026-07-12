---
name: delta-win A griglia
overview: "Sostituire il metodo A (DWinA): al fit, lookup empirico per ogni |delta| 0–150 su Lighter con merge a vicini se n&lt;min_samples; al runtime, media su finestra ±2 (clamp ai bordi) e range mostrato [lo$-hi$]. Metodo B invariato."
todos:
  - id: fit-grid
    content: "Riscrivere delta_win_bands.py: fit_delta_p_for_sec (griglia 0-150, merge vicini) + helper window_bounds"
    status: completed
  - id: runtime-a
    content: "Aggiornare delta_win.py: predict_delta_win_a con media finestra ±2, load artifact delta_p_by_sec, row_part range runtime"
    status: completed
  - id: study-artifact
    content: "study_delta_win_v2.py: serializzare delta_p_by_sec, diagnostica aggiornata; rigenerare models/delta_win_v2.json"
    status: completed
  - id: eval-probe-tests
    content: eval_delta_win_v2_compare, probe_delta_win_bands, test_delta_win, docs + AGENTS.md
    status: completed
isProject: false
---

# Piano: delta_win A su griglia 0–150 + finestra ±2

## Contesto

Oggi il metodo A in [`src/delta_win_bands.py`](src/delta_win_bands.py) costruisce **5 fasce variabili** via quantili, merge per `min_samples` e monotonia forzata; al runtime fa lookup della fascia che contiene `|delta|`.

Nuova logica (solo **metodo A** / colonna `DWinA`; **DWinB logistic invariato**):

```mermaid
flowchart LR
  fit [Fit one-shot Lighter]
  grid ["delta_p_by_sec: p per ogni d in 0..150"]
  fit --> grid
  grid --> runtime [Runtime feed]
  runtime --> win ["finestra clamp(d-2, d+2)"]
  win --> avg [media p_win]
  avg --> cell ["88% [31$-35$]"]
```

**Decisioni confermate:**
- `|delta|` assoluto arrotondato (come oggi)
- Bordi griglia: clamp (`d=0` → media su 3 valori; `d=150` idem)
- `|delta| > 150`: clamp a 150 per lookup e range
- Fit con `n < min_samples`: espandi vicini fino a soglia (riuso `delta_win_band_min_samples: 500`)
- Solo metodo A cambia

---

## 1. Fit one-shot — nuova griglia nell'artifact

**File:** [`src/delta_win_bands.py`](src/delta_win_bands.py) (riscrittura core, rimuovere quantili/monotonia/lookup bande)

Nuova funzione principale, es. `fit_delta_p_for_sec(samples, sec, max_delta=150, min_samples)`:

- Per ogni `d` in `0..150`:
  - Partire da raggio 0, espandere `±radius` finché i campioni con `abs_delta ∈ [max(0,d-r), min(150,d+r)]` hanno `n ≥ min_samples` (o raggio esaurito)
  - `p_win = sum(y_win) / n` sul pool mergiato
  - Salvare `{"p_win", "n", "merge_radius"}` per diagnostica

**File:** [`scripts/study_delta_win_v2.py`](scripts/study_delta_win_v2.py)

- Sostituire `fit_bands_for_sec` → `fit_delta_p_for_sec`
- Serializzare `delta_p_by_sec` al posto di `bands_by_sec`
- In-sample / holdout diagnostico: usare `predict_delta_win_a` (media finestra) invece di `lookup_band_p_win`
- Report: conteggio slot con `merge_radius > 0`, distribuzione `n` min/max per sec

**Nuova struttura artifact** in [`models/delta_win_v2.json`](models/delta_win_v2.json) (da rigenerare):

```json
{
  "model_version": 2,
  "methods": ["delta_band_lookup", "logistic_isotonic"],
  "delta_lookup_max": 150,
  "delta_window_half": 2,
  "delta_p_by_sec": {
    "90": {
      "0": {"p_win": 0.52, "n": 840, "merge_radius": 1},
      "33": {"p_win": 0.74, "n": 620, "merge_radius": 0},
      "150": {"p_win": 0.99, "n": 510, "merge_radius": 0}
    }
  },
  "logistic_by_sec": { "...": "invariato" }
}
```

Rimuovere `bands_by_sec` dall'artifact (no retrocompat — eccezione se manca `delta_p_by_sec`).

---

## 2. Runtime — predizione e rendering feed

**File:** [`src/delta_win.py`](src/delta_win.py)

Aggiungere helper compatto:

```python
def _clamp_delta(abs_delta: int, max_delta: int = 150) -> int:
    return min(abs_delta, max_delta)

def _window_bounds(d: int, max_delta: int = 150, half: int = 2) -> tuple[int, int]:
    return max(0, d - half), min(max_delta, d + half)

def _predict_delta_p_window(sec, abs_delta, artifact) -> tuple[float, int, int]:
    d = _clamp_delta(abs_delta)
    lo, hi = _window_bounds(d)
    table = artifact["delta_p_by_sec"][str(sec)]
    ps = [float(table[str(i)]["p_win"]) for i in range(lo, hi + 1)]
    return sum(ps) / len(ps), lo, hi
```

- `predict_delta_win_a`: delega a `_predict_delta_p_window`, ritorna solo la media
- `delta_win_row_part` (colonna `a`): usa `(p, lo, hi)` per `format_delta_win_a_cell` — il range mostrato è **sempre la finestra runtime**, non il merge del fit
- `load_delta_win_artifact`: validare `delta_p_by_sec` (151 chiavi `"0"`…`"150"` per ogni checkpoint), rimuovere check `bands_by_sec`
- Header metadati: aggiungere `delta_lookup_max`, `delta_window_half`; aggiornare descrizione metodo A

**Feed interessati** (nessuna modifica strutturale, solo valori diversi):
- [`src/lighter_txt_format.py`](src/lighter_txt_format.py) — build Lighter
- [`src/txt_format.py`](src/txt_format.py) — convert / feed reali Polymarket
- [`scripts/backfill_lighter_delta_win.py`](scripts/backfill_lighter_delta_win.py), [`scripts/backfill_real_delta_win.py`](scripts/backfill_real_delta_win.py) — idempotenti, ma conviene `--dry-run` poi rerun dopo refit

---

## 3. Script di valutazione e probe

**[`scripts/eval_delta_win_v2_compare.py`](scripts/eval_delta_win_v2_compare.py):**
- `_band_label(abs_delta)` → label finestra runtime es. `"31-35"` via `_window_bounds`
- Rimuovere dipendenza da `artifact["bands_by_sec"]`

**[`scripts/probe_delta_win_bands.py`](scripts/probe_delta_win_bands.py):**
- Raggruppare per finestra ±2 osservata (non più fascia quantile)
- Aggiornare nome report / campi se utile (`delta_window` al posto di `band`)

---

## 4. Test, docs, rigenerazione

**[`tests/test_delta_win.py`](tests/test_delta_win.py):**
- Test unitari su `_window_bounds` (bordi 0, 150, clamp >150)
- Test fit merge: pool sintetico con delta raro → `merge_radius > 0`
- Aggiornare `test_format_cells` / width: verificare `[0$-2$]`, `[148$-150$]` ≤ 15 char
- `test_artifact_load_and_predict_ab`: `predict_delta_win_a(sec, 200)` deve funzionare (clamp 150)
- Rimuovere iterazione su `bands_by_sec` nell'artifact

**Docs:**
- [`docs/indicator_delta_win.md`](docs/indicator_delta_win.md) — nuova definizione metodo A
- [`AGENTS.md`](AGENTS.md) — colonna `DWinA`: griglia + finestra ±2

**Post-implementazione (obbligatorio):**
```bash
python scripts/study_delta_win_v2.py          # rigenera models/delta_win_v2.json
python -m unittest tests.test_delta_win
python scripts/backfill_real_delta_win.py data/ 4   # opzionale, feed reali
```

---

## Comportamento atteso (esempi)

| `|delta|` riga | Finestra | Celletta esempio |
|---------------|----------|------------------|
| 33 | [31, 35] | `74% [31$-35$]` |
| 0 | [0, 2] | `52% [0$-2$]` |
| 150 | [148, 150] | `99% [148$-150$]` |
| 180 (clamp) | [148, 150] | come riga 150 |

La percentuale è `round(mean(p[d_lo]…p[d_hi]) * 100)` — stesso arrotondamento intero di oggi.

---

## Fuori scope

- Metodo B (`logistic_isotonic`) e colonna `DWinB`
- Modifiche al `.bin` v6
- Scelta automatica A vs B per strategia live
