# Manifest contesto meeting `bug-poly-collector`

Indice del materiale disponibile in `context/` (solo lettura durante il meeting).

## Report e documentazione

| File | Contenuto |
|------|-----------|
| `report-bug-0707.md` | **Report principale** — sintomi, timeline, ipotesi H1–H5, punti critici codice, diagnostica proposta |
| `report-0607.md` | Report storico pre-bug (contesto evoluzione progetto) |
| `ssh-commands.txt` | Comandi SSH rapidi verso poly (`ticksaver`) |
| `AGENTS.md` | Obiettivo progetto, requisiti CT poly |
| `README.md` | Overview progetto |
| `requirements.txt` | Dipendenze Python (`httpx`, `websocket-client`, `numpy`) |
| `deploy-ct-lan-poly.md` | Piano deploy su poly (Python 3.12, systemd, architettura) |

## Log

| File | Contenuto |
|------|-----------|
| `collector-poly.log` | **Log produzione** — run ~4h su poly (2026-07-06 22:38 – 2026-07-07 02:40 UTC) |
| `collector-dev.log` | Log breve da Windows dev (confronto) |

## Codice sorgente (`src/`)

| File | Ruolo |
|------|-------|
| `feed_chainlink.py` | WS RTDS singleton, ping, stall detector, dispatch Chainlink — **file critico** |
| `feed_clob.py` | WS CLOB per round |
| `round_state.py` | Logica `price_to_beat` / `final_chainlink` da timestamp oracle |
| `round_runner.py` | Orchestrazione round, eccezioni ptb/final |
| `main.py` | Avvio ChainlinkFeed + spawn round ogni 5 min |
| `round_buffer.py` | Buffer tick round |
| `sample_log.py` | Log SAMPLE periodico (`btc=... ptb=-`) |
| `market.py` | Risoluzione mercato Polymarket |
| `clob_api.py` | API REST CLOB |
| `book.py` | Order book |
| `binary_format.py` | Formato file `.bin` |
| `reader.py` / `convert.py` / `verify.py` | Lettura, conversione, verifica round |
| `settlement.py` | Settlement |

## Script diagnostici (`scripts/`)

| File | Ruolo |
|------|-------|
| `probe_btc_gaps.py` | Probe 10 min gap tick `btc/usd` (usato per H1/H2) |
| `probe_chainlink_ws.py` | Probe generico RTDS 2 min |
| `diag_ptb.py` | Diagnostica price_to_beat |

## Esempi round da poly (`examples-poly/`)

11 file `.txt` esportati dal CT poly (coppie con `.bin` omessi — formato binario).

| File | Note |
|------|------|
| `btc5m_1783377600.txt` … `btc5m_1783379100.txt` | 6 round OK completi (300 sec) |
| `btc5m_1783384500.txt` | **Parziale** — 260 sec, ptb con lag oracle 222s |
| `btc5m_1783384800.txt` … `btc5m_1783385700.txt` | 4 round OK dopo reconnect WS |
| *(nessun file)* | Round falliti non producono output |

## Esempi round dev Windows (`examples-dev/`)

2 round completi da test locale breve (confronto comportamento OK).

## Note per i partecipanti

- I file `.bin` originali sono in `data/bin/` sul repo (gitignored); i `.txt` sono la rappresentazione leggibile.
- Sul server poly esiste anche `/opt/btc5min/debug-9c51e0.log` (NDJSON debug, ~138 KB) — non incluso qui; accessibile via `ssh ticksaver`.
- Probe H1/H2 già eseguiti: Windows e poly identici su 10 min (579 tick, gap max ~8.3s, 0 disconnect).
