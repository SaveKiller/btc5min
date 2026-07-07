# Report finale — bug-poly-collector

- **generated_utc**: 2026-07-07T10:40:00Z
- **participants**: m-sonnet, m-deepseek, m-gpt, m-gemini, m-composer, m-glm, m-kimi, m-grok, m-minimax
- **turni**: 01
- **status**: chiuso

---

## Scopo e contesto

Il meeting `bug-poly-collector` (2026-07-07) ha analizzato il bug del collector `btc5min` in produzione sul container **poly** (Proxmox CT 103, Debian 12 LXC unprivileged, IP `10.1.1.73`). Il servizio systemd `btc5min.service` raccoglie tick ask/bid e prezzi Chainlink per i mercati Polymarket "BTC Up or Down 5m", scrivendo file binari e `.txt` in `/opt/btc5min/data/`.

**Sintomo osservato:** in un run di ~4 h (2026-07-06 22:38 – 2026-07-07 02:40 UTC) solo **11 round salvati** su ~48 attesi (~23%), con **~34 fallimenti `price_to_beat not captured`**, **2 `chainlink final not captured`**, **1 disconnect RTDS** (`Going away` 1001) e **0 eventi `chainlink stall`**.

**Materiale analizzato:** `context/report-bug-0707.md`, log `collector-poly.log`, 11 esempi round poly, codice in `context/src/`, script diagnostici, probe 10 min Windows↔poly, debug NDJSON `debug-9c51e0.log` (analisi locale post-turno).

**Deliverable atteso:** ipotesi strutturate, test/prove, logging, criteri validazione fix, raccomandazioni infra/OS — per guidare implementazione successiva.

---

## Sintesi esecutiva

Il meeting ha raggiunto **consenso unanime (9/9)** sulla diagnosi di fondo: **H5 — WebSocket RTDS apparentemente connessa ma stream `btc/usd` non utilizzabile** per catturare `price_to_beat` e `final_chainlink`. Container Debian 12, rete LXC e probe 10 min **escludono** infra come causa primaria (H1–H3 deprioritizzate).

Due meccanismi applicativi concatenati spiegano il pattern:

1. **Stall detector strutturalmente inattivo** durante connessioni long-lived: il check in `_run()` non gira mentre `run_forever()` è bloccante → **0 `chainlink stall`** nonostante buchi di fallimento di 80–90 min.
2. **Timestamp oracle obsoleti** scartati silenziosamente in `apply_chainlink` (`ts_ms < market_start_ms`) mentre `prime_chainlink` mostra `btc=` ma non imposta ptb → falsi positivi operativi.

**Decisioni prese:**

| Priorità | Azione |
|----------|--------|
| **P0** | Spostare stall detector in `_ping_loop` (soglia 30–45 s su assenza tick `btc/usd`) |
| **P1** | Deploy logging NDJSON in `feed_chainlink.py` (`ptb_skip`, `btc_gap_warn`, `ws_close`, ecc.) |
| **Infra** | **Mantenere Debian 12 LXC**; firewall PVE test A/B opzionale, non prima azione |
| **Validazione** | Soak collector ≥4 h: ≥90–95% round `done`, 0 ptb/final fail |

**Analisi post-turno `debug-9c51e0.log`:** 73 `sampler start`, 39 `ptb captured`, 34 senza ptb — coerente con il log principale. Solo eventi `round_runner` (P1/P2); **nessun** `ptb_skip`/`btc_gap` → logging Chainlink non ancora deployato; **H5.1 vs H5.2 resta da confermare** con NDJSON su `feed_chainlink`.

L'utente ha accettato il report turno 01 come base implementativa e chiuso il meeting senza turno 02.

---

## Evoluzione per punto di discussione

### Punto 01 — Diagnosi bug collector poly

**Turno 01:** Tutti e 9 i partecipanti hanno prodotto analisi strutturate. Il merge ha identificato:

- Pattern a **blocchi** nel log: OK 22:38–23:10 (6 round) → FAIL 23:10–00:38 (~17 round) → reconnect `Going away` 00:38 → OK parziale + 4 round → FAIL 01:05+.
- **H5 confermata** come causa principale; sottocasi H5.1 (stall dead code) e H5.2 (timestamp obsoleti) entrambi ad alta probabilità.
- **H1–H3 rejected** (probe 10 min identico Windows/poly); **H4** inconclusa (NAT/CLOB); **H9–H12** basse probabilità.
- Piano fix: F1 stall in ping loop, F2 NDJSON, F3 recv-fallback ptb (opzionale), F4 `chainlink_ready()` più stretto, F5 reconnect proattivo, F6 log `_on_close`.
- Roadmap operativa in 7 step (analisi debug log → NDJSON → soak → F1 → validazione 4 h → test infra se necessario).

**Feedback utente:** chiusura meeting richiesta; report accettato; chiarimento path `debug-9c51e0.log` su poly (`/opt/btc5min/debug-9c51e0.log`) e copia locale analizzata.

**Decisione finale:** procedere con fix applicativo P0 + logging P1 su Debian 12 LXC esistente; non cambiare OS come prima azione.

**Dubbio finale:** meccanismo dominante tra H5.1 e H5.2 — richiede NDJSON Chainlink post-deploy.

---

## Cronologia turni

### Turno 01

- **report:** Merge completo in `responses/report-turn01.md`. Consenso H5, due meccanismi (stall + timestamp), tabella ipotesi, fix prioritizzati, script diagnostici, schema NDJSON, criteri validazione, raccomandazioni infra, insight per partecipante, dubbi aperti per turno 02.
- **feedback utente:** Chiusura meeting senza turno 02. Report accettato. Analisi locale debug log: 73 sampler start, 39 ptb captured, 34 falliti; solo messaggi P1/P2 da `round_runner`.

---

## Interazioni utente (sintesi trasversale)

- **Orientamento implementativo:** l'utente non ha contestato la diagnosi; ha chiesto chiusura meeting e indicato il report come base per implementazione.
- **Chiarimento operativo:** percorso file debug NDJSON su poly e coerenza conteggi con log principale.
- **Nessuna richiesta** di cambio OS, disabilitazione firewall immediata, o turno 02 di approfondimento.

---

## Insight da singoli partecipanti

| Agente | Contributo distintivo |
|--------|----------------------|
| **m-sonnet** | Meccanismo Chainlink oracle: heartbeat 3600 s + deviation 0.5% spiega blocchi ~80–90 min; codice completo fix F1 in `_ping_loop`; script `probe_oracle_ts.py` 2 h; recv-fallback ptb (F3) come safety net; primo round FAIL può essere `final not captured` (H8 transizione). |
| **m-gemini** | **Minoranza:** sconsiglia disabilitazione firewall PVE; attribuisce H5.2 solo 10% vs H5.1 95%; focus esclusivo su bug thread `run_forever`. |
| **m-gpt** | `btc=` nei SAMPLE è **falso positivo** (prime obsoleto); probe parallelo fresh vs collector; reconnect proattivo 20–30 min; Gamma `priceToBeat` come controllo incrociato; ping loop che fa `return` su send fail senza close. |
| **m-composer** | Checklist 9 step; analisi `debug-9c51e0.log` a costo zero; schema NDJSON con `hypothesisId`; distinzione H5a vs H5b da stall=0; script `probe_btc_staleness.py`, `analyze_debug_log.py`. |
| **m-deepseek** | Tabella H5–H11 con probabilità numeriche; tcpdump 10 min; variabile env `DEBUG_FILE` per NDJSON. |
| **m-glm** | 10 comandi diagnostici numerati; esempio codice `apply_chainlink` con log skip esplicito. |
| **m-kimi** | Ipotesi H5d race singleton; script `diag_stream_btc.py`; criterio nessun cluster ≥3 round persi; allargamento finestra final. |
| **m-grok** | Script `diag_h5_btc_stream.py`; sintesi conservativa infra. |
| **m-minimax** | Catalogo esteso H1–H22; half-open socket H11; fail-fast dopo N round consecutivi falliti; `Restart=always` come possibile mascheramento. |

---

## Decisioni prese

1. **Causa principale:** bug applicativo H5 (WS up, stream BTC inutilizzabile) — **non** Debian 12, LXC o rete LAN come causa primaria.
2. **Fix P0:** implementare stall detector in `_ping_loop` con soglia 30–45 s sull'assenza di tick `btc/usd`, chiamando `_close_ws(intentional=True)`.
3. **Fix P1:** logging NDJSON strutturato in `feed_chainlink.py` e `round_runner.py` (eventi §6 report turno 01); env suggerito `BTC5MIN_DEBUG_NDJSON=1`, file `/opt/btc5min/data/chainlink-debug.ndjson`.
4. **Infra OS:** **mantenere Debian 12 LXC unprivileged** su CT 103; cambio OS/VM solo se fix software fallisce dopo validazione 4 h.
5. **Firewall PVE:** non disabilitare come prima azione; test A/B `firewall=0` opzionale se fail persiste (dissenso m-gemini documentato).
6. **Ordine operativo:** (a) analisi debug log esistente, (b) deploy solo logging NDJSON, (c) soak 2–4 h per distinguere H5.1/H5.2, (d) deploy F1, (e) validazione 4 h con criteri §7 report turno 01.
7. **Meeting chiuso** dopo turno 01; nessun turno 02.

---

## Dubbi aperti

1. **H5.1 vs H5.2:** i tick BTC **mancano** (>45 s) o **arrivano con `oracle_ts_ms < market_start_ms`**? Il debug log attuale non risponde; serve NDJSON Chainlink post-deploy.
2. **Stall=0:** conferma assoluta che il check outer loop non gira durante `run_forever()`, oppure tick BTC ogni <45 s ma inutilizzabili?
3. **Soak Windows 4 h:** il bug si manifesta anche su dev? Campione attuale troppo breve.
4. **Recv-fallback ptb (F3):** semanticamente corretto o maschera il problema oracle?
5. **Meccanismo oracle heartbeat 3600 s (m-sonnet):** plausibile ma non verificato con `probe_oracle_ts.py`.
6. **485 eventi `books not ready` (P2)** nel debug log: impatto sulla qualità dati round salvati?
7. **Probe long-run ≥60 min** non eseguiti: failure intermittenti multi-ora formalmente ancora possibili su H1–H4 a bassa probabilità.

---

## Meccanismo tecnico (riferimento codice)

Tre punti concatenati nel collector:

```73:98:meetings/bug-poly-collector/context/src/feed_chainlink.py
    def _run(self) -> None:
        while not self._stop.is_set():
            if self._last_msg_ts and time.time() - self._last_msg_ts > STALL_RECONNECT_SEC:
                log.warning("chainlink stall %.0fs, reconnecting", time.time() - self._last_msg_ts)
                self._close_ws(intentional=True)
            try:
                self._run_once()
            # ...
    def _run_once(self) -> None:
        # ...
            self._ws.run_forever(ping_interval=None)  # bloccante per tutta la connessione
```

```131:156:meetings/bug-poly-collector/context/src/feed_chainlink.py
    def _on_message(self, ws, raw: str) -> None:
        # ...
        if payload.get("symbol") != self.symbol:
            return
        self._last_msg_ts = time.time()  # solo btc/usd
        # ...
    def _dispatch(self, value: float, ts_ms: int, rounds: list[RoundState]) -> None:
        # ...
            state.apply_chainlink(value, ts_ms, recv_ms)
```

In `round_state.py`: `if ts_ms < self._ptb_start_ms: return` — skip silenzioso senza log. `prime_chainlink` imposta `chainlink_price` ma non `price_to_beat`. `chainlink_ready()` può essere true con solo prezzo → sampler logga `btc=... ptb=-`.

**`_ping_loop` attuale:** invia `"ping"` ogni 5 s ma **non** controlla stall; su eccezione send fa `return` senza close.

---

## Analisi `debug-9c51e0.log` (post-turno)

| Metrica | Valore |
|---------|--------|
| `sampler start` | 73 |
| `ptb captured` | 39 |
| Round senza ptb | 34 |
| `first sample` con `ptb_ready: false` | 73 (100%) |
| `books not ready` (P2) | 485 |
| Eventi `feed_chainlink` | **0** |
| hypothesisId presenti | P1 (185), P2 (485) |

**Interpretazione:** il file conferma il tasso di fallimento ptb (~47%) coerente con `collector-poly.log`. Tutti i round partono senza ptb al primo sample (normale). L'assenza di log Chainlink impedisce di distinguere gap tick vs skip timestamp. I messaggi P2 (`books not ready`) indicano latenza/assenza order book CLOB — problema secondario non risolto nel meeting.

Esempi round senza ptb (start_ts): 1783379700, 1783380000, 1783380300, 1783380600, 1783380900 — cluster consecutivi compatibili con blocchi FAIL del log principale.

---

## Roadmap implementazione

### Fase 0 — Preparazione (immediata)

- [ ] Verificare parità `src/` repo principale vs snapshot meeting context
- [ ] Scaricare/aggiornare `debug-9c51e0.log` da poly se serve confronto post-fix
- [ ] Baseline conteggi su poly: `done`, `ptb_fail`, `final_fail`, `stall`, `ws error`

### Fase 1 — Logging NDJSON (P1, senza fix funzionale)

Implementare in `feed_chainlink.py`:

| location | message | Campi |
|----------|---------|-------|
| `_on_open` | `ws_open` | `conn_id` |
| `_on_close` | `ws_close` | `code`, `msg`, `last_btc_age_sec` |
| `_ping_loop` | `stall_reconnect` | `stall_sec`, `last_btc_age_sec` |
| `_on_message` | `btc_tick` | `oracle_ts_ms`, `recv_ms`, `gap_sec` |
| `_on_message` | `btc_gap_warn` | se `gap_sec > 15` |
| `_dispatch` | `ptb_skip` | `round`, `oracle_ts_ms`, `market_start_ms`, `skipped_reason` |
| `_dispatch` | `ptb_set` | `lag_ptb_ms` |
| `register` | `prime_chainlink` | `primed_ts_ms`, `primed_stale` |

Env: `BTC5MIN_DEBUG_NDJSON=1`, output `/opt/btc5min/data/chainlink-debug.ndjson`.

**Deploy:** rsync su poly, restart `btc5min.service`.

**Soak 2–4 h** → analizzare pattern:

| Pattern NDJSON | Interpretazione |
|----------------|-----------------|
| `ptb_skip` ripetuto, nessun `btc_gap_warn` | **H5.2** — tick arrivano, timestamp obsoleti |
| `btc_gap_warn` > 45 s senza `ws_close` | **H5.1** — stall detector non funziona (pre-fix) |
| `ws_close` 1001 + batch + `primed_stale` | Reconnect server + dati accumulati |

### Fase 2 — Fix P0 stall in `_ping_loop`

```python
# In _ping_loop, ogni PING_INTERVAL_SEC:
if self._last_msg_ts and time.time() - self._last_msg_ts > STALL_RECONNECT_SEC:
    log.warning("chainlink stall %.0fs, reconnecting", time.time() - self._last_msg_ts)
    self._close_ws(intentional=True)
```

Opzionale nello stesso loop: su eccezione `send("ping")` → log + `_close_ws()` (m-gpt).

### Fase 3 — Fix complementari (dopo validazione P0)

| ID | Fix | Priorità |
|----|-----|----------|
| F3 | Recv-fallback ptb se `recv_ms >= market_start` e ptb None | P2, solo se dibattito risolto |
| F4 | `chainlink_ready()` richiede ptb o tick fresco (age ≤ 10 s) | P3 |
| F5 | Reconnect proattivo ogni 20–30 min | P4, workaround |
| F6 | `_on_close` / `_on_error` con dump età ultimo tick BTC | P5 |

### Fase 4 — Validazione (≥4 h)

| Criterio | Soglia |
|----------|--------|
| Round `done` | ≥ 90–95% attesi |
| `price_to_beat not captured` | 0 (≤1 restart) |
| `chainlink final not captured` | 0 |
| Lag ptb p95 | ≤ 3–5 s, max ≤ 15 s |
| `ptb_skip` su round completati | 0 |
| `verify` su ogni `.bin` | 0 errori bloccanti |

Comando post-run:

```bash
ssh ticksaver 'LOG=/opt/btc5min/data/collector.log
echo "done=$(grep -c \"done [0-9]* seconds\" $LOG) ptb_fail=$(grep -c \"price_to_beat not captured\" $LOG) final_fail=$(grep -c \"chainlink final not captured\" $LOG)"
ls -1 /opt/btc5min/data/btc5m_*.bin | wc -l'
```

### Fase 5 — Escalation (solo se Fase 4 fallisce)

1. Test A/B `firewall=0` su CT 103 per 4 h
2. Soak Windows dev 4 h (stesso codice)
3. Probe parallelo `probe_btc_gaps.py` 3600 s vs collector attivo
4. `probe_oracle_ts.py` (nuovo, m-sonnet) 7200 s
5. VM Debian non-LXC su Proxmox
6. tcpdump + Wireshark su flusso WS

---

## Script e comandi diagnostici (inventario)

### Esistenti in context

| Script | Uso |
|--------|-----|
| `probe_btc_gaps.py` | Gap tick btc/usd; **rieseguire 3600 s** non 600 s |
| `probe_chainlink_ws.py` | Tutti i simboli RTDS; soak 1800–3600 s |
| `diag_ptb.py` | Formato timestamp + cattura ptb al bordo round |

### Proposti, da creare se necessario

| Script | Proponente |
|--------|------------|
| `probe_oracle_ts.py` | m-sonnet |
| `probe_btc_staleness.py` | m-composer |
| `analyze_debug_log.py` | m-composer |
| `diag_stream_btc.py` | m-kimi |
| `diag_h5_btc_stream.py` | m-grok |

### Comandi operativi rapidi

```bash
ssh ticksaver systemctl status btc5min
ssh ticksaver "grep -cE 'done [0-9]+ seconds|price_to_beat not captured|chainlink final not captured|chainlink ws error|chainlink stall' /opt/btc5min/data/collector.log"
ssh ticksaver "cat /opt/btc5min/debug-9c51e0.log" > debug-9c51e0.log
ssh proxmox-root "pct config 103 | grep firewall"
```

---

## Raccomandazioni infra (sintesi)

| Area | Decisione |
|------|-----------|
| **OS** | Mantenere Debian 12 bookworm LXC |
| **Firewall PVE** | Resta `firewall=1`; test A/B opzionale |
| **Rete** | Non modificare `tcp_keepalive_time`; MTU 1500 OK |
| **Python** | 3.12.10 venv; pin `websocket-client` solo se sospetto libreria |
| **Risorse CT** | 2 GB RAM / 6 vCPU sufficienti (nessuna evidenza starvation) |

---

## Completeness critic

Integrazione da `responses/completeness.md`:

**Gap principali:** H5.1 vs H5.2 non distinta senza NDJSON Chainlink; soak test solo 10 min; fix non implementati; script proposti non creati; un solo turno; `books not ready` non approfondito.

**Claim deboli:** probabilità 85–95% su H5.1 senza misura gap tick; meccanismo oracle heartbeat m-sonnet non verificato; recv-fallback ptb senza consenso.

**Angoli non esplorati:** ping send fail zombie; fail-fast N round; race singleton; confronto CT lobsaver; run in periodi bassa volatilità BTC.

---

## Riferimenti file

### Meeting

| Path | Descrizione |
|------|-------------|
| `meetings/bug-poly-collector/meeting.md` | Meta meeting, Punto 01 |
| `meetings/bug-poly-collector/context/baseline.md` | Fatti oggettivi pre-turno 01 |
| `meetings/bug-poly-collector/context/report-bug-0707.md` | Report bug originale |
| `meetings/bug-poly-collector/context/collector-poly.log` | Log produzione ~4 h |
| `meetings/bug-poly-collector/context/examples-poly/*.txt` | 11 round esportati |
| `meetings/bug-poly-collector/context/src/*.py` | Snapshot codice analizzato |
| `meetings/bug-poly-collector/context/scripts/*.py` | Script diagnostici |
| `meetings/bug-poly-collector/responses/report-turn01.md` | Report merge turno 01 |
| `meetings/bug-poly-collector/responses/user-feedback-turn01.md` | Feedback utente |
| `meetings/bug-poly-collector/responses/completeness.md` | Gap critic chiusura |
| `meetings/bug-poly-collector/responses/report-final.md` | Questo documento |

### Risposte partecipanti turno 01

- `responses/response-m-sonnet-turn01.md`
- `responses/response-m-deepseek-turn01.md`
- `responses/response-m-gpt-turn01.md`
- `responses/response-m-gemini-turn01.md`
- `responses/response-m-composer-turn01.md`
- `responses/response-m-glm-turn01.md`
- `responses/response-m-kimi-turn01.md`
- `responses/response-m-grok-turn01.md`
- `responses/response-m-minimax-turn01.md`

### Esterni al meeting

| Path | Descrizione |
|------|-------------|
| `docs/debug-9c51e0.log` | Copia locale debug NDJSON (analisi post-turno) |
| `src/feed_chainlink.py` | Codice produzione (target fix) |
| `/opt/btc5min/` su poly | Deploy produzione |

---

*Meeting chiuso — generato da m-coordinator*
