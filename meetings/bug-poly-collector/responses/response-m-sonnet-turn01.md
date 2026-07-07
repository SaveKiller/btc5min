# Response m-sonnet — Turno 01
**meeting-id**: bug-poly-collector  
**agente**: m-sonnet  
**turno**: 01  
**data**: 2026-07-07

---

## Punto 01

### Premessa metodologica

Ho analizzato in dettaglio: `report-bug-0707.md`, `baseline.md`, tutti i sorgenti in `src/`, il log di produzione `collector-poly.log` (394 righe, ~4h), il log dev `collector-dev.log`, gli 11 round `.txt` da poly, e i 3 script diagnostici. Quello che segue è basato esclusivamente su evidenze nei file disponibili, non su supposizioni generiche.

---

### 1. Analisi del pattern di fallimento nel log

Dalla lettura integrale di `collector-poly.log` emergono **tre blocchi** distinti:

| Blocco | Intervallo UTC | Round | Esito |
|--------|----------------|-------|-------|
| A (OK) | 22:38–23:10 | 1783377600–1783379100 | 6 round `done` |
| B (FAIL) | 23:10–00:38 | 1783379400–1783384500 | 18 round falliti |
| C (OK parziale) | 00:38–01:05 | 1783384500–1783385700 | 1 parziale + 4 `done` |
| D (FAIL) | 01:05–02:38 | 1783386000–1783391700 | ~20+ round falliti |
| E (parziale in log) | 02:38 | 1783391700 | ptb lag=226s (log tronco) |

Ogni blocco FAIL termina con un evento `chainlink ws error: fin=1 opcode=8 data=b'\x03\xe9Going away'` (code 1001 = server-side close volontario). Il blocco FAIL B dura ~83 minuti, il blocco FAIL D ~93 minuti. I due blocchi OK iniziali (A, C) hanno in comune: sono i primissimi round dopo un (re)connect WS.

**Pattern di transizione blocco OK→FAIL**: il primo round a fallire in ogni blocco FAIL non è sempre `ptb not captured` ma può essere `final not captured` (round 1783379400 e 1783386000). Questo è un indizio diagnostico cruciale (vedi H8).

---

### 2. Ipotesi strutturate

#### H6 — Stall detector architetturalmente inutile durante `run_forever()` — **Probabilità: 95%**

**Evidenze**:
- 18 round consecutivi falliti senza UN SOLO log `chainlink stall` né `chainlink ws error`
- La WS rimane connessa per ~83 e ~93 minuti durante i fallimenti
- Zero occorrenze di `chainlink stall` in tutto il log di 4 ore

**Meccanismo esatto** (codice `feed_chainlink.py`):

```python
def _run(self) -> None:
    while not self._stop.is_set():
        # ← stall check SOLO QUI (outer loop)
        if self._last_msg_ts and time.time() - self._last_msg_ts > STALL_RECONNECT_SEC:
            self._close_ws(intentional=True)
        try:
            self._run_once()   # ← BLOCCA qui per ore
```

```python
def _run_once(self) -> None:
    self._ws = websocket.WebSocketApp(...)
    while not self._stop.is_set():
        self._intentional_close = False
        self._ws.run_forever(ping_interval=None)  # ← BLOCKING per tutta la durata connessione
        if self._stop.is_set() or self._intentional_close:
            return
```

`_run_once()` contiene un inner loop con `run_forever()` bloccante. Quando la WS è connessa, l'esecuzione è ferma su `run_forever()`. Lo stall check nell'outer loop di `_run()` **non viene mai eseguito** durante la vita di una connessione attiva. Viene eseguito **solo** tra una `_run_once()` e la successiva, cioè dopo una disconnessione. In pratica: il codice dello stall detector è strutturalmente dead code per connessioni long-lived.

**Controprova**: se lo stall detector funzionasse, vedremmo `chainlink stall` nei log entro 45s dal freeze del feed BTC. Non lo vediamo mai.

**Nota critica**: `_close_ws(intentional=True)` è chiamato dallo stall check, e **funzionerebbe** se lo stall check girasse. Chiama `_ws.close()` che farebbe uscire `run_forever()` e poi `_run_once()` restituirebbe perché `_intentional_close=True`. Il problema è solo che lo stall check non gira durante la connessione.

---

#### H7 — Oracle Chainlink emette timestamp stale (stessa `updatedAt` per periodi lunghi) — **Probabilità: 85%**

**Evidenze**:
- Il SAMPLE mostra `btc=63985.15 ptb=-` alle 01:45 UTC: `chainlink_price` è valorizzato (oracle sta inviando qualcosa o `prime_chainlink` ha settato il valore), ma `price_to_beat` rimane None
- Dopo il reconnect `Going away` a 00:38:39, il ptb viene catturato con **lag=222s**: questo significa che l'oracle ha inviato un batch con timestamp `ts_ms ≥ market_start_ms(1783384500)`, ma la prima occorrenza valida ha lag di 222 secondi dall'inizio del round (il round era già a 3:42 di percorso). Questo è compatibile con: l'oracle ha accumulato N rounds in 83 minuti, e il primo round con timestamp ≥ 1783384500000 era quello con lag=222s.
- La logica `apply_chainlink` in `round_state.py`:
  ```python
  if ts_ms < self._ptb_start_ms: return  # skip se oracle ts < market start
  ```
  Se il Chainlink oracle su Polygon non posta un nuovo round per 83+ minuti (nessuna deviazione >0.5% o heartbeat 3600s non ancora scattato), tutti i messaggi btc/usd del RTDS riportano lo stesso `updatedAt` (timestamp dell'ultimo round oracle postato on-chain). Questo valore è fisso e inevitabilmente inferiore a `market_start_ts * 1000` per tutti i round successivi.

**Meccanismo Chainlink**: su Polygon, il feed BTC/USD di Chainlink ha:
- **Deviation threshold**: 0.5% (posta un nuovo round se il prezzo si muove >0.5% dall'ultimo valore)
- **Heartbeat**: 3600 secondi (posta al massimo ogni ora se non ci sono deviazioni)

Se BTC rimane in un range stretto per >5 minuti (plausibile), l'oracle non posta un nuovo round. Il RTDS continua a emettere messaggi btc/usd con l'ultimo `roundId` e il suo `updatedAt` (fisso). `chainlink_price` si aggiorna (stesso valore o lieve variazione), `_last_msg_ts` si aggiorna → stall non scatta (o non scatterebbe neanche se funzionasse, finché arrivano messaggi). Ma `ts_ms` è costante e stale → tutti i round falliscono.

**Sottovariante B**: il RTDS smette completamente di inviare btc/usd quando l'oracle è quiescente. In questo caso `chainlink_price` resta al valore di `prime_chainlink`, e `_last_msg_ts` non si aggiorna → stall sarebbe rilevante se funzionasse.

Entrambe le sottovarianti portano agli stessi sintomi e allo stesso fix.

---

#### H8 — Guard `ts_ms < _ptb_start_ms` troppo restrittivo; nessun recv-fallback per ptb — **Probabilità: 80%**

**Evidenze**:
- `final_chainlink` ha un recv-fallback (`recv_ms >= _final_end_ms`) che lo cattura anche se l'oracle ts è stale
- `price_to_beat` **non ha** un recv-fallback equivalente: se `ts_ms < _ptb_start_ms`, il ptb non viene mai impostato indipendentemente da quanto a lungo si aspetti
- Il round 1783379400 riesce a catturare ptb (perché l'oracle ha postato un round con `ts_ms == 1783379400000` esattamente). Ma il round successivo (1783379700) fallisce perché l'oracle non ha postato un round con `ts_ms >= 1783379700000`.
- Il "chainlink final not captured" per round 1783379400 e 1783386000 ha la stessa causa: ptb era stato catturato (oracle ts valido per quel round), ma il `final_chainlink` richiede `ts_ms >= market_end_ts * 1000` — che non arriva perché l'oracle non ha postato oltre quel timestamp. Il recv-fallback **esiste** ma richiede che `apply_chainlink` venga chiamato con `recv_ms >= _final_end_ms`, cioè che arrivi UN messaggio oracle DOPO la scadenza del round. Se l'oracle è completamente silenzioso, nemmeno questo trigger viene attivato.

**Semantica corretta del ptb**: se l'oracle non ha postato un nuovo round dal momento T < market_start_ts, il prezzo oracle AL momento di market_start_ts è esattamente il prezzo del round T. Usarlo come `price_to_beat` è semanticamente corretto! La guard `ts_ms < _ptb_start_ms` è quindi troppo conservativa: scarta dati validi per ragioni di freshness che non si applicano quando l'oracle ha heartbeat lungo.

---

#### H5 — WS connessa ma stream BTC inutilizzabile — **CONFIRMED (come da report)** — **Probabilità: 95%**

Questa è la sintesi dei symptomi visibili, spiegata meccanicamente da H6+H7+H8 combinati.

---

#### H4 — NAT/router Fritz.box droppa connessioni long-lived — **Probabilità: 25%**

**Evidenze a favore**:
- 5 `clob ws drop` nel log (CLOB usa WS per-round, più brevi; i drop sono per round diversi → potrebbero essere timeout NAT dopo 2-3 minuti di inattività CLOB)
- Il Fritz.box ha tipicamente un timeout per TCP/TLS idle di 3-5 minuti; connessioni WS senza traffico per >180s potrebbero essere droppate

**Evidenze contro**:
- L'app invia `"ping"` testuale ogni 5s su RTDS → il NAT vede traffico costante → improbabile timeout NAT su RTDS
- CLOB riceve già `ping_interval=30, ping_timeout=10` via websocket-client → ping WS ogni 30s, dovrebbe mantenere viva anche la connessione CLOB
- I probe 10min non hanno mostrato drop

**Valutazione**: H4 spiega i drop CLOB meglio che i problemi Chainlink. Per RTDS (con ping ogni 5s) è quasi certamente non applicabile.

---

#### H_new9 — Overlap round: dispatch a round multipli con ts stale — **Probabilità: 60% (conseguenza, non causa)**

In `_dispatch`, tutti i round registrati ricevono ogni oracle tick. Se l'oracle ts è stale (< market_start_ts del round più recente), il round più vecchio (ancora dentro il suo window) potrebbe ricevere ptb, ma il round più recente no. Questo spiega la transizione OK→FAIL: l'ultimo round prima del freeze oracle riesce perché la sua `_ptb_start_ms` coincide con l'ultimo oracle timestamp valido. Il successivo già no.

---

#### H_new10 — `_run_once` backoff post-`Going away` — **Probabilità: 5%**

Dopo il `Going away` a 00:38:39, il ptb per 1783384500 è catturato alle 00:38:43 (4 secondi dopo). Questo indica che il reconnect è quasi istantaneo, compatibile con `_backoff_sec = 2.0` (reset all'inizio di `_run_once()`). Non è una causa di problemi significativi.

---

#### H_new11 — Problema `ts_to_ms` con timestamp oracle in formato millisecondo — **Probabilità: 10%**

`ts_to_ms(ts)` applica `*1000` se `ts < 10_000_000_000`. L'epoch attuale (luglio 2026) è ~1.78×10⁹ secondi << 10^10, quindi la detection è corretta. Tuttavia: se in futuro (anno 2286) l'epoch supera 10^10 la funzione si rompe — non rilevante ora. Nessun edge case attuale identificato.

---

### 3. Fix proposti e criteri di validazione

#### Fix F1 — Stall detector nel ping loop (priorità ALTA)

**File**: `src/feed_chainlink.py` — `_ping_loop`

Il fix sposta il controllo stall dentro il ping loop, che gira durante la connessione attiva:

```python
def _ping_loop(self) -> None:
    while not self._ping_stop.is_set() and not self._stop.is_set():
        if self._ws:
            try: self._ws.send("ping")
            except Exception: return
        if self._last_msg_ts and time.time() - self._last_msg_ts > STALL_RECONNECT_SEC:
            log.warning("chainlink stall %.0fs in ping loop, forcing reconnect",
                        time.time() - self._last_msg_ts)
            self._close_ws(intentional=True)
            return
        time.sleep(PING_INTERVAL_SEC)
```

Il loop gira ogni `PING_INTERVAL_SEC=5s`. Se per 45s non arrivano messaggi btc/usd, chiude la WS (`intentional=True`), `run_forever()` esce, `_run_once()` ritorna, l'outer `_run()` ri-chiama `_run_once()` che crea una nuova connessione e riceve il batch aggiornato.

**Criterio validazione F1**: dopo deploy, nel log devono comparire occorrenze di `chainlink stall ... in ping loop, forcing reconnect` durante i periodi di oracle quiet. I round successivi al reconnect devono catturare ptb con lag basso. Zero `chainlink price_to_beat not captured` su run 2h+.

---

#### Fix F2 — Recv-fallback per ptb in `apply_chainlink` (priorità MEDIA)

**File**: `src/round_state.py`

```python
def apply_chainlink(self, value: float, ts_ms: int, recv_ms: int) -> None:
    with self.lock:
        self.chainlink_price = value
        self.chainlink_ts_ms = ts_ms
        if ts_ms >= self._ptb_start_ms:
            if self._ptb_ts_ms is None or ts_ms < self._ptb_ts_ms:
                self._ptb_ts_ms = ts_ms
                self.price_to_beat = value
        elif recv_ms >= self._ptb_start_ms and self._ptb_ts_ms is None:
            # oracle ts stale ma wall clock siamo già nel round: usa come ptb
            self._ptb_ts_ms = ts_ms
            self.price_to_beat = value
        if ts_ms >= self._final_end_ms:
            ...  # invariato
```

Questo è un safety net per i casi in cui F1 non scatta abbastanza velocemente. Semanticamente corretto: se l'oracle non ha postato dopo `market_start_ts`, l'ultimo prezzo disponibile IS il prezzo al market start.

**Criterio validazione F2**: con solo F2 (senza F1), i round non falliscono più con ptb, ma il lag del ptb potrebbe essere alto (es. 222s come nel caso osservato). Con F1+F2, il lag ptb dovrebbe essere basso (<5s) grazie al reconnect tempestivo.

---

#### Fix F3 — Logging aggiuntivo per diagnosi oracle freshness (priorità ALTA per diagnostica)

**File**: `src/feed_chainlink.py` — `_on_message`/`_dispatch`

```python
def _on_message(self, ws, raw: str) -> None:
    ...
    self._last_msg_ts = time.time()
    prev_ts = self._last_ts_ms  # salva prima del dispatch
    ...

def _dispatch(self, value: float, ts_ms: int, rounds: list[RoundState]) -> None:
    recv_ms = int(time.time() * 1000)
    gap_oracle_sec = (ts_ms - (self._last_ts_ms or ts_ms)) / 1000.0
    if abs(gap_oracle_sec) < 0.001:  # stessa ts → oracle silenzioso
        log.debug("chainlink oracle ts unchanged: ts_ms=%d value=%.2f", ts_ms, value)
    elif gap_oracle_sec < 0:
        log.warning("chainlink oracle ts backward: gap=%.1fs ts_ms=%d", gap_oracle_sec, ts_ms)
    self._last_value = value
    self._last_ts_ms = ts_ms
    for state in rounds:
        if state.chainlink_done.is_set(): continue
        ptb_before = state.price_to_beat
        state.apply_chainlink(value, ts_ms, recv_ms)
        if ptb_before is None and state.price_to_beat is None:
            ptb_skip_delta = (state._ptb_start_ms - ts_ms) / 1000.0
            log.debug("chainlink ptb skip: round=%d ts_ms=%d ptb_start_ms=%d delta=+%.1fs",
                      state.start_ts, ts_ms, state._ptb_start_ms, ptb_skip_delta)
```

In `_ping_loop`, loggare l'età del last btc/usd ogni minuto:
```python
# in _ping_loop, ogni ~12 iterazioni (60s):
if self._last_msg_ts:
    age = time.time() - self._last_msg_ts
    if age > 10:
        log.info("chainlink last_btc_msg_age=%.1fs", age)
```

**Cosa cerca questo logging**: 
- `oracle ts unchanged` → conferma H7 (oracle silenzioso, ripete stesso ts)
- `oracle ts backward` → anomalia batch replay
- `ptb skip delta` → mostra di quanti secondi l'oracle è indietro rispetto al market start
- `last_btc_msg_age` → mostra quando il feed si ferma

---

#### Fix F4 — Logging eventi WS (diagnosi H6 e H4)

**File**: `src/feed_chainlink.py`

```python
def _on_open(self, ws) -> None:
    log.info("chainlink ws open, subscribing")
    ...

def _on_close(self, ws, close_status_code, close_msg) -> None:
    age_sec = time.time() - (self._last_msg_ts or 0)
    log.info("chainlink ws close: code=%s msg=%s last_btc_age=%.1fs intentional=%s",
             close_status_code, close_msg, age_sec, self._intentional_close)

def _on_error(self, ws, error) -> None:
    if self._intentional_close or self._stop.is_set(): return
    log.warning("chainlink ws error: %s", error)
```

`_on_close` attualmente fa `pass`. Loggarla è essenziale per distinguere close intenzionali da drop.

---

### 4. Script diagnostici

#### Script D1 — Probe oracle ts freshness (2h+)

Da deployare su poly per confermare H7. Registra ogni btc/usd ricevuto con ts e verifica se l'oracle ts avanza.

```python
#!/usr/bin/env python3
"""Probe oracle timestamp freshness. Run 2+ hours on poly to catch quiet periods."""
import json, time, threading, sys
import websocket

RTDS = "wss://ws-live-data.polymarket.com"
events = []
last_oracle_ts_ms = None
conn_t0 = None

def on_open(ws):
    global conn_t0
    conn_t0 = time.time()
    ws.send(json.dumps({
        "action": "subscribe",
        "subscriptions": [{"topic": "crypto_prices_chainlink", "type": "*", "filters": ""}],
    }))
    def ping():
        while True:
            time.sleep(5)
            try: ws.send("ping")
            except: return
    threading.Thread(target=ping, daemon=True).start()

def on_message(ws, raw):
    global last_oracle_ts_ms
    if not raw or raw.upper() == "PONG": return
    try: msg = json.loads(raw)
    except: return
    p = msg.get("payload") or {}
    if p.get("symbol") != "btc/usd": return
    now = time.time()
    if "value" in p:
        ts_ms = int(p["timestamp"]) * 1000 if int(p["timestamp"]) < 10_000_000_000 else int(p["timestamp"])
        oracle_age = now - ts_ms / 1000.0
        oracle_delta = ts_ms - last_oracle_ts_ms if last_oracle_ts_ms else 0
        events.append({"t": round(now - conn_t0, 1), "ts_ms": ts_ms, "val": p["value"],
                       "oracle_age_s": round(oracle_age, 1), "oracle_delta_ms": oracle_delta})
        if oracle_age > 60:
            print(f"[{round(now-conn_t0,0)}s] STALE oracle ts: age={oracle_age:.0f}s val={p['value']}")
        last_oracle_ts_ms = ts_ms
    elif "data" in p:
        pts = p["data"]
        print(f"[{round(now-conn_t0,0)}s] BATCH {len(pts)} points, "
              f"first_ts={pts[0]['timestamp']}, last_ts={pts[-1]['timestamp']}")

def on_close(ws, code, msg):
    print(f"[{round(time.time()-conn_t0,0)}s] CLOSE code={code} msg={msg}")

def on_error(ws, err):
    print(f"[{round(time.time()-conn_t0,0)}s] ERROR {err}")

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 7200
ws = websocket.WebSocketApp(RTDS, on_open=on_open, on_message=on_message,
                             on_close=on_close, on_error=on_error)
threading.Thread(target=lambda: ws.run_forever(ping_interval=None), daemon=True).start()
t_start = time.time()
try:
    while time.time() - t_start < duration:
        time.sleep(30)
        stale = [e for e in events[-100:] if e.get("oracle_age_s", 0) > 60]
        same_ts = [e for e in events[-20:] if e.get("oracle_delta_ms", 1) == 0]
        print(f"[{round(time.time()-t_start,0)}s] total={len(events)} stale_recent={len(stale)} same_ts={len(same_ts)}")
finally:
    ws.close()
    import json as _j
    with open("/tmp/oracle_probe.json", "w") as f:
        _j.dump(events[-500:], f, indent=2)
    print(f"Saved {min(500, len(events))} events to /tmp/oracle_probe.json")
```

Deploy su poly:
```bash
scp meetings/bug-poly-collector/context/scripts/probe_oracle_ts.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/probe_oracle_ts.py 7200"
```

**Cosa cercare**: quando compaiono `STALE oracle ts: age=NNs` → conferma H7. Se age > 5 minuti → certezza. Se appaiono `BATCH` multipli in rapida successione dopo una riconnessione → conferma che il batch post-reconnect contiene gli oracle rounds accumulati.

---

#### Script D2 — Analisi del `debug-9c51e0.log` su poly

Il log NDJSON (~138KB) esiste su `/opt/btc5min/debug-9c51e0.log`. Analizzarlo per pattern ptb:

```bash
ssh ticksaver "python3 -c \"
import json, sys
with open('/opt/btc5min/debug-9c51e0.log') as f:
    lines = [json.loads(l) for l in f if l.strip()]
ptb = [l for l in lines if l.get('message') == 'ptb captured']
first = [l for l in lines if l.get('message') == 'first sample']
print('PTB captured:', len(ptb))
print('First samples:', len(first))
for p in ptb[-5:]:
    print('  ptb:', p.get('data',{}).get('start_ts'), 'lag:', p.get('data',{}).get('lag_ptb_sec'))
\""
```

Cercare: round con `ptb_ready: false` nel `first sample` → conferma che ptb non era pronto al primo sample.

---

#### Script D3 — Estrazione gap oracle dal log esistente

Verifica del pattern di timestamp oracle nel `debug-9c51e0.log`:

```bash
ssh ticksaver "python3 -c \"
import json
events = []
with open('/opt/btc5min/debug-9c51e0.log') as f:
    for line in f:
        try:
            d = json.loads(line)
            if 'oracle_ts_ms' in str(d):
                events.append(d)
        except: pass
print(f'Total events with oracle_ts_ms: {len(events)}')
# Cerca eventi con ts stale
for e in events[:20]:
    print(json.dumps(e.get('data', {}), default=str)[:200])
\""
```

---

#### Script D4 — Verifica comandi su poly (diagnostica rapida stato attuale)

```bash
# Stato attuale servizio
ssh ticksaver systemctl status btc5min

# Conteggio errori run corrente
ssh ticksaver "grep -cE 'price_to_beat not captured|final not captured|chainlink ws error|done [0-9]+ seconds' /opt/btc5min/data/collector.log"

# Ultimi 20 round
ssh ticksaver "tail -40 /opt/btc5min/data/collector.log"

# Verifica firewall CT (su proxmox host)
ssh proxmox-root "pct config 103 | grep net0"

# Verifica nf_conntrack da dentro CT
ssh ticksaver "cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo 'conntrack non disponibile'"

# TCP keepalive attuale
ssh ticksaver "sysctl net.ipv4.tcp_keepalive_time net.ipv4.tcp_keepalive_intvl net.ipv4.tcp_keepalive_probes"

# Verifica che il log debug sia ancora in crescita
ssh ticksaver "wc -l /opt/btc5min/debug-9c51e0.log && ls -lh /opt/btc5min/debug-9c51e0.log"
```

---

#### Script D5 — Modifica temporanea per logging diagnostico senza fix funzionale

Patch minimale da applicare su poly per raccogliere dati nel prossimo run senza alterare il comportamento:

```python
# In feed_chainlink.py, _ping_loop:
def _ping_loop(self) -> None:
    _iter = 0
    while not self._ping_stop.is_set() and not self._stop.is_set():
        if self._ws:
            try: self._ws.send("ping")
            except Exception: return
        _iter += 1
        if _iter % 12 == 0:  # ogni ~60s
            if self._last_msg_ts:
                age = time.time() - self._last_msg_ts
                log.info("chainlink heartbeat: last_btc_age=%.1fs last_ts_ms=%s",
                         age, self._last_ts_ms)
        time.sleep(PING_INTERVAL_SEC)

# In _on_message, dopo self._last_msg_ts = time.time():
#   Loggare se ts_ms non avanza:
#   (aggiungere nei _dispatch):
#   if self._last_ts_ms and ts_ms <= self._last_ts_ms:
#       log.info("chainlink oracle ts stale: new=%d prev=%d delta=%d",
#                ts_ms, self._last_ts_ms, ts_ms - self._last_ts_ms)
```

---

### 5. Criteri di validazione del fix completo

Il fix è validato **solo** se soddisfa TUTTI questi criteri su poly con run ≥ 2h:

| Criterio | Threshold | Metodo |
|----------|-----------|--------|
| Round completati | ≥ 90% dei round attesi (≥ 22/24 su 2h) | `grep -c 'done [0-9]+ seconds' collector.log` |
| Assenza `ptb not captured` su run completo | 0 occorrenze (o ≤ 1 per restart service) | `grep -c 'price_to_beat not captured' collector.log` |
| Stall detector si attiva | ≥ 1 log `chainlink stall` per ora in condizioni oracle quiet | Verificare durante periodo di bassa volatilità BTC |
| Lag ptb post-reconnect | ≤ 60s (con F1), ≤ 300s (con solo F2) | `grep 'price_to_beat.*lag=' collector.log` |
| Nessun blocco FAIL lungo | Nessun periodo >10min senza `done` (esclusi restart service) | Analisi visiva log |

**Run di validazione minimo raccomandato**: 4-6 ore in orario UTC notturno (bassa volatilità BTC, maggiore probabilità di oracle quiet period).

**Non validare** con probe 10min o con run in orario ad alta volatilità (oracle aggiorna frequentemente, bug non si manifesta).

---

### 6. Raccomandazioni infrastruttura e OS

#### 6.1 Firewall PVE CT 103 — Raccomandazione: DISABILITARE

**Stato attuale**: `firewall=1` nella config del CT (`net0: ...,firewall=1,...`)

**Rischio del firewall**: il firewall PVE è basato su iptables/nftables con conntrack. Per default consente tutto l'outbound, ma il tracking delle connessioni TCP long-lived (WS attivi per 80-90 minuti) potrebbe avere side effect in LXC unprivileged in edge case. Anche se H4 è poco probabile come causa principale, il firewall in una LAN sicura (dietro Fritz.box) non aggiunge sicurezza e può avere effetti collaterali non documentati su WS long-lived.

**Come disabilitare**:
```bash
# Su proxmox host
ssh proxmox-root "pct stop 103 && sed -i 's/,firewall=1//' /etc/pve/lxc/103.conf && pct start 103"
# Verifica
ssh proxmox-root "pct config 103 | grep net0"
```
Oppure via UI Proxmox: CT 103 → Network → eth0 → deseleziona Firewall.

**Rischio operazione**: basso. Il CT è in LAN chiusa con Fritz.box come outer firewall.

---

#### 6.2 OS del container — Raccomandazione: mantenere Debian 12 LXC

**Motivazione**: il bug è applicativo (H6+H7+H8), non OS-dipendente. I probe hanno escluso H1 e H2 con certezza. Cambiare OS aggiungerebbe lavoro senza affrontare la causa reale.

**Se si vuole semplificare la gestione Python**: Ubuntu 24.04 LTS include Python 3.12 come pacchetto ufficiale (`apt install python3.12`), eliminando la necessità del build da sorgente. Questo NON è un fix del bug ma una semplificazione operativa per futuri re-deploy.

Se si vuole migrare:
```bash
# Opzione: Ubuntu 24.04 LXC template su Proxmox
# vantaggi: python3.12 in apt, python3.12-venv in apt
# svantaggi: migrazione, re-validazione deploy
```
Raccomandazione: se si procede con il fix applicativo (F1+F2), rimandare la valutazione del cambio OS ad un momento più tranquillo. Non è bloccante.

---

#### 6.3 Rete OS — Raccomandazione: TCP keepalive (opzionale, bassa priorità)

**Stato attuale**: `tcp_keepalive_time=7200` (default kernel).

Con i ping applicativi ogni 5s, il TCP keepalive del kernel è irrilevante. Tuttavia, per belt-and-suspenders:
```bash
ssh ticksaver "sysctl -w net.ipv4.tcp_keepalive_time=300 net.ipv4.tcp_keepalive_intvl=30 net.ipv4.tcp_keepalive_probes=5"
# Per rendere persistente:
echo -e "net.ipv4.tcp_keepalive_time=300\nnet.ipv4.tcp_keepalive_intvl=30\nnet.ipv4.tcp_keepalive_probes=5" >> /etc/sysctl.conf
```

**Effetto atteso**: nessuno sull'attuale bug, ma utile se in futuro si disabilitasse il ping applicativo.

---

#### 6.4 Sistemd e restart policy — Raccomandazione: OK, nessuna modifica

`Restart=always` e `RestartSec=5` sono configurazioni corrette. Il restart automatico gestisce crash/eccezioni non catturate. Non modificare.

---

### 7. Riepilogo priorità di intervento

| Priorità | Fix | Impatto atteso | Rischio |
|----------|-----|----------------|---------|
| 1 (CRITICA) | F1: stall detector nel ping loop | Elimina i blocchi FAIL di 80-90 min | Basso — logica ben localizzata |
| 2 (IMPORTANTE) | F3: logging oracle ts + ws events | Conferma H7 e misura impatto stall | Zero (solo log) |
| 3 (COMPLEMENTARE) | F2: recv-fallback ptb | Safety net se F1 non scatta in tempo | Basso — logica già presente per final |
| 4 (INFRA) | Disabilitare firewall CT 103 | Elimina H4, semplifica debug futuro | Molto basso |
| 5 (OPZIONALE) | F4: logging _on_close / _on_open | Migliore visibilità su reconnect | Zero |

**Percorso raccomandato**:
1. Deploy F3 (solo logging) → run 2h su poly → analisi `debug-9c51e0.log` e nuovo `collector.log` → **conferma H7**
2. Deploy F1 → run 4h → validazione con criteri sezione 5
3. Deploy F2 come safety net
4. Disabilitare firewall CT 103 (operazione separata, non urgente per il bug)

Se si vuole andare diretti alla soluzione senza la fase diagnostica intermedia (H7 già sufficientemente probabile dalle evidenze attuali), si può deployare F1+F2+F3 insieme e validare direttamente.
