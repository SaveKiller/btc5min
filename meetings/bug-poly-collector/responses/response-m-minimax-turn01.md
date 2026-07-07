
# Turno 01 — Analisi meeting `bug-poly-collector`

> **Scope:** risposta al **Punto 01** del meeting `bug-poly-collector` (creato 2026-07-07T09:20:00Z), ancorata ai fatti oggettivi di `baseline.md` e al report `report-bug-0707.md`. Nessun report-turn precedente; baseline generata ora.

---

## ## Punto 01

**Richiesta:** analizzare il report del bug, valutare **tutte** le possibilità (anche meno frequenti), proporre cambio OS container poly, disattivazione firewall, verifica impostazioni di rete, e produrre test/prove/info di debug strutturati per la successiva implementazione.

**Deliverable:** ipotesi strutturate con probabilità/evidenze, comandi e script diagnostici, modifiche di logging, criteri di validazione fix, raccomandazioni infra/OS.

---

### 1. Sintesi dei fatti (da `baseline.md`)

| Fatto | Valore baseline | Implicazione |
|-------|-----------------|--------------|
| Round attesi in ~4h | ~48 | Produzione largamente insufficiente |
| Round salvati | **11** (10×300s + 1×260s) | ~23% del teorico |
| `price_to_beat not captured` | **68** occorrenze (~34 eventi) | Maggioranza dei fallimenti |
| `chainlink final not captured` | **4** occorrenze (~2 eventi) | Secondo tipo di fallimento |
| `chainlink ws error` | **2** (1 solo `Going away` 1001) | Disconnessioni lato server sporadiche |
| `ws drop` (CLOB) | **6** | CLOB più instabile di RTDS |
| `chainlink stall` | **0** | Blind‑spot confermato: stall detector non scatta |
| Probe 10 min poly vs Win | 579 tick, gap max 8.3s, **0 disconnect** | Esclude H1/H2/H3 su scala breve |
| H1/H2/H3 dichiarate | REJECTED | Da confermare/estendere a run lunghi |
| H4 | INCONCLUSIVE | Può avere contributo su CLOB |
| H5 | CONFIRMED (causa sospetta) | Da validare con log diagnostico mirato |
| CT 103 | LXC unprivileged, 2 GB RAM, 6 vCPU, firewall PVE=1, MTU 1500, gw 10.1.1.1 | Vincoli operativi noti |
| Python runtime | 3.12.10 venv (`/usr/local/bin/python3.12`) | Allineato a dev |
| Servizio | `btc5min.service` `Restart=always RestartSec=5` | Restart può mascherare stati degradati |
| Run analizzato | 2026‑07‑06 22:38 → 2026‑07‑07 02:40 UTC | ~13 min CPU su 4h, idle lungo |

**Pattern temporale chiave** (estratto da `report-bug-0707.md` §3):

- 22:38–23:10: 6 round OK consecutivi.
- 23:10–00:30: **~17 round consecutivi falliti ptb**, **nessun** `chainlink ws error` e nessun `chainlink stall` nel log.
- 00:38:39 unico `Going away` 1001.
- 00:38:43 ptb catturato con **lag 222 s** → round parziale 260 s.
- 00:45–01:00: 4 round OK dopo reconnect.
- 01:05+: nuova ondata di fallimenti ptb/final senza disconnect.

> Il “buco” 23:10–00:30 (17 round falliti, 0 ws error, 0 stall) è l’evidenza strutturale più importante: il difetto **convive con la WS apparentemente up** e non produce segnale né reconnect né log di errore. È esattamente la firma di H5 (stall detector cieco ai soli messaggi `btc/usd`).

---

### 2. Ipotesi strutturate (probabilità, evidenze, test)

> Legenda probabilità: **A** Alta (>60%), **M** Media (30–60%), **B** Bassa (5–30%), **MB** Molto bassa (<5%).

#### H1 — Container / rete LXC / Debian 12 causano drop WS

- **Probabilità:** **B** (≤15%).
- **Stato:** REJECTED a 10 min su scala breve.
- **Evidenze a sfavore:** probe 10 min `probe_btc_gaps.py` su poly = Windows (579 tick, gap max 8.3s, 0 disconnect), latenza TCP ~24 ms stabile, MTU 1500, conntrack 0, `tcp_keepalive_time=7200` (il collector usa ping applicativo 5s).
- **Caveat:** probe 10 min **non** esclude failure intermittenti su run multi‑ora (es. saturazione cgroup, throttling I/O, garbage‑collection pause). Da ripetere con soak ≥ 30 min e con `so_connect` di test che emette solo `btc/usd` (simula il carico del collector).
- **Test proposto:** vedi §4.A.

#### H2 — Stack TCP Debian 12 / kernel 6.8.12‑10‑pve

- **Probabilità:** **MB** (<5%).
- **Stato:** REJECTED come causa primaria.
- **Evidenze:** parametri kernel di default accettabili; il ping applicativo 5s in `feed_chainlink.py` maschera `tcp_keepalive_time=7200`.
- **Test proposto:** `ss -tin` su connessione RTDS attiva + `nstat | grep -E 'Tcp(Retrans|OutOfOrder|Packets)'` per ~30 min durante run collector.

#### H3 — Disconnect frequenti lato server RTDS

- **Probabilità:** **B** (≤10%).
- **Stato:** REJECTED per “frequenti”.
- **Evidenze:** 1 solo `Going away` (1001) in 4h. Il server RTDS non sta cacciando il client; la WS resta aperta.
- **Caveat:** possibile che il server chiuda e il client **non se ne accorga** (half‑open socket lato client dietro NAT) — vedi H11/H13.
- **Test proposto:** heartbeat applicativo bidirezionale + log `last_recv_age_sec` ogni 5s (vedi §5).

#### H4 — NAT/router Fritz.box droppa long‑lived

- **Probabilità:** **M** (30–40%) per CLOB, **B** (≤15%) per RTDS.
- **Stato:** INCONCLUSIVE.
- **Evidenze a favore:** 5 `clob ws drop` (CLOB), ma RTDS ha solo 1 disconnect. Il traffico RTDS è ~1 msg/s ⇒ keepalive continuo, mentre CLOB può stare in silenzio ⇒ timeout NAT/Fritz!Box plausibile.
- **Test proposto:** misurare con `conntrack -E -t` sul router (se accessibile) o con `ss -tin` lato poly durante run; probing con due sessioni WS lunghe (RTDS vs CLOB) in parallelo per 1h+.

#### H5 — WS “up” ma stream `btc/usd` fermo (stall detector cieco)

- **Probabilità:** **A** (>70%) come causa principale dei fallimenti ptb.
- **Stato:** CONFIRMED a livello di meccanismo.
- **Evidenze a favore:**
  - 17 round consecutivi falliti **senza** un solo `chainlink ws error` né `chainlink stall`.
  - `feed_chainlink.py`: `STALL_RECONNECT_SEC=45.0` ma `_last_msg_ts` aggiornato **solo** quando `symbol == "btc/usd"` (`_on_message` ha il filtro symbol prima del timestamp di attività). Se la connessione resta viva con altri simboli o heartbeat, lo stall **non** scatta.
  - `round_state.py`: `apply_chainlink` esce immediatamente se `ts_ms < self._ptb_start_ms`. Se l’ultimo `last_value/last_ts_ms` provenienti da `prime_chainlink` è anteriore al `market_start`, il sampler vede `chainlink_price` valorizzato ma `price_to_beat` resta `None` per tutto il round → `btc=... ptb=-` (esattamente la firma osservata a fine run: `btc=63985.15 ptb=-`).
  - Dopo il reconnect `Going away`, il primo ptb arriva con **lag 222 s** (round parziale a 260 s): conferma che alla caduta di connessione il client recupera, ma la “fase” di stream fermo **prima** del disconnect non era stata rilevata.
- **Caveat:** H5 spiega molto bene i fallimenti **ptb**, ma non tutti i 2 fallimenti **final** (potrebbe essere correlato: se ptb non arriva, anche `final_chainlink` nella finestra `_final_end_ms` non viene materializzato). Da distinguere nei log diagnostici.
- **Test proposto:** vedi §4.B (arricchimento log) e §5 (stall detector mirato su `btc/usd`).

#### H6 — `websocket-client` 1.9.0 non emette ping/pong corretti su Python 3.12

- **Probabilità:** **M** (20–30%) come concausa.
- **Evidenze:** la libreria gestisce il ping con un thread interno; bug noti su versioni 1.6–1.8 (es. issue #871) con freeze del keepalive. 1.9.0 è recente; potrebbe esserci regressione su 3.12.
- **Caveat:** non spiegherebbe la totale assenza di `chainlink stall` (l’eccezione di invio ping dovrebbe emergere).
- **Test proposto:** versione pinning su dev → poly (`pip install websocket-client==1.8.0` poi `==1.9.0`), confronto in probe 30 min. Misurare `ping latency` lato client (timestamp invio → `pong` ricevuto).

#### H7 — Race condition su `register` / `prime_chainlink` con round overlap

- **Probabilità:** **M** (25–35%) come concausa.
- **Evidenze:** l’overlap tra round è progettuale (`main.py` spawn ogni 5 min). Se `prime_chainlink` viene chiamato con un `last_value` di un round precedente il cui `ts_ms` è < `market_start_ms` del nuovo round, `chainlink_price` viene visualizzato ma `price_to_beat` no (vedi H5 e codice `round_state.py`).
- **Test proposto:** aggiungere in `feed_chainlink._dispatch` log esplicito del “ts_ms vs market_start_ms” al primo messaggio di ogni round; verificare se il `last_value` “priming” è sempre dello stesso round.

#### H8 — DNS / risoluzione FQDN `ws‑api.polymarket.com`

- **Probabilità:** **MB** (<5%).
- **Evidenze a sfavore:** connessione RTDS aperta, quindi DNS risolto correttamente. Una failure DNS reciderebbe la WS e genererebbe `_on_error`/`_on_close`.
- **Test proposto:** `getent hosts ws-api.polymarket.com` + `dig +short` da poly; verificare `nsswitch.conf` (`hosts: files dns`).

#### H9 — `Restart=always` + `RestartSec=5` mascherano stati degradati

- **Probabilità:** **M** (30–40%) di **confondere** la diagnosi.
- **Evidenze:** se lo stream `btc/usd` si ferma ma la WS resta aperta, dopo `STALL_RECONNECT_SEC=45` (impostato in `feed_chainlink.py`) dovrebbe esserci reconnect. Il fatto che lo stall non scatti e il servizio non riparta è sintomo che **il client crede che tutto funzioni**. Il restart di systemd non aiuta: nessun crash.
- **Implicazione:** prima di toccare restart policy, aggiungere contatori di “round consecutivi falliti” e fare restart controllato quando N>2 (fail‑fast).
- **Test proposto:** vedi §5 logging.

#### H10 — Clock skew / NTP / `adjtimex`

- **Probabilità:** **B** (≤10%).
- **Evidenze:** il log dice “clock sincronizzato”. Però `ts_ms` oracle è generato lato Chainlink, non è la `recv_ms` di sistema. Un drift anche di 200 ms non spiega `lag_ptb=222s`.
- **Test proposto:** `chronyc tracking` / `timedatectl status` + confronto drift su 4h. Verificare `ts_ms` oracle vs `time.time()` Python a campione.

#### H11 — Half‑open socket dietro NAT/Fritz!Box + firewall PVE stateful

- **Probabilità:** **M** (20–30%).
- **Evidenze:**
  - `firewall=1` su `net0` del CT 103 → PVE abilita regole di INPUT/FORWARD stateful via `iptables`/`nftables`.
  - Una connessione WS che resta idle (solo ping ogni 5s) può essere evictata dalla NAT table del router Fritz!Box e/o “dimenticata” dallo stateful firewall di PVE.
  - Con il **firewall PVE attivo** e `net0` configurato con `firewall=1`, il bridge `vmbr0` filtra i pacchetti. Anche se `iptables -L` lato guest è vuoto, l’host PVE applica regole.
- **Caveat:** il ping applicativo 5s dovrebbe tenere viva la connessione, ma solo se il client effettivamente **invia** (handshake ping/pong). Se il bug è su `websocket-client` (H6), il client non invia e la connessione muore silenziosamente.
- **Raccomandazione:** §6.B — disattivare firewall PVE su `net0` come test rapido (`pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,...`); è in LAN sicura.
- **Test proposto:** vedi §4.D.

#### H12 — TCP send/receive buffer, RWIN, `tcp_notsent_lowat`

- **Probabilità:** **B** (≤10%).
- **Test proposto:** `sysctl net.ipv4.tcp_rmem/tcp_wmem` + `ss -tin` durante un run; considerare `tcp_notsent_lowat=16384`.

#### H13 — Preferenza IPv6 / fallback IPv4

- **Probabilità:** **B** (≤10%).
- **Evidenze a sfavore:** log non mostra cambi di indirizzo.
- **Test proposto:** `ip -6 addr`; `getent ahosts ws-api.polymarket.com`; provare connessione forzata IPv4.

#### H14 — Throttling cgroup v2 (CPU/memory) durante run

- **Probabilità:** **B** (≤10%).
- **Evidenze:** CPU collector ~13 min su 4h (idle >99%). RAM 119/2048 MB. Nessuna pressione evidente.
- **Test proposto:** monitorare `systemd-cgtop` / `cat /sys/fs/cgroup/system.slice/btc5min.service/memory.peak` durante un run.

#### H15 — File system ZFS / barrier / sync su `/opt/btc5min/data`

- **Probabilità:** **MB** (<5%) per i fallimenti ptb.
- **Evidenze:** i fallimenti sono di **rete/logica**, non di I/O (il file `.bin` viene scritto a fine round; il problema è prima).
- **Test proposto:** monitorare `zfs_iostat`/iostat; verificare `mount | grep btc5min` (opzioni `sync/async`).

#### H16 — SIGPIPE / gestione segnali

- **Probabilità:** **MB** (<5%) — `websocket-client` intercetta SIGPIPE internamente.
- **Test proposto:** `strace -f -e signal -p $(pgrep -f 'src.main')` per 5 min.

#### H17 — Garbage collection pause / GIL contention

- **Probabilità:** **B** (≤10%).
- **Evidenze:** Python 3.12 con GIL; l’overlap di più round può creare contention. Pause GC >45s **potrebbe** mascherare lo stall.
- **Test proposto:** `python -X dev -X tracemalloc=10`; misurare `gc.get_stats()` in un thread di monitor.

#### H18 — Bug applicativo puro (logica `apply_chainlink` / `prime_chainlink`)

- **Probabilità:** **A** (>60%) **come fattore scatenante** di H5.
- **Evidenze:** vedi H5. Il `last_value` con `ts_ms < market_start` non viene né scartato né segnalato; il round entra con `chainlink_price` visibile ma `ptb=None`. Fino al primo messaggio valido, ogni round resta in stato “sospeso”.
- **Implicazione:** anche se H6/H11 venissero risolti, **qualsiasi** discontinuità del flusso `btc/usd` (anche < 1s di buco) può propagare il bug.
- **Test proposto:** aggiungere in `_dispatch` log che distingua `prime_chainlink‑derived value` da `live value`; rifiutare esplicitamente `last_ts_ms < market_start` come `prime`.

#### H19 — Proxy/inspector TLS (MITM) sulla LAN

- **Probabilità:** **MB** (<1%) — nessun proxy noto.
- **Test proposto:** `openssl s_client -connect ws-api.polymarket.com:443 -servername ws-api.polymarket.com` per ispezionare catena.

#### H20 — LXC unprivileged: limiti `RLIMIT_NOFILE`, seccomp

- **Probabilità:** **B** (≤10%).
- **Evidenze:** con overlap di round e CLOB + Chainlink aperti, il numero di fd può crescere. `RLIMIT_NOFILE` di default Debian 12 = 1024 soft / 4096 hard. CLOB può aprire multiple connessioni in retry.
- **Test proposto:** `prlimit` su PID del servizio; `lsof -p $(pgrep -f src.main) | wc -l`.

#### H21 — Problema PyPI / wheels su Python 3.12.10 build locale

- **Probabilità:** **MB** (<1%) — `httpx 0.28.1`, `websocket-client 1.9.0`, `numpy 2.5.1` sono versioni stabili.
- **Test proposto:** `pip check` + `pip install --force-reinstall --no-deps` per sanity.

#### H22 — Race su thread dei round (overlap) + global state in `ChainlinkFeed`

- **Probabilità:** **M** (25–35%) come concausa.
- **Evidenze:** `_dispatch` itera su `self._rounds` (dizionario). Se `_register`/`_unregister` non sono protetti da lock, un round che termina può pulire lo stato mentre un altro è in `apply_chainlink`. Comportamento tipico: ptb non impostato in alcuni round, random.
- **Test proposto:** aggiungere log esplicito di `len(self._rounds)` in `_dispatch`; verifiche con `helgrind`/analisi statica.

#### H23 — Saturazione `journald` / rate‑limit logging

- **Probabilità:** **MB** (<1%) — non spiega la mancanza di stall.
- **Test proposto:** `journalctl -u btc5min --since "1 hour ago" | wc -l`.

---

### 3. Tabella sinottica ipotesi (ordinata per probabilità di contributo al sintomo)

| ID | Sintesi | Prob. | Stato | Azione immediata |
|----|---------|-------|-------|------------------|
| **H5** | WS up, stream `btc/usd` fermo, stall detector cieco | **A** | Confermata come meccanismo | Arricchire log + fix stall su `btc/usd` |
| **H18** | Bug applicativo `apply_chainlink`/`prime_chainlink` accetta `ts_ms < market_start` | **A** | Forte sospetto | Fix logica: rifiutare/esplicitare priming obsoleto |
| **H22** | Race su `_rounds` in overlap round | **M** | Da confermare | Aggiungere lock + log `len(_rounds)` |
| **H11** | Half‑open / NAT / firewall PVE stateful | **M** | Plausibile | **Disattivare firewall PVE su CT 103** (test) |
| **H7** | Race su `register`/`prime_chainlink` | **M** | Plausibile | Log esplicito ts_ms vs market_start_ms |
| **H9** | `Restart=always` maschera degrado | **M** | Osservato | Aggiungere fail‑fast counter |
| **H4** | NAT/router drop su CLOB | **M** | Inconclusive | Probe 1h parallelo RTDS/CLOB |
| **H6** | `websocket-client` 1.9.0 ping/pong su 3.12 | **M** | Da testare | Pinning 1.8.0 vs 1.9.0 |
| **H20** | RLIMIT_NOFILE / fd exhaustion | **B** | Da verificare | `prlimit`, `lsof` |
| **H14** | Throttling cgroup v2 | **B** | Da verificare | `systemd-cgtop` |
| **H10** | Clock skew NTP | **B** | Da verificare | `chronyc tracking` |
| **H1** | LXC/rete drop WS | **B** | Rejected 10 min | Probe 30 min mirato su `btc/usd` |
| **H12** | TCP buffer/RWIN | **B** | Da verificare | `ss -tin`, `sysctl` |
| **H13** | IPv6 preference | **B** | Da verificare | `getent ahosts` |
| **H17** | GC pause / GIL | **B** | Da verificare | `tracemalloc` |
| **H2** | Stack TCP Debian 12 | **MB** | Rejected | `nstat` 30 min |
| **H3** | Disconnect server frequenti | **MB** | Rejected | Heartbeat applicativo |
| **H8** | DNS | **MB** | Improbabile | `getent` |
| **H15** | ZFS/sync | **MB** | Improbabile | iostat |
| **H16** | SIGPIPE | **MB** | Improbabile | strace |
| **H19** | MITM TLS | **MB** | Improbabile | s_client |
| **H21** | PyPI wheels | **MB** | Improbabile | pip check |
| **H23** | journald rate-limit | **MB** | Improbabile | conteggio |

---

### 4. Comandi e script diagnostici

> Tutti i comandi sono pensati per essere eseguiti su **poly** (via `ssh ticksaver` o localmente) salvo diversa indicazione. Output strutturato (JSON/NDJSON) per analisi successiva.

#### 4.A — Probe lungo mirato su `btc/usd` (H1, H5, H11)

Nuovo script `scripts/probe_btc_long.py` (suggerito): identico a `probe_btc_gaps.py` ma durata **30 min** e con **heartbeat applicativo** (invia un ping testuale ogni 5s e misura round‑trip), salvataggio NDJSON con `recv_age_sec`.

```bash
scp scripts/probe_btc_long.py ticksaver:/tmp/
ssh ticksaver "cd /opt/btc5min && venv/bin/python3 /tmp/probe_btc_long.py 1800 | tee /tmp/probe_long.ndjson"
```

Output atteso (campione):

```json
{"ts":1783388400.12,"event":"tick","symbol":"btc/usd","oracle_ts_ms":1783388399123,"recv_ms":1783388400119,"gap_sec":0.996}
{"ts":1783388405.13,"event":"ping","rtt_ms":42}
{"ts":1783388501.40,"event":"gap_warn","gap_sec":18.3,"symbol":"btc/usd"}
```

Pattern critico da cercare: `gap_warn` ricorrenti > 15s **senza** `close`/`error`.

#### 4.B — Log arricchiti su `feed_chainlink.py` (H5, H18, H22)

Comando per ispezione mirata del run attuale (post‑mortem):

```bash
ssh ticksaver "grep -nE 'chainlink|price_to_beat|done|stall|ws drop' /opt/btc5min/data/collector.log | head -200"
```

Estrazione dei blocchi “gap” di fallimenti consecutivi (per matching con H5):

```bash
ssh ticksaver "awk '/price_to_beat not captured/{f++} /done /{if(f>0){print \"FAIL_BLOCK:\",f; f=0} else {ok++}} END{print \"OK:\",ok,\"FAIL_BLOKS:\",f}' /opt/btc5min/data/collector.log"
```

#### 4.C — Stato connessione RTDS live (H11, H12, H20)

```bash
# Connessioni WS attive del processo
ssh ticksaver "ss -tin \$(pgrep -f 'src.main' | head -1) | grep -E 'ws-api|polymarket'"

# File descriptor aperti (fd count + tipologia)
ssh ticksaver "lsof -p \$(pgrep -f 'src.main') | awk '{print \$5}' | sort | uniq -c | sort -rn | head"

# Limite fd
ssh ticksaver "prlimit --pid \$(pgrep -f 'src.main') | grep -E 'NOFILE|AS'"

# Statistiche TCP cumulative
ssh ticksaver "nstat -az | grep -E 'Tcp(Retrans|OutOfOrder|Packets|Timeout|ESTAB)'"
```

#### 4.D — Test disattivazione firewall PVE (H11)

Da host PVE (`ssh proxmox-root`):

```bash
# Backup config
pct config 103 > /tmp/poly.conf.bak

# Disattiva firewall PVE sulla net0 (mantieni IP, bridge, MAC)
pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth

# Verifica
pct config 103 | grep net0
# Niente riavvio: PCT 103 conserva la net attiva. Test 1h.
```

Criterio di successo: nessun cambiamento ⇒ non è firewall; miglioramento ⇒ H11 confermata, **mantieni disattivato** (vedi §6.B).

Per ripristinare: `pct set 103 -net0 name=eth0,...,firewall=1,...` (ripristinare da `/tmp/poly.conf.bak`).

#### 4.E — Diagnostica versioni libreria (H6, H21)

```bash
ssh ticksaver "venv/bin/pip freeze | grep -iE 'websocket|httpx|numpy'"
ssh ticksaver "venv/bin/pip check"
# Test downgrade controllato
ssh ticksaver "venv/bin/pip install websocket-client==1.8.0 --no-deps && systemctl restart btc5min"
# Dopo 1h, confronto log; poi ripristino 1.9.0
```

#### 4.F — Diagnostica cgroup/LXC (H14, H20)

```bash
# Cgroup v2 (Debian 12 default)
ssh ticksaver "cat /proc/self/cgroup"
ssh ticksaver "systemd-cgtop -n 1 -b"
# Memory peak del servizio
ssh ticksaver "systemctl show btc5min -p MemoryCurrent -p MemoryPeak -p CPUUsageNSec"
# Eventuali OOM
ssh ticksaver "dmesg | grep -iE 'oom|killed' | tail -20"
```

#### 4.G — Clock & DNS (H8, H10)

```bash
ssh ticksaver "timedatectl status && chronyc tracking 2>/dev/null || echo no-chrony"
ssh ticksaver "getent hosts ws-api.polymarket.com gamma-api.polymarket.com clob.polymarket.com"
ssh ticksaver "cat /etc/resolv.conf"
```

#### 4.H — Debug NDJSON esistente

```bash
ssh ticksaver "ls -la /opt/btc5min/debug-*.log"
ssh ticksaver "tail -50 /opt/btc5min/debug-9c51e0.log"
# Estrarre eventi di feed_chainlink dal debug NDJSON
ssh ticksaver "grep -E '\"location\":\"feed_chainlink' /opt/btc5min/debug-9c51e0.log | tail -100"
```

Questo file **non** è incluso nel contesto ed è la **prima fonte da scaricare** per la diagnosi post‑mortem del run 22:38–02:40.

#### 4.I — Script di correlazione (suggerito nuovo)

`scripts/correlate_failures.py` (suggerito): parsa `collector.log` + `debug-*.log` e per ogni round fallito estrae: timestamp, ptb_status, chainlink_ts_ms, last_recv_age, ws_state, num_rounds_attivi.

```bash
scp scripts/correlate_failures.py ticksaver:/tmp/
ssh ticksaver "venv/bin/python3 /tmp/correlate_failures.py /opt/btc5min/data/collector.log /opt/btc5min/debug-9c51e0.log > /tmp/corr.tsv"
scp ticksaver:/tmp/corr.tsv ./
```

---

### 5. Modifiche di logging suggerite

Tutti i punti sono **aggiunte non distruttive** (nessuna rimozione di log esistenti) per preservare la compatibilità con `verify`/test esistenti.

#### 5.A — `src/feed_chainlink.py`

| Punto | Evento NDJSON | Campi |
|-------|---------------|-------|
| `_on_open` | `feed.conn_open` | `conn_open_ts`, `subscribe_sent_ts`, `symbols` |
| `_on_close` | `feed.conn_close` | `close_code`, `close_msg`, `intentional`, `connected_sec`, `last_btc_recv_age_sec` |
| `_on_error` | `feed.conn_error` | `error_str`, `intentional`, `last_btc_recv_age_sec` |
| `_close_ws` | `feed.conn_close_intentional` | `intentional`, `reason` (`"stall"\|"stop"\|"reconnect"\|"error"`) |
| `_run` (branch stall) | `feed.stall_detected` | `stall_sec`, `last_btc_recv_age_sec`, `last_other_recv_age_sec` |
| `_on_message` (prima del filtro symbol) | `feed.msg_recv` | `symbol`, `ts_recv_ms`, `gap_from_prev_sec` — **counter incrementato per ogni messaggio** (non filtrato) |
| `_on_message` (dopo filtro `btc/usd`) | `feed.btc_tick` | `oracle_ts_ms`, `recv_ms`, `gap_sec_from_prev_btc` |
| `_on_message` (se `gap > 15`) | `feed.btc_gap_warn` | `gap_sec` |
| `_dispatch` (per round attivo) | `feed.dispatch` | `round_id`, `oracle_ts_ms`, `market_start_ms`, `ptb_set`, `final_set`, `skipped_reason` |
| `_dispatch` (skip) | `feed.dispatch_skip` | `round_id`, `ts_ms`, `market_start_ms`, `delta_ms`, `reason` (`"ts_before_market_start"\|"ptb_already_set"`) |
| `_ping_loop` (except) | `feed.ping_failed` | `err`, `last_btc_recv_age_sec` |
| `register` round | `feed.round_register` | `round_id`, `market_start_ms`, `last_btc_value`, `last_btc_ts_ms`, `last_btc_age_sec` |

#### 5.B — `src/round_state.py`

| Punto | Evento NDJSON | Campi |
|-------|---------------|-------|
| `apply_chainlink` (ptb impostato) | `state.ptb_set` | `round_id`, `value`, `ts_ms`, `recv_ms`, `lag_sec` |
| `apply_chainlink` (final impostato) | `state.final_set` | `round_id`, `value`, `ts_ms`, `recv_ms` |
| `apply_chainlink` (skip ts) | `state.apply_skip` | `round_id`, `ts_ms`, `market_start_ms`, `delta_ms` |
| `prime_chainlink` | `state.prime` | `round_id`, `value`, `ts_ms`, `market_start_ms`, `delta_ms`, `accepted` (bool) |

#### 5.C — `src/round_runner.py`

| Punto | Evento NDJSON | Campi |
|-------|---------------|-------|
| `sampler start` | `runner.sampler_start` | `round_id`, `lag_after_market_start_sec` |
| `first sample` | `runner.first_sample` | `round_id`, `ptb_ready` |
| `ptb captured` | `runner.ptb_captured` | `round_id`, `lag_ptb_sec`, `tick_count` |
| fine round OK | `runner.round_done` | `round_id`, `duration_sec`, `ticks`, `ptb_lag_sec` |
| fine round FAILED | `runner.round_failed` | `round_id`, `reason`, `chainlink_ts_ms`, `chainlink_recv_ms`, `price_to_beat`, `_ptb_start_ms`, `_final_end_ms`, `last_btc_age_sec` |
| fail‑fast counter | `runner.consecutive_failures` | `n`, `action` (`"warn"\|"restart_pending"`) |

#### 5.D — Formato NDJSON (esteso)

Ogni riga = un evento JSON. Schema:

```json
{"ts":1783388700.123,"loc":"feed_chainlink","evt":"btc_tick","data":{"oracle_ts_ms":1783388699123,"recv_ms":1783388700119,"gap_sec":0.996}}
```

Implementazione suggerita: un piccolo helper `src/log_ndjson.py` (singleton) che scrive su `/opt/btc5min/debug-<uuid>.log` (rotating opzionale). Sostituisce/affianca `debug-9c51e0.log` attuale.

#### 5.E — SAMPLE‑log migliorato (anti falso positivo)

In `sample_log.py`, distinguere `ptb_pending` da `ptb_captured`:

```text
SAMPLE btc=63985.15 ptb=PENDING elapsed=42s round=1783388700
SAMPLE btc=63985.15 ptb=63980.10 (lag=222s) elapsed=240s round=1783388700
```

Permette di distinguere a colpo d’occhio il “priming display” da un ptb reale.

#### 5.F — Watchdog lato servizio

In `round_runner.py`, contatore `consecutive_ptb_failures`. Se ≥ 3, loggere `runner.fail_fast_trigger` e **forzare** `chainlink_feed.force_reconnect()` (nuovo metodo) e `systemctl restart btc5min` se ≥ 5. **Criterio fail‑fast esplicito**, non implicito in systemd.

---

### 6. Raccomandazioni infra/OS

#### 6.A — Cambio OS container poly: analisi pro/contro

**Stato attuale:** Debian 12 bookworm, LXC unprivileged, kernel 6.8.12‑10‑pve (condiviso con host PVE).

| Opzione | Pro | Contro | Verdetto |
|---------|-----|--------|----------|
| **Debian 12 LXC unprivileged** (status quo) | Familiare, debug facile, Python 3.12 già buildato, replica `lobsaver` | Possibili limiti cgroup v2, fd limit, seccomp, namespace isolation (vedi H14/H20) | **Mantenere come baseline** |
| **Debian 12 LXC privileged** | Nessun UID mapping, meno vincoli su `/proc`/`/sys`, fd limit più alti | Perde isolamento sicurezza, ma poly è in LAN fidata e fa solo IO di rete | **Raccomandato test A/B** se H20 confermata |
| **Ubuntu 24.04 LTS LXC** | Python 3.12 in apt, `systemd‑resolved` di default, kernel recente | Cambio toolchain, `apt` diversi, nessun vantaggio tecnico dimostrabile | **Non raccomandato** ora |
| **Alpine 3.20 LXC** | Immagine piccola, musl, avvio veloce | Python 3.12 solo via `py3‑numpy`/community, `pandas‑compat` assente, debug più ostico | **Non raccomandato** |
| **Windows 11 Pro in VM** (VM 100) | Ambiente dev‑like, sospetta assenza bug | VM già **stopped** sul nodo; overhead 2× (RAM+CPU); poco win in LAN; sconsigliato perché non è lo scenario di deploy definitivo | **Scartato** |
| **KVM VM Debian 12** (vs LXC) | Nessun namespace, semantica “bare”, niente seccomp/namespacing LXC | Peso risorse superiore; replica poco utile se LXC non è il problema | **Riserva**: solo se LXC è confermato colpevole |
| **Rocky/AlmaLinux 9 LXC** | SELinux, RHEL‑like | Toolchain diversa, no vantaggio evidente per il workload | **Non raccomandato** |

**Raccomandazione concreta:** **non** cambiare OS ora. Prima esaurire H5/H11/H18/H22 (interventi a costo ~zero). Se dopo fix + soak test 2h il tasso di round persi resta > 5%, **allora** valutare:
1. `pct set 103 -unprivileged 0` (LXC **privileged**) — modifica di 1 attributo, nessun re‑install, 30 s di downtime.
2. Se ancora insufficiente, ricreare CT 103 come **KVM VM** Debian 12.

#### 6.B — Disattivazione firewall PVE sul CT 103

**Stato attuale:** `firewall=1` su `net0` (regola stateful di PVE host). Il CT è in LAN 10.1.1.0/24 dietro Fritz.box, senza esposizione WAN diretta.

**Raccomandazione:** **disattivare** `firewall=1` su `net0` come **azione di test rapido** (§4.D). È in LAN sicura, **non c’è valore di sicurezza aggiunto** rispetto a Fritz.box, e introduce una stateful inspection che può contribuire a H11.

Se il fix migliora la situazione: **mantenere disattivato** e documentare la scelta in `deploy-ct-lan-poly.md`.

```bash
# Da proxmox-host
pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth
```

Per ripristino: `pct set 103 -net0 ...,firewall=1,...`.

#### 6.C — Impostazioni di rete OS (lato guest)

| Parametro | Valore atteso | Razionale | Comando verifica |
|-----------|---------------|-----------|------------------|
| MTU `eth0` | 1500 (OK) | Standard Ethernet; non toccare | `ip link show eth0` |
| `net.ipv4.tcp_rmem` | `4096 87380 6291456` (default) | OK; misurare con `ss -tin` | `sysctl net.ipv4.tcp_rmem` |
| `net.ipv4.tcp_wmem` | default | OK | `sysctl net.ipv4.tcp_wmem` |
| `net.ipv4.tcp_keepalive_time` | 7200 (default) | Irrilevante: ping app 5s | non toccare |
| `net.ipv4.tcp_notsent_lowat` | suggerito `16384` | Riduce latency su socket WS | `sysctl -w net.ipv4.tcp_notsent_lowat=16384` |
| `net.core.rmem_max` / `wmem_max` | default | OK | `sysctl` |
| IPv6 | disabilitare se non usato | Evita preferenze A/AAAA strane | `sysctl -w net.ipv6.conf.all.disable_ipv6=1` (test) |
| DNS resolver | `10.1.1.1` (Fritz.box) | OK; verificare `nsswitch.conf` | `cat /etc/resolv.conf /etc/nsswitch.conf` |
| Routing | gw 10.1.1.1 | OK | `ip route` |
| `/etc/hosts` | pulito, no override strani | — | `cat /etc/hosts` |

Nessun intervento drastico richiesto. Eventuali modifiche `sysctl` vanno applicate via `/etc/sysctl.d/99-btc5min.conf` per persistenza.

#### 6.D — Conflitti con altri container/servizi

| Conflitto potenziale | Verifica |
|----------------------|----------|
| IP duplicato 10.1.1.73 | `arping -I eth0 10.1.1.73` da poly; `arp -a` da altro host |
| Conflitto MAC `BC:24:11:F1:F7:75` | improbabile in LAN gestita |
| CT 104 `lobsaver` 10.1.1.77 | non dovrebbe interferire (subnet diversa? no, stessa /24) — verificare entrambi i CGROUP memory e `pct list` |
| Router Fritz.box table NAT piena | `conntrack -L 2>/dev/null` (se accessibile); considerare `Fritz.box → Heimnetz → Heimnetzfreigaben` |
| Interferenza con `vmbr0` su PVE | `bridge link show` su proxmox-host |

#### 6.E — Hardening minimo del servizio (post‑fix)

- Aggiungere in `btc5min.service`:
  ```ini
  LimitNOFILE=16384
  ```
  Mitiga H20.
- Aggiungere `WatchdogSec=60` e `RestartPreventExitStatus=200` (per evitare loop restart su bug noto).

---

### 7. Criteri di validazione del fix

> Il fix è considerato **validato** quando **tutti** i criteri seguenti sono soddisfatti in un run collettore di **almeno 6 ore** (>= 72 round attesi) con il logging arricchito §5 attivo.

| # | Criterio | Soglia | Misura |
|---|----------|--------|--------|
| C1 | Round OK / Round attesi | **≥ 95%** | `grep -c "done " /opt/btc5min/data/collector.log` vs `floor(durata_sec/300)` |
| C2 | Eventi `price_to_beat not captured` consecutivi senza disconnect | **≤ 1** (in qualunque blocco) | analisi con `correlate_failures.py` |
| C3 | `chainlink stall` effettivamente **triggerato** in caso di gap `btc/usd` > 45s | **sì** (almeno 1 caso in 6h se il problema si ripresenta) | log NDJSON `feed.stall_detected` |
| C4 | `ws drop` Chainlink (non CLOB) | **≤ 2** in 6h | `grep -c 'chainlink ws error'` |
| C5 | Restart di systemd per fail‑fast | **0** (a regime) | `journalctl -u btc5min --since "6h ago" \| grep -c "Starting btc5min"` |
| C6 | `btc=... ptb=PENDING` nei SAMPLE | **≤ 10%** dei sample (transient fisiologico) | parser NDJSON |
| C7 | Latenza p95 `recv_ms − oracle_ts_ms` per `btc/usd` | **< 2.0 s** | log NDJSON `feed.btc_tick` |
| C8 | `verify` su tutti i `.bin` salvati | **exit 0** | `venv/bin/python3 -m src.verify /opt/btc5min/data/` |
| C9 | `feed.dispatch_skip` con `reason=ts_before_market_start` | **0** in run normali (solo post‑reconnect) | log NDJSON |

**Finestra di soak test raccomandata:**

1. Applicare i log arricchiti (§5).
2. Applicare il fix H5 (stall detector su `btc/usd`) + H18 (rifiuto `last_ts_ms < market_start` in `prime_chainlink`) + H22 (lock su `_rounds`).
3. Riavviare servizio.
4. Lasciare in esecuzione **6h** (almeno 72 round).
5. Verificare C1–C9.

Se C1 < 95%: investigare con `correlate_failures.py` e `debug-*.log`; considerare disattivazione firewall PVE (§6.B) e nuovo run.

**Test di regressione (su dev Windows) prima del deploy poly:**

- Stesso run di 6h su Windows con codice fixato + log arricchiti.
- Verifica C1–C9 anche lì (se l’osservazione lunga in dev è possibile). Se non possibile, minimo 1h (12 round attesi, soglia C1 rilassata a ≥ 90%).

---

### 8. Roadmap operativa proposta (per il prossimo turno)

1. **Scaricare** `/opt/btc5min/debug-9c51e0.log` (non in context) e analizzarlo per conferma H5/H18/H22 sui dati reali.
2. **Applicare logging arricchito** §5 (intervento non distruttivo) → nuovo run 1h → analisi.
3. **Test disattivazione firewall PVE** §4.D → run 1h.
4. **Fix mirato** su H5 (stall detector su `btc/usd`) + H18 (rigetto priming obsoleto) + H22 (lock).
5. **Soak test 6h** con criteri §7.
6. Se soak test < soglia: valutare LXC privileged e/o KVM.

---

### 9. Note di chiusura / non‑fallacie

- Il run analizzato è di **4h**; non si può escludere che un run più lungo mostri pattern diversi (es. OOM notturni, GC pause, throttling notturno del router).
- Il `verify` su `data/` non è stato eseguito nel baseline; va fatto (`venv/bin/python3 -m src.verify /opt/btc5min/data/`) per confermare l’integrità dei 11 file prima di ogni intervento.
- Il file `debug-9c51e0.log` (~138 KB NDJSON) è la **fonte primaria** per la verifica delle ipotesi H5/H18/H22 e deve essere ottenuto prima del prossimo turno.
- Tutte le azioni proposte sono **reversibili** (configurazione PVE backup, pip install `--force-reinstall`, sysctl in `/etc/sysctl.d/` rimovibile).
- Il `Restart=always` di systemd **non** è la causa dei fallimenti (non c’è crash), ma contribuisce a **ritardare** l’evidenza del degrado; sarà reso più “intelligente” con il fail‑fast counter (§5.F).

---

**Fine Turno 01 — Punto 01.** Pronto per il prossimo punto o per la validazione delle ipotesi con i dati del `debug-9c51e0.log` e del probe 30 min.