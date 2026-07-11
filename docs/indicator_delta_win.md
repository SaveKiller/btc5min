# Indice delta_win (feed Lighter)

Probabilità **calibrata su archivio sintetico** che il lato indicato dal **segno del delta** al checkpoint coincida con l'**outcome ufficiale Gamma** a settlement.

## Definizione

- **Checkpoint:** `180, 150, 120, 90, 60, 30` secondi mancanti alla scadenza (`setup.json` → `delta_win_checkpoints`).
- **Lato predetto:** UP se `delta ≥ 0`, DOWN se negativo — stessa regola della colonna `quote` nel feed Lighter (non la maggioranza CLOB).
- **Label training:** `1` se quel lato = `outcome` Gamma nell'header; round con `outcome_agreement: nan` esclusi; round `FALSE` **inclusi** (mismatch Lighter→Gamma utile al modello).
- **Feature (live-safe):** `sec`, `|delta|` arrotondato come nel `.txt`, `V30/V60/V90/V120` arrotondate, fascia `intraday` H da `hour_bands.json`.
- **Non eleggibile:** delta `---`, vol mancante, stale Lighter nella finestra causale V120 → cella `---`.

## Artifact

- Path: `models/delta_win_v1.json` (`delta_win_model_path` in `setup.json`).
- Verifica `hour_bands_hash` e lista checkpoint all'avvio; mismatch → eccezione.
- Stato header feed: `synthetic_calibrated` (addestrato su Lighter Apr–Giu 2026, non sui round reali Chainlink).

## Comandi

```bash
# Studio e rigenerazione artifact (solo Lighter)
python scripts/study_delta_win.py

# Valutazione esterna su round reali in data/ (label da ptb_gamma/final_gamma)
python scripts/eval_delta_win_real.py [data_dir]

# Backfill colonna su feed storici
python scripts/backfill_lighter_delta_win.py [rounds_root] [workers] [--dry-run]

# Test
python -m unittest tests.test_delta_win
```

## Limiti

- Il modello selezionato (v1: **prevalence** per checkpoint) ignora `|delta|`, vol e H nella predizione; le feature servono all'estrazione e alla comparazione in `study_delta_win.py`.
- Le percentuali nei feed storici dopo backfill sono **enrichment in-sample**; non usare quelle celle per misurare la bontà del modello.
- Nei round reali Polymarket `delta_win` **non** è ancora nel `.txt` v6 (`src/txt_format.py` invariato): solo dataset Lighter.
- Transfer Lighter→Chainlink va letto in `data/reports/delta_win_real_eval_*.json` senza ricalibrare sul holdout reale.
