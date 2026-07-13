# Indice delta_win v2 (feed Lighter)



Due stime parallele che il lato indicato dal **segno del delta** al checkpoint vinca l'**outcome ufficiale Gamma** a settlement. Fit su archivio Lighter (train weeks, holdout escluso); confronto sui reali via report dedicato.



## Metodi



| Colonna | Artifact | Input | Meccanismo |

|---------|----------|-------|------------|

| `DWinA` | `delta_band_lookup` | `sec`, `\|delta\|` arrotondato, **H** | Pool empirico per fascia H: win rate su campioni con `\|delta\| ∈ [lo,hi]`; espansione progressiva se `n` basso |

| `DWinB` | `logistic_isotonic` | `sec`, `\|delta\|`, V30–V120, H | Logistic + calibrazione isotonica per checkpoint |



**Non è il lato maggioritario CLOB.**



## Definizione comune



- **Checkpoint:** da `delta_win_checkpoints_start` a `delta_win_checkpoints_end` ogni `delta_win_checkpoints_step` secondi in `setup.json` (default 240→5 step 5); altrove `---`.

- **Formato:** `DWinA` → `66% [19$-23$ n=535]` (pool empirico; `n` = checkpoint nel range); `64% [16$-26$ n=150*]` se range allargato oltre ±2; `---` se pool insufficiente anche a 0–150; `DWinB` → `93%` (arrotondamento intero).

- **Colonne feed:** `delta_win_txt_columns` in `setup.json` — `["a","b"]`, `["a"]` o `["b"]`; posizione **prima** di `btc`.

- **Lato predetto:** UP se `delta ≥ 0`, DOWN se negativo — stessa regola della colonna `quote`.

- **Label training:** `1` se quel lato = `outcome` Gamma; round con `outcome_agreement: nan` esclusi.

- **Non eleggibile:** delta `---`, vol mancante, stale nella finestra V120 → `---` ai checkpoint; fuori checkpoint solo spazi.



## Metodo A — pool empirico per H



**Fit** su Lighter train weeks (`study_delta_win_v2.py`):



- Per ogni **H** (1…6), checkpoint e `center_d` in `0..150`:

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

- Cella mostra `p_win`, range `[lo, hi]` effettivo del fit, `n` del pool; `*` se `expanded=true`



## Artifact



- Path: `models/delta_win_v2.json` (`delta_win_model_path`, versione `2`).

- Sezioni: `delta_window_by_sec_h` (metodo A, slot solo dove `n ≥ soglia`), `logistic_by_sec` (metodo B).

- Metadati: `delta_win_band_stratify: intraday_h`, `delta_lookup_max: 150`, `delta_win_window_half_base`, `delta_win_window_expand_step`, `delta_win_window_min_samples`.

- Verifica `hour_bands_hash` e lista checkpoint; mismatch → eccezione.



## Comandi



```bash

# Fit A+B su Lighter (train weeks) + calibrazione soglia + audit

python scripts/study_delta_win_v2.py

python scripts/study_delta_win_v2.py --audit-only



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

