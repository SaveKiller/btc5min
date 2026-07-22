# Collector multi-token su poly — report 22-07-26

Documento di sintesi: obiettivo, lavoro fatto sul CT **poly**, misure, risorse, architettura attuale e follow-up su stabilità Chainlink.

| Campo | Valore |
|-------|--------|
| Host | CT Proxmox **poly** (id 103), IP `10.1.1.73`, SSH `ticksaver` |
| App | `/opt/btc5min` |
| Dati | `/opt/btc5min/data/` (`YYYY-MM-DD/bin|txt/`) |
| Data | 22 luglio 2026 |

Documenti correlati: [`nota-risorse-btc15m-22-07-26.md`](nota-risorse-btc15m-22-07-26.md), [`inventory-capacity-updown-22-07-26.md`](inventory-capacity-updown-22-07-26.md), [`nota-ticksaver-deploy.md`](nota-ticksaver-deploy.md), [`nota-round-persi-22-07-26.md`](nota-round-persi-22-07-26.md), [`nota-round-persi-22-07-26-reboot.md`](nota-round-persi-22-07-26-reboot.md).

---

## 1. Obiettivo

Estendere il ticksaver (collector Polymarket Up/Down) oltre il solo **BTC 5m**, mantenendo:

- campionamento **1 Hz**, book depth **8**, formato `.bin` / `.txt` invariato nella logica di salvataggio
- scrittura continua 24h su poly

Fasi previste e seguite:

1. Generalizzare il codice alla durata interval (non solo 300 s)
2. Affiancare **BTC 15m**, misurare risorse, go/no-go
3. Inventariare i mercati live; abilitare gli altri token dopo resize CT
4. (downstream, non in questo report) sync locale / dashv2 multi-market — ancora fuori scope

---

## 2. Cosa è stato fatto

### 2.1 Codice (repo → poly)

- CLI già parametrica: `python -m src.main --asset … --interval …`
- Generalizzati countdown / verify / finestre vol sul path txt rispetto a `INTERVAL_SECS` (`5m`→300, `15m`→900)
- `ChainlinkFeed.configure(asset)` + mappa symbol RTDS (`btc/usd`, `eth/usd`, …)
- Unit systemd versionate in [`deploy/`](../deploy/); generatore `scripts/gen_collector_units.py`
- Helper: `scripts/inventory_updown_markets.py`, `scripts/poly_resource_snapshot.py`

### 2.2 Fase BTC 15m (CT ancora a 2 GB)

- Nuova unit `btc15min.service` (log `data/collector-btc15m.log`)
- Misura ~1 h dual-service → **GO** (vedi §3)
- Smoke locale + verify su round 15m (900 tick)

### 2.3 Resize Proxmox

- RAM **2 GB → 6 GB** (vCPU già **6**, invariati)
- Riavvio CT → ripartenza automatica servizi enabled

### 2.4 Multi-token

Inventario Gamma live (slug `{asset}-updown-{5m|15m}-{ts}`):

| Asset | 5m | 15m | Chainlink symbol |
|-------|----|-----|------------------|
| btc | sì | sì | `btc/usd` |
| eth | sì | sì | `eth/usd` |
| sol | sì | sì | `sol/usd` |
| xrp | sì | sì | `xrp/usd` |
| doge | sì | sì | `doge/usd` |
| bnb | sì | sì | `bnb/usd` |
| hype | sì | sì | `hype/usd` |

**1h:** assente al probe. Altri asset (matic, avax, link, …) non trovati.

Abilitati **14** servizi systemd (7×5m + 7×15m). Primo round 5m post-enable validato (`done` + verify su campione eth/sol/hype).

### 2.5 Round persi (cutover / reboot)

| Evento | Round | Nota |
|--------|-------|------|
| Restart `btc5min` cutover codice | 1× 5m (`1784716200`) | [`nota-round-persi-22-07-26.md`](nota-round-persi-22-07-26.md) |
| Reboot CT resize RAM | skip slot 5m/15m in corso a ~12:03 UTC | [`nota-round-persi-22-07-26-reboot.md`](nota-round-persi-22-07-26-reboot.md) |

---

## 3. Misurazioni e risorse

### 3.1 Baseline e dual BTC (CT 2 GB)

| Scenario | RSS tipico | MemAvailable | ESTAB WS (ordine) | Disco |
|----------|------------|--------------|-------------------|--------|
| Solo `btc5min` | ~76 MB | ~1.9 GB / 2 GB | ~3 | ~44 MB/giorno (5m) |
| `btc5min` + `btc15min` (~1 h) | max ~106 + ~112 MB | min ~1.85 GB (**88% free**) | somma max ~6 | combo ~89 MB/giorno |

Soglie piano (RAM libera ≥30%, disco ≥30 giorni headroom, stabilità 1 h): **tutte GO** per BTC 5m+15m su 2 GB.

Dettaglio: [`nota-risorse-btc15m-22-07-26.md`](nota-risorse-btc15m-22-07-26.md). Sample JSONL: `data/reports/resource_btc15m.jsonl` su poly.

### 3.2 Pieno carico (CT 6 GB, 14 unit)

Snapshot a caldo subito dopo enable multi-token (sampling attivo):

| Metrica | Valore |
|---------|--------|
| Processi collector | **14** active |
| RSS somma | ≈ **0.95 GB** |
| MemAvailable | ≈ **5.3 GB** / 6 GB |
| ESTAB WS somma | ≈ **42** (Chainlink + CLOB per round in overlap) |
| Disco host | ~101 GB, ~99 GB liberi; stima piena ~0.6 GB/giorno |

Margine RAM ampio rispetto al vecchio limite 2 GB (che avrebbe reso i 14 slot non “sereni”).

### 3.3 Stima disco (depth 8)

- Un mercato **5m**: ~288 round/giorno × ~152 KB ≈ **~44 MB/giorno**
- Un mercato **15m**: ~96 round/giorno × ~465 KB ≈ **~45 MB/giorno**
- **14 slot**: ordine **~0.6 GB/giorno** → decine di giorni su 100 GB senza cleanup aggressivo

---

## 4. Architettura attuale

### 4.1 Modello operativo

```text
Proxmox CT poly
└── /opt/btc5min
    ├── 14 × systemd (un processo Python ciascuno)
    │     python -m src.main --asset X --interval Y
    ├── data/YYYY-MM-DD/{bin,txt}/  (prefissi X+Y, es. eth5m_*, btc15m_*)
    └── models/, hour_bands.json, setup.json
```

Ogni processo:

1. **1× WebSocket RTDS** Chainlink (singleton *nel processo*), filtrato sul symbol dell’asset
2. Fino a **2× WebSocket CLOB** in overlap (round corrente + prep del successivo)
3. Poll Gamma REST (outcome / fee / patch)

Isolamento: restart di `eth5m` non ferma `btc5min`. Trade-off: più processi, più connessioni.

### 4.2 BTC 5m vs BTC 15m vs altri token

| Aspetto | BTC 5m | BTC 15m | Altri token (eth, sol, …) |
|---------|--------|---------|---------------------------|
| Unit tipica | `btc5min` | `btc15min` | `{asset}5m` / `{asset}15m` |
| Slug | `btc-updown-5m-{ts}` | `btc-updown-15m-{ts}` | `{asset}-updown-{interval}-{ts}` |
| Durata / tick attesi | 300 s / ~300 | 900 s / ~900 | come interval |
| File | `btc5m_*` | `btc15m_*` | es. `eth5m_*`, `sol15m_*` |
| Chainlink | `btc/usd` | `btc/usd` (WS **separata** oggi) | symbol dedicato per asset |
| Log | `collector.log` | `collector-btc15m.log` | `collector-{asset}{interval}.log` |
| CLOB | token Up/Down di quel mercato | altro mercato (altri token id) | idem per asset/interval |
| Ruolo storico | servizio “primario” originale | affiancato | stessi meccanismi, asset diversi |

Cosa è **uguale** tra tutti: pipeline round (wait Gamma → sample 1 Hz → enrich gain → write bin/txt → verify → patch Gamma), `book_depth`, fee CLOB, layout `data/`.

Cosa è **diverso**: durata slot, densità di overlap (il 5m spawna più spesso), symbol oracle, liquidità/quote del CLOB (dato di mercato, non di codice).

### 4.3 Connessioni Chainlink oggi

`ChainlinkFeed` è singleton **per processo**, non globale sulla macchina.

- 7 asset × 2 timeframe = **14 WS Chainlink** verso RTDS
- `btc5m` e `btc15min` aprono **due** socket indipendenti sullo stesso `btc/usd`
- La subscribe RTDS è ampia (`crypto_prices_chainlink`); il filtro symbol è lato client

Il CLOB non si può fondere tra 5m e 15m dello stesso asset: mercati e `clobTokenIds` diversi.

---

## 5. Appunto follow-up: stabilità Chainlink e possibile refactor

### Idea

Se nei prossimi giorni le connessioni RTDS risultano **instabili** (stall frequenti, reconnect storm, gap tick, rate limit), ha senso un piccolo refactor:

- **un processo per asset** che orchestra **entrambi** i timeframe (5m + 15m)
- **una sola** WS Chainlink per symbol
- effetto: connessioni Chainlink **14 → 7**

Obiettivo del refactor: **stabilità / carico sul feed**, non tanto la RAM (già comoda a 6 GB).

### Se invece è stabile

Se stall/reconnect restano rari e i round chiudono senza buchi sistematici sui prezzi oracle, **si può rimandare** il refactor senza urgenza.

### Cosa monitorare (prossimi giorni)

Sui log `collector*.log` / journal, per ciascun asset:

1. Frequenza di `chainlink stall` e reconnect
2. Close WS anomali / errori Cloudflare / 429
3. Round con molti tick partial o `ptb_chainlink` / `final_chainlink` inconsistenti
4. Confronto `btc5m` vs `btc15min` (stesso symbol, due socket): se entrambi degradano insieme → problema RTDS/rete; se solo uno → più processo/locale
5. Eventuale correlazione con picchi ESTAB (overlap multi-token)

Strumenti già utili: `scripts/poly_resource_snapshot.py`, `grep stall` / `ws error` sui log, sequenza file `.bin` per giorno.

### Criterio pratico (proposta)

| Esito monitoraggio | Azione |
|--------------------|--------|
| Stall rari, round completi, verify ok | Nessun refactor; rivedere tra qualche settimana |
| Stall/gap ricorrenti su più asset | Pianificare processo per-asset (5m+15m, 1 Chainlink) |
| Solo un asset problematico | Prima verificare symbol RTDS / liquidità CLOB, non refactor globale |

---

## 6. Fuori scope (esplicito)

- `sync.py` / pull locale dei nuovi prefissi (`eth5m_*`, …)
- Dashboard `dashv2` multi-market / picker non-BTC
- Rinominare colonna `chainlink_btc` nel `.txt` in label generica (il valore è già quello dell’asset)
- Mercati 1h

---

## 7. Comandi operativi rapidi

```bash
# Stato servizi
ssh ticksaver 'systemctl list-units --type=service --state=running | grep -E "btc|eth|sol|xrp|doge|bnb|hype"'

# Snapshot risorse
ssh ticksaver 'PYTHONPATH=/opt/btc5min /opt/btc5min/venv/bin/python3 /opt/btc5min/scripts/poly_resource_snapshot.py'

# Stall Chainlink recenti
ssh ticksaver 'grep -h "chainlink stall\|chainlink ws error" /opt/btc5min/data/collector*.log | tail -50'
```
