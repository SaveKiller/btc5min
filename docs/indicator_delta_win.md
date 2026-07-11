# Indice delta_win v2 (feed Lighter)

Due stime parallele che il lato indicato dal **segno del delta** al checkpoint vinca l'**outcome ufficiale Gamma** a settlement. Fit su tutto l'archivio Lighter; confronto sui reali via report dedicato.

## Metodi

| Colonna | Artifact | Input | Meccanismo |
|---------|----------|-------|------------|
| `DWinA` | `delta_band_lookup` | `sec`, `\|delta\|` arrotondato | Fasce di `\|delta\|` per checkpoint → `p_win` empirica |
| `DWinB` | `logistic_isotonic` | `sec`, `\|delta\|`, V30–V120, H | Logistic + calibrazione isotonica per checkpoint |

**Non è il lato maggioritario CLOB.**

## Definizione comune

- **Checkpoint:** `180, 150, 120, 90, 60, 30` (`delta_win_checkpoints`); altrove `---`.
- **Formato:** `DWinA` → `88% [12$-26$]`; `DWinB` → `93%` (arrotondamento intero).
- **Colonne feed:** `delta_win_txt_columns` in `setup.json` — `["a","b"]`, `["a"]` o `["b"]`; posizione **prima** di `btc`.
- **Lato predetto:** UP se `delta ≥ 0`, DOWN se negativo — stessa regola della colonna `quote`.
- **Label training:** `1` se quel lato = `outcome` Gamma; round con `outcome_agreement: nan` esclusi.
- **Non eleggibile:** delta `---`, vol mancante, stale nella finestra V120 → `---` ai checkpoint; fuori checkpoint solo spazi.

## Artifact

- Path: `models/delta_win_v2.json` (`delta_win_model_path`, versione `2`).
- Sezioni: `bands_by_sec` (metodo A), `logistic_by_sec` (metodo B).
- Verifica `hour_bands_hash` e lista checkpoint; mismatch → eccezione.

## Comandi

```bash
# Fit A+B su tutto Lighter
python scripts/study_delta_win_v2.py

# Confronto A vs B su round reali in data/
python scripts/eval_delta_win_v2_compare.py [data_dir]

# Probe fasce osservate sui reali (metodo A)
python scripts/probe_delta_win_bands.py [data_dir]

# Backfill colonne su feed storici (Lighter)
python scripts/backfill_lighter_delta_win.py [rounds_root] [workers] [--dry-run]

# Backfill colonne su feed reali in data/ (rigenera .txt da .bin)
python scripts/backfill_real_delta_win.py [data_dir] [workers] [--dry-run]

# Test
python -m unittest tests.test_delta_win
```

## Esempio sec=90

Stesso round: `DWinA` dipende solo dalla fascia di `\|delta\|`; `DWinB` può differire se vol o H spostano la calibrazione. Due round con `\|delta\|` in fasce diverse → `DWinA` diverse.

## Limiti

- Nessuna scelta automatica A vs B nel codice: usare `data/reports/delta_win_compare_*.json`.
- Nei round reali Polymarket le colonne sono nel `.txt` (da `convert` o collector); il `.bin` v6 resta invariato.
- Percentuali nei feed dopo backfill/convert sono enrichment in-sample; non usarle per misurare bontà del modello su Lighter.
