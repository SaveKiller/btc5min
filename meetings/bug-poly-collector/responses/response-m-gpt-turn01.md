# Risposta m-gpt - turno 01

## Punto 01

### Sintesi tecnica

La causa piu' probabile non e' Debian 12/LXC/firewall, ma una combinazione di **feed Chainlink RTDS vivo a livello WebSocket ma non piu' utile per `btc/usd`**, **watchdog applicativo inefficace mentre `run_forever()` e' bloccante**, e **stato Chainlink vecchio usato come prezzo "ready" per i round nuovi**.

Il fatto decisivo, ancorato alla baseline e al report, e' questo: in circa 4 ore poly salva 11 round invece dei ~48 attesi; ci sono ~34 eventi `price_to_beat not captured`, 2 eventi `chainlink final not captured`, solo 2 `chainlink ws error` / close `Going away`, e 0 `chainlink stall`. Quindi i round falliscono molto piu' spesso delle disconnessioni esplicite.

Un dettaglio codice importante: in `src/feed_chainlink.py` il controllo `STALL_RECONNECT_SEC` e' nel ciclo esterno di `_run()`, ma `_run_once()` chiama `self._ws.run_forever()` e resta li' finche' la WS non chiude. Di conseguenza lo stall detector non puo' chiudere una connessione gia' aperta ma silenziosa/zombie. Questo spiega perche' nel log non compare mai `chainlink stall` durante i lunghi buchi.

### Ipotesi ordinate per probabilita'

| ID | Prob. | Ipotesi | Evidenze a favore | Test decisivo |
|---|---:|---|---|---|
| H1 | 35% | Watchdog Chainlink inefficace: la WS resta aperta ma non arrivano tick BTC utili; nessun thread chiude `run_forever()` | 0 `chainlink stall`; lunghi blocchi senza `ws error`; codice controlla lo stall solo prima/dopo `run_forever()` | Loggare `last_btc_age_sec` ogni 5s da thread separato e forzare `_close_ws()` se >15s |
| H2 | 25% | RTDS/Polymarket smette di inviare `btc/usd` su connessioni long-lived, ma riparte con reconnect | Dopo close `Going away` il collector riprende; probe fresh 10 min OK su poly e Windows; fallisce solo long-run collector | Soak 3-4h con probe fresh parallelo e collector: se probe riceve BTC mentre collector no, e' connessione/subscription degradata |
| H3 | 15% | `prime_chainlink()` e `chainlink_ready()` espongono prezzo vecchio come se fosse live | Round parziale `1783384500`: prime righe con `btc=64229.11` costante e delta +219$, poi ptb reale a `64009.95`; `price_to_beat` arriva con lag 222s | Loggare `last_value_recv_age_sec` e impedire sample/prime se il tick ha age >10s |
| H4 | 8% | Cattura `final_chainlink` dipende da tick post-end; se feed tace nei 30s finali il round fallisce | Due `chainlink final not captured`; stesso pattern dei PTB persi | Log a fine round: ultimo tick BTC, ultimo `recv_ms`, eta' ultimo tick, `_final_source` |
| H5 | 5% | Ping loop non chiude la WS su errore di send, lasciando connessione zombie | `_ping_loop()` fa `return` su eccezione senza `_close_ws()` e senza log | Loggare errore ping e chiudere WS su primo send fail |
| H6 | 4% | Server RTDS chiude periodicamente ogni ~2h (`Going away`) e il client non gestisce bene la fase precedente | Close a 00:38 e 02:38, quasi esattamente 2h; ma i fallimenti iniziano molto prima del close | Reconnect proattivo ogni 15-30 min: se spariscono i buchi, il long-lived e' il trigger |
| H7 | 3% | NAT/router/firewall PVE degrada connessioni long-lived | H4 nel report e' inconclusive; CLOB drop presenti; ambiente LAN con PVE firewall attivo | A/B 4h con firewall CT off vs on, piu' tcpdump/ss |
| H8 | 2% | DNS/IPv6/routing o MTU intermittente | Probe e ping OK; MTU 1500; stessa LAN | Forzare IPv4 nei test, `mtr`, `tcpdump`, `ss -tinp` durante buco |
| H9 | 2% | Bug/libreria `websocket-client`/Python 3.12 su Debian LXC | Possibile ma non supportato: probe usa stessa libreria e va bene per 10 min | Test stesso codice 4h su Windows e su Debian VM non-LXC |
| H10 | 1% | Clock/timezone o timestamp Polymarket sbagliati | UTC sincronizzato; round OK hanno timestamp corretti | `timedatectl`, log offset oracle `recv_ms - ts_ms` su ogni tick |

### Diagnosi principale

La sequenza piu' coerente e':

1. Il collector parte e riceve tick BTC validi: 6 round OK.
2. A un certo punto la connessione resta formalmente aperta, ma il callback non riceve piu' tick BTC live oppure non riceve tick utilizzabili.
3. Il watchdog non interviene perche' e' fuori da `run_forever()`.
4. I nuovi round vengono registrati e ricevono `prime_chainlink(last_value, last_ts_ms)`, quindi `chainlink_ready()` diventa vero anche con un prezzo vecchio.
5. `RoundState.apply_chainlink()` imposta `chainlink_price` prima del check `ts_ms < _ptb_start_ms`; quindi lo stato puo' mostrare `btc=...` ma `ptb=None`.
6. Il sampler puo' scrivere sample con prezzo vecchio o senza ptb; a fine round scatta `price_to_beat not captured`.
7. Quando il server chiude con `Going away`, il client si riconnette e il feed riprende; il round `1783384500` cattura ptb con lag enorme e salva un file parziale.

Il punto piu' sottovalutato e' che il valore BTC nei SAMPLE non prova che il feed sia sano: puo' essere un valore vecchio primed o l'ultimo valore ricevuto prima del blocco. Serve sempre associare al prezzo anche `recv_age_sec` e `oracle_age_sec`.

### Test proposti

#### Test A - Soak collector con debug feed 4h

Obiettivo: confermare se il collector smette di ricevere BTC senza close/error.

Comandi suggeriti su poly:

```bash
ssh ticksaver "cd /opt/btc5min && systemctl stop btc5min"
ssh ticksaver "cd /opt/btc5min && mv data/collector.log data/collector.$(date -u +%Y%m%dT%H%M%SZ).log 2>/dev/null || true"
ssh ticksaver "cd /opt/btc5min && BTC5MIN_DEBUG=1 /opt/btc5min/venv/bin/python3 -m src.main"
```

Metriche da estrarre ogni 5 minuti:

```bash
ssh ticksaver "grep -E 'chainlink|price_to_beat|final_chainlink| failed| done ' /opt/btc5min/data/collector.log | tail -200"
ssh ticksaver "grep -c ' done ' /opt/btc5min/data/collector.log; grep -c 'price_to_beat not captured' /opt/btc5min/data/collector.log; grep -c 'final not captured' /opt/btc5min/data/collector.log"
```

Esito atteso se H1/H2 sono vere: `last_btc_age_sec` cresce oltre 15-45s senza `_on_close`, senza `_on_error`, e i round successivi falliscono finche' non avviene reconnect.

#### Test B - Probe fresh parallelo vs collector

Obiettivo: distinguere problema di rete generale da problema della singola connessione/subscription del collector.

```bash
scp meetings/bug-poly-collector/context/scripts/probe_btc_gaps.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/probe_btc_gaps.py 14400"
```

Far girare il probe in parallelo al collector per 4h. Se il probe nuovo riceve tick regolari mentre il collector perde PTB, non e' LXC/rete generale: e' gestione long-lived/subscription nel collector.

#### Test C - Probe long-lived identico al feed

Serve uno script che usi proprio `ChainlinkFeed.get()`, non solo `websocket.WebSocketApp` minimale. Deve registrare un `RoundState` finto ogni 5 minuti e loggare:

- tick BTC ricevuti;
- `last_btc_age_sec`;
- `last_value_recv_age_sec`;
- ptb catturato entro T+5s;
- close/error/ping fail.

Durata minima: 3h, per superare almeno una chiusura `Going away` e verificare se compare il buco pre-close.

#### Test D - Fix provvisorio: reconnect aggressivo

Applicare solo come esperimento:

- monitor thread dentro `ChainlinkFeed`;
- chiusura WS se `last_btc_age_sec > 15`;
- reconnect proattivo ogni 20-30 minuti;
- chiusura WS su errore ping.

Validazione: se in 4h i round tornano quasi tutti OK, il problema e' confermato come gestione feed/stale WS e non OS.

#### Test E - A/B firewall PVE

Non lo metterei come primo fix, ma e' un test economico.

Su Proxmox:

```bash
ssh proxmox-root "pct config 103 | grep net0"
ssh proxmox-root "pct set 103 -net0 name=eth0,bridge=vmbr0,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth,firewall=0"
ssh proxmox-root "pct reboot 103"
```

Poi run collector 4h. Ripetere con `firewall=1`. Se non cambia nulla, firewall escluso. Se cambia, verificare regole PVE e log firewall.

#### Test F - OS/container comparison

Solo dopo aver testato watchdog/reconnect:

1. stesso CT Debian 12 LXC con firewall off;
2. nuovo CT Ubuntu 24.04 LTS unprivileged;
3. VM Debian 12 minimale su Proxmox, non LXC;
4. Windows solo come confronto, non target.

Durata minima per ogni ambiente: 4h, idealmente 8-12h.

### Logging da aggiungere

#### `feed_chainlink.py`

Campi minimi per ogni evento importante:

- `conn_id` progressivo;
- `conn_open_ts`, `connected_sec`;
- `last_any_msg_age_sec`;
- `last_btc_msg_age_sec`;
- `last_btc_oracle_ts_ms`;
- `last_btc_recv_ms`;
- `last_btc_oracle_age_sec = recv_ms - oracle_ts_ms`;
- `payload_shape`: `live` o `batch`;
- `batch_count`, `batch_min_ts_ms`, `batch_max_ts_ms`;
- close code/msg;
- errore ping.

Eventi:

```text
chainlink open conn_id=...
chainlink subscribed conn_id=...
chainlink btc tick value=... oracle_ts_ms=... recv_ms=... oracle_age=...
chainlink btc gap gap_sec=...
chainlink btc stall age=... closing
chainlink close code=... msg=... connected_sec=... last_btc_age=...
chainlink ping error err=... closing
```

Nota: il controllo stall deve stare in un thread/loop separato che gira mentre `run_forever()` e' attivo. Tenerlo solo nel ciclo esterno non basta.

#### `round_state.py`

Loggare una sola volta per round, non a ogni tick:

- primo tick ricevuto per il round;
- primo tick scartato per `ts_ms < _ptb_start_ms`;
- ptb catturato con `lag_ptb_sec`;
- final catturato con `source=oracle|recv`;
- eta' del tick usato.

Esempio:

```json
{"event":"ptb_skip","round":1783384500,"oracle_ts_ms":1783384278000,"market_start_ms":1783384500000,"delta_ms":-222000,"value":64229.11}
{"event":"ptb_set","round":1783384500,"oracle_ts_ms":1783384722000,"lag_ptb_sec":222.0,"value":64009.95}
```

#### `round_runner.py`

A fine round, sia OK sia failed:

- `tick_count`;
- `first_sec`, `last_sec`;
- `ptb_ready`;
- `ptb_lag_sec`;
- `final_ready`;
- `final_source`;
- `last_chainlink_price`;
- `last_chainlink_ts_ms`;
- `last_chainlink_recv_age_sec`;
- snapshot diagnostico del feed: `conn_id`, `last_btc_age_sec`, `connected_sec`.

In caso di fallimento, scrivere anche un file `data/failures/round_<ts>.json` per non perdere il contesto.

#### `sample_log.py`

Modificare il SAMPLE per non stampare solo `btc=...`, ma:

```text
btc=64009.95 btc_age=1.2s oracle_age=0.8s ptb=-
```

Se `btc_age > 10s`, stampare `btc_stale=...` invece di `btc=...`. Questo evita il falso senso di feed sano.

### Fix candidati da validare

#### Fix 1 - Watchdog reale sul feed BTC

Implementare un thread monitor nel `ChainlinkFeed`:

- parte a `_on_open`;
- ogni 2-5 secondi controlla `time.time() - _last_btc_recv_monotonic`;
- dopo una grace iniziale di 10-15s, se non arrivano tick BTC per 15s chiude la WS;
- logga motivo `btc_stall`.

Soglia consigliata: 15s per il collector 5m. Il probe mostra gap max ~8.3s, quindi 15s e' abbastanza conservativo e molto sotto i 45s attuali.

#### Fix 2 - Non considerare ready un prezzo primed/stale

`prime_chainlink()` non dovrebbe rendere il round pronto per campionare se il valore e' vecchio. Opzioni:

- aggiungere `last_value_recv_ms` e prime solo se `age <= 10s`;
- separare `chainlink_display_price` da `chainlink_live_price`;
- `chainlink_ready()` deve essere vero solo dopo un tick BTC fresco ricevuto durante la finestra del round.

Questa correzione evita file come `1783384500`, dove le prime righe mostrano un BTC vecchio di centinaia di dollari rispetto al ptb reale.

#### Fix 3 - Reconnect proattivo periodico

Anche con watchdog, fare reconnect pulito ogni 20-30 minuti o ogni 4-6 round riduce il rischio di subscription long-lived degradata. Per un mercato da 5 minuti e' accettabile se il reconnect dura pochi secondi e se non avviene esattamente a T+0/T+300.

#### Fix 4 - Gestione robusta del final

Se il feed e' sano, `final_chainlink` deve arrivare subito dopo `market_end_ts`. Se non arriva:

- aspettare fino a 30s come ora;
- ma loggare `last_btc_age_sec`;
- opzionalmente usare fallback `recv` solo se il tick e' fresco (`recv_age <= 5s`) e `oracle_ts_ms` e' vicino alla fine;
- in parallelo interrogare Gamma dopo chiusura per `finalPrice` come verifica esterna, non come sostituto silenzioso.

#### Fix 5 - Gamma `priceToBeat` come controllo incrociato

Il codice legge `eventMetadata.priceToBeat` ma poi non lo usa per inizializzare il round. Suggerisco di loggare sempre:

- `gamma_price_to_beat`;
- `chainlink_price_to_beat`;
- differenza.

Se Gamma espone `priceToBeat` in tempo utile, si puo' decidere di usarlo come fonte primaria del PTB Polymarket e Chainlink come feed live/final, ma questa va validata: non va introdotta come fallback silenzioso senza capire quando Gamma aggiorna quel campo.

### Validazione del fix

Un fix e' valido solo se supera questi criteri:

| Criterio | Soglia |
|---|---:|
| Durata soak su poly | minimo 4h, meglio 12-24h |
| Round attesi salvati | >= 98% su 4h; idealmente 100% esclusi avvii gia' iniziati |
| `price_to_beat not captured` | 0 |
| `chainlink final not captured` | 0 |
| `ptb_lag_sec` | p95 <= 3s, max <= 10s |
| `last_btc_age_sec` durante sample | p95 <= 5s, max <= 15s |
| Tick count | >=295 per round completo, salvo ultimi secondi di book chiuso |
| File parziali con stale BTC | 0 |
| Reconnect | motivati da `btc_stall`, ping error o reconnect proattivo; mai buchi muti |

Controlli post-run:

```bash
ssh ticksaver "grep -c ' done ' /opt/btc5min/data/collector.log"
ssh ticksaver "grep -c 'price_to_beat not captured' /opt/btc5min/data/collector.log"
ssh ticksaver "grep -c 'chainlink final not captured' /opt/btc5min/data/collector.log"
ssh ticksaver "grep -E 'btc stall|chainlink close|ping error|ptb captured|final_chainlink' /opt/btc5min/data/collector.log | tail -300"
ssh ticksaver "cd /opt/btc5min && /opt/btc5min/venv/bin/python3 -m src.verify data"
```

### Raccomandazioni OS/rete/firewall

#### Sistema operativo

Non raccomando un cambio OS come prima azione. Debian 12 LXC unprivileged e' compatibile con lo scopo: il probe 10 min e' identico a Windows/poly, il clock e' UTC/sincronizzato, risorse e rete sono sane, e il pattern dei log punta al feed applicativo.

Cambiare OS prima di correggere watchdog/stale state rischia di spostare il problema senza capirlo. Se dopo il fix applicativo restano fallimenti, allora il confronto piu' utile e':

1. VM Debian 12 minimale su Proxmox, stessa rete bridge, per escludere LXC;
2. CT Ubuntu 24.04 LTS unprivileged, per cambiare userland ma non architettura;
3. Windows solo come soak diagnostico, non come target 24/7.

#### Firewall CT

Disattivarlo e' ragionevole come esperimento A/B perche' il CT e' in LAN e il collector fa quasi solo traffico outbound. Pero' non lo considero causa primaria: i WebSocket RTDS ricevono traffico continuo e il probe non mostra loss. La disattivazione puo' restare se semplifica la macchina, ma non deve essere venduta come fix finche' non supera un confronto on/off di pari durata.

#### Rete

Controlli consigliati durante un buco:

```bash
ssh ticksaver "date -u; timedatectl"
ssh ticksaver "ip addr show eth0; ip route; resolvectl status || cat /etc/resolv.conf"
ssh ticksaver "getent ahostsv4 ws-live-data.polymarket.com; getent ahostsv4 gamma-api.polymarket.com"
ssh ticksaver "ss -tinp | grep -E '443|python' || true"
ssh ticksaver "ping -c 20 10.1.1.1"
ssh proxmox-root "pct config 103"
ssh proxmox-root "pve-firewall status"
```

Se serve prova pacchetti:

```bash
ssh proxmox-root "tcpdump -i vmbr0 host 10.1.1.73 and port 443 -w /tmp/poly-ws.pcap"
```

Il dato da cercare non e' solo "la TCP e' aperta", ma se arrivano frame dal server mentre il collector non produce tick BTC. Se arrivano frame ma non BTC, e' subscription/protocollo; se non arrivano frame ma la socket resta established, e' rete/NAT/server idle.

### Raccomandazione finale

Procederei in questo ordine:

1. Aggiungere logging strutturato minimo su feed/round, soprattutto `last_btc_age_sec`, `btc_age`, close/error/ping e ptb skip.
2. Implementare watchdog reale in thread separato e chiusura WS su BTC stall >15s.
3. Impedire che un valore `prime_chainlink` vecchio renda il round `chainlink_ready`.
4. Fare soak 4h su poly con firewall invariato.
5. Solo se fallisce, fare A/B firewall off e poi confronto VM/Ubuntu.

La priorita' e' evitare round persi per feed muto: il collector deve accorgersi entro pochi secondi che BTC non e' fresco e riconnettersi, invece di aspettare la chiusura server ogni ~2 ore.
