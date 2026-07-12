# Indice delta_win v2 (feed Lighter)

Due stime parallele che il lato indicato dal **segno del delta** al checkpoint vinca l'**outcome ufficiale Gamma** a settlement. Fit su tutto l'archivio Lighter; confronto sui reali via report dedicato.

## Metodi

| Colonna | Artifact | Input | Meccanismo |
|---------|----------|-------|------------|
| `DWinA` | `delta_band_lookup` | `sec`, `\|delta\|` arrotondato | Griglia 0–150: `p_win` empirica per ogni delta; al runtime media su finestra ±2 e range `[lo$-hi$]` |
| `DWinB` | `logistic_isotonic` | `sec`, `\|delta\|`, V30–V120, H | Logistic + calibrazione isotonica per checkpoint |

**Non è il lato maggioritario CLOB.**

## Definizione comune

- **Checkpoint:** da `delta_win_checkpoints_start` a `delta_win_checkpoints_end` ogni `delta_win_checkpoints_step` secondi in `setup.json` (default 180→5 step 5); altrove `---`.
- **Formato:** `DWinA` → `88% [31$-35$]` (media su delta±2, clamp 0–150); `DWinB` → `93%` (arrotondamento intero).
- **Colonne feed:** `delta_win_txt_columns` in `setup.json` — `["a","b"]`, `["a"]` o `["b"]`; posizione **prima** di `btc`.
- **Lato predetto:** UP se `delta ≥ 0`, DOWN se negativo — stessa regola della colonna `quote`.
- **Label training:** `1` se quel lato = `outcome` Gamma; round con `outcome_agreement: nan` esclusi.
- **Non eleggibile:** delta `---`, vol mancante, stale nella finestra V120 → `---` ai checkpoint; fuori checkpoint solo spazi.

## Metodo A — griglia e finestra

**Fit one-shot** su Lighter (`study_delta_win_v2.py`):

- Per ogni checkpoint e ogni `d` in `0..150`: `p_win(d)` = win rate empirico su campioni con `|delta|=d` (merge con vicini fino a `delta_win_band_min_samples` se `n` insufficiente).
- Salvato in artifact `delta_p_by_sec`.

**Runtime** (feed reale e Lighter):

- `d = min(|delta|, 150)`
- Finestra `[max(0,d-2), min(150,d+2)]`
- Percentuale = media aritmetica di `p_win` sui delta nella finestra
- Range mostrato = estremi della finestra (es. delta=33 → `74% [31$-35$]`)

## Artifact

- Path: `models/delta_win_v2.json` (`delta_win_model_path`, versione `2`).
- Sezioni: `delta_p_by_sec` (metodo A, 151 slot per checkpoint), `logistic_by_sec` (metodo B).
- Metadati: `delta_lookup_max: 150`, `delta_window_half: 2`.
- Verifica `hour_bands_hash` e lista checkpoint; mismatch → eccezione.

## Comandi

```bash
# Fit A+B su tutto Lighter
python scripts/study_delta_win_v2.py

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

Stesso round: `DWinA` dipende dalla finestra ±2 intorno a `|delta|`; `DWinB` può differire se vol o H spostano la calibrazione. Due round con `|delta|` distanti di ≥5 → `DWinA` diverse (finestre non sovrapposte).

## Limiti

- Nessuna scelta automatica A vs B nel codice: usare `data/reports/delta_win_compare_*.json`.
- Nei round reali Polymarket le colonne sono nel `.txt` (da `convert` o collector); il `.bin` v6 resta invariato.
- Percentuali nei feed dopo backfill/convert sono enrichment in-sample; non usarle per misurare bontà del modello su Lighter.
