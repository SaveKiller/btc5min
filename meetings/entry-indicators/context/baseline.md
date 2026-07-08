# Baseline — entry-indicators

- **generated_utc**: 2026-07-08T12:48:00Z
- **scope**: Indici di timing entrata per scommesse Polymarket "BTC Up or Down 5m"; analisi su file `.txt` campionati 1 Hz in `context/` e pipeline dati del progetto `btc5min`.

## Fatti oggettivi

### Meeting

- **Path**: `f:\btc5min\meetings\entry-indicators\`
- **meeting.md**: creato 2026-07-08T12:43:00Z; 1 punto di discussione (`## Punto 01`); 9 partecipanti elencati.
- **responses/**: cartella assente o vuota al momento della baseline (nessun `report-turn*.md`, nessuna `response-m-*-turn*.md`).
- **context/baseline.md**: generato in Fase 0 (questo file).

### Documenti in context/

| File | Righe (approx) | Dimensione | Ultima modifica |
|------|----------------|------------|-----------------|
| `00-manifest.md` | 41 | 2068 B | 2026-07-08 14:44:29 |
| `btc5m_1783476600.txt` | 319 | 17881 B | 2026-07-08 12:19:00 |
| `btc5m_1783476900.txt` | 320 | 17935 B | 2026-07-08 12:19:00 |
| `btc5m_1783477200.txt` | 320 | 17933 B | 2026-07-08 12:19:00 |
| `btc5m_1783479600.txt` | 317 | 17836 B | 2026-07-08 12:19:00 |
| `btc5m_1783479900.txt` | 317 | 17838 B | 2026-07-08 12:19:00 |
| `btc5m_1783480200.txt` | 317 | 17836 B | 2026-07-08 12:19:00 |
| `btc5m_1783481100.txt` | 317 | 17836 B | 2026-07-08 12:19:00 |

Totale file contesto utente: **8** (1 manifest + 7 round `.txt`).

### Struttura file `.txt` (verificata su tutti e 7)

- Sezione `header`: `market_start_ts`, `market_end_ts`, `ptb_price`, `ptb_chainlink`, `ptb_gamma`, `final_price`, `final_chainlink`, `final_gamma`, `outcome`, `tick_count`, `fee_rate`, eventuali `warnings`.
- Sezione `data`: **300 righe** per round; colonna `sec` da **300 a 1** (secondi alla scadenza); campi `time`, `quote` (UP/DOWN/----), prezzo in centesimi, `delta` ($ arrotondato vs PTB chainlink), `gain%`, `btc` (chainlink).
- `fee_rate`: **0.07** su tutti i 7 file.
- Outcome: **5 Up**, **2 Down** (tabella manifest confermata).

### Statistiche per file (script Python locale sui 7 `.txt`)

| File | Outcome | gain% min–max | Righe quote `----` |
|------|---------|---------------|-------------------|
| btc5m_1783476600 | Up | 0.9–89.6% | 6 |
| btc5m_1783476900 | Down | 0.9–89.6% | 26 |
| btc5m_1783477200 | Up | 2.9–89.6% | 26 |
| btc5m_1783479600 | Up | 0.9–89.6% | 8 |
| btc5m_1783479900 | Down | 0.9–89.6% | 8 |
| btc5m_1783480200 | Up | 0.0–86.3% | 2 |
| btc5m_1783481100 | Up | 0.9–89.6% | 9 |

- Un file (`1783476600`) ha warning header: `ptb_gamma missing at write`.
- `btc5m_1783481100.txt`: quote `----` alla riga `sec=300` (manifest: "quote parte da ---- a sec 300").

### Scala produzione (repo)

- `f:\btc5min\data\txt\`: **98** file `.txt` al momento del check.
- `f:\btc5min\data\bin\`: **98** file `.bin` corrispondenti.
- Manifest dichiara: **288 round/giorno** (target operativo).

### Codice rilevante (path citati / verificati)

| Path | Ruolo |
|------|-------|
| `src/convert.py` | Conversione `.bin` → `.txt`; formattazione colonne; `gain` da tick binario |
| `src/clob_api.py` | `market_buy_gain()`: ROI = payout/amount − 1 su walk LOB; `BET_USD=100`; fee inclusa |
| `src/binary_format.py` | Tick binario: 8 campi incl. `chainlink_btc`, `majority_gain` |
| `src/round_runner.py` | `enrich_gains()` a runtime dal LOB |
| `src/verify.py` | Validazione gain vs ricalcolo LOB |

**Definizione operativa `gain%` nel `.txt`**: frazione ROI su puntata simbolica $100 (`BET_USD`), netta fee Polymarket, calcolata sul lato majority (Up/Down) al secondo; mostrata come percentuale (`gain * 100`).

**Definizione operativa `delta`**: `round(chainlink_btc - ptb_chainlink)` in dollari, segno esplicito.

**Definizione operativa `quote`**: majority side da mid bid/ask Up vs Down; `----` se probabilità pari; righe parziali (`UP ---` / `DOWN ---`) se quote LOB mancanti ma chainlink presente.

### File binari LOB

- Presenti in `data/bin/` ma **non** inclusi in `context/` del meeting.
- Manifest: `.bin` contiene LOB completo oltre ai campi del `.txt`.

## Comandi eseguiti

- `Get-ChildItem meetings/entry-indicators/context` → 8 file elencati con dimensioni e date.
- `Measure-Object data/txt/*.txt` → count 98.
- `Measure-Object data/bin/*.bin` → count 98.
- `python -c "..."` (parse regex sui 7 `.txt` in context) → exit 0, statistiche tabulate sopra.
