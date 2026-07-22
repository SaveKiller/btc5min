# Inventario Up/Down + stima capacità poly — 22-07-26

Script: `python scripts/inventory_updown_markets.py`  
Snapshot JSON (es.): `data/inventory_updown.json`

## Mercati live trovati (5m + 15m)

Asset con **entrambi** i timeframe attivi su Gamma (slug `{asset}-updown-{5m|15m}-{ts}`):

| Asset | 5m | 15m | Note |
|-------|----|-----|------|
| btc | sì | sì | già in raccolta su poly |
| eth | sì | sì | Chainlink `eth/usd` |
| sol | sì | sì | Chainlink `sol/usd` |
| xrp | sì | sì | Chainlink `xrp/usd` |
| doge | sì | sì | Chainlink `doge/usd` |
| bnb | sì | sì | Chainlink `bnb/usd` |
| hype | sì | sì | Hyperliquid; Chainlink `hype/usd` |

**1h:** nessuno dei candidati ha prodotto slug live al momento del probe.  
Altri asset probeati e assenti: matic, avax, link, ada, dot, ltc, pepe, wif, trump, sui, ton.

Totale slot 5m+15m: **14** (7 asset × 2).

## Costo risorse (da misura BTC 15m)

Riferimento [`nota-risorse-btc15m-22-07-26.md`](nota-risorse-btc15m-22-07-26.md):

- 1 processo collector ≈ **40–112 MB RSS** peak, fino a **3** WS ESTAB in overlap
- Disco: **~44 MB/giorno** per un mercato 5m; **~45 MB/giorno** per un 15m (depth 8)
- Soglie: ≥30% RAM libera (≥600 MB su 2 GB); ≥30 giorni headroom disco

### Stima lineare (conservativa)

| Config | Processi | RSS peak stimato | Free RAM stimata | Disco MB/g | 30g | Soglia RAM 30% |
|--------|----------|------------------|------------------|------------|-----|----------------|
| Solo btc5m (prima) | 1 | ~0.1 GB | ~1.9 GB | ~44 | ~1.3 GB | OK |
| btc5m+btc15m (ora) | 2 | ~0.22 GB | ~1.85 GB | ~89 | ~2.7 GB | **OK (misurato)** |
| + eth+sol 5m only | 4 | ~0.45 GB | ~1.6 GB | ~177 | ~5.3 GB | OK |
| btc+eth+sol ×(5m+15m) | 6 | ~0.7 GB | ~1.3 GB | ~266 | ~8 GB | OK |
| tutti 7×5m only | 7 | ~0.8 GB | ~1.2 GB | ~308 | ~9 GB | OK |
| tutti 14 slot | 14 | ~1.5 GB | ~0.5 GB | ~620 | ~19 GB | **NO** (~24% free) |

Disco non è il collo di bottiglia (99 G liberi). **Il limite è la RAM** del CT 2 GB.

## Ranking consigliato (abilitazione)

1. **eth5m** poi **sol5m** (template già in `deploy/`)
2. Poi **xrp5m** / **doge5m** / **bnb5m** / **hype5m** uno alla volta con misura breve
3. Timeframe **15m** degli altri asset solo dopo che i 5m aggiuntivi restano sotto soglia
4. Evitare di accendere tutti i 14 slot insieme su questo CT

## Decisione richiesta (fase 2 stop)

Scegliere la lista da abilitare su poly. Esempi:

- **A (raccomandata):** eth5m + sol5m, poi rivalutare
- **B:** tutti i 5m (7 processi totali con btc5m; btc15m resta)
- **C:** btc+eth+sol su 5m e 15m (6 processi)
- **D:** altra lista esplicita

## Stato abilitato su poly (22-07-26 post resize 6 GB)

Abilitati e validati (primo round 5m `done` + verify OK su campione eth/sol/hype):

**14 unit:** btc/eth/sol/xrp/doge/bnb/hype × (5m + 15m).

Risorse a caldo (~14 processi in sampling): RSS somma ≈ **0.95 GB**, MemAvailable ≈ **5.3 GB** su 6 GB, ESTAB WS ≈ 42.

I 15m dei nuovi asset campionano dal round successivo al enable (primo boundary 15m dopo 12:08 UTC).
