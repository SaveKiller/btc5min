# Nota risorse BTC 15m — 22-07-26

Host: CT **poly** (`10.1.1.73`), app `/opt/btc5min`.

## Setup misurato

| Servizio | Unit | Log |
|----------|------|-----|
| BTC 5m | `btc5min.service` | `data/collector.log` |
| BTC 15m | `btc15min.service` | `data/collector-btc15m.log` |

Finestra: ~1 h steady-state, 30 sample JSONL in `data/reports/resource_btc15m.jsonl` (ogni 120 s).

## Baseline (solo 5m, pre-15m)

- RSS `btc5min` ≈ **76 MB**, ESTAB WS ≈ **3**, MemAvailable ≈ **1941 MB** / 2048 MB (~95% free)
- Size medio `btc5m_*.bin` (24 h) ≈ **152 KB** → ≈ **43.9 MB/giorno**

## Dual service (5m + 15m)

| Metrica | Valore |
|---------|--------|
| RSS `btc5min` | min 39 MB · max **106 MB** · last ~105 MB |
| RSS `btc15min` | min 40 MB · max **112 MB** · last ~112 MB |
| MemAvailable min | **1853 MB** → **88.4%** del totale libero |
| ESTAB WS somma max | **6** |
| `btc15m` size medio (3 round) | **465 KB** → ≈ **44.6 MB/giorno** (96 round/giorno) |
| Combo disco stimato | ≈ **88.5 MB/giorno** |
| Disco host | 101 G, **99 G** liberi; data/ ≈ 693 MB |

### Round 15m validati

- `btc15m_1784717100_1045.bin` — 900 tick, verify OK
- `btc15m_1784718000_1100.bin` — done
- `btc15m_1784718900_1115.bin` — done

## Go / no-go (soglie piano)

| Soglia | Esito |
|--------|-------|
| RAM libera ≥ 30% (~≥600 MB) | **GO** (min free 88.4%) |
| Disco ≥ 30 giorni headroom | **GO** (~2.7 GB / 30 g su 99 G liberi) |
| Stabilità 1 h (no crash/stall imputabili al 15m; 5m continuo) | **GO** (3× done 15m; 5m attivo). 1 round 5m perso al restart cutover: vedi [`nota-round-persi-22-07-26.md`](nota-round-persi-22-07-26.md) |

**Verdetto fase 1: GO** — si può stimare/abilitare altri mercati sotto le stesse soglie.

## Note operative cutover

- Sync necessari oltre a `src/`: `models/delta_win_v2.json`, `hour_bands.json` (senza di essi `write_round_txt` fallisce dopo il `.bin`).
- Template unit: [`deploy/btc5min.service`](../deploy/btc5min.service), [`deploy/btc15min.service`](../deploy/btc15min.service).
