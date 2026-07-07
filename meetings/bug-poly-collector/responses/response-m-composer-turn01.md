# Risposta m-composer — turno 01

- **meeting-id**: bug-poly-collector
- **agent**: m-composer
- **turno**: 01
- **generated_utc**: 2026-07-07T10:05:00Z

---

## Punto 01 — Diagnosi bug collector poly

### Sintesi esecutiva

Il run di ~4 h su poly (baseline: 11 `done` su ~48 round attesi, ~34 fallimenti `price_to_beat`, 2 `final`) non è spiegabile da container/rete/Debian (H1–H2 **rejected** dai probe 10 min identici Windows↔poly) né da disconnect frequenti RTDS (H3 **rejected**: 1 solo `Going away` 1001). La causa principale sospetta resta **H5**: WebSocket RTDS apparentemente viva ma stream `btc/usd` non utilizzabile — sia per **assenza di tick** (stall detector cieco ai non-BTC) sia per **timestamp oracle obsoleti** che `apply_chainlink` scarta silenziosamente (`ts_ms < market_start`).

**Raccomandazione prioritaria:** fix applicativo (stall su assenza tick BTC + logging NDJSON strutturato) **prima** di qualsiasi cambio OS/firewall. Cambio OS o disattivazione firewall ha probabilità bassa di risolvere il problema e va trattato come test di esclusione, non come fix primario.

---

### 1. Ipotesi strutturate (probabilità ed evidenze)

| ID | Ipotesi | Prob. | Stato | Evidenze a favore | Evidenze contro / gap |
|----|---------|-------|-------|-------------------|----------------------|
| **H5** | WS up ma stream BTC inutilizzabile (tick assenti o timestamp non validi per ptb/final) | **Alta (70%)** | Confermata (report) | ~17 round consecutivi falliti **senza** `chainlink ws error` né `chainlink stall`; sampler con `btc=... ptb=-`; dopo reconnect ptb con lag 222 s; `_last_msg_ts` aggiornato solo su `btc/usd` ma stall conta qualsiasi msg — in realtà stall=0 implica che **nessun** msg btc/usd per 45 s non è stato rilevato come stall perché forse arrivano PONG o altri simboli? (vedi H5a/H5b) | Serve NDJSON su `debug-9c51e0.log` (138 KB su server, non in context) per distinguere gap tick vs skip timestamp |
| **H5a** | Tick BTC assenti a lungo ma WS viva (PONG/ping, altri topic) → stall non scatta | **Alta (55%)** | Sottocaso H5 | `STALL_RECONNECT_SEC=45` ma `_last_msg_ts` solo su btc/usd: se **nessun** tick BTC per >45 s dovrebbe scattare stall — **ma stall=0 nel log**. Quindi o i tick BTC arrivano spesso (<45 s) ma con `ts_ms < market_start`, oppure c'è un bug nel loop `_run` (stall check prima di `_run_once` ma `_last_msg_ts` non aggiornato se solo PONG) | PONG non aggiorna `_last_msg_ts` → se **zero** tick BTC per >45 s, stall **dovrebbe** scattare. Stall=0 suggerisce più probabile **H5b** |
| **H5b** | Tick BTC arrivano ma con `oracle_ts_ms < market_start_ms` per tutto il round | **Alta (60%)** | Sottocaso H5 | `prime_chainlink` imposta `chainlink_price` senza ptb; `chainlink_ready()` true → sampler logga `btc=` ma ptb resta `None`; dopo reconnect batch storico con timestamp vecchi (lag 222 s nel round parziale) | `diag_ptb.py` in context verifica formato; manca correlazione round-fallito ↔ skip reason |
| **H5c** | Dopo reconnect, burst di tick batch ordinati ma tutti pre-market_start per il round corrente | **Media (40%)** | Sottocaso H5 | `_on_message` ordina batch per timestamp; se oracle in ritardo di minuti, tutti i punti potrebbero essere `< _ptb_start_ms` fino a quando oracle non supera market_start | Round 1783384500: ptb catturato a 00:38:43 per market_start 00:35:00 |
| **H6** | Final non catturato: nessun tick con `ts_ms >= market_end` entro `FINAL_WAIT_SEC=30` | **Media (35%)** | Parziale | 2 round `final not captured` (1783379400, 1783386000); logica final richiede oracle timestamp ≥ fine mercato | Stesso meccanismo H5b applicato a `_final_end_ms` |
| **H7** | Race/overlap round: più `RoundState` registrati, tick dispatchati a round sbagliato o `chainlink_done` prematuro | **Bassa (15%)** | Aperta | Fino a 2 round sovrapposti (spawn T-10s, durata 300s); singleton feed con lista `_rounds` | Codice filtra `chainlink_done`; nessuna evidenza diretta nel log |
| **H8** | `chainlink_ready()` da `prime_chainlink` maschera assenza ptb → round campiona secondi senza ptb valido | **Media (30%)** | Aperta | Sampler richiede solo `chainlink_ready()`, non `price_to_beat`; log SAMPLE `ptb=-` con `btc=` valorizzato | Comportamento by-design ma contribuisce al falso senso di "feed OK" |
| **H4** | NAT Fritz.box (10.1.1.1) droppa connessioni long-lived | **Bassa (20%)** | Inconclusa | 5 `clob ws drop`; probe 10 min OK | RTDS ha traffico ~1 Hz; un solo disconnect Chainlink in 4 h |
| **H9** | Firewall PVE sul CT (`firewall=1`) filtra traffico WS intermittente | **Bassa (10%)** | Aperta | Config `pct config 103` ha `firewall=1` | Probe 10 min identico a Windows sulla stessa LAN; ping/TCP OK |
| **H10** | Thread starvation / carico host Proxmox | **Bassa (10%)** | Aperta | 6 vCPU allocati, host con altri CT | CPU collector ~13 min/4 h; RAM 36 MB app |
| **H11** | Bug `websocket-client` + Python 3.12.10 compilato (non pacchetto Debian) | **Bassa (15%)** | Aperta | Runtime custom `/usr/local/bin/python3.12` | Stessa versione 3.12.10 su Windows dev; probe OK |
| **H12** | Cambio OS (es. Ubuntu/Windows VM) risolve il problema | **Molto bassa (5%)** | Sconsigliata come prima azione | — | H1/H2 rejected; kernel guest = host PVE; problema long-run non riprodotto in probe brevi su nessuna macchina |

**Ordine di investigazione consigliato:** H5b → H5a → H5c → H6 → H8 → (H4/H9 come test infra paralleli a basso costo).

---

### 2. Meccanismo codice (ancorato a baseline)

Tre punti critici concatenati:

1. **`feed_chainlink.py`**: `_last_msg_ts` aggiornato solo su messaggi `payload.symbol == "btc/usd"`. PONG e altri topic ignorati. Lo stall check in `_run()` confronta `time.time() - _last_msg_ts` — **corretto per assenza tick BTC**, ma nel log **zero** eventi `chainlink stall` implica che o i tick BTC arrivano almeno ogni 45 s (ma inutilizzabili), o c'è un percorso che resetta `_last_msg_ts` senza produrre ptb (improbabile).

2. **`round_state.py`**: `if ts_ms < self._ptb_start_ms: return` — tick visibili in `chainlink_price` ma ptb mai impostato.

3. **`round_runner.py`**: `SamplerThread` parte se `chainlink_ready()` (solo prezzo, non ptb) → falsi positivi operativi.

Il round parziale `btc5m_1783384500.txt` (260 tick, ptb lag 222 s) prova che **dopo** il `Going away` il feed torna utile ma troppo tardi per un round completo.

---

### 3. Script e comandi di diagnostica

#### 3.1 Script già in context (da rieseguire/estendere)

| Script | Comando su poly | Scopo |
|--------|-----------------|-------|
| `probe_btc_gaps.py` | `ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/probe_btc_gaps.py 3600"` | Soak **60 min** (non 10): gap BTC, eventi close/error |
| `probe_chainlink_ws.py` | idem 3600 s | Tutti i simboli/topic — verifica se arrivano msg non-BTC quando BTC fermo |
| `diag_ptb.py` | `cd /opt/btc5min && venv/bin/python3 scripts/diag_ptb.py` | Formato timestamp live vs batch + test cattura ptb al bordo round |

#### 3.2 Script nuovi proposti

**A. `scripts/probe_btc_staleness.py`** — correlazione tick ricevuti vs `market_start` simulato

```python
"""Per ogni tick btc/usd logga: recv_ts, oracle_ts_ms, delta_recv-oracle, flag stale se oracle_ts < floor(recv_ts - 60s)."""
# Eseguire 30-60 min in parallelo al collector (seconda istanza su porta diversa o stop servizio brevemente)
# Output: CSV o NDJSON su stdout
```

**B. `scripts/analyze_debug_log.py`** — parser per `/opt/btc5min/debug-9c51e0.log`

```bash
ssh ticksaver "venv/bin/python3 -c \"
import json, sys
from collections import Counter
c = Counter()
for line in open('/opt/btc5min/debug-9c51e0.log'):
    o=json.loads(line); c[o.get('message','')]+=1
print(c.most_common(20))
\""
```

**C. `scripts/correlate_collector_log.py`** — incrocia `collector.log` con round spawn/fail

```bash
ssh ticksaver "grep -E 'spawn|sampling started|price_to_beat|failed|chainlink ws|chainlink stall|done ' /opt/btc5min/data/collector.log"
```

#### 3.3 Comandi infra/rete (esclusione H4/H9/H10)

```bash
# Firewall CT — stato regole PVE
ssh proxmox-root "pct config 103 | grep firewall"
ssh proxmox-root "iptables -L -n -v"   # sul host, se accessibile

# Disabilitare firewall CT (test, reversibile)
ssh proxmox-root "pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth"

# TCP/long connection
ssh ticksaver "sysctl net.ipv4.tcp_keepalive_time net.ipv4.tcp_keepalive_intvl net.core.somaxconn"
ssh ticksaver "ss -tn state established '( dport = :443 )'"

# Confronto probe da host Proxmox (esclude veth CT)
ssh proxmox-root "python3 /tmp/probe_btc_gaps.py 600"   # dopo scp script

# Traceroute / MTU
ssh ticksaver "ip link show eth0; ping -c 3 -M do -s 1472 8.8.8.8"

# Risorse durante run
ssh ticksaver "free -h; ps aux --sort=-%cpu | head -5; uptime"
```

#### 3.4 Test A/B raccomandati

| Test | Durata | Setup | Metrica successo esclusione |
|------|--------|-------|----------------------------|
| Soak probe BTC | 60 min | poly, servizio **fermo** | 0 disconnect; gap max < 15 s; tick ≥ 3400 |
| Soak collector con NDJSON | 60 min | poly, patch logging | `done` ≥ 11/12 round; ptb fail ≤ 1 |
| Firewall off | 60 min | `firewall=0` + collector | Nessun miglioramento vs baseline → H9 rejected |
| Windows long-run | 4 h | PC dev, stesso codice | Se fallisce ugualmente → conferma bug app, non infra |

---

### 4. Logging NDJSON suggerito

Estendere il pattern già presente in `round_runner.py` (`debug-9c51e0.log`) a `feed_chainlink.py`. Un unico file rotabile: `/opt/btc5min/data/chainlink-debug.ndjson` (max 50 MB, rotate).

#### 4.1 Eventi obbligatori

| location | message | data (campi chiave) |
|----------|---------|---------------------|
| `feed_chainlink._on_open` | `ws_open` | `conn_id`, `subscribe_sent` |
| `feed_chainlink._on_close` | `ws_close` | `code`, `msg`, `connected_sec`, `last_btc_age_sec` |
| `feed_chainlink._on_error` | `ws_error` | `error`, `intentional_close` |
| `feed_chainlink._run` | `stall_reconnect` | `stall_sec`, `last_btc_age_sec` |
| `feed_chainlink._on_message` | `btc_tick` | `oracle_ts_ms`, `recv_ms`, `value`, `gap_since_last_btc_sec` (ogni tick; **sample** ogni 10 s se volume alto) |
| `feed_chainlink._on_message` | `btc_gap_warn` | se `gap_since_last_btc_sec > 15` |
| `feed_chainlink._dispatch` | `ptb_skip` | `round_start_ts`, `oracle_ts_ms`, `market_start_ms`, `delta_ms`, `skipped_reason` |
| `feed_chainlink._dispatch` | `ptb_set` | `round_start_ts`, `oracle_ts_ms`, `lag_ptb_ms`, `value` |
| `feed_chainlink.register` | `prime_chainlink` | `round_start_ts`, `primed_ts_ms`, `market_start_ms`, `primed_stale` (bool) |
| `round_runner._run_round` | `round_fail` | `start_ts`, `chainlink_price`, `chainlink_ts_ms`, `ptb`, `final`, `_ptb_start_ms`, `_final_end_ms` |

#### 4.2 Schema NDJSON (esempio)

```json
{
  "ts": 1783388700123,
  "location": "feed_chainlink._dispatch",
  "message": "ptb_skip",
  "hypothesisId": "H5b",
  "data": {
    "round": 1783388700,
    "oracle_ts_ms": 1783388699000,
    "market_start_ms": 1783388700000,
    "value": 63985.15,
    "skipped_reason": "ts_ms_lt_market_start",
    "recv_ms": 1783388700450
  }
}
```

#### 4.3 Implementazione minima (senza dipendenze)

```python
# src/debug_ndjson.py — helper condiviso
def dbg(location, message, data, hypothesis_id="H5"):
    with open(DEBUG_PATH, "a") as f:
        f.write(json.dumps({"ts": int(time.time()*1000), "location": location,
            "message": message, "hypothesisId": hypothesis_id, "data": data}) + "\n")
```

Attivazione via env `BTC5MIN_DEBUG_NDJSON=1` per non impattare produzione dopo il fix.

#### 4.4 Pattern attesi post-deploy logging

| Pattern nel NDJSON | Interpretazione |
|--------------------|-----------------|
| `ptb_skip` ripetuto per 300 s su stesso round | **H5b confermata** |
| `btc_gap_warn` > 45 s senza `ws_close` | **H5a** — stall detector non sufficiente (o non in esecuzione) |
| `ws_close` code 1001 sporadico + `primed_stale: true` | **H5c** — batch post-reconnect |
| `ptb_set` presente ma `round_fail` su final | **H6** — problema finestra final |
| Nessun `ptb_skip`, gap normali, fail comunque | Investigare H7/H11 |

---

### 5. Direzioni di fix (da validare con log, non implementare nel meeting)

1. **Stall su assenza tick BTC**: tracciare `_last_btc_msg_ts` separato da eventuali altri messaggi; reconnect se `now - _last_btc_msg_ts > 30` (soglia < 45 per margine).

2. **Non considerare `chainlink_ready()` sufficiente**: sampler attende `price_to_beat is not None` oppure timeout esplicito con log.

3. **`prime_chainlink`**: non impostare `chainlink_price` se `ts_ms < market_start_ms`; loggare `primed_stale`.

4. **Fallback ptb controllato**: se a T+30 s dal market_start non c'è ptb oracle-valido, forzare reconnect WS (non usare prezzo stale come ptb senza flag).

5. **Final**: estendere `FINAL_WAIT_SEC` solo se NDJSON mostra tick in arrivo ma con lag oracle; altrimenti reconnect.

6. **Rimuovere/condizionare** `debug-9c51e0.log` hardcoded in `round_runner.py` → path configurabile.

---

### 6. Criteri di validazione fix

#### 6.1 Criteri funzionali (obbligatori)

| Criterio | Soglia | Durata test |
|----------|--------|-------------|
| Round completati (`done ... 300 seconds`) | **≥ 95%** dei round attesi | **≥ 4 h** consecutive |
| Fallimenti `price_to_beat not captured` | **≤ 1** per 4 h | 4 h |
| Fallimenti `chainlink final not captured` | **0** | 4 h |
| `verify` su ogni `.bin` prodotto | 0 errori bloccanti | per round |
| Lag ptb (`lag=` nel log) | **< 5 s** nel p95 | 4 h |

#### 6.2 Criteri diagnostici (conferma root cause)

| Criterio | Atteso dopo fix H5 |
|----------|-------------------|
| Eventi `ptb_skip` nel NDJSON | **0** per round completati |
| `chainlink stall` o `stall_reconnect` | Presenti solo se gap BTC reale; seguiti da ptb entro 10 s |
| `btc_gap_warn` | Nessuno > 30 s senza reconnect |

#### 6.3 Criteri infra (se si testa firewall/OS)

| Test | Esito che esclude infra |
|------|-------------------------|
| `firewall=0` per 4 h | Stesso tasso fail → ripristinare firewall=1 |
| Nuovo CT Ubuntu 24.04 | Stesso tasso fail → problema app |
| VM Windows su Proxmox 4 h | Stesso tasso fail → conferma app |

#### 6.4 Comando verifica rapida post-run

```bash
ssh ticksaver '
  LOG=/opt/btc5min/data/collector.log
  DONE=$(grep -c "done .* seconds" $LOG)
  PTB_FAIL=$(grep -c "price_to_beat not captured" $LOG)
  FINAL_FAIL=$(grep -c "chainlink final not captured" $LOG)
  echo "done=$DONE ptb_fail=$PTB_FAIL final_fail=$FINAL_FAIL"
  ls -1 /opt/btc5min/data/btc5m_*.bin 2>/dev/null | wc -l
'
```

---

### 7. Raccomandazioni infra / OS / firewall / rete

#### 7.1 Debian 12 LXC unprivileged — **mantenere**

- Probe identici Windows↔poly escludono Debian/container come causa primaria.
- Il CT è adeguato (2 GB RAM, 6 core, ZFS, UTC).
- **Non** migrare a Windows: non adatto a servizio 24/7 headless già validato su lobsaver (CT 104, stesso pattern).
- **Non** prioritizzare Ubuntu/Alpine: stesso kernel PVE, stesso bridge `vmbr0`; costo migrazione alto, beneficio atteso nullo.

#### 7.2 Firewall PVE (`firewall=1`) — **test opzionale, non prima azione**

- LAN `10.1.1.0/24` considerata sicura dall'utente; disabilitazione accettabile **solo come test A/B** per 1 run da 4 h.
- Procedura: `pct set 103 ... firewall=0` → soak → confronto metriche → ripristino.
- Se probe 10 min e TCP 443 OK, probabilità impatto **bassa**.

#### 7.3 Rete

- Gateway Fritz.box (H4): possibile contributo ai `clob ws drop` (5 eventi), **non** alla maggioranza fail ptb senza disconnect Chainlink.
- **Non** modificare `tcp_keepalive_time` kernel (7200 s): il collector usa ping applicativo ogni 5 s.
- Verificare assenza doppio NAT o policy guest WiFi se il CT fosse spostato; attualmente IP statico su `vmbr0` è corretto.
- MTU 1500 standard; test `ping -M do -s 1472` per escludere fragmentation black hole.

#### 7.4 Proxmox / risorse

- Config attuale sufficiente; monitorare durante soak: `pct exec 103 -- free -h`.
- CT 104 `lobsaver` running sulla stessa LAN — nessun conflitto IP/porta; utile come riferimento deploy systemd, non come causa.
- **Nesting=1** non rilevante per websocket outbound.

#### 7.5 Python 3.12.10 compilato

- Mantenere parità con dev; alternativa futura: pacchetto backport Debian se rebuild diventa oneroso — **non** correlato al bug.

---

### 8. Obiezioni e rischi del piano

1. **Probe 10 min insufficienti** (già noto nel report): qualsiasi conclusione infra va validata con soak ≥ 60 min; idem per il fix.

2. **Interpretare `btc=... ptb=-` come feed OK è fuorviante** (H8): i log SAMPLE non devono guidare la diagnosi senza NDJSON su skip ptb.

3. **Cambio OS prematuro** maschera il tempo sul fix applicativo e introduce variabili (systemd, path Python, rsync).

4. **Disabilitare firewall senza documentare** rischia di lasciare CT aperto se si dimentica il ripristino — annotare in checklist deploy.

5. **`debug-9c51e0.log` esiste già sul server** (~138 KB): **scaricarlo e analizzarlo** prima di nuovo deploy è a costo zero e potrebbe confermare H5b senza attendere nuove patch.

---

### 9. Checklist operativa per agente implementatore

1. [ ] Scaricare `ssh ticksaver:/opt/btc5min/debug-9c51e0.log` e analizzare messaggi `ptb_skip` / `first sample`
2. [ ] Eseguire `probe_btc_gaps.py 3600` su poly (servizio fermo)
3. [ ] Implementare NDJSON in `feed_chainlink.py` (tabella §4.1)
4. [ ] Deploy su poly, restart `btc5min`, soak 4 h
5. [ ] Valutare metriche §6.1
6. [ ] Se fail persiste senza `ptb_skip`: test `firewall=0` (§7.2)
7. [ ] Implementare fix §5 solo dopo evidenza NDJSON

---

*Fine risposta turno 01 — m-composer*
