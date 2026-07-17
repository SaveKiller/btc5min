# Sanity check round

Se l'utente chiede un **sanity check** (o controllo/sanità dei file round), eseguire **tutti** i controlli sotto sui `.bin` / `.txt` locali in `data/` (dopo `sync.bat` se serve aggiornare dal server). Comprende sia **Chainlink stall** sia **quote partial CLOB**.

Parametri collector attuali in `setup.json` (per interpretare stall/stale): `stall_reconnect_sec`, `ping_interval_sec`, `reconnect_cooldown_sec`.

## 1. Log collector (Chainlink stall, round completi, verify)

Se presente `data/collector-poly.log` (o il log passato come argomento):

```
python scripts/analyze_collector_log.py
python scripts/analyze_collector_log.py <path_log>
```

Controllare e riportare:


| Metrica                       | Cosa significa                                                                                                                         |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `chainlink stall`             | Gap tick BTC > `stall_reconnect_sec` → reconnect forzato. Contare eventi e **quali round erano in campionamento** (`sampling_active`). |
| `chainlink ws error`          | Chiusura WS (es. `Going away` 1001). Idem: correlare con round attivi.                                                                 |
| `ROUND A RISCHIO CHAINLINK`   | Round che hanno avuto stall/error **durante** il campionamento — candidati a prezzo BTC bloccato nel `.bin`/`.txt`.                    |
| `verify ERROR`                | Mismatch outcome / integrità (es. V13 outcome). Elencare `start_ts` e messaggio.                                                       |
| `round failed` / `no seconds` | Round persi del tutto.                                                                                                                 |
| `done con tick != 300`        | Round incompleti.                                                                                                                      |
| `outcome=computed`            | Settlement provvisorio (gamma timeout): non è un bug feed, ma affidabilità outcome inferiore.                                          |
| `clob ws drop`                | Disconnect CLOB — **non** basta da solo per diagnosi; correlare con analisi partial (§2).                                              |


**Verifica manuale sui round a rischio Chainlink:** per ogni `start_ts` in `ROUND A RISCHIO CHAINLINK`, aprire `data/txt/btc5m_<ts>.txt` (o `data/**/txt/`) e controllare:

- header `warnings` (outcome provvisorio, ptb_gamma mancante, …)
- righe con `delta: ---` (solo su `.txt` v6 rigenerati; indica chainlink stale oltre `stall_reconnect_sec`)
- header `stale_ticks` / `stale_sec` (solo v6)
- **BTC fermo**: ≥4 tick consecutivi con stesso prezzo `NNNNN$` (il log script ha `analyze_txt_files` per questo pattern)

Lo script analizza automaticamente in coda i `.txt` dei round in `ROUND A RISCHIO CHAINLINK` e dei `verify ERROR` (btc piatto, `delta_stale`, `stale_ticks`, warnings).

**Interpretazione stall (sessione baseline ~252 round):** gli stall sono attesi occasionalmente; sono un problema solo se il round a rischio mostra nel `.txt` BTC piatto per molti secondi **a metà round** con mercato ancora contestabile, o verify error sullo stesso `start_ts`. Dopo tuning `stall_reconnect_sec: 15` gli stall dovrebbero essere più brevi.

## 2. Quote partial CLOB

```
python scripts/analyze_clob_partial.py 100
python scripts/analyze_clob_partial.py 100 <data_dir> <log_collector>
```

Il primo argomento è la soglia `|delta|` in USD (100 = regola attuale).

Leggere il report in `data/reports/clob_partial_<timestamp>.json` e confrontarlo con `data/reports/clob_partial_baseline.json`.


| Verdetto         | Significato                                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `no_liquidity`   | Normale: delta alto, mercato a 99c+, o pochi tick a delta basso con max delta alto. Nessuna liquidità utile, **non** è bug CLOB.     |
| `warmup`         | Partial solo all'apertura round (sec ≥ 240): book non ancora pronto.                                                                 |
| `certainty_skew` | Partial solo negli ultimi 60s con quota 97–98c, o book sbilanciato (bid senza ask).                                                  |
| `clob_suspect`   | Partial sostenuto (≥10 tick) a delta basso nella fascia centrale (sec 60–240): possibile problema feed CLOB — verificare sul `.txt`. |
| `mixed`          | Pattern non chiaro — revisione manuale.                                                                                              |


**Non** classificare come problema CLOB i round in cui la quota manca perché il delta è già molto alto (outcome quasi deciso) o il mercato è a 99c+: è assenza di liquidità, non disconnect.

## 3. Cosa riportare all'utente

Sintesi unica con:

- round totali / completati / con tick ≠ 300
- conteggio stall, ws error chainlink, ws drop CLOB, verify error, outcome computed
- elenco round a rischio chainlink + esito controllo `.txt` (btc piatto, stale, warnings)
- conteggio verdetto partial (`no_liquidity`, `warmup`, `certainty_skew`, `clob_suspect`, `mixed`)
- eventuali `clob_suspect` / `mixed` da rivedere manualmente
- discrepanze vs `clob_partial_baseline.json`



## Baseline e review manuali

- `data/reports/clob_partial_baseline.json` — metodologia CLOB, review manuali sessione 252 round, round ancora `pending_reviews`.
- Per aggiornare le review CLOB: aggiungere voci in `manual_reviews`, togliere da `pending_reviews`.
- Ogni run `analyze_clob_partial.py` scrive un report timestampato in `data/reports/`.



## Criterio di esito

- **OK**: nessun round fallito; tutti i `done` a 300 tick; nessun `verify ERROR`; nessun `clob_suspect`; stall/ws error senza danni visibili sui `.txt` dei round a rischio (niente BTC piatto lungo a metà round con mercato aperto).
- **Da indagare**: `verify ERROR`; tick ≠ 300; round a rischio chainlink con BTC piatto prolungato o molti `delta: ---`; `clob_suspect` > 0; `mixed` con delta basso e mercato ancora contestabile (<97c).
