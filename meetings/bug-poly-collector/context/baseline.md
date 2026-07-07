# Baseline — bug-poly-collector

- **generated_utc**: 2026-07-07T10:00:00Z
- **scope**: Diagnosi bug collector `btc5min` su CT poly (Proxmox 103): round persi, errori `price_to_beat not captured` / `chainlink final not captured`, feed Chainlink RTDS. Materiale in `meetings/bug-poly-collector/context/`.

## Fatti oggettivi

### Meeting

| Campo | Valore |
|-------|--------|
| meeting-id | `bug-poly-collector` |
| created_utc | 2026-07-07T09:20:00Z |
| participants | m-sonnet, m-deepseek, m-gpt, m-gemini, m-composer, m-glm, m-kimi, m-grok, m-minimax |
| punti discussione | 1 (`## Punto 01`) |
| report-turn esistenti | nessuno |
| baseline precedente | assente (generata ora) |

### Documenti context letti

| File | Righe/note |
|------|------------|
| `report-bug-0707.md` | Report principale bug (~395 righe) |
| `00-manifest.md` | Indice materiale meeting |
| `deploy-ct-lan-poly.md` | Piano deploy CT poly |
| `README.md` | Overview progetto |
| `requirements.txt` | httpx>=0.27, websocket-client>=1.7, numpy>=1.26 |
| `AGENTS.md` | Obiettivo progetto, requisiti CT poly |
| `collector-poly.log` | 394 righe — log produzione run ~4h |
| `collector-dev.log` | 17 righe — log breve Windows dev |

### Conteggi log `collector-poly.log` (PowerShell Select-String)

| Pattern | Occorrenze |
|---------|------------|
| `done \d+ seconds` | 11 |
| `price_to_beat not captured` | 68 (include righe raise+Exception → ~34 eventi fallimento ptb) |
| `chainlink final not captured` | 4 (→ ~2 eventi fallimento final) |
| `chainlink ws error` | 2 |
| `ws drop` | 6 |
| `chainlink stall` | 0 |

### Esempi round

| Directory | File .txt | Note |
|-----------|-----------|------|
| `examples-poly/` | 11 | 10 round 300 sec + 1 parziale 260 sec (`btc5m_1783384500.txt`) |
| `examples-dev/` | 2 | Round completi da test Windows breve |

### Codice sorgente in context (`src/`)

| File | Righe | Ruolo |
|------|-------|-------|
| `feed_chainlink.py` | 157 | WS RTDS singleton, `STALL_RECONNECT_SEC=45.0`, `PING_INTERVAL_SEC=5.0`, `_last_msg_ts` aggiornato solo su `btc/usd` |
| `round_state.py` | 70 | `apply_chainlink`: skip ptb se `ts_ms < _ptb_start_ms`; `prime_chainlink` non imposta ptb |
| `round_runner.py` | presente | Orchestrazione round |
| `main.py` | presente | Entrypoint orchestratore |
| `feed_clob.py` | presente | WS CLOB per round |
| Totale file `.py` in `src/` | 16 | |

### Parametri infra (da `report-bug-0707.md`)

| Elemento | Valore |
|----------|--------|
| CT | 103 `poly`, Debian 12 bookworm, LXC unprivileged |
| IP | 10.1.1.73/24, gateway 10.1.1.1, firewall PVE=1 |
| RAM/vCPU | 2048 MB / 6 core |
| Python runtime | 3.12.10 (`/usr/local/bin/python3.12`) |
| Servizio | `btc5min.service`, Restart=always |
| Run analizzato | 2026-07-06 22:38 – 2026-07-07 02:40 UTC (~4h) |
| Round attesi ~4h | ~48 (5 min ciascuno) |
| Round salvati | 11 file (10 completi + 1 parziale) |

### Ipotesi pre-valutate nel report (stato dichiarato)

| ID | Esito dichiarato |
|----|------------------|
| H1 Container/rete LXC | REJECTED (probe 10 min identico Windows/poly) |
| H2 Debian 12 / TCP stack | REJECTED |
| H3 Disconnect frequenti RTDS | REJECTED (1 solo `Going away`) |
| H4 NAT/router LAN | INCONCLUSIVE |
| H5 WS up ma stream BTC inutilizzabile | CONFIRMED (causa principale sospetta) |

### Script diagnostici in context

| File | Scopo |
|------|-------|
| `scripts/probe_btc_gaps.py` | Probe 10 min gap tick btc/usd |
| `scripts/probe_chainlink_ws.py` | Probe generico RTDS 2 min |
| `scripts/diag_ptb.py` | Ispezione formato timestamp + test cattura ptb |

### Git (repo `f:\btc5min`)

| Commit recente su file correlati | Messaggio |
|----------------------------------|-----------|
| baa1753 | sistemato il final price da chainlink |
| 8f5dec0 | setup poc per il collector |

## Comandi eseguiti

| Comando | Esito |
|---------|-------|
| `python -m py_compile src/feed_chainlink.py src/round_state.py src/round_runner.py src/main.py` (in context/) | exit 0 — sintassi OK |
| Conteggio righe log + file examples | exit 0 — vedi tabelle sopra |
| `git log --oneline -5` su path meeting/src | exit 0 — 2 commit rilevanti |
