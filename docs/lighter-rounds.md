# Round sintetici Lighter (feed `.txt` ausiliario)

Dataset separato dai round Polymarket reali. Percorso intraround da mid top-of-book Lighter; label e audit da Gamma quando disponibile.

Radice dati tick in `setup.json` → `ticks_root` (default `H:\ticks\`).

**Output:** `<ticks_root>/lighter-rounds5m/<settimana_ISO>/btc5m_<market_start_ts>_<HHMM>.txt`  
**Input:** `<ticks_root>/lighter-fullrawticks/btc/<settimana_ISO>/raw-btc-YYYY-MM-DD.csv`  
**Cache Gamma:** `<ticks_root>/lighter-rounds5m/_gamma_cache.jsonl` — prefetch giornaliero via `src/lighter_gamma.py` (`GET /events/keyset?series_id=10684`, ~3 richieste/giorno); lock solo su scrittura cache con pool parallelo.


| Comando                                                                                                            | Uso                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `python scripts/build_lighter_rounds.py test-day <csv> <out_dir> [cache_name]`                                     | Build di un solo giorno (controllo qualità)                                                                                                                                 |
| `python scripts/build_lighter_rounds.py all <input_root> <out_dir> <workers> [cache_name]`                         | Build completo; `<workers>` = processi paralleli (1 = sequenziale, una giornata CSV per worker)                                                                             |
| `python scripts/compare_lighter_gamma_cache.py <baseline_cache> <bulk_cache> <baseline_dir> <bulk_dir> <week_iso>` | Confronto regressione cache + `.txt`                                                                                                                                        |
| `python -m src.listats [summary]`                                                                                  | Sommario tabellare del dataset Lighter (vedi sotto)                                                                                                                         |
| `build_lighter_rounds.bat [workers]`                                                                               | Batch Windows (default 8 worker); **salta** i `.txt` già presenti in output                                                                                                 |
| `python scripts/backfill_lighter_intraday.py [rounds_root] [workers] [--dry-run]`                                  | Aggiunge `intraday: Hk` agli header storici (idempotente; non tocca `data:`)                                                                                                |
| `python scripts/backfill_lighter_delta_win.py [rounds_root] [workers] [--dry-run]`                                 | Aggiunge header modello v2 + colonne `DWinA` / `DWinB` (idempotente)                                                                                                        |
| `python scripts/study_delta_win_v2.py [workers]`                                                                   | Fit metodo A (pool empirico per H + espansione finestra) + B (logistic) su Lighter train weeks → `models/delta_win_v2.json`; calibrazione soglia + report; default 8 worker |
| `python scripts/eval_delta_win_v2_compare.py [data_dir]`                                                           | Report comparativo A vs B su round Chainlink (label Gamma)                                                                                                                  |
| `python scripts/backfill_real_delta_win.py [data_dir] [workers] [--dry-run]`                                       | Rifit `study_delta_win_v2.py` poi rigenera `.txt` reali da `.bin` con `DWinA`/`DWinB` (idempotente; `--dry-run` salta il fit)                                               |
| `python scripts/probe_delta_win_bands.py [data_dir]`                                                               | Win rate osservato per finestra |delta| ±2 sui reali (supporto metodo A)                                                                                                    |
| `python scripts/study_delta_win.py`                                                                                | Studio modelli v1 (legacy) → `models/delta_win_v1.json`                                                                                                                     |
| `python scripts/eval_delta_win_real.py [data_dir]`                                                                 | Valutazione esterna v1 su round Chainlink (legacy)                                                                                                                          |
| `backfill_lighter_intraday.bat [workers]`                                                                          | Batch Windows backfill header `intraday` su `H:\ticks\lighter-rounds5m`                                                                                                     |


**Statistiche (**`src/listats.py`**).** Modulo dedicato all’analisi del dataset Lighter: funzioni con prefisso `li_` (es. `li_summary`, `li_rounds_root`, `read_lighter_header`). Legge gli header dei `.txt` sotto `<ticks_root>/lighter-rounds5m/`; estendere qui nuove metriche derivate dallo studio dei round sintetici. CLI: `python -m src.listats` o `python -m src.listats summary` — output a sezioni tabellari. Prima statistica implementata: `li_summary` (conteggio round, intervallo temporale, distribuzione outcome gamma/lighter, `outcome_agreement`, completezza tick, gap `ptb_gamma`/`final_gamma`, `move_error` medio e move_error medio, round per settimana ISO).

Header: `source: lighter_synthetic`; `intraday: Hk` (fascia oraria da `hour_bands.json` / `hour_band(market_start_ts)`); campi audit `outcome_lighter`, `outcome_agreement: TRUE` / `FALSE`, `delta_lighter`, `delta_chainlink`, `move_error`. Colonna `outcome` = Gamma ufficiale se presente, altrimenti proxy Lighter. `ptb_chainlink` / `final_chainlink` / colonna `btc` = valori Lighter. Header `delta_win_*`: versione modello `2`, metodi `[band, logistic]`, hash `hour_bands`, target, intervallo sec, periodo training, stato `synthetic_calibrated` (vedi `docs/indicator_delta_win.md`).

Tabella `data:` **senza** `gain%` e **senza** `Rq`; colonne `DWinA`/`DWinB` (se in `delta_win_txt_columns`), poi `btc`, `vol`, `Rs`.

Filtro build: griglia causale completa (301 confini); round 23:55 UTC esclusi (confine finale oltre il giorno CSV). Non usare `convert` / `verify` su questi file.

Filtrare round discordanti: `grep -l "outcome_agreement: FALSE" <ticks_root>/lighter-rounds5m/**/*.txt`

Build incrementale: se `btc5m_<start_ts>_<HHMM>.txt` esiste già in output, il round viene saltato (`present` nel log). Giornata interamente presente → nessuna lettura CSV. `skipped` = griglia causale incompleta.
