# Nota round persi — 23-07-26 (btc5m, disallineamento deploy)

## Contesto

Deploy scaglionato `src/verify.py` (V19/V13) su due collector **btc5m** indipendenti, per poter riconciliare i round persi al restart dall’host gemello.

Solo **BTC 5m** (`btc5m_*`); altri token/timeframe su poly ignorati in questa nota.

## Netcup1 — round persi (copia su poly)

- Host: VPS **netcup1**, `/opt/btc5min/data/`
- Causa: restart `btc5min` (venv Python 3.12 + deploy `verify.py`) alle **10:29** e **10:32** CEST (**08:29 / 08:32 UTC**)
- Log: `round … skipped (already started)`

| market_start_ts | Ora UTC (slot) | File atteso | Copia su poly |
|-----------------|----------------|-------------|---------------|
| `1784795100` | 08:25–08:30 | `btc5m_1784795100_0825.bin` | sì |
| `1784795400` | 08:30–08:35 | `btc5m_1784795400_0830.bin` | sì |
| `1784795700` | 08:35–08:40 | `btc5m_1784795700_0835.bin` | sì |

**3** round persi su netcup; tutti recuperabili da poly.

## Poly — round perso (copia su netcup1)

- Host: CT **poly** (`ticksaver`, `10.1.1.73`), `/opt/btc5min/data/`
- Causa: restart `btc5min` per deploy `verify.py` alle **08:48:10 UTC**
- Log: `round 1784796300 skipped (already started), next round 1784796600`

| market_start_ts | Ora UTC (slot) | File atteso | Copia su netcup1 |
|-----------------|----------------|-------------|------------------|
| `1784796300` | 08:45–08:50 | `btc5m_1784796300_0845.bin` | sì (`done` 10:52 CEST) |

**1** round perso su poly; recuperabile da netcup1.

## Timeline utile

1. **08:29 / 08:32 UTC** — restart netcup1 → skip `1784795100`, `1784795400`; campionamento `1784795700` interrotto.
2. **08:47 UTC** — entrambi gli host `done` `1784796000` (ultimo round comune prima del deploy poly).
3. **08:48 UTC** — restart poly → skip `1784796300`; netcup1 continua campionamento e scrive il bin.
4. **08:57 UTC** — poly riprende con `done` `1784796600` (verify senza V19).

## Riconciliazione

- Da poly → netcup: copiare i `btc5m` mancanti `1784795100`, `1784795400`, `1784795700`.
- Da netcup1 → poly: copiare `btc5m_1784796300_0845.bin` + `.txt`.

### Eseguita 23-07-26 ~11:15 CEST

Copia (non spostamento) via PC locale; originali lasciati su entrambi gli host.

| market_start_ts | Direzione | bin + txt | verify |
|-----------------|-----------|-----------|--------|
| `1784795100` | poly → netcup1 | OK | OK netcup |
| `1784795400` | poly → netcup1 | OK | OK netcup |
| `1784795700` | — | già presente su netcup (collector) | — |
| `1784796300` | netcup1 → poly | OK | OK poly |

Indice `data/rounds_index.json` aggiornato su netcup1 (`upsert_bins`). Poly non usa `round_index` (modulo assente su host).
