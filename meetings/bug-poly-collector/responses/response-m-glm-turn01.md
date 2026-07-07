# Diagnosi bug-poly-collector — Turno 01

## Punto 01

### Analisi del contesto

Dalla lettura di `report-bug-0707.md`, `baseline.md` e tutto il materiale in `context/`, il quadro è il seguente:

- **Run ~4h**, ~48 round attesi, **11 salvati** (10 completi + 1 parziale)
- **68 occorrenze** di `price_to_beat not captured` (~34 eventi fallimento ptb)
- **4 occorrenze** di `chainlink final not captured` (~2 eventi fallimento final)
- **1 solo** evento `chainlink ws error` (close 1001 `Going away`)
- **6** `ws drop` (CLOB, non Chainlink)
- **0** `chainlink stall`
- Il feed WS Chainlink risulta "connesso" per quasi tutto il run, ma i tick BTC/oracle non producono `price_to_beat` utilizzabile
- Lo stall detector aggiorna `_last_msg_ts` **solo** su messaggi `btc/usd`, ma non scatta se la connessione resta viva con altri simboli
- `apply_chainlink` in `round_state.py` fa `return` se `ts_ms < _ptb_start_ms` → ptb resta `None` per tutto il round
- `prime_chainlink` imposta `chainlink_price` ma non `ptb`, creando un falso "prezzo visibile" nei log SAMPLE

---

### Ipotesi strutturate

| ID | Ipotesi | Probabilità | Evidenze |
|----|---------|-------------|----------|
| **H5a** | **Stall detector non scatta su assenza tick BTC**: la WS resta connessa, altri simboli continuano ad arrivare, ma lo stream `btc/usd` si ferma. `_last_msg_ts` non viene aggiornato per BTC, ma il stall check potrebbe non scattare correttamente o la logica di reconnect non si attiva. | **65%** | 17 round consecutivi falliti senza alcun log `chainlink ws error` o `chainlink stall`; `btc=...` presente nei SAMPLE ma `ptb=-`; stall detector filtra solo su `btc/usd` ma il check avviene sul generico `_last_msg_ts` che potrebbe essere aggiornato da altri messaggi o non essere controllato con frequenza sufficiente. |
| **H5b** | **Timestamp oracle retrodatati rispetto a `market_start_ts`**: i tick BTC arrivano con `ts_ms < _ptb_start_ms` (batch storico post-reconnect, ritardo oracle, o dati di "priming" obsoleti). `apply_chainlink` esce senza impostare ptb per tutto il round. | **20%** | Codice `round_state.py`: `if ts_ms < self._ptb_start_ms: return` — skip silenzioso senza log; `prime_chainlink` non imposta ptb ma imposta `chainlink_price` visibile; dopo reconnect `Going away`, ptb catturato con lag oracle 222s (round parziale 260 sec). |
| **H5c** | **WS RTDS cambia subscription/flag internamente**: Polymarket RTDS potrebbe smettere di inviare tick `btc/usd` senza chiudere la connessione (rate limiting, throttling, cambio di canale, sessione stale). La WS è tecnicamente "up" ma il feed BTC è inutilizzabile. | **8%** | Sintomi coerenti con H5a ma la causa è lato server; il probe 10 min non ha mostrato questo comportamento (troppo breve); spiegazione plausibile per "WS up ma BTC fermo". |
| **H4** | **NAT/router LAN droppa connessioni long-lived CLOB**: il Fritz.box potrebbe droppare connessioni WebSocket long-lived dopo un idle timeout, colpendo il CLOB (`ws drop` ×6) ma non il RTDS (traffico ogni ~1s). | **4%** | `ws drop` ×5 nel log CLOB; probe 10 min non ha mostrato drop; INCONCLUSIVE nel report; meno plausibile per RTDS che ha traffico frequente. |
| **H6** | **Bug di concurrency/threading**: race condition tra thread del round corrente e quello successivo (overlap). Il `round_state` viene corrotto o sovrascritto da thread concorrenti, impedendo la cattura di ptb. | **2%** | Architettura sync+thread con overlap round; `feed_chainlink.py` è un singleton condiviso; possibile ma non ci sono evidenze dirette nel log; da non escludere completamente. |
| **H7** | **Firewall PVE interferisce con traffico WebSocket long-lived**: il firewall Proxmox a livello CT (`firewall=1`) potrebbe avere regole di conntrack o timeout che droppano pacchetti su connessioni long-lived, differenziando da Windows (nessun firewall intermedio). | **1%** | H1/H2 rejection basata su probe 10 min, ma il firewall PVE è abilitato; `nf_conntrack_count=0` nel CT; improbabile ma da verificare disabilitando il firewall. |

**Nota su H1/H2/H3 (già rejectate):** concordo con il report. I probe 10 min identici Windows/poly escludono problemi di rete/container/TCP stack come causa primaria. L'unico `Going away` non spiega i ~17 round consecutivi falliti. Tuttavia, **l'assenza di un soak test lungo su Windows** significa che non possiamo escludere completamente un fattore ambientale che si manifesta solo su run lunghi.

---

### Comandi/script di diagnostica

#### 1. Verifica stato attuale del servizio e log

```bash
# Stato servizio
ssh ticksaver systemctl status btc5min

# Ultimi 100 righe di log
ssh ticksaver "tail -100 /opt/btc5min/data/collector.log"

# Conteggi errori correnti
ssh ticksaver "grep -cE 'chainlink ws error|ws drop|price_to_beat not captured|chainlink final not captured| done ' /opt/btc5min/data/collector.log"

# Journal systemd per SAMPLE stderr
ssh ticksaver "journalctl -u btc5min --since '1 hour ago' | tail -200"
```

#### 2. Probe RTDS esteso (30 min) con logging di TUTTI i simboli e timestamp

```bash
# Esegui probe 30 min su poly, loggando tutti i messaggi ricevuti (non solo btc/usd)
# per verificare se la WS resta viva con altri simboli ma BTC si ferma
scp scripts/probe_chainlink_ws.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/probe_chainlink_ws.py 1800 2>&1 | tee /tmp/probe_rtds_30min.log"
```

Se `probe_chainlink_ws.py` non logga già tutti i simboli, modificare temporaneamente per stampare ogni messaggio con simbolo, timestamp oracle, e recv_ts.

#### 3. Probe focalizzato BTC gap esteso (60 min)

```bash
# Probe 1 ora focalizzato su gap tick btc/usd
# per catturare stall del BTC durante run lunghi
scp scripts/probe_btc_gaps.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/probe_btc_gaps.py 3600 2>&1 | tee /tmp/probe_btc_60min.log"
```

#### 4. Ispezione del debug NDJSON log esistente

```bash
# Scarica e analizza il debug log NDJSON esistente su poly
ssh ticksaver "cat /opt/btc5min/debug-9c51e0.log" > /tmp/debug-9c51e0.log

# Analizza: cerca pattern di timestamp oracle vs market_start
grep -i "ptb\|skip\|prime\|market_start\|oracle_ts" /tmp/debug-9c51e0.log | head -100

# Conta eventi di skip ptb nel debug log
grep -c "skip" /tmp/debug-9c51e0.log
```

#### 5. Tcpdump durante un fallimento (cattura traffico WS)

```bash
# Cattura traffico verso Polymarket RTDS per 10 minuti durante un run
ssh ticksaver "timeout 600 tcpdump -i eth0 -w /tmp/rtds_capture.pcap host gamma-api.polymarket.com or port 443" 

# Poi analizza offline con tshark/wireshark per verificare:
# - La connessione TCP è attiva
# - I frame WebSocket continuano ad arrivare
# - Il contenuto dei frame (quali simboli?)
```

#### 6. Verifica timestamp oracle vs market_start

```bash
# Script di test: connetti al RTDS, per ogni tick btc/usd logga:
# - oracle_ts_ms (dal messaggio)
# - recv_ms (time.time() * 1000)
# - current_utc (per confronto con market_start)
# Verifica se oracle_ts_ms è retrodatato rispetto all'ora attuale

cat > /tmp/diag_timestamps.py << 'EOF'
import time, json, websocket, threading

WS_URL = "wss://attestation.news/chat"
# (sostituire con URL reale RTDS Polymarket dal codice)

def on_message(ws, msg):
    recv_ms = int(time.time() * 1000)
    try:
        data = json.loads(msg)
        symbol = data.get("symbol", "?")
        ts_ms = data.get("timestamp", data.get("ts", 0))
        if symbol == "btc/usd" or "btc" in str(symbol).lower():
            lag = recv_ms - ts_ms if ts_ms else 0
            print(f"[{time.strftime('%H:%M:%S')}] symbol={symbol} oracle_ts={ts_ms} recv_ms={recv_ms} lag_ms={lag}")
            if lag > 5000:
                print(f"  WARNING: oracle timestamp retrodated by {lag}ms")
    except:
        pass

def on_error(ws, err):
    print(f"[{time.strftime('%H:%M:%S')}] WS ERROR: {err}")

def on_close(ws, code, msg):
    print(f"[{time.strftime('%H:%M:%S')}] WS CLOSED: code={code} msg={msg}")

def on_open(ws):
    print(f"[{time.strftime('%H:%M:%S')}] WS OPENED")
    # Invia subscribe (adattare al formato reale)
    ws.send(json.dumps({"type": "subscribe", "channel": "btc/usd"}))

ws = websocket.WebSocketApp(WS_URL, on_message=on_message, on_error=on_error, on_close=on_close, on_open=on_open)
ws.run_forever(ping_interval=5, ping_timeout=3)
EOF

scp /tmp/diag_timestamps.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/diag_timestamps.py 2>&1 | tee /tmp/diag_ts.log"
```

#### 7. Verifica configurazione di rete e firewall del CT

```bash
# Config CT dal nodo Proxmox
ssh proxmox-root "pct config 103"

# Stato firewall PVE
ssh proxmox-root "pct config 103 | grep firewall"

# Regole firewall PVE a livello datacenter/nodo
ssh proxmox-root "cat /etc/pve/firewall/cluster.fw 2>/dev/null || echo 'no cluster.fw'"
ssh proxmox-root "cat /etc/pve/lxc/103.fw 2>/dev/null || echo 'no CT firewall rules'"

# Verifica connettività TCP verso RTDS
ssh ticksaver "timeout 10 bash -c 'echo | openssl s_client -connect gamma-api.polymarket.com:443 2>&1 | head -20'"

# Verifica MTU e path MTU discovery
ssh ticksaver "ip link show eth0"
ssh ticksaver "ip addr show eth0"

# Verifica routing
ssh ticksaver "ip route"
ssh ticksaver "cat /etc/resolv.conf"

# Verifica che non ci siano processi in conflitto sulla stessa porta/connessione
ssh ticksaver "ss -tnp | grep 443"
ssh ticksaver "netstat -tnp 2>/dev/null | grep 443 || ss -tnp | grep 443"
```

#### 8. Test con firewall PVE disabilitato

```bash
# Sul nodo Proxmox, disabilitare firewall per CT 103
ssh proxmox-root "pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth"

# Riavviare il CT per applicare
ssh proxmox-root "pct reboot 103"

# Dopo reboot, verificare e fare un run di test
ssh ticksaver "systemctl restart btc5min"
ssh ticksaver "tail -f /opt/btc5min/data/collector.log"
```

#### 9. Soak test lungo su Windows dev (per confronto)

```powershell
# Sul PC dev Windows, eseguire il collector per almeno 1-2 ore
# per verificare se il bug si manifesta anche lì
cd F:\btc5min
.\.venv\Scripts\python.exe -m src.main
# Lasciare girare 1-2 ore, controllare quanti round vengono salvati
# e se ci sono errori price_to_beat not captured
```

#### 10. Verifica memoria e leak

```bash
# Monitorare uso memoria durante il run
ssh ticksaver "free -h"
ssh ticksaver "ps aux | grep python"
ssh ticksaver "cat /proc/$(pgrep -f 'src.main')/status | grep -i vm"

# Se possibile, installare memory_profiler
ssh ticksaver "/opt/btc5min/venv/bin/pip install memory_profiler"
# Aggiungere @profile装饰器 temporaneo o usare mprof
```

---

### Modifiche di logging suggerite

Le modifiche vanno implementate in `src/feed_chainlink.py` e `src/round_state.py` con formato NDJSON strutturato, da scrivere in un file di debug separato (es. `/opt/btc5min/data/debug.log`).

#### In `src/feed_chainlink.py`

| # | Punto | Cosa loggare | Formato |
|---|-------|--------------|---------|
| 1 | `_on_open` | `conn_open_ts`, subscribe inviato, URL | `{"location":"feed_chainlink._on_open","data":{"conn_open_ts":...,"subscribe":...}}` |
| 2 | `_on_close` | `close_status_code`, `close_msg`, `intentional_close`, `connected_sec`, `last_btc_msg_age_sec`, `last_any_msg_age_sec` | NDJSON |
| 3 | `_on_error` | `error` (str), `intentional_close`, `last_btc_msg_age_sec`, `last_any_msg_age_sec` | NDJSON |
| 4 | `_close_ws` | `intentional` (bool), `reason` (stall/stop/error), `last_btc_msg_age_sec` | NDJSON |
| 5 | `_run` (stall check) | **Ogni iterazione del loop di stall check**: `now_ts`, `last_btc_msg_ts`, `last_any_msg_ts`, `btc_age_sec`, `any_age_sec`, `stall_threshold`, `should_reconnect` | NDJSON (questo è il più critico per confermare H5a) |
| 6 | `_on_message` (btc/usd) | Ogni tick: `oracle_ts_ms`, `recv_ms`, `gap_sec` dall'ultimo tick BTC, `value` | NDJSON (o campionato ogni N tick per volume) |
| 7 | `_on_message` (non btc/usd) | Contatore messaggi non-BTC, simboli ricevuti, `recv_ms` (per verificare se la WS è viva con altri simboli) | NDJSON campionato |
| 8 | `_dispatch` | Per round attivo: `round_start_ts`, `oracle_ts_ms`, `market_start_ms`, `ptb_set` (bool), `skipped_reason` se applicabile | NDJSON |
| 9 | `_ping_loop` | Successo/fallimento invio ping, `error` se except | NDJSON |

#### In `src/round_state.py`

| # | Punto | Cosa loggare |
|---|-------|--------------|
| 1 | `apply_chainlink` (skip branch) | `ts_ms`, `_ptb_start_ms`, `diff_ms`, `value`, `round_id` — **loggare SEMPRE quando si fa skip per `ts_ms < _ptb_start_ms`** (attualmente è silenzioso) |
| 2 | `apply_chainlink` (ptb set) | `ts_ms`, `_ptb_start_ms`, `value`, `lag_ptb_sec`, `round_id` |
| 3 | `prime_chainlink` | `last_value`, `last_ts_ms`, `market_start_ms`, `is_valid` (bool: `last_ts_ms >= market_start_ms`) |

#### In `src/round_runner.py`

| # | Punto | Cosa loggare |
|---|-------|--------------|
| 1 | `sampler start` | `market_start_ts`, `now_ts`, `lag_after_start_sec` |
| 2 | `first sample` | `ptb_ready` (bool), `chainlink_price`, `chainlink_ts_ms` |
| 3 | `ptb captured` | `lag_ptb_sec`, `tick_count_so_far` |
| 4 | Fine round fallito | Dump completo: `chainlink_ts_ms`, `chainlink_price`, `price_to_beat`, `_ptb_start_ms`, `_final_end_ms`, `total_ticks_received`, `total_btc_ticks`, `total_non_btc_ticks` |

#### Esempio di implementazione del logging di skip ptb (critico)

In `src/round_state.py`, modificare:
```python
def apply_chainlink(self, value, ts_ms, recv_ms):
    self.chainlink_price = value
    self.chainlink_ts_ms = ts_ms
    if ts_ms < self._ptb_start_ms:
        # LOG CRITICO: prima era silenzioso
        logger.debug(json.dumps({
            "location": "round_state.apply_chainlink",
            "message": "ptb skip",
            "data": {
                "round": self.round_id,
                "oracle_ts_ms": ts_ms,
                "market_start_ms": self._ptb_start_ms,
                "diff_ms": self._ptb_start_ms - ts_ms,
                "value": value,
                "skipped_reason": "ts_ms < market_start"
            },
            "timestamp": int(time.time() * 1000)
        }))
        return
    if self._ptb_ts_ms is None or ts_ms < self._ptb_ts_ms:
        self.price_to_beat = value
        logger.debug(json.dumps({
            "location": "round_state.apply_chainlink",
            "message": "ptb set",
            "data": {
                "round": self.round_id,
                "oracle_ts_ms": ts_ms,
                "market_start_ms": self._ptb_start_ms,
                "value": value,
                "lag_ptb_sec": (ts_ms - self._ptb_start_ms) / 1000
            }
        }))
```

---

### Criteri di validazione fix

Un fix è considerato **validato** se soddisfa **tutti** i seguenti criteri:

| # | Criterio | Misura |
|---|----------|--------|
| 1 | **Run collector ≥ 60 min su poly** | Non sufficiente un probe 10 min; serve un run reale del collector |
| 2 | **Tasso di success ≥ 90%** | In 1 ora (12 round attesi), almeno 10-11 round salvati come completi (300 sec) |
| 3 | **Zero errori `price_to_beat not captured`** | Nessun evento di questo tipo nel log durante il run di validazione |
| 4 | **Zero errori `chainlink final not captured`** | Nessun evento di questo tipo nel log |
| 5 | **Log diagnostico mostra ptb catturato** | NDJSON con `ptb set` presente per ogni round, con `lag_ptb_sec < 30s` |
| 6 | **Nessuno skip ptb silenzioso** | Se ci sono skip per `ts_ms < market_start`, sono loggati e spiegati |
| 7 | **Stall detector funzionante** | Se BTC si ferma per >45s, il log mostra `stall detected` e reconnect automatico |
| 8 | **Run ≥ 4h come test finale** | Ripetere un run della stessa durata del run analizzato (4h), confrontare: 11 round → aspettativa ≥ 44 round |
| 9 | **Confronto Windows dev** | Eseguire un run lungo (≥1h) anche su Windows per verificare se il comportamento è coerente |

**Criterio di non-regressione:** nessun nuovo tipo di errore o warning introdotto; i round che prima funzionavano continuano a funzionare.

---

### Raccomandazioni infra/OS/rete/firewall

#### Firewall PVE (CT 103)

**Raccomandazione: disabilitare il firewall PVE sul CT 103.**

Motivazione:
- Il CT è in una LAN sicura (`10.1.1.0/24` dietro Fritz.box)
- Il firewall PVE a livello CT aggiunge un layer di conntrack che **potrebbe** interferire con connessioni WebSocket long-lived (H7, bassa probabilità ma non esclusa)
- `nf_conntrack` a livello PVE potrebbe avere timeout diversi per connessioni idle
- Elimina una variabile nella diagnosi

Implementazione:
```bash
# Sul nodo Proxmox
ssh proxmox-root "pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth"
ssh proxmox-root "pct reboot 103"
```

#### Sistema operativo

**Raccomandazione: mantenere Debian 12 LXC unprivileged.** Non è necessario un cambio di OS.

Motivazione:
- I probe 10 min identici Windows/poly escludono problemi di OS/TCP stack come causa primaria (H1/H2 REJECTED)
- Debian 12 LXC è una scelta appropriata per un container 24/7
- Il problema è applicativo (logica di stall/ptb), non infrastrutturale
- Un cambio di OS introdurrebbe variabili aggiuntive senza risolvere il bug

**Se si vuole comunque un'alternativa per test:**
- **Alpine Linux LXC**: più leggero, ma meno compatibilità con Python 3.12 compilato da sorgente
- **Ubuntu 24.04 LXC**: Python 3.12 disponibile nativamente via apt, eliminando la compilazione manuale; potrebbe essere un'opzione per semplificare il deploy, ma non risolverebbe il bug
- **Windows Server/Pro**: non raccomandato per un container 24/7 su Proxmox; più complesso da gestire

#### Configurazione di rete

**Raccomandazioni:**

1. **Verificare che non ci siano conflitti IP**: il CT 103 ha IP statico `10.1.1.73`; verificare che il Fritz.box non assegni lo stesso IP via DHCP a un altro dispositivo:
```bash
# Dal nodo Proxmox o da qualsiasi macchina LAN
arp-scan 10.1.1.0/24 | grep 10.1.1.73
# oppure
ping -c 1 10.1.1.73 && arp -n | grep 10.1.1.73
```

2. **Verificare DNS resolution**: il CT usa il Fritz.box come DNS; verificare che la risoluzione di `gamma-api.polymarket.com` sia stabile e non fluttui:
```bash
ssh ticksaver "for i in \$(seq 1 20); do dig +short gamma-api.polymarket.com; sleep 5; done"
```

3. **Considerare DNS statico**: per evitare problemi di risoluzione DNS, aggiungere un entry in `/etc/hosts` per l'endpoint Polymarket RTDS (se l'IP è stabile):
```bash
# Verificare IP corrente
ssh ticksaver "dig +short gamma-api.polymarket.com"
# Se stabile, aggiungere a /etc/hosts
```

4. **Verificare MTU**: confermare che MTU 1500 è corretto e non ci sono framing issues:
```bash
ssh ticksaver "ip link show eth0 | grep mtu"
# Test di path MTU
ssh ticksaver "ping -M do -s 1472 -c 3 gamma-api.polymarket.com"
```

5. **TCP keepalive tuning** (opzionale, anche se il collector usa ping applicativo):
```bash
# Verificare valori attuali
ssh ticksaver "sysctl net.ipv4.tcp_keepalive_time net.ipv4.tcp_keepalive_intvl net.ipv4.tcp_keepalive_probes"
# Se si vuole rendere più aggressivi (opzionale, non critico)
# ssh ticksaver "sysctl -w net.ipv4.tcp_keepalive_time=60 net.ipv4.tcp_keepalive_intvl=10 net.ipv4.tcp_keepalive_probes=6"
```

#### Risorse CT

**Raccomandazione:** le risorse attuali (2 GB RAM, 6 vCPU) sono adeguate. L'uso osservato è ~36 MB app + ~187 MB cache, CPU ~13 min su 4h. Non sono necessari aumenti.

**Swap:** la swap configurata (1024 MB) non risulta montata nel guest. Verificare:
```bash
ssh ticksaver "swapon --show"
ssh ticksaver "free -h"
```
Se la swap non è attiva, non è un problema (l'app usa poca RAM), ma per completezza si può verificare la configurazione PVE.

---

### Riepilogo delle azioni raccomandate (priorità)

| Priorità | Azione | Scopo |
|----------|-------|-------|
| **1** | Implementare logging diagnostico NDJSON in `feed_chainlink.py` e `round_state.py` (specialmente skip ptb silenzioso e stall check loop) | Confermare H5a/H5b |
| **2** | Eseguire probe RTDS 30 min con logging di tutti i simboli | Verificare se WS resta viva con altri simboli ma BTC si ferma |
| **3** | Analizzare `debug-9c51e0.log` esistente su poly | Evidenze indirette già disponibili |
| **4** | Disabilitare firewall PVE sul CT 103 | Eliminare variabile infra |
| **5** | Eseguire soak test collector ≥ 60 min su poly con nuovo logging | Validare diagnosi |
| **6** | Eseguire soak test collector ≥ 60 min su Windows dev | Escludere/confermare fattore ambientale |
| **7** | Eseguire `diag_timestamps.py` per verificare lag oracle | Confermare/escludere H5b |
| **8** | Tcpdump durante un fallimento | Analisi a livello pacchetto |

**Prossimo step dopo diagnosi confermata:** implementare fix mirato in base all'ipotesi confermata (probabilmente: stall detector su assenza tick BTC specificamente + gestione timestamp oracle retrodatati + log di skip ptb).