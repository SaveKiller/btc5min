## Punto 01

### Ipotesi (con probabilità e evidenze, basate su fatti in `baseline.md`)

| Codice | Ipotesi | Probabilità | Evidenze dai fatti (baseline, report, log) |
|--------|---------|-------------|---------------------------------------------|
| **H5** | WS Chainlink attiva ma stream BTC inutilizzabile: i tick `btc/usd` arrivano con timestamp `ts_ms < market_start_ms`, quindi `price_to_beat` non viene mai impostato. | **Alta (80%)** | – 68 righe `price_to_beat not captured` vs solo 1 chiusura WS (`Going away`).<br>– Dopo reconnect (00:38:39) ptb catturato con lag oracle 222s (round parziale).<br>– Sampler logga `btc=63985.15 ptb=-`, cioè `chainlink_price` valorizzato ma ptb `None`.<br>– Nessuno stall detector scattato (0 `chainlink stall`).<br>– Periodi di fallimenti consecutivi (~17 round) senza disconnessioni. |
| **H6** | Timestamp obsoleto in `prime_chainlink` al `register()` del round: se `last_ts_ms` è anteriore a `market_start_ms`, il primo valore visibile non imposta ptb. | **Media (60%)** | – Codice `round_state.py`: `if ts_ms < self._ptb_start_ms: return` (salta ptb).<br>– `prime_chainlink` imposta `chainlink_price` ma **non** `price_to_beat` (nessuna logica di verifica età).<br>– Il sampler mostra `btc=...` subito, ma ptb assente per interi round.<br>– Dopo reconnect, il primo tick utile arriva 222s dopo: ciò suggerisce che lo stato interno contiene un timestamp vecchio. |
| **H7** | Overlap tra round consecutivi causa competizione su variabili condivise (`_last_msg_ts`, `chainlink_price`), saltando la cattura ptb per il round successivo. | **Bassa (20%)** | – Il codice `feed_chainlink.py` è singleton con `_last_msg_ts` globale; il `register()` lo legge ma non resetta nulla.<br>– In teoria possibile se il nuovo round si registra prima che il precedente abbia finalizzato la cattura. <br>– Non ci sono prove dirette nel log (nessun errore di concorrenza). |
| **H8** | Firewall PVE del CT ( `firewall=1` ) interrompe connessioni long‑lived per stato conntrack scaduto o regole default. | **Bassa (10%)** | – Il probe 10 min ha funzionato perfettamente (579 tick, 0 disconnect).<br>– `nf_conntrack_count=0` nel CT, ma il firewall PVE lavora a livello host.<br>– Possibile che sessioni inattive da >5 min vengano droppate (i ping ogni 5s dovrebbero evitarlo). |
| **H9** | Risorse limitate (RAM 2GB, CPU 6 core) causano throttling o scheduling delay che rallentano la cattura timestamp. | **Bassa (5%)** | – Uso RAM tipico ~36 MB app + cache, CPU ~13 min su 4h (leggero).<br>– Non ci sono OOM o errori di memoria.<br>– Overlap round è leggero: un thread WS + un thread per round. |
| **H10** | Bug in libreria `websocket-client` 1.9.0 (versione su poly) che perde messaggi su connessione stabile. | **Bassa (5%)** | – Versione diversa da ambiente dev? (dev ha stessa requirements.txt, ma non è stato testato a lungo).<br>– Possibile se la libreria gestisce male messaggi frammentati, ma non abbiamo evidenze.<br>– Il probe 10 min con stessa libreria ha funzionato. |
| **H11** | Clock skew o disallineamento timestamp di sistema (NTP non performante) causa falsi positivi su `ts_ms < market_start_ms`. | **Molto bassa (1%)** | – Timezone UTC, clock sincronizzato. Nella timeline log non ci sono salti temporali anomali.<br>– L’unico round parziale ha lag oracle 222s, plausibile per latenza rete, non per clock. |

### Comandi / script di diagnostica

**Da eseguire su poly (via SSH `ticksaver`)**

1. **Probe lungo WS BTC** – per verificare se il tick `btc/usd` smette di arrivare per periodi >45s senza disconnessione.
   ```bash
   ssh ticksaver "/opt/btc5min/venv/bin/python /tmp/probe_btc_gaps.py 1800"   # 30 min
   ```
   Salvare output per analisi gap massimi e timestamp.

2. **Cattura TCP dei websocket** – per ispezionare il flusso messaggi in un round tipico che fallisce.
   ```bash
   ssh ticksaver "tcpdump -i eth0 -s 0 -w /tmp/ws.pcap host gamma-api.polymarket.com and port 443" &
   sleep 600   # 10 min
   kill %1
   scp ticksaver:/tmp/ws.pcap ./
   ```
   Analizzare con Wireshark: presenza di messaggi `btc/usd` e loro timestamp.

3. **Verifica stato `_ptb_start_ms` e `_last_msg_ts` in tempo reale** – aggiungere un endpoint di debug **temporaneo** (es. file `/tmp/debug_state.json`) che dump ogni secondo le variabili critiche di `ChainlinkFeed` e `RoundState` del round corrente.

4. **Esecuzione di `diag_ptb.py` su poly** – già presente in `scripts/`, da lanciare dopo un round fallito:
   ```bash
   ssh ticksaver "/opt/btc5min/venv/bin/python /opt/btc5min/scripts/diag_ptb.py /opt/btc5min/data/collector.log"
   ```

5. **Log strutturato NDJSON** – abilitare il debug logger aggiungendo una variabile d’ambiente `DEBUG_FILE=/opt/btc5min/debug-9c51e0.log` (il collector già lo supporta). Analizzare righe `"location": "feed_chainlink._dispatch"` per vedere quanti tick vengono scartati per `ts_ms < market_start`.

6. **Ping continuo a `gamma-api.polymarket.com`** per monitorare latenza rete durante il run:
   ```bash
   ssh ticksaver "nohup ping gamma-api.polymarket.com > /tmp/ping.log 2>&1 &"
   ```

### Modifiche di logging suggerite (da implementare nel codice prima del prossimo test)

**In `src/feed_chainlink.py`** (punti critici dal report §7):

| Punto | Cosa loggare | Nuova riga log |
|-------|-------------|----------------|
| `_on_message` (btc/usd) | Ogni tick: `oracle_ts_ms`, `gap_sec` dall’ultimo; warning se `gap_sec > 15` | `DEBUG: btc/usd tick: oracle_ts_ms=..., recv_ms=..., gap_since_last=...` |
| `_dispatch` | Per round attivo: `round_start_ts`, `oracle_ts_ms`, `market_start_ms`, `skipped` (true/false) | `DEBUG: dispatch round=... oracle_ts=... market_start=... skipped_reason=ts_ms<start` |
| `_on_open` | Timestamp connessione, subscribe inviato | `INFO: WS connected at ..., subscribe sent` |
| `_on_close` | `status_code`, `msg`, `connected_sec`, `last_btc_msg_age_sec` | `WARNING: WS closed code=... reason=... connected_sec=... btc_age=...` |
| `_run` | Prima di stall reconnect: `stall_sec`, `last_btc_msg_age` | `WARNING: stall detected: no btc tick for ... sec, reconnecting` |
| `prime_chainlink` | Valore e timestamp usati per priming | `INFO: prime_chainlink value=... ts_ms=... current_ptb_start=...` |

**In `src/round_runner.py`:**

- Allo start del sampler: log `ptb_ready` booleano e primo valore `chainlink_price`.
- A fine round fallito: dump `chainlink_ts_ms`, `price_to_beat`, `_ptb_start_ms`, `_final_end_ms`.
- Se `price_to_beat` non catturato nei primi 60 secondi, log `WARNING: ptb still None after 60s`.

**Formato:** preferibilmente JSON su stderr (già usato per SAMPLE) per facilitare analisi.

### Criteri di validazione fix

Dopo ogni modifica, eseguire un **run di almeno 1 ora** su poly (meglio 2 ore) e verificare:

1. **Numero di round salvati**: attesi ~12 round completi in 1 ora (ogni 5 min). Accettabile 10–12.
2. **Zero errori** `price_to_beat not captured` e `chainlink final not captured` nel log (escludendo eventuali prime righe dopo avvio).
3. **Log diagnostico** deve mostrare che ogni round ha `ptb_set` entro i primi secondi (gap < 10s).
4. **Assenza di `chainlink stall`** nel log (se lo stall detector è stato migliorato).
5. **Round parziale** non più accettabile: tutti i round devono avere durata 300 sec esatti.
6. **Confronto con probe 10 min**: gap `btc/usd` massimo < 10 secondi (come già visto).

**Checklist automatable** (script di validazione):
```bash
grep -c 'price_to_beat not captured' collector.log   # deve essere 0
grep -c 'done ' collector.log                        # >= 10 per ora
grep -c 'final not captured' collector.log           # 0
```

### Raccomandazioni infra / OS / rete / firewall

#### Firewall CT (raccomandazione forte)
**Disattivare il firewall a livello CT** ( `firewall=0` in PVE), dato che il container è su LAN sicura (10.1.1.0/24) e non espone servizi verso l’esterno. La protezione è già garantita dal firewall host Proxmox (se presente) e dal router Fritz.box. Nessun rischio aggiuntivo. Comando:
```
pct set 103 -firewall 0
```
Poi riavviare il servizio o il CT per sicurezza.

#### Sistema operativo
**Nessun cambio OS raccomandato.** Debian 12 bookworm LXC unprivileged è adeguato; il problema è nel codice applicativo, non nel kernel o nella distribuzione. I probe hanno mostrato comportamento identico a Windows, confermando che non è una causa OS.

#### Impostazioni di rete
- **MTU 1500** è corretto.
- **tcp_keepalive** non necessario (collettore usa ping applicativo ogni 5s).
- **Disattivare IPv6** nel CT se non serve (evita eventuale traffico spurio): aggiungere `net.ipv6.conf.all.disable_ipv6=1` in `/etc/sysctl.d/99-disable-ipv6.conf`.
- **Verificare la tabella di routing** e assenza di conflitti: su `poly` non ci sono altre interfacce (solo `eth0`), gateway singolo.
- **Aumentare `net.core.rmem_max`** se si osservano perdite di pacchetti WS (opzionale, bassa priorità).

#### Risorse CT
- RAM 2 GB sono sufficienti; monitorare con `free -h` e `/proc/meminfo` per eventuale crescita.
- CPU 6 core non è un collo di bottiglia.

#### Raccomandazione operativa
Prima di applicare fix al codice, eseguire un **run diagnostico di 1 ora** con il logging aggiuntivo proposto (senza modificare la logica) per raccogliere dati concreti sulla causa dei fallimenti ptb. Ciò eviterà di implementare fix non mirati.