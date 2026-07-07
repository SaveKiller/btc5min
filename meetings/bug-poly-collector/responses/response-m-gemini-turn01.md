# Risposta m-gemini - Turno 01

Analizzando il codice e i log forniti, la causa principale dei round persi su container non risiede nell'infrastruttura o in problematiche OS, ma emerge chiaramente come un **bug logico nell'orchestrazione dei thread** all'interno dell'applicazione Python.

## 1. Ipotesi 

### H5.1: Stall detector bloccato dal run_forever (Causa Primaria - Probabilità 95%)
- **Dinamica:** Nel file `src/feed_chainlink.py`, il controllo di stallo sull'assenza di dati per `btc/usd` (`time.time() - self._last_msg_ts > STALL_RECONNECT_SEC`) si trova all'inizio del ciclo in `_run()`. Tuttavia, la reale esecuzione della WebSocket avviene tramite `_run_once()`, che invoca `self._ws.run_forever()`. Poiché questo metodo è bloccante, il ciclo esterno che dovrebbe effettuare i check di stallo rimane sospeso finché la WebSocket è tecnicamente "viva".
- **Evidenze:** Se lo stream di `btc/usd` si ferma ma il server non chiude esplicitamente la connessione (ad esempio inviando ping o tick di altri mercati non rilevanti), il check dello stall non interverrà mai. Ciò si allinea perfettamente all'osservazione: *«Lunghi periodi di fallimento senza log chainlink ws error né chainlink stall»*. Durante questo stallo la UI/sampler logga un `btc=...` perché `chainlink_price` mantiene i valori di priming (o obsoleti), ma `price_to_beat` rimane a `None` in attesa di un timestamp idoneo che non arriva mai.

### H5.2: Dati obsoleti (Stale data) costanti da RTDS (Probabilità 10%)
- **Dinamica:** La connessione è attiva e produce messaggi, ma il server Chainlink/Polymarket RTDS inoltra timestamp (`ts_ms`) arretrati e costantemente inferiori a `market_start_ts`.
- **Evidenze:** Il metodo `apply_chainlink` aggiorna `chainlink_price` permettendone la stampa nel sampler, ma poi usa `if ts_ms < self._ptb_start_ms: return` ignorando l'assegnazione per `price_to_beat`. Potrebbe spiegare i fallimenti per `ptb`, ma non giustifica appieno l'assenza di update del prezzo su lunghi periodi.

### H6: Problemi OS / Networking / Container (Probabilità < 5%)
- **Dinamica:** Interazioni problematiche a livello kernel TCP in Debian 12 o timeout/drop causati dal networking di Proxmox o NAT del FritzBox.
- **Evidenze:** Già esclusi di fatto dai test di probe (`probe_btc_gaps.py`) eseguiti sia su Windows locale che su container. Il probe di 10 minuti non ha presentato drop di connessione WS e i valori di latenza risultano nella norma.

## 2. Test e Piano di Debug

Per provare definitivamente l'H5.1 e fornire dati all'implementazione:

1. **Spostamento logico dello Stall Detector in thread libero:**
   Implementare il check dello stallo in `_ping_loop`, l'unico thread ausiliario sempre attivo durante la vita della WebSocket e non bloccato dal `run_forever`.
   ```python
   def _ping_loop(self) -> None:
       while not self._ping_stop.is_set() and not self._stop.is_set():
           if self._last_msg_ts and time.time() - self._last_msg_ts > STALL_RECONNECT_SEC:
               log.warning("chainlink stall %.0fs, reconnecting", time.time() - self._last_msg_ts)
               self._close_ws(intentional=True)
           # ...
   ```

2. **Diagnostica sui Timestamp e Scarti in `round_state.py` / `feed_chainlink.py`:**
   Produrre log NDJSON specifici ogni volta che un `ts_ms < market_start_ms` ignora il ptb per evitare dubbi su H5.2. Aggiungere il log suggerito in `_dispatch` con la `skipped_reason`.

3. **Migliorare reportistica ciclo vita della WS:**
   Modificare gli handler `_on_close` e `_on_error` registrando il `last_btc_msg_age_sec`, per identificare se l'errore che rompe la connessione fa seguito a periodi di mancata ricezione dati (`btc/usd`).

## 3. Criteri di Validazione Fix

- **Fine stalli silenziosi:** Dopo aver inserito lo stall detector in `_ping_loop`, non devono più accumularsi round sequenziali che terminano con eccezione per `price_to_beat not captured` prolungato oltre i 45 secondi. Al presentarsi del blocco, il log deve riportare immediatamente `chainlink stall` e ripristinare il flusso per il round in corso o il successivo.
- **Test prolungato (Soak Test):** Validazione di 1-2 ore con il demone attivo sul CT `poly`. Il rapporto round generati / tempo di up dovrà allinearsi alle attese teoriche (es. ~12 file all'ora).

## 4. Raccomandazioni Infra/OS

- **Sistema Operativo e Container:** Sconsiglio caldamente di sostituire Debian 12 o abbandonare l'architettura LXC unprivileged di Proxmox, poiché la natura del bug è a livello applicativo e non di container. 
- **Firewall e Networking:** Sconsiglio di disattivare il firewall integrato in PVE, in quanto il networking locale e l'uscita HTTPS appaiono robusti e ottimali. Eventuali modifiche aprirebbero inutili vulnerabilità e non andrebbero a incidere sulla logica asincrona della libreria `websocket-client`. Invariato anche lo stack di rete corrente che risponde egregiamente nei probe testuali.