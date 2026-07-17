# Formato file del round (bin e txt)

Ogni round del mercato **BTC Up or Down 5m** produce una coppia di file: `.bin` (formato canonico, versione 6) e `.txt` (vista tabellare per analisi umana). Un round dura **300 secondi**; il campionamento mira a **un tick al secondo** (tipicamente ~300 tick, `sec` da 300 a 1).

## Percorsi e nomi

```
data/<YYYY-MM-DD>/bin/btc5m_<market_start_ts>_<HHMM>.bin
data/<YYYY-MM-DD>/txt/btc5m_<market_start_ts>_<HHMM>.txt
```

- `market_start_ts`: Unix UTC di inizio round (allineato allo slug Polymarket, es. `btc-updown-5m-1783238400`).
- `HHMM`: ora UTC di inizio (solo comodità nel nome file).
- Il `.txt` è generato dal `.bin` con `python -m src.convert`; le regole di formattazione del feed testuale sono centralizzate in `src/txt_format.py` (`render_round_txt`). I `warnings` nel `.txt` vengono preservati tra rigenerazioni.



## Campionamento (cosa finisce in ogni tick)

Un thread campiona **una volta per ogni secondo di countdown** (`sec` = secondi mancanti alla scadenza, arrotondato). Per ogni `sec` nuovo:

1. Legge il prezzo BTC da **Chainlink** (feed RTDS Polymarket).
2. Se il CLOB ha bid/ask su entrambi i token Up/Down → tick **completo** (quote + book).
3. Altrimenti → tick **partial**: solo BTC Chainlink, quote = `NaN` nel `.bin` e `UP/DOWN ---` nel `.txt`.

**PTB (price to beat)** usato per il delta durante il round: `ptb_gamma` se già arrivato da Gamma API, altrimenti `ptb_chainlink` (ultimo tick Chainlink con timestamp ≤ `market_start_ts`). Alla chiusura, `final_chainlink` è l’ultimo tick Chainlink con timestamp ≤ `market_end_ts`.

Dopo il campionamento, `enrich_gains` calcola il `majority_gain` su ogni tick completo (vedi sotto). Poi scrittura `.bin` + `.txt`; un worker in background può patchare `ptb_gamma` / `final_gamma` nel header e rigenerare il `.txt`.

---



## File `.bin` (versione 6)

Magic `BTC5`, little-endian. Struttura: **header fisso** + **N record tick** (ciascuno seguito da uno **snapshot del book**).

### Header (76 byte)


| Campo             | Tipo    | Significato                                                          |
| ----------------- | ------- | -------------------------------------------------------------------- |
| `magic`           | 4 char  | `BTC5`                                                               |
| `version`         | uint16  | `6`                                                                  |
| `market_start_ts` | uint32  | Inizio round (Unix UTC)                                              |
| `market_end_ts`   | uint32  | Fine round (`start + 300`)                                           |
| `outcome`         | uint8   | `0` unknown, `1` Up, `2` Down                                        |
| `tick_count`      | uint32  | Numero di tick (≈ 300)                                               |
| `fee_rate`        | float32 | Fee CLOB da Gamma (`feeSchedule.rate`)                               |
| `ptb_price`       | float64 | BTC al primo tick campionato (`ticks[0].chainlink_btc`, arrotondato) |
| `ptb_chainlink`   | float64 | PTB da feed Chainlink (ultimo tick ≤ start)                          |
| `ptb_gamma`       | float64 | PTB ufficiale Polymarket/Gamma; `NaN` se non ancora patchato         |
| `final_price`     | float64 | BTC all’ultimo tick campionato                                       |
| `final_chainlink` | float64 | Prezzo finale Chainlink (ultimo tick ≤ end)                          |
| `final_gamma`     | float64 | Prezzo finale Gamma; `NaN` finché non patchato                       |


**Outcome:** se Gamma ha risposto in tempo → outcome Gamma; altrimenti `Up` se `final_chainlink >= ptb_chainlink`, `Down` altrimenti (warning nel `.txt`).

### Record tick (40 byte) + book snapshot

Ogni tick:


| Campo                  | Tipo    | Significato                                                               |
| ---------------------- | ------- | ------------------------------------------------------------------------- |
| `recv_ts_ms`           | uint64  | Timestamp locale di campionamento (ms)                                    |
| `secs_to_expiry`       | float32 | Secondi reali mancanti a `market_end_ts` (non arrotondato)                |
| `up_bid`, `up_ask`     | float32 | Miglior bid/ask token **Up** (0–1); `NaN` se partial                      |
| `down_bid`, `down_ask` | float32 | Miglior bid/ask token **Down** (0–1); `NaN` se partial                    |
| `chainlink_btc`        | float32 | Prezzo BTC USD da Chainlink al campionamento                              |
| `majority_gain`        | float32 | ROI frazionario su acquisto $100 sul lato maggioritario; `NaN` se partial |
| `chainlink_recv_ms`    | uint64  | Quando è arrivato l’ultimo aggiornamento Chainlink usato (ms)             |


Subito dopo: **book snapshot** = 4× uint16 (conteggi livelli up_bids, up_asks, down_bids, down_asks) + per ogni livello `(price: float64, size: float64)`. I best bid/ask nel record tick devono coincidere con il primo livello dello snapshot (verificato da `verify`).

Tick partial: quote e gain = `NaN`, snapshot vuoto (tutti i conteggi 0).

---



## File `.txt` (vista tabellare)

Sezione `header:` con metadati del round + contatori utili per il sanity check:

- `stale_sec`: soglia da `setup.json` → `stall_reconnect_sec` (default 15).
- `stale_ticks`: quanti tick hanno Chainlink “stale” (vedi colonna `delta`).
- `vol_windows_sec`, `vol_min_changes`, `vol_unit`: parametri indici volatilità `VW` (vedi colonna `vol`).
- `risk_model_version`, `risk_status`, `risk_target`, `risk_label_source`, `risk_ptb_source`, `risk_primary_vol_window_sec`, `risk_min_vol_coverage_ratio`, `risk_probability_buckets`, `risk_variants`: metadati indice di rischio R (vedi colonna `risk`).
- `delta_win_*`: versione modello v2, metodi `[band, logistic]`, hash `hour_bands`, target, intervallo sec, periodo training (vedi `docs/indicator_delta_win.md`).
- `intraday: Hk`: fascia oraria UTC da `hour_bands.json`.
- `warnings`: es. outcome provvisorio, `ptb_gamma` mancante, mismatch outcome gamma vs chainlink.

Sezione `data:` — righe ordinate per `sec` **decrescente** (300 → 1):

```
sec  time  quote      delta    gain%             DWinA DWinB       btc  vol                         risk
240  4:00  DOWN  61c   -28$  62.3%  66% [n=535]   93%  97206$  V30 18  V60 22  V120 31  Rq 5   Rs 4
```


| Colonna   | Calcolo / significato                                                                                                                                                                                                                                                                                                                                                                                                |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **sec**   | `floor(secs_to_expiry + 0.5)` — secondi mancanti alla scadenza                                                                                                                                                                                                                                                                                                                                                       |
| **time**  | `sec` in `M:SS`                                                                                                                                                                                                                                                                                                                                                                                                      |
| **quote** | Se tick completo: probabilità implicita = `round(mid_bid_ask × 100)` in centesimi; mostra il lato con probabilità più alta (`UP 75c`, `DOWN 60c`, oppure `---- 50c` se pari). Se partial: `UP ---` o `DOWN ---` (lato stimato da ultimo tick completo o da `chainlink` vs PTB)                                                                                                                                       |
| **delta** | `round(chainlink_btc - ptb_chainlink)` in USD, con segno (`+12$`, `-5$`, `0$`). Se Chainlink stale: `---` (campione più vecchio di `stall_reconnect_sec` rispetto a `chainlink_recv_ms`)                                                                                                                                                                                                                             |
| **gain%** | `majority_gain × 100`, una cifra decimale (`8.5%`). `---` se partial. Vedi formula sotto                                                                                                                                                                                                                                                                                                                             |
| **DWinA** | Intero % + `[n=N]` (pool empirico per fascia **H**, finestra fissa ±2 implicita), es. `87% [n=39]`; slot con `p_win` solo se `n ≥ delta_win_window_min_samples` (default 30); se `n` sotto soglia: spazi al posto della % e `[n=N*]` allineato ( `[n=29*]`); `---` se nessun pool locale; calcolato ogni secondo da `delta_win_sec_start` a `delta_win_sec_end`.                                                     |
| **DWinB** | Intero %, es. `93%`; stesso intervallo sec; colonna opzionale.                                                                                                                                                                                                                                                                                                                                                       |
| **btc**   | `chainlink_btc` arrotondato all'intero, seguito da `$` senza spazio (es. `97235$`)                                                                                                                                                                                                                                                                                                                                   |
| **vol**   | Token `VW N` per ogni `W` in `setup.json` → `volatility_windows_sec` (es. `V30 18`, `V60 22`). Volatilità realizzata trailing in USD, intero arrotondato (`V30 0` se BTC fermo). `VW ---` se dati insufficienti o Chainlink stale sulla riga. Non è previsione forward.                                                                                                                                              |
| **risk**  | `Rq N` rischio di quota (`Pq0 = 1 − quota normalizzata del lato maggioritario` → bucket 1–9). `Rs N` rischio statistico (`Pz = Φ(−z)` con `z = delta_signed / (sigma_W × √secs_to_expiry)`, finestra primaria W60). `-` al posto del numero se non calcolabile. Ingresso eseguibile quando entrambi hanno valore numerico (nessuna lineetta). Stato `experimental_uncalibrated` finché non c'è calibrazione holdout. |


**Indice R (rischio perdita a settlement):** target = outcome ufficiale header ≠ lato maggioritario scelto. Calcolo live-safe in `src/risk.py`, solo dati passati. Bucket preliminari da `risk_probability_buckets` in `setup.json`. Valutazione: `python scripts/eval_risk.py [data_dir]` → report in `data/reports/risk_eval_<timestamp>.json`. Test: `python -m unittest tests.test_risk`.

**Indici VW (volatilità intra-round):** calcolati in `convert` su `chainlink_btc`, solo tick già osservati nel round (trailing/live-safe). Per ogni secondo `sec` e finestra `W`: tick con `sec' ∈ [sec, sec+W−1]` (asse countdown: presente + passato, mai futuro); `Δ = btc_j − btc_{j−1}` tra coppie consecutive nella finestra; `VW = round(std(Δ) × √(n_pairs))`. Configurazione in `setup.json`: `volatility_windows_sec` (array, es. `[30, 45]`), `volatility_min_changes` (minimo variazioni nella finestra). Unità USD documentata in header (`vol_unit: usd_trailing`). Confronto utile con `|delta|`: se `|delta| < VW` il movimento vs PTB è ancora nel rumore recente.

**Lato maggioritario** (per quote e gain): confronto dei mid `((up_bid+up_ask)/2)` vs `((down_bid+down_ask)/2)`; vince Up se `up_mid >= down_mid`.

**majority_gain** (solo tick completi): simula un **market buy da $100** (`BET_USD=100`) sul lato maggioritario, camminando il book ask con fee Polymarket (`fee_rate × price × (1-price)` per livello). ROI = `(payout_usd / 100) - 1` (es. `0.085` → `8.5%` nel `.txt`). Se il book ask è vuoto ma il token è a ≥99c, usa il best ask sintetico.

**delta nel** `.txt` usa sempre `ptb_chainlink` dell’header (non `ptb_gamma`), per coerenza con il feed live.

---



## Strumenti utili


| Comando                                  | Uso                                                                                                                   |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `python -m src.reader <file.bin>`        | Riepilogo header, range quote/gain, primi/ultimi tick; `--csv`, `--book-sec N` per dump book                          |
| `python -m src.convert <file.bin         | dir>`                                                                                                                 |
| `python -m src.verify <file.bin          | dir>`                                                                                                                 |
| `python scripts/eval_risk.py [data_dir]` | Preview metriche R (Brier, AUC, reliability) su round locali; non statisticamente significativa su una sola giornata. |
| `python -m unittest tests.test_risk`     | Test anti-leakage, batch/live e casi limite indice R.                                                                 |


Per analisi programmatica preferire `read_round()` in `src/binary_format.py` → `(header, ticks ndarray N×9, list[BookSnapshot])`.

---



## Note per strategie / altri agenti

- **sec** è l’asse temporale principale: “quanto manca alla scadenza”, non il timestamp assoluto.
- **quote** riflette il mercato CLOB; **delta** riflette Chainlink vs PTB. Disallineamenti (quota maggioritaria vs segno del delta) sono pattern di trading rilevanti (vedi `docs/patterns.txt`).
- Tick **partial** ≠ bug automatico: spesso assenza di liquidità (delta alto, mercato a 99c+) o warmup book; usare `scripts/analyze_clob_partial.py` per classificare.
- Round **completo** atteso: `tick_count == 300`, primo tick `sec ≥ 295`, ultimo `sec ≤ 10`, nessun errore `verify`.
- Campi `*_gamma` nel header possono arrivare in ritardo via `GammaPatchWorker`; finché `NaN`, affidarsi a Chainlink per outcome e PTB live.
