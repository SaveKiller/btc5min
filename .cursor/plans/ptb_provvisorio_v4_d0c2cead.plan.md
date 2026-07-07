---
name: PTB provvisorio v4
overview: PTB/final provvisori da RTDS al boundary, sostituzione via polling Gamma API (10s), timeout 20 min in setup.json, bin v4 con delta RTDS vs settlement Polymarket, round sempre salvati.
todos:
  - id: setup-json
    content: Creare setup.json e src/setup.py (settlement_wait_sec, gamma_poll_sec, ecc.)
    status: pending
  - id: round-state
    content: Provisorio RTDS in round_state; campi gamma/delta; apply_chainlink solo per tick live
    status: pending
  - id: gamma-poll
    content: wait_gamma_settlement in market.py + integrazione polling in round_runner
    status: pending
  - id: round-runner
    content: No fail ptb/final; poll PTB intra-round e final post-round; warnings
    status: pending
  - id: bin-v4
    content: Bump binary_format v4, settlement, verify, convert, reader (flag gamma)
    status: pending
  - id: wire-setup
    content: Collegare setup a main.py e feed_chainlink.py
    status: pending
  - id: debug-logs
    content: Eventi NDJSON provisional/gamma/delta e settlement_timeout
    status: pending
  - id: purge-bin-v3
    content: Cancellare tutti i .bin/.txt v3 esistenti (dev data/ e poly) prima del deploy v4
    status: pending
  - id: validate
    content: Test round; confronto .bin vs Gamma; grep fail ptb = 0
    status: pending
isProject: false
---

# PTB provvisorio + Gamma settlement + setup.json + bin v4

## Obiettivo

Eliminare i fallimenti round per `price_to_beat not captured` / `final not captured` quando il valore RTDS è disponibile ma il timestamp oracle Chainlink non è ancora valido (o resta in stasi notturna).

**Strategia settlement:** allinearsi al sito Polymarket — non aspettare tick Chainlink con `oracle_ts >= boundary`, ma **pollare Gamma API** (`priceToBeat`, `finalPrice`, `outcome`) ogni `gamma_poll_sec` (default 10 s), fino a `settlement_wait_sec` (default 20 min).

Salvare nel `.bin`:
- prezzi **effettivi** usati per outcome (Gamma se disponibile, altrimenti provvisori RTDS)
- provvisori RTDS e **delta** = `gamma - provisional` per analisi statistica RTDS vs settlement reale

**Policy confermata:** se dopo `settlement_wait_sec` Gamma non risponde, outcome da provvisori RTDS, flag `ptb_gamma`/`final_gamma` = 0, warning in `.warn`.

## Perché Gamma e non Chainlink oracle timestamp

Il sito mostra l'outcome in ~10–15 s perché il backend Polymarket scrive su Gamma, non perché attende un nuovo round on-chain. In stasi BTC (nessun movimento ≥ 0,5%), Chainlink può non postare un nuovo round per molti minuti, ma il settlement usa comunque l'ultimo prezzo Chainlink valido — esposto da Gamma come `priceToBeat` / `finalPrice`.

Il collector oggi è **più restrittivo** del sito (`ts_ms < market_start` → skip). Gamma è la fonte di verità per il confronto con l'UI.

## Flusso dati

```mermaid
sequenceDiagram
    participant RTDS as RTDS_btc_usd
    participant RS as RoundState
    participant Sampler as SamplerThread
    participant Gamma as Gamma_API
    participant RR as RoundRunner

    Note over RTDS,RR: market_start
    RTDS->>RS: recv_ms >= start
    RS->>RS: ptb_provisional, price_to_beat = provisional
    Sampler->>Sampler: campiona con ptb provvisorio

    loop ogni gamma_poll_sec durante round
        RR->>Gamma: fetch priceToBeat
        Gamma-->>RR: priceToBeat se presente
        RR->>RS: ptb_gamma, ptb_delta, aggiorna price_to_beat
    end

    Note over RTDS,RR: market_end
    RTDS->>RS: final_provisional
    loop fino a settlement_wait_sec
        RR->>Gamma: fetch finalPrice + outcome
        Gamma-->>RR: final + closed se pronti
        RR->>RS: final_gamma, final_delta
    end
    RR->>RR: scrive .bin v4 + .warn se solo RTDS
```

## 1. `setup.json` + loader

Creare [`setup.json`](f:\btc5min\setup.json) alla root progetto (JSON indent 4 spazi):

```json
{
    "settlement_wait_sec": 1200,
    "gamma_poll_sec": 10,
    "prep_ahead_sec": 10,
    "stall_reconnect_sec": 45,
    "ping_interval_sec": 5
}
```

| Chiave | Default | Uso |
|--------|---------|-----|
| `settlement_wait_sec` | 1200 (20 min) | Finestra max polling Gamma post-`market_end` (e per PTB se non arrivato prima) |
| `gamma_poll_sec` | 10 | Intervallo tra richieste HTTP Gamma (gentile sui server) |
| `prep_ahead_sec` | 10 | Spawn round (da `main.py`) |
| `stall_reconnect_sec` | 45 | Feed Chainlink |
| `ping_interval_sec` | 5 | Feed Chainlink |

Nuovo modulo [`src/setup.py`](f:\btc5min\src\setup.py):
- `load_setup()` legge `Path(__file__).parent.parent / "setup.json"` una volta all'avvio
- Nessun default in codice (D2): chiave mancante → eccezione esplicita
- Espone: `SETTLEMENT_WAIT_SEC`, `GAMMA_POLL_SEC`, `PREP_AHEAD_SEC`, `STALL_RECONNECT_SEC`, `PING_INTERVAL_SEC`

Wire-up:
- [`src/main.py`](f:\btc5min\src\main.py): `load_setup()` all'import; `PREP_AHEAD_SEC` da setup
- [`src/feed_chainlink.py`](f:\btc5min\src\feed_chainlink.py): `STALL_RECONNECT_SEC`, `PING_INTERVAL_SEC` da setup
- [`src/round_runner.py`](f:\btc5min\src\round_runner.py): `SETTLEMENT_WAIT_SEC`, `GAMMA_POLL_SEC`

## 2. Provisorio RTDS in `RoundState`

File: [`src/round_state.py`](f:\btc5min\src\round_state.py)

Nuovi campi:
- `ptb_provisional`, `final_provisional` (float)
- `ptb_gamma`, `final_gamma` (float | None) — da Gamma API
- `ptb_delta`, `final_delta` (float | None) — `gamma - provisional`
- `ptb_gamma_flag`, `final_gamma_flag` (bool)
- `_ptb_source`, `_final_source`: `"rtds"` | `"gamma"`

**`apply_chainlink`** — semplificato rispetto al piano precedente:
- aggiorna `chainlink_price` / `chainlink_ts_ms` (serie tick `chainlink_btc`)
- al primo tick con `recv_ms >= _ptb_start_ms`: imposta `ptb_provisional` e `price_to_beat` se non ancora da Gamma
- al primo tick con `recv_ms >= _final_end_ms`: imposta `final_provisional`
- **non** usa più `oracle_ts >= boundary` per settlement (rimuovere guard ptb-oracle e logica final oracle/recv come gate obbligatorio)

Metodi aggiuntivi:
- `apply_gamma_ptb(value)` / `apply_gamma_final(value, outcome)` — chiamati dal round runner dopo poll
- `effective_ptb()` / `effective_final()` — gamma se flag, altrimenti provisional

`chainlink_ready()`: invariato (`chainlink_price is not None`).

## 3. Polling Gamma

File: [`src/market.py`](f:\btc5min\src\market.py)

Riutilizzare `fetch_market_by_slug(asset, interval, start_ts)` — già espone:
- `price_to_beat` da `eventMetadata.priceToBeat`
- `final_chainlink` da `eventMetadata.finalPrice`
- `outcome` da `outcomePrices` / `closed`

Nuova funzione (nome indicativo):

```python
def poll_gamma_settlement(asset, interval, start_ts, need_ptb, need_final, deadline) -> dict:
    # loop: fetch_market_by_slug; sleep GAMMA_POLL_SEC; return quando ptb/final/outcome pronti o timeout
```

Comportamento:
- **PTB:** poll da `market_start_ts` in parallelo al sampler (thread leggero o check nel loop round runner ogni 10 s)
- **Final + outcome:** poll da `market_end_ts` fino a `market_end_ts + SETTLEMENT_WAIT_SEC`
- 1 richiesta HTTP ogni `gamma_poll_sec` per round → trascurabile per Gamma
- Esco appena ho i campi richiesti (tipicamente 1–2 poll = 10–20 s post-chiusura)

## 4. `RoundRunner`

File: [`src/round_runner.py`](f:\btc5min\src\round_runner.py)

**Durante il round (0–300 s):**
- Sampler parte con `price_to_beat` provvisorio RTDS
- Ogni `gamma_poll_sec`: se Gamma ha `priceToBeat`, sostituisci ptb, calcola `ptb_delta`, log `ptb gamma (delta=...)`

**Dopo `market_end_ts`:**
- Sampler fermato
- Cattura `final_provisional` da ultimo tick RTDS al boundary (se non già fatto in `apply_chainlink`)
- Poll Gamma per `finalPrice` + `outcome` fino a successo o `settlement_wait_sec`
- Se PTB non ancora da Gamma, continua poll anche per `priceToBeat` nella stessa finestra

**Non fallire** per ptb/final mancanti se esistono provvisori RTDS.

**Outcome:**
1. Preferire `outcome` da Gamma se `closed`/outcomePrices disponibile
2. Altrimenti `outcome_from_prices(effective_final, effective_ptb)`
3. Se solo provvisori: calcolo locale + `.warn`

**Eccezione** solo se manca anche il provvisorio (feed RTDS morto al boundary).

**Warnings** (`.warn`):
- `ptb not from gamma (rtds only)`
- `final not from gamma (rtds only)`
- `outcome from rtds provisional, not gamma`
- includere delta quando Gamma arriva in ritardo

## 5. Formato binario VERSION 4

File: [`src/binary_format.py`](f:\btc5min\src\binary_format.py)

- `VERSION = 4`
- Header 84 byte:

```
ptb_provisional    d
final_provisional  d
ptb_delta          d   # gamma - provisional; 0.0 se N/A (flag distingue)
final_delta        d
ptb_gamma          B   # 0=rtds only, 1=from Gamma
final_gamma        B
padding            6x
```

`HEADER_FMT = "<4sHII d B x d I d d d d d B B 6x>"`

Campi header:
- `price_to_beat` / `final_chainlink` = valori **effettivi** (Gamma se flag=1, altrimenti provisional)
- `outcome` = da Gamma preferito, altrimenti calcolato

**Incompatibilità totale con v2 e v3** (policy progetto, come già fatto v2→v3):
- `read_round`, `verify`, `convert`, `reader` accettano **solo** `VERSION = 4`
- header 84 byte vs 64 byte v3; campi aggiuntivi non interpretabili dai reader vecchi
- tentativo di leggere un `.bin` v3 con tooling aggiornato → eccezione `unsupported version`

### Migrazione: cancellare i `.bin` esistenti

Prima del primo deploy del collector v4, **eliminare tutti i file round v3** (e relativi `.txt`/`.warn` accoppiati). Non sono convertibili automaticamente; mescolarli con v4 in `data/` crea confusione in verify/convert e analisi.

**Dev (Windows)** — path effettivo del collector: `data/btc5m_*` (default `--out data`); se esistono copie in `data/bin/`, pulire anche quella cartella:
```text
f:\btc5min\data\btc5m_*.bin
f:\btc5min\data\btc5m_*.txt
f:\btc5min\data\btc5m_*.warn
f:\btc5min\data\bin\btc5m_*.*
```

**Produzione poly:**
```bash
ssh ticksaver "rm -f /opt/btc5min/data/btc5m_*.bin /opt/btc5min/data/btc5m_*.txt /opt/btc5min/data/btc5m_*.warn /opt/btc5min/data/bin/btc5m_*.*"
```

Opzionale: backup archivio dei v3 in cartella separata (es. `data/archive-v3/`) se servono per riferimento storico — il tooling nuovo non li leggerà più.

Dopo la pulizia, ogni nuovo round scritto dal collector sarà **solo v4**.

Aggiornare: [`settlement.py`](f:\btc5min\src\settlement.py), [`verify.py`](f:\btc5min\src\verify.py), [`convert.py`](f:\btc5min\src\convert.py), [`reader.py`](f:\btc5min\src\reader.py).

`verify` V13: outcome coerente con ptb/final effettivi; opzionale V19 log se outcome_gamma ≠ outcome_computed (warning, non hard fail).

## 6. Ruolo feed Chainlink WS

Il WebSocket RTDS resta per:
- colonna `chainlink_btc` nei 300 tick al secondo
- `chainlink_price` live per sampler / delta nel round

**Non** è più gate per salvare il round. Opzionale in NDJSON: confronto oracle_ts vs Gamma per ricerca futura.

## 7. NDJSON debug

Eventi in [`round_runner.py`](f:\btc5min\src\round_runner.py):
- `ptb_provisional_set`, `ptb_gamma_set` (con delta)
- `final_provisional_set`, `final_gamma_set`
- `gamma_poll`, `settlement_timeout`
- `outcome_gamma` vs `outcome_computed` se divergono

## 8. Validazione

0. **Pre-deploy:** `.bin` v3 cancellati (o archiviati fuori da `data/`); `data/` contiene solo v4 dopo i primi round
1. Run 2–3 round: `.bin` v4 con delta; Gamma di solito entro 10–20 s post-chiusura
2. Round con solo RTDS (Gamma down o timeout simulato): `.warn`, round `done`, flag=0
3. `python -m src.verify data/*.bin` — OK
4. **Cross-check:** confrontare header `.bin` con `fetch_market_by_slug` post-round (ptb, final, outcome devono coincidere quando flag=1)
5. `grep -c 'price_to_beat not captured'` su poly → atteso 0

## File toccati (riepilogo)

| File | Modifica |
|------|----------|
| `setup.json` | **nuovo** |
| `src/setup.py` | **nuovo** loader |
| `src/round_state.py` | provvisorio RTDS; apply_gamma_* |
| `src/market.py` | `poll_gamma_settlement` |
| `src/round_runner.py` | polling PTB intra-round + final post-round |
| `src/binary_format.py` | v4 header, flag gamma |
| `src/settlement.py` | header esteso, outcome da Gamma |
| `src/verify.py`, `convert.py`, `reader.py` | v4 + campi gamma/delta |
| `src/main.py`, `feed_chainlink.py` | setup |
| `src/feed_chainlink.py` | apply_chainlink semplificato (solo live + provisional) |

## Fuori scope (per ora)

- Fix P0 stall in `_ping_loop` (meeting bug-poly-collector) — commit separato
- Script batch analisi distribuzione delta RTDS vs Gamma su N round

## Rischi

- **Gamma in ritardo 10–30 s:** polling 10 s adeguato; `settlement_wait_sec` 20 min come rete di sicurezza
- **PTB su Gamma non al secondo 0:** provvisorio RTDS necessario all'avvio; sostituzione appena Gamma risponde
- **Dipendenza HTTP settlement:** fallback provvisori + `.warn`; tick order book comunque salvati
- **Sampler usa ptb provvisorio** nei primi secondi fino al primo poll Gamma: accettato; delta tipicamente piccolo
- **Header 84 byte / incompatibilità v3:** richiede purge `.bin` esistenti prima del deploy; non mescolare versioni in `data/`
