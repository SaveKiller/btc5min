# Report turno 01 — bug-poly-collector

- **generated_utc**: 2026-07-07T10:30:00Z
- **turno**: 01
- **participants**: m-sonnet, m-deepseek, m-gpt, m-gemini, m-composer, m-glm, m-kimi, m-grok, m-minimax
- **baseline**: `context/baseline.md`

---

## Sintesi esecutiva

Il run di ~4 h su poly ha prodotto **11 round salvati su ~48 attesi** (~23%), con **~34 fallimenti `price_to_beat`** e **2 `chainlink final`**, contro **1 solo disconnect RTDS** (`Going away` 1001) e **0 eventi `chainlink stall`**. I probe 10 min Windows↔poly sono identici (579 tick, gap max ~8.3 s) — **escludono container/rete/Debian come causa primaria**.

**Consenso unanime (9/9):** la causa principale è **H5** — WebSocket RTDS apparentemente viva ma stream `btc/usd` non utilizzabile per catturare `price_to_beat`/`final_chainlink`.

**Due meccanismi concatenati** (non mutuamente esclusivi, entrambi da confermare con logging):

| Meccanismo | Probabilità media | Chi lo ha evidenziato |
|------------|-------------------|----------------------|
| **A — Stall detector strutturalmente inattivo** durante connessione attiva (`run_forever()` bloccante; check stall solo nel loop esterno di `_run()`) | **Alta (85–95%)** | m-sonnet (H6, 95%), m-gemini (H5.1, 95%), m-gpt (H1, 35% come watchdog), m-composer |
| **B — Timestamp oracle obsoleti** (`ts_ms < market_start_ms` → skip silenzioso in `apply_chainlink`; `prime_chainlink` mostra `btc=` ma non imposta ptb) | **Alta (60–85%)** | m-sonnet (H7, 85%), m-composer (H5b, 60%), m-deepseek (H5, 80%), m-kimi (H5a) |

**Raccomandazione operativa unanime:** fix applicativo + logging NDJSON **prima** di cambio OS. Debian 12 LXC **da mantenere**. Firewall PVE: test A/B opzionale (`firewall=0`), non fix primario.

---

## Punto 01 — Diagnosi bug collector poly

### 1. Pattern di fallimento (evidenza log)

Tutti i partecipanti concordano sul pattern a **blocchi** nel `collector-poly.log`:

| Blocco | Intervallo UTC | Esito |
|--------|----------------|-------|
| A | 22:38–23:10 | 6 round OK |
| B | 23:10–00:38 | ~17 round falliti ptb, **zero** ws error/stall |
| C | 00:38–01:05 | 1 parziale (lag ptb 222 s) + 4 round OK dopo `Going away` |
| D | 01:05–02:38 | nuova ondata fallimenti |

**Insight unico m-sonnet:** i blocchi FAIL durano ~80–90 min e si chiudono con `Going away` (1001). Compatibile con **heartbeat Chainlink oracle 3600 s** e deviation threshold 0.5%: in periodi di bassa volatilità l'oracle non posta nuovi round → tutti i tick RTDS riportano lo stesso `updatedAt` < `market_start_ms` → cascata di fallimenti ptb fino a reconnect server.

**Insight unico m-gpt:** il valore `btc=...` nei SAMPLE **non prova feed sano** — può essere `prime_chainlink` obsoleto. Servono `btc_age_sec` e `oracle_age_sec` nel log.

---

### 2. Ipotesi strutturate (merge)

#### Confermate / alta probabilità

| ID | Ipotesi | Prob. | Evidenze | Dissenso |
|----|---------|-------|----------|----------|
| **H5** | WS up ma stream BTC inutilizzabile | **70–95%** | 17 round consecutivi senza disconnect; `btc=... ptb=-`; stall=0 | — |
| **H5.1 / H6** | Stall detector nel loop esterno `_run()` ma `run_forever()` blocca → **dead code** durante connessione long-lived | **85–95%** | 0 `chainlink stall` in 4 h; codice `feed_chainlink.py` L73–98 | m-composer nota: se `_last_msg_ts` è solo su btc/usd, stall **dovrebbe** scattare se zero tick BTC >45 s — stall=0 implica più probabile H5b |
| **H5.2 / H7** | Tick BTC arrivano ma `oracle_ts_ms < market_start_ms` → ptb mai impostato | **60–85%** | `round_state.py` L43; round parziale lag 222 s; skip silenzioso | — |
| **H8** | `prime_chainlink` + `chainlink_ready()` mascherano assenza ptb | **30–80%** | Sampler parte con prezzo visibile ma ptb `None` | m-gpt, m-composer, m-deepseek (H6) |
| **H8b** | Manca recv-fallback per ptb (esiste per `final_chainlink`) | **80%** | Solo m-sonnet propone esplicitamente | Altri non prioritizzano |

#### Deprioritizzate (probe già negativi)

| ID | Ipotesi | Prob. | Stato |
|----|---------|-------|-------|
| H1 | Container/rete LXC | ≤15% | REJECTED (probe 10 min) |
| H2 | Debian 12 / TCP stack | <5% | REJECTED |
| H3 | Disconnect frequenti RTDS | ≤10% | REJECTED (1 Going away / 4 h) |

#### Inconclusive / test secondari

| ID | Ipotesi | Prob. | Azione |
|----|---------|-------|--------|
| H4 | NAT Fritz.box long-lived | 15–40% (CLOB), ≤15% (RTDS) | 5 `clob ws drop`; test firewall off |
| H9/H11 | Firewall PVE / conntrack | 1–30% | `pct set 103 ... firewall=0` A/B 4 h |
| H6-lib | `websocket-client` 1.9.0 su Py 3.12 | 5–30% | Pin versione, soak | m-minimax (H6) |
| H7-race | Race overlap round / singleton | 2–35% | Review lock; log `len(_rounds)` | m-kimi (H5d), m-minimax (H22) |
| H12 | Cambio OS risolve | **≤5%** | Sconsigliato come prima azione | m-gemini **sconsiglia** anche disabilitare firewall |

---

### 3. Meccanismo codice (consenso)

Tre punti concatenati in `feed_chainlink.py` + `round_state.py` + `round_runner.py`:

1. **`_last_msg_ts`** aggiornato solo su `btc/usd` (L140). PONG ignorato.
2. **Stall check** in `_run()` L75–77 — **non eseguito** mentre `run_forever()` è attivo (m-sonnet, m-gemini, m-gpt).
3. **`apply_chainlink`**: `if ts_ms < self._ptb_start_ms: return` — skip silenzioso, nessun log (tutti).
4. **`prime_chainlink`**: imposta `chainlink_price` ma non `price_to_beat` (tutti).
5. **`chainlink_ready()`**: true con solo prezzo, non ptb → falsi positivi SAMPLE (m-gpt, m-composer H8).

---

### 4. Fix proposti (priorità merge)

| Priorità | Fix | Descrizione | Proponenti |
|----------|-----|-------------|------------|
| **P0** | **F1 — Stall nel `_ping_loop`** | Ogni 5 s: se `now - _last_btc_msg_ts > 30–45 s` → `_close_ws(intentional=True)` | m-sonnet, m-gemini, m-gpt, m-deepseek, m-glm — **unanime** |
| **P1** | **F2 — Logging NDJSON** | `ptb_skip`, `btc_gap_warn`, `ws_close`, `prime_chainlink` stale | Tutti; tabella dettagliata in m-composer §4 |
| **P2** | **F3 — Recv-fallback ptb** | Se `recv_ms >= market_start` e ptb None, accetta tick stale come ptb | m-sonnet (H8, safety net) |
| **P3** | **F4 — `chainlink_ready()` più stretto** | Richiede ptb o tick fresco (`age <= 10s`) | m-gpt, m-composer |
| **P4** | **F5 — Reconnect proattivo** | Ogni 20–30 min o su ping fail | m-gpt (H6), m-kimi |
| **P5** | **F6 — Log `_on_close`** (attualmente `pass`) | code, msg, `last_btc_age_sec` | m-sonnet, m-glm |

**Insight m-composer (costo zero):** scaricare e analizzare `/opt/btc5min/debug-9c51e0.log` (~138 KB) **prima** di nuovo deploy — può confermare H5b senza patch.

---

### 5. Script e comandi diagnostici (merge)

#### Immediati (nessuna modifica codice)

```bash
# Stato e conteggi
ssh ticksaver systemctl status btc5min
ssh ticksaver "grep -cE 'done [0-9]+ seconds|price_to_beat not captured|chainlink final not captured|chainlink ws error|chainlink stall' /opt/btc5min/data/collector.log"

# Scarica debug NDJSON esistente (PRIORITÀ — m-composer)
ssh ticksaver "cat /opt/btc5min/debug-9c51e0.log" > debug-9c51e0.log

# Firewall CT
ssh proxmox-root "pct config 103 | grep firewall"
```

#### Probe soak (≥30–60 min, non 10 min)

| Script | Durata | Scopo |
|--------|--------|-------|
| `probe_btc_gaps.py` | 3600 s | Gap tick btc/usd su poly (servizio fermo) |
| `probe_chainlink_ws.py` | 1800–3600 s | Tutti i simboli — verifica WS viva senza BTC |
| `diag_ptb.py` | 1 round live | Formato timestamp + cattura ptb al bordo |
| `probe_oracle_ts.py` (nuovo, m-sonnet D1) | 7200 s | Freshness timestamp oracle, batch post-reconnect |

#### Test A/B

| Test | Durata | Esito che esclude causa |
|------|--------|-------------------------|
| Collector + NDJSON logging | 4 h | Pattern `ptb_skip` vs `btc_gap_warn` distingue H5.1 vs H5.2 |
| `firewall=0` su CT 103 | 4 h | Stesso fail rate → H9 rejected |
| Probe parallelo vs collector (m-gpt Test B) | 4 h | Probe OK + collector fail → bug connessione singleton |
| Soak Windows dev | 4 h | Stesso fail → conferma bug app, non infra |

#### Cattura pacchetti (opzionale)

```bash
ssh proxmox-root "tcpdump -i vmbr0 -w /tmp/poly-ws.pcap host 10.1.1.73 and port 443"
```

---

### 6. Logging NDJSON — eventi obbligatori (merge)

File suggerito: `/opt/btc5min/data/chainlink-debug.ndjson` (env `BTC5MIN_DEBUG_NDJSON=1`).

| location | message | Campi chiave |
|----------|---------|--------------|
| `feed_chainlink._on_open` | `ws_open` | `conn_id` |
| `feed_chainlink._on_close` | `ws_close` | `code`, `msg`, `last_btc_age_sec` |
| `feed_chainlink._ping_loop` | `stall_reconnect` | `stall_sec`, `last_btc_age_sec` |
| `feed_chainlink._on_message` | `btc_tick` | `oracle_ts_ms`, `recv_ms`, `gap_sec` |
| `feed_chainlink._on_message` | `btc_gap_warn` | se `gap_sec > 15` |
| `feed_chainlink._dispatch` | `ptb_skip` | `round`, `oracle_ts_ms`, `market_start_ms`, `skipped_reason` |
| `feed_chainlink._dispatch` | `ptb_set` | `lag_ptb_ms` |
| `feed_chainlink.register` | `prime_chainlink` | `primed_ts_ms`, `primed_stale` |
| `round_runner` | `round_fail` | dump completo stato chainlink |

**Pattern attesi:**

| Pattern NDJSON | Interpretazione |
|----------------|-----------------|
| `ptb_skip` ripetuto 300 s, nessun `btc_gap_warn` | **H5.2** — tick arrivano ma timestamp obsoleti |
| `btc_gap_warn` > 45 s senza `ws_close` | **H5.1** — stall detector non funziona |
| `ws_close` 1001 + batch + `primed_stale` | Reconnect server + dati accumulati |

---

### 7. Criteri validazione fix (merge)

| Criterio | Soglia | Durata min |
|----------|--------|------------|
| Round `done` | ≥ **90–95%** attesi | **≥ 4 h** |
| `price_to_beat not captured` | **0** (≤1 restart) | 4 h |
| `chainlink final not captured` | **0** | 4 h |
| Lag ptb (`lag=` nel log) | p95 ≤ 3–5 s, max ≤ 15 s | 4 h |
| `ptb_skip` su round completati | **0** | 4 h |
| `chainlink stall` in ping loop | presente se gap reale; seguito da ptb < 10 s | 4 h |
| `verify` su ogni `.bin` | 0 errori bloccanti | per round |

**Non validare** con probe 10 min o solo in orari ad alta volatilità BTC (m-sonnet, m-composer).

Comando post-run:

```bash
ssh ticksaver 'LOG=/opt/btc5min/data/collector.log
echo "done=$(grep -c \"done [0-9]* seconds\" $LOG) ptb_fail=$(grep -c \"price_to_beat not captured\" $LOG) final_fail=$(grep -c \"chainlink final not captured\" $LOG)"
ls -1 /opt/btc5min/data/btc5m_*.bin | wc -l'
```

---

### 8. Raccomandazioni infra / OS / rete / firewall

#### OS — **mantenere Debian 12 LXC** (9/9)

- Bug applicativo, non OS-dipendente.
- Ubuntu 24.04 utile solo per Python 3.12 da apt (semplificazione deploy futura), **non** fix bug.
- VM Debian non-LXC solo se fix software fallisce (m-gpt Test F).

#### Firewall PVE (`firewall=1`) — **test A/B, non prima azione** (7/9)

```bash
ssh proxmox-root "pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth"
```

- LAN `10.1.1.0/24` considerata sicura.
- **Dissenso m-gemini:** sconsiglia disabilitazione firewall — «networking robusto nei probe, modifiche aprirebbero vulnerabilità inutili».

#### Rete

- `tcp_keepalive_time=7200` irrilevante (ping app ogni 5 s) — non modificare come fix primario.
- MTU 1500 OK; test `ping -M do -s 1472` opzionale.
- IPv6: disabilitare solo se test mostra instabilità (m-deepseek).
- H4 NAT: possibile per CLOB, improbabile per RTDS con traffico ~1 Hz.

---

### 9. Roadmap operativa (checklist merge)

1. [ ] Scaricare e analizzare `debug-9c51e0.log` su poly
2. [ ] Implementare logging NDJSON (§6) — deploy senza fix funzionale
3. [ ] Soak 2–4 h → confermare H5.1 vs H5.2 da pattern NDJSON
4. [ ] Implementare **F1** (stall in `_ping_loop`, soglia 30–45 s)
5. [ ] Opzionale **F3** recv-fallback ptb + **F4** chainlink_ready stretto
6. [ ] Validazione 4 h con criteri §7
7. [ ] Se fail persiste: test `firewall=0` A/B; soak Windows 4 h; VM non-LXC

---

### 10. Insight unici per partecipante

| Agente | Contributo distintivo non emerso dagli altri |
|--------|-----------------------------------------------|
| **m-sonnet** | Meccanismo Chainlink oracle: heartbeat 3600 s + deviation 0.5% spiega blocchi ~80–90 min; fix F1 nel ping loop con codice completo; script `probe_oracle_ts.py` 2 h |
| **m-gemini** | Minoranza: **non** disabilitare firewall PVE; focus esclusivo su bug thread `run_forever` |
| **m-gpt** | `btc=` nei SAMPLE è falso positivo; probe parallelo fresh vs collector; reconnect proattivo 20–30 min; Gamma `priceToBeat` come controllo incrociato |
| **m-composer** | Checklist 9 step; analisi `debug-9c51e0.log` a costo zero; schema NDJSON con `hypothesisId`; H5a vs H5b da stall=0 |
| **m-deepseek** | Tabella ipotesi H5–H11 con probabilità numeriche; probe 30 min + tcpdump |
| **m-glm** | 10 comandi diagnostici numerati; esempio codice `apply_chainlink` con log skip |
| **m-kimi** | Ipotesi H5d race singleton; script `diag_stream_btc.py`; criterio nessun cluster ≥3 round persi |
| **m-grok** | Script `diag_h5_btc_stream.py`; sintesi conservativa infra |
| **m-minimax** | Catalogo esteso H1–H22; half-open socket H11; fail-fast dopo N round consecutivi falliti (H9) |

---

### 11. Dubbi aperti per turno 02

1. **H5.1 vs H5.2:** i tick BTC **mancano** (>45 s) o **arrivano con timestamp obsoleti**? Serve NDJSON o analisi `debug-9c51e0.log`.
2. **Stall=0:** conferma che il check outer loop non gira durante `run_forever()`, oppure i tick BTC arrivano ogni <45 s ma inutilizzabili?
3. **Soak Windows 4 h:** il bug si manifesta anche su dev? Non testato.
4. **Recv-fallback ptb:** semanticamente corretto o maschera il problema oracle? Solo m-sonnet propone come safety net.

---

*Fine report turno 01 — generato da m-coordinator*
