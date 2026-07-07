# Turno 01 — Diagnosi bug collector `btc5min` su CT poly

## Punto 01 — Analisi delle cause, diagnostica e piano di debug

L’analisi si fonda esclusivamente sui fatti oggettivi riportati in `baseline.md`:
- run di ~4 h su poly → solo **11 round salvati** su ~48 attesi;
- **~34 eventi** `price_to_beat not captured` vs **1 sola** disconnessione RTDS (`Going away`, close 1001);
- **0** `chainlink stall`;
- probe 10 min su Windows e su poly **identici** (579 tick, gap max ~8.3 s, 0 drop): *non* è un problema primario di rete/container/Debian 12;
- il codice scarta `price_to_beat` quando `ts_ms < _ptb_start_ms` e aggiorna `_last_msg_ts` solo su `btc/usd`;
- `prime_chainlink` non imposta `price_to_beat`.

Da questi fatti la causa più probabile è **H5: WebSocket tecnicamente up ma stream BTC/oracle non utilizzabile** per catturare ptb/final. Di seguito tutte le ipotesi, in ordine di probabilità decrescente, con test da eseguire, modifiche di logging, criteri di validazione e raccomandazioni infra/OS.

---

### 1. Ipotesi strutturate

| ID | Ipotesi | Probabilità | Evidenze a favore | Evidenze contro / caveat | Conferma / Test rapido | Fix plausibile |
|---|---|---|---|---|---|---|
| **H5a** | **Timestamp oracle `ts_ms` è in ritardo rispetto al market start del round**. Il primo tick btc/usd ricevuto ha `ts_ms < _ptb_start_ms`, quindi `price_to_beat` non viene impostato per tutta la durata del round (o arriva troppo tardi) | **Alta** | – 17 round consecutivi falliti senza alcun log di reconnect RTDS.<br>– Round parziale con ptb catturato dopo **lag di 222 s**.<br>– Codice esplicito: `if ts_ms < self._ptb_start_ms: return`.<br>– Log con `btc=... ptb=-`: prezzo Chainlink presente ma ptb `None`. | – Richiede conferma sul valore assoluto di `ts_ms` vs `market_start_ms`. | Log NDJSON di ogni tick con `oracle_ts_ms`, `market_start_ms`, `ptb_start_ms`; calcolare ritardo medio/mediano ptb. | Considerare ptb “live” entro una tolleranza (es. tick con ts_ms non troppo antecedente all’inizio round); oppure sincronizzare meglio l’attesa del primo tick valido. |
| **H5b** | **Connessione WS “zombi”: RTDS resta aperta ma smette di spedire `btc/usd` per lunghi tratti**, mentre altri simboli/ping mantengono il canale tecnicamente vivo | **Media-Alta** | – Molti fallimenti e un solo `Going away`.<br>– 0 stall loggati: lo stall detector potrebbe essere aggiornato su altri messaggi (se diverso da baseline) oppure il loop di controllo non funziona. | – Baseline afferma `_last_msg_ts` aggiornato solo su `btc/usd`: se così, uno stallo BTC dovrebbe scattare. | Verificare codice reale di `_last_msg_ts` e dello stall detector; trace raw WS; abilitare log di *tutti* i messaggi ricevuti. | Rilevare stallo in base all’ultimo tick `btc/usd`, non all’ultimo pacchetto WS; forzare reconnect dopo gap > 15–20 s su btc/usd. |
| **H5c** | **`prime_chainlink()` fornisce un valore/timestamp obsoleto ma non imposta ptb**, lasciando il round senza ptb fino all’arrivo (eventuale) di un tick valido | **Media** | – Baseline: `prime_chainlink` non imposta ptb.<br>– Codice: `ts_ms < _ptb_start_ms` scarta anche il tick successivo. | – Non spiega da solo round *consecutivi* senza tick valido. | Aggiungere log in `prime_chainlink` con `last_value`, `last_ts_ms`, `_ptb_start_ms`. | Al register/prime esplicitamente *non* propagare un prezzo obsoleto come “live”; se timestamp antecedente, attendere primo tick valido. |
| **H5d** | **Race condition / stato non thread-safe tra `register()` del nuovo round e `_on_message`/`_dispatch` del WS singleton** | **Media** | – Architettura sync+thread con round che si sovrappongono ogni 5 min.<br>– `feed_chainlink.py` singleton condiviso tra round.<br>– Fallimenti in cluster potrebbero coincidere con boundary round. | – Il run stato ptb perdurante per minuti non è tipico di una race passeggera. | Review sorgente `feed_chainlink.py` e `round_state.py` per lock/queue; strace/thread dump durante round fallito. | Proteggere `register`/`apply_chainlink`/`prime_chainlink` con un lock; usare `queue.Queue` per l’handoff WS→round. |
| **H5e** | **Finestra di cattura del final price troppo stretta** rispetto ai gap reali del feed oracle | **Media** | – 2 eventi `chainlink final not captured`.<br>– H5a implica timestamp con lag variabile. | – Solo 2 final falliti vs 34 ptb; non è il problema principale ma può essere correlato. | Log della window `_final_end_ms` e del timestamp del tick final. | Allargare finestra finale ≥ 15–30 s o accettare l’ultimo tick disponibile entro la scadenza reale. |
| **H5f** | **Bug/regressione in `websocket-client` o nella build Python 3.12 su Debian 12** (es. reconnect silenzioso, mancata dispatch) | **Bassa-Media** | – Python 3.12.10 compilato manualmente su poly.<br>– `websocket-client 1.9.0`. | – Windows con stesso Python/pacchetti non mostra problemi (ma run troppo breve). | Downgrade/upgrade `websocket-client`; test con libreria alternativa (`websockets`); trace esteso. | Aggiornare a versione stabile; valutare sostituzione libreria se il bug è confermato. |
| **H5g** | **Stateful firewall PVE / conntrack su bridge `vmbr0` droppa/fluscona connessioni long-lived** | **Bassa** | – `firewall=1` sulla veth di CT 103.<br>– 5 `clob ws drop` (altro feed, ma sintomo simile LAN-side). | – Probe 10 min OK, zero drop RTDS; tick frequenti mantengono vivo il flusso. | Disabilitare temporaneamente il firewall di CT 103 e ri-run collector per ≥ 1 h. | Disabilitare firewall CT se il test risolve; altrimenti regolare timeout conntrack. |
| **H5h** | **Risoluzione IPv6 / TLS handshake si blocca silenziosamente o produce connessioni zombi** | **Bassa** | – Container Debian, rete LAN pass-through Fritz.box; IPv6 potenzialmente presente. | – Probe funziona, quindi la connessione iniziale riesce. | Forzare IPv4 vs IPv6 dal container; `curl -4`/`-6` verso endpoint RTDS. | Forzare IPv4 nel codice o nel resolver se IPv6 è instabile. |
| **H5i** | **Resource exhaustion / GC pause / CPU throttling nel CT** | **Molto bassa** | – CT ha 2 GB RAM, 6 vCPU; Python overhead ridotto. | – Log non mostra OOM, CPU ~13 min su 4 h, uso RAM ~36 MB. | Monitoraggio `vmstat`, `dmesg`, `journalctl`, `python -m tracemalloc`. | Aumentare RAM/CPU solo se emergono evidenze. |
| **H1–H4** | Container/rete LXC, Debian 12 TCP stack, disconnect frequenti server, NAT/router LAN | **Rifiutate / inconclusive** | – Probe 10 min identico Windows/poly. | – Non spiegano il cluster di ptb persi senza reconnect. | Già eseguiti con esito negativo. | Non richiedono azione come causa primaria; H4 merita ulteriore test con firewall off. |

---

### 2. Comandi/script di diagnostica

Eseguire **direttamente su poly** (via alias `ticksaver`) o, dove indicato, sull’host Proxmox per cattura pacchetti.

#### 2.1 Stato servizio e log rapido
```bash
# Stato
ssh ticksaver systemctl status btc5min --no-pager

# Coda log
ssh ticksaver tail -f /opt/btc5min/data/collector.log
ssh ticksaver journalctl -u btc5min -f

# Conteggio eventi nel run corrente
ssh ticksaver "grep -cE 'done [0-9]+ seconds|price_to_beat not captured|chainlink final not captured|chainlink ws error|chainlink stall|ws drop' /opt/btc5min/data/collector.log"
```

#### 2.2 Trace raw della WebSocket RTDS (non invasivo)
In `src/feed_chainlink.py`, subito dopo la creazione del `WebSocketApp`:
```python
import websocket as ws_sdk
ws_sdk.enableTrace(True)  # logga ogni frame WS su stderr
```
e ridirigere stderr su file dedicato aggiungendo al service:
```ini
StandardError=append:/opt/btc5min/data/ws-trace.log
```
oppure avviare manualmente in foreground:
```bash
ssh ticksaver "cd /opt/btc5min && venv/bin/python3 -m src.main 2>/opt/btc5min/data/ws-trace.log"
```

#### 2.3 Script diagnostico `scripts/diag_stream_btc.py` (da aggiungere)
```python
#!/usr/bin/env python3
"""
probe RTDS btc/usd che logga, per ogni tick:
- oracle_ts_ms
- recv_ts_ms
- gap dall'ultimo tick
- differenza recv_ts_ms - oracle_ts_ms
- l'eventuale skew di clock
"""
import time, json, websocket

WS_URL = "wss://..."  # endpoint RTDS reale del progetto

def on_msg(ws, msg):
    now_ms = int(time.time() * 1000)
    data = json.loads(msg)
    # adattare chiavi reali usate da Polymarket RTDS
    symbol = data.get("ticker") or data.get("symbol")
    if symbol == "btc/usd":
        ts = data.get("time", 0)
        payload = {
            "event": "btc_tick",
            "oracle_ts_ms": ts,
            "recv_ms": now_ms,
            "recv_minus_oracle_ms": now_ms - ts,
            "price": data.get("price"),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        }
        print(json.dumps(payload), flush=True)

if __name__ == "__main__":
    ws = websocket.WebSocketApp(WS_URL, on_message=on_msg)
    ws.run_forever(ping_interval=5, ping_payload="ping")
```
Eseguire su poly per **30–60 min** (non 10 min) e confrontare con run su Windows:
```bash
scp scripts/diag_stream_btc.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/diag_stream_btc.py" > rtds_poly.jsonl
# idem su Windows
```

#### 2.4 Cattura pacchetti sull’host Proxmox
```bash
ssh proxmox-root "tcpdump -i vmbr0 -n -s0 -w /tmp/rtds_poly.pcap host <HOST_O_IP_RTD_SERVER>"
# dopo 30 min scaricare e analizzare con Wireshark / tshark
tshark -r /tmp/rtds_poly.pcap -Y "websocket" -T fields -e frame.time -e websocket.payload.text
```
Serve per verificare se:
- i frame `btc/usd` realmente mancano;
- la connessione riceve ping/pong o altri simboli;
- ci sono RST/FIN anomali dal firewall/conntrack.

#### 2.5 Analisi timestamp oracle vs market start
Aggiungendo log NDJSON (vedi §3), eseguire sul CT:
```bash
ssh ticksaver "cat /opt/btc5min/data/debug_chainlink.jsonl | python3 -c '
import sys, json
for l in sys.stdin:
    d=json.loads(l)
    if d["event"]=="ptb_skip":
        print(d["market_start_ms"]-d["oracle_ts_ms"], "ms di ritardo oracle")
'"
```

#### 2.6 Verifica thread-locked e stall detector
```bash
# Thread dump del processo Python in esecuzione
ssh ticksaver "kill -USR2 \$(pgrep -f 'src.main') 2>/dev/null || py-spy dump --pid \$(pgrep -f 'src.main')"
# Se disponibile py-spy (consigliato installarlo in venv)
ssh ticksaver "/opt/btc5min/venv/bin/py-spy record -d 30 -o /tmp/btc5min.svg --pid \$(pgrep -f 'src.main')"
```

---

### 3. Modifiche di logging suggerite

Creare un **file di debug NDJSON separato** (es. `/opt/btc5min/data/debug_chainlink.jsonl`) ruotato giornalmente, senza toccare il log leggibile principale.

#### 3.1 In `src/feed_chainlink.py`

| Punto | Log da emettere (NDJSON) |
|---|---|
| `_on_open` | `event: ws_open`, `ts_open`, `subscribe_sent`, `endpoint` |
| `_on_message` per `btc/usd` | `event: btc_tick`, `symbol`, `oracle_ts_ms`, `recv_ms`, `gap_ms` (dall’ultimo btc_tick), `price`, `latency_ms = recv_ms - oracle_ts_ms` |
| `_on_message` per altri simboli/pong | `event: ws_msg_non_btc`, `symbol`, `recv_ms` — per valutare H5b |
| `_on_close` | `event: ws_close`, `code`, `reason`, `uptime_sec`, `last_btc_msg_age_sec` |
| `_on_error` | `event: ws_error`, `error`, `last_btc_msg_age_sec` |
| `_close_ws` | `event: ws_close_intentional`, `reason` (`stall`, `stop`, `error`) |
| `_run` branch stall | `event: stall_check`, `last_msg_ts`, `now`, `age_sec`, `triggered: true/false` |
| `_ping_loop` fail | `event: ping_fail`, `exception` |
| `_dispatch` ai round | `event: dispatch`, `round_id`, `oracle_ts_ms`, `market_start_ms`, `ptb_start_ms`, `ptb_set`, `skipped_reason` |

> **Importante**: se `_last_msg_ts` è effettivamente aggiornato solo su `btc/usd`, verificarlo; se invece lo stall detector misura l’ultimo messaggio **qualsiasi**, aggiungere un secondo timer `_last_btc_msg_ts` dedicato.

#### 3.2 In `src/round_state.py`

| Punto | Log da emettere |
|---|---|
| `prime_chainlink` | `event: prime`, `value`, `last_ts_ms`, `_ptb_start_ms`, `is_valid_for_ptb` |
| `apply_chainlink` ptb skip | `event: ptb_skip`, `oracle_ts_ms`, `_ptb_start_ms`, `reason: ts_ms < ptb_start` |
| `apply_chainlink` ptb set | `event: ptb_set`, `lag_ptb_ms = oracle_ts_ms - _ptb_start_ms`, `price` |
| `apply_chainlink` final set/skip | `event: final_set` / `final_skip`, `oracle_ts_ms`, `_final_end_ms`, `reason` |

#### 3.3 In `src/round_runner.py`

| Punto | Log da emettere |
|---|---|
| round start | `event: round_start`, `market_start_ms`, `ptb_start_ms`, `final_end_ms` |
| sampler first tick | `event: sampler_first_tick`, `ptb_ready: bool`, `chainlink_price` |
| round end OK | `event: round_done`, `round_id`, `duration_sec`, `ticks_count` |
| round end FAIL | `event: round_failed`, `reason: ptb/final/other`, `chainlink_ts_ms`, `price_to_beat`, `_ptb_start_ms`, `_final_end_ms` |

#### 3.4 Flushing e rotazione
- Abilitare `flush=True` su ogni scrittura NDJSON (`print(..., flush=True)`).
- Log NDJSON su file separato per non interferire con `collector.log`.
- Configurare `logrotate` giornaliero su `/opt/btc5min/data/debug_chainlink.jsonl`.

---

### 4. Criteri di validazione del fix

1. **Metrica principale**: eseguire un run di **almeno 4 ore consecutive** su poly e contare:
   - round `done` / round falliti per ptb / round falliti per final;
   - tasso di successo globale ≥ **95%** e nessun cluster ≥ 3 round consecutivi persi.

2. **Lag ptb accettabile**: ogni ptb deve essere catturato entro **≤ 15 s** dall’inizio round (`market_start_ms`). Eventi sporadici fino a 30 s vanno loggati ma non devono ripetersi.

3. **Gap BTC**: nel log NDJSON non devono esistere gap `btc/usd` > **15 s** senza corrispondente `stall_check` → reconnect entro **10 s**.

4. **Final price**: tutti i round devono catturare il final entro la finestra prevista; nessun `chainlink final not captured`.

5. **Stabilità WS**: eventi `ws_close` devono essere sporadici (< 1/h) e ognuno deve essere seguito da reconnect entro 10 s; nessun periodo > 60 s senza `btc/usd` valido.

6. **Confronto dev**: ripetere un run lungo (≥ 2 h) anche su Windows 11 dev con la stessa versione del codice per escludere un difetto OS-specifico.

7. **Reproducibilità**: eseguire **3 run** consecutivi di ≥ 2 h ciascuno dopo il fix; tutti devono soddisfare i criteri sopra.

---

### 5. Raccomandazioni infra/OS

#### 5.1 Non cambiare OS (a meno di evidenze nuove)
I probe escludono Debian 12 / LXC / kernel Proxmox come causa primaria. Cambiare OS (es. Ubuntu 24.04, Alpine, Windows) **non risolve H5** e introduce variabili:
- `websocket-client` si comporta allo stesso modo su Linux;
- Python 3.12 compilato manualmente è un rischio noto, ma non ha prodotto errori di sintesi/runtime (`py_compile` OK).

**Eccezione**: se si decide di re-creare il CT, si può usare **Ubuntu 24.04 LTS** per avere Python 3.12.x dai repo ufficiali, riducendo il rischio di artefatti da build manuale. Questo è un *miglioramento operativo*, non una fix del bug.

#### 5.2 Disabilitare temporaneamente il firewall PVE del CT
Il CT è in LAN sicura; vale la pena escludere il firewall stateful come variabile. Da host Proxmox:
```bash
# Vedere config attuale
ssh proxmox-root "pct config 103"

# Rimuovere flag firewall dalla scheda di rete
ssh proxmox-root "pct set 103 -net0 name=eth0,bridge=vmbr0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth"
```
Poi riavviare il CT e monitorare un run di ≥ 1 h. Se il bug persiste, il firewall non è la causa; se scompare, indagare timeout conntrack o regole PVE.

#### 5.3 Regolazioni TCP keepalive (solo se firewall/conntrack sospetto)
Se il test con firewall off non cambia nulla, **non applicare**. Altrimenti impostare sull’host Proxmox (kernel condiviso):
```bash
# /etc/sysctl.d/99-poly-keepalive.conf
net.ipv4.tcp_keepalive_time=60
net.ipv4.tcp_keepalive_intvl=10
net.ipv4.tcp_keepalive_probes=6
```
e ricaricare con `sysctl --system`. Nel codice, abilitare `SO_KEEPALIVE` sul socket se `websocket-client` lo supporta.

#### 5.4 Verificare rete e DNS
```bash
ssh ticksaver "cat /etc/resolv.conf; ip -4 a; ip -6 a; ip r"
ssh ticksaver "curl -4 -I https://gamma-api.polymarket.com"
ssh ticksaver "curl -6 -I https://gamma-api.polymarket.com"   # se fallisce, IPv6 è instabile
```
Se IPv6 è problematico, forzare IPv4 nel resolver o nel codice.

#### 5.5 Evitare conflitti di rete
- Verificare che nessun altro CT/VM sul bridge `vmbr0` abbia IP `10.1.1.73` o lo stesso MAC.
- Confermare che CT 104 `lobsaver` non interferisca (stesso bridge ma IP diverso, nessun conflitto atteso).

#### 5.6 Monitoraggio risorse
```bash
ssh ticksaver "df -h /opt/btc5min; free -m; uptime; cat /proc/loadavg"
ssh ticksaver "dmesg | tail -20"
```

---

### 6. Piano d’azione riassuntivo consigliato

1. **Subito**: abilitare log NDJSON descritti in §3 e rilanciare il collector.
2. **In parallelo**: eseguire `diag_stream_btc.py` su poly per 30–60 min per misurare skew/oracle gap.
3. **Validare H5a/H5b**: analizzare i log NDJSON; se `ts_ms` è sistematicamente indietro rispetto a `market_start_ms`, agire su logica ptb; se invece `btc/usd` manca pur essendo la connessione up, agire sullo stall detector.
4. **Test firewall**: disabilitare `firewall=1` su CT 103 per un run di ≥ 1 h; se non cambia nulla, riabilitarlo.
5. **Fix applicativo** basato sui dati: probabilmente unione di (a) stall detector sensibile a `btc/usd` e (b) gestione ptb con tick “live” entro una tolleranza sensata.
6. **Validazione**: 3 run ≥ 2 h con tasso successo ≥ 95%, ptb entro 15 s, final sempre catturato.
7. **Solo se necessario**: re-creare CT con Ubuntu 24.04 LTS per Python 3.12 da pacchetto, replicando la stessa validazione.

---

**Prossimo deliverable richiesto**: implementazione dei log NDJSON e degli script diagnostici, esecuzione di almeno un run di 30–60 min su poly, e report con i dati grezzi emersi.