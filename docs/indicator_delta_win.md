# Indice delta_win v2 (feed Lighter)



Due stime parallele che il lato indicato dal **segno del delta** al checkpoint vinca l'**outcome ufficiale Gamma** a settlement. Fit su archivio Lighter (train weeks, holdout escluso); confronto sui reali via report dedicato.



## Metodi



| Colonna | Artifact | Input | Meccanismo |

|---------|----------|-------|------------|

| `DWinA` | `delta_band_lookup` | `sec`, `\|delta\|` arrotondato, **H** | Pool empirico per fascia H: win rate su campioni con `\|delta\| ∈ [lo,hi]`; espansione progressiva se `n` basso |

| `DWinB` | `logistic_isotonic` | `sec`, `\|delta\|`, V30–V120, H | Logistic + calibrazione isotonica per ogni `sec` |



**Non è il lato maggioritario CLOB.**



## Definizione comune



- **Intervallo sec:** da `delta_win_sec_start` a `delta_win_sec_end` inclusi, **ogni secondo** in `setup.json` (default 240→5); sopra `sec_start` solo spazi.

- **Formato:** `DWinA` → `87% [n=39]` (pool empirico; `n` = campioni nel range ±2 implicito); `    [n=29*]` se `n < delta_win_window_min_samples` (spazi al posto della %, `*` = campioni insufficienti); `---` se nessun pool locale; `DWinB` → `93%` (arrotondamento intero).

- **Colonne feed:** `delta_win_txt_columns` in `setup.json` — `["a","b"]`, `["a"]` o `["b"]`; posizione **prima** di `btc`.

- **Lato predetto:** UP se `delta ≥ 0`, DOWN se negativo — stessa regola della colonna `quote`.

- **Label training:** `1` se quel lato = `outcome` Gamma; round con `outcome_agreement: nan` esclusi.

- **Non eleggibile:** delta `---`, vol mancante, stale nella finestra V120 → `---` nel range; fuori intervallo solo spazi.



## Metodo A — pool empirico per H



**Fit** su Lighter train weeks (`study_delta_win_v2.py`):



- Per ogni **H** (1…6), `sec` nell'intervallo e `center_d` in `0..150`:

  - Partenza finestra ±`delta_win_window_half_base` (default 2) → `[d-2, d+2]` clamp 0–150

  - Pool = campioni con stessa `intraday_h`, stesso `sec`, `|delta|` nel range

  - Se `n < delta_win_window_min_samples`: allarga di `delta_win_window_expand_step` (default +3) per lato finché `n ≥ soglia` o range max 0–150

  - Slot sufficiente: `p_win = mean(y_win)` su pool, `n = len(pool)` reale

  - Slot insufficiente anche al max: assente → runtime `---`

- Soglia `delta_win_window_min_samples` calibrata su holdout (candidati 20…150) prima del fit finale

- Salvato in artifact `delta_window_by_sec_h[H][sec][center_d]` con `{p_win, n, lo, hi, half, expanded}`



**Runtime** (feed reale e Lighter):



- `H` da header `intraday: Hk` o `hour_band(market_start_ts)`

- Lookup `delta_window_by_sec_h[H][sec][min(|delta|, 150)]`

- Cella mostra `p_win` e `[n=N]` solo se `n ≥ soglia`; altrimenti spazi + `[n=N*]` (asterisco = campioni insufficienti)



## Artifact



- Path: `models/delta_win_v2.json` (`delta_win_model_path`, versione `2`).

- Sezioni: `delta_window_by_sec_h` (metodo A, slot solo dove `n ≥ soglia`), `logistic_by_sec` (metodo B).

- Metadati: `delta_win_band_stratify: intraday_h`, `delta_lookup_max: 150`, `delta_win_window_half_base`, `delta_win_window_expand_step`, `delta_win_window_min_samples`.

- Verifica `hour_bands_hash` e intervallo `sec_start`/`sec_end`; mismatch → eccezione.



## Comandi



```bash

# Fit A+B su Lighter (train weeks) + calibrazione soglia + audit

python scripts/study_delta_win_v2.py [workers]

python scripts/study_delta_win_v2.py 8

python scripts/study_delta_win_v2.py --audit-only

```

`workers` default 8: collect Lighter, fit A (1416 task H×sec), calibrazione 6 soglie e fit B in parallelo.

```bash

# Confronto A vs B su round reali in data/

python scripts/eval_delta_win_v2_compare.py [data_dir]



# Probe finestre ±2 osservate sui reali (metodo A)

python scripts/probe_delta_win_bands.py [data_dir]



# Backfill colonne su feed storici (Lighter)

python scripts/backfill_lighter_delta_win.py [rounds_root] [workers] [--dry-run]



# Backfill colonne su feed reali in data/ (rigenera .txt da .bin)

python scripts/backfill_real_delta_win.py [data_dir] [workers] [--dry-run]



# Test

python -m unittest tests.test_delta_win

```



## Esempio sec=90



Stesso round: `DWinA` dipende da H e dal pool empirico intorno a `|delta|`; `DWinB` può differire se vol sposta la calibrazione. Due round con stessa `|delta|` ma H diversi → `DWinA` diverse.



## Limiti



- Nessuna scelta automatica A vs B nel codice: usare `data/reports/delta_win_compare_*.json`.

- Nei round reali Polymarket le colonne sono nel `.txt` (da `convert` o collector); il `.bin` v6 resta invariato.

- Percentuali nei feed dopo backfill/convert sono enrichment in-sample; non usarle per misurare bontà del modello su Lighter.

- Fasce H con pochi round (es. H6) possono avere più celle `---` o `*`: usare `n` e l'asterisco in `DWinA`.

