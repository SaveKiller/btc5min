---
name: delta-win-2 bands
overview: "delta_win v2 dual: metodo A (fasce |delta| + p empirica) e metodo B (logistic_isotonic su |delta|+vol+H); due colonne nel feed ai 6 checkpoint; report comparativo su reali per scegliere il migliore in seguito."
todos:
  - id: fit-v2
    content: "delta_win_bands.py + study_delta_win_v2.py: fit A e B su tutto Lighter → models/delta_win_v2.json"
    status: completed
  - id: runtime-v2
    content: "delta_win.py: predict_band + predict_logistic; due colonne in lighter_txt_format, build, backfill"
    status: completed
  - id: probe-eval
    content: probe bande osservate sui reali + eval_delta_win_v2_compare.py report A vs B
    status: completed
  - id: docs-tests
    content: test parità due colonne, docs indicator v2, AGENTS.md
    status: completed
isProject: false
---

# Piano delta_win-2: metodo A (fasce) + metodo B (logistic)

## Obiettivo

Produrre **due stime parallele** della probabilità che il **lato del delta** vinca l'outcome Gamma al checkpoint, entrambe fit su **tutto l'archivio Lighter**, entrambe scritte nel feed e nei test. Un **report comparativo** sui round reali (holdout esterno) dirà quale usare per la strategia live — **nessuna scelta automatica in questa fase**.

**No: non è il lato maggioritario CLOB.**

```mermaid
flowchart TD
  fit [Fit su tutto Lighter]
  art [models/delta_win_v2.json]
  fit --> art
  art --> A[Metodo A: band lookup]
  art --> B[Metodo B: logistic_isotonic]
  A --> colA["Colonna delta_win_a"]
  B --> colB["Colonna delta_win_b"]
  colA --> cmp [Report confronto su reali]
  colB --> cmp
```

---

## Due metodi (definizioni fisse)

| | **Metodo A — `delta_win_a`** | **Metodo B — `delta_win_b`** |
|---|------------------------------|--------------------------------|
| **Nome artifact** | `delta_band_lookup` | `logistic_isotonic` |
| **Input** | `sec`, `\|delta\|` arrotondato | `sec`, `\|delta\|`, V30–V120, H |
| **Meccanismo** | Fasce di `\|delta\|` per checkpoint → `p_win` empirica della fascia | Logistic + calibrazione isotonica per checkpoint |
| **Variabilità tra round** | Stesso sec, `\|delta\|` in fasce diverse → % diverse (a gradini) | Stesso sec, feature diverse → % diverse (continue) |
| **Fit** | Intero Lighter | Intero Lighter |

**Perché le fasce (A):** rendono esplicito il win rate per fascia di delta (es. ~20$ vs ~100$ a sec=90).

**Perché logistic (B):** usa anche vol e H come richiesto originariamente; probabilità calibrata multivariata.

---

## Contratto statistico (comune)

- **Target:** `y_win = 1` se lato delta = outcome Gamma.
- **Checkpoint colonne:** `180, 150, 120, 90, 60, 30` soltanto; altrove `---`.
- **Eleggibilità:** stesse regole v1 (no stale V120, vol complete per B; A richiede solo delta valido ma stesso gate stale per coerenza feed).
- **Dati fit:** **tutto** Lighter Apr–Giu (~131k righe checkpoint); **mai** refit sui reali.
- **Colonne feed:** `delta_win_a` e `delta_win_b` (header `data:` aggiornato); deprecare/sostituire colonna singola `delta_win` v1 nel backfill v2.

---

## Fase 1 — Fit su tutto Lighter → artifact unico

[`src/delta_win_bands.py`](src/delta_win_bands.py) — metodo A:

- Per ogni `sec`: 5 fasce (+ fascia `0$`), quantili → merge monotonia + `min_samples` ( [`setup.json`](setup.json) `delta_win_band_min_samples` ).
- `p_win` empirica per banda sull'archivio completo.

[`scripts/study_delta_win_v2.py`](scripts/study_delta_win_v2.py) — metodo A + B:

- **A:** serializza `bands_by_sec` in artifact.
- **B:** per ogni `sec`, `LogisticRegression` su `log1p(|delta|)`, `log1p(V*)`, dummy H1–H6; calibrazione isotonica (riuso logica da [`study_delta_win.py`](scripts/study_delta_win.py)); fit su **tutto** Lighter (report diagnostico opzionale su ultime 2 settimane **senza** rifit).
- Output: [`models/delta_win_v2.json`](models/delta_win_v2.json) con entrambe le sezioni.

```json
{
  "model_version": 2,
  "methods": ["delta_band_lookup", "logistic_isotonic"],
  "bands_by_sec": { "90": [{"lo": 1, "hi": 18, "p_win": 0.62, "n": 4500}, ...] },
  "logistic_by_sec": { "90": {"type": "logistic_isotonic", "coef": [...], "intercept": ..., "iso_x": [...], "iso_y": [...]} }
}
```

Config: `delta_win_model_version: 2`, `delta_win_model_path: models/delta_win_v2.json`.

Report fit: `data/reports/delta_win_study_v2_<ts>.json` (conteggi bande, monotonia, metriche Brier **in-sample** solo diagnostiche).

---

## Fase 2 — Due colonne nel feed (build, backfill, runtime)

[`src/delta_win.py`](src/delta_win.py):

- `predict_delta_win_a(sec, abs_delta, artifact)` → lookup banda.
- `predict_delta_win_b(sec, abs_delta, vols, intraday_h, artifact)` → logistic_isotonic.
- `format_delta_win_cell` invariato (`74.2%` / `---`).

[`src/lighter_txt_format.py`](src/lighter_txt_format.py):

- Header `data:`: colonne `delta_win_a` e `delta_win_b` (sostituiscono `delta_win` v1).
- Header metadati: `delta_win_model_version: 2`, `delta_win_methods: [band, logistic]`, periodo training, hash `hour_bands`.

[`scripts/build_lighter_rounds.py`](scripts/build_lighter_rounds.py), [`scripts/backfill_lighter_delta_win.py`](scripts/backfill_lighter_delta_win.py):

- Idempotente: se già presenti entrambe le colonne → `present`.
- Backfill: rilegge `|delta|`, vol, H dalle righe esistenti.

**Esempio sec=90, stesso round:** solo A dipende solo da fascia; B può differire se vol/H spostano la calibrazione.

**Strategia live (fase successiva alla scelta):** API espone entrambe; la soglia di ingresso userà una delle due dopo il report comparativo.

---

## Fase 3 — Test sui reali e report comparativo

[`scripts/eval_delta_win_real.py`](scripts/eval_delta_win_real.py) esteso **oppure** nuovo [`scripts/eval_delta_win_v2_compare.py`](scripts/eval_delta_win_v2_compare.py):

Per ogni campione checkpoint su `data/` (label Gamma, stesso estrattore attuale):

| Metrica | A | B |
|---------|---|---|
| Brier vs `y_win` | sì | sì |
| log-loss | sì | sì |
| Per `sec` | sì | sì |
| Per H | sì | sì |
| Per fascia (solo osservato + p_A) | tabella win rate osservato per `(sec, banda)` | — |

Output dedicato: `data/reports/delta_win_compare_<ts>.json` — **questo** è il report per decidere A vs B; non sceglie un vincitore nel codice.

[`scripts/probe_delta_win_bands.py`](scripts/probe_delta_win_bands.py): tabelle empiriche fasce sui reali (supporto interpretazione metodo A).

---

## Fase 4 — Test e documentazione

- [`tests/test_delta_win.py`](tests/test_delta_win.py): mapping banda; A e B diversi su stesso sec con delta/vol diversi; parità renderer/backfill; no `prevalence`.
- [`docs/indicator_delta_win.md`](docs/indicator_delta_win.md): definizione A vs B, esempio sec=90, comando compare.
- [`AGENTS.md`](AGENTS.md): colonne `delta_win_a` / `delta_win_b`, comandi v2.

---

## Criteri di successo

1. Artifact v2 contiene **sia** `bands_by_sec` **sia** `logistic_by_sec`.
2. Feed e backfill scrivono **due** percentuali distinte ai 6 checkpoint.
3. Report `delta_win_compare_*` su reali con Brier/log-loss affiancati per A e B.
4. A sec=90 sui reali: almeno 3 fasce con win rate osservato diverso ≥10 pp (`n ≥ 50`) — valida utilità di A.
5. Due round stesso sec, delta in fasce diverse → **`delta_win_a` diverse**; B può differire anche con stessa fascia se vol/H cambiano.

---

## Cosa non fare in questa fase

- Non scegliere automaticamente A o B per la strategia (solo report).
- Non usare `prevalence` v1.
- Non rifittare sui reali.
- Non toccare [`src/txt_format.py`](src/txt_format.py) / `.bin` v6 Polymarket.

---

## Dopo v2 (fuori scope)

- Scelta ufficiale A o B (o soglie diverse) per ingresso live.
- Ablation e altri challenger (brownian, RF).
- Eventuale colonna singola nel feed quando il metodo sarà scelto.
