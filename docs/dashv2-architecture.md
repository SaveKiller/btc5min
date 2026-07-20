# dashV2 — Architettura di riferimento

Documento canonico sull’architettura della dashboard replay (`dashv2/`).  
Destinato a guidare estensioni future (strategie automatiche, modalità live, nuovi pannelli UI, nuovi account/ledger, ecc.).

In caso di conflitto tra questo documento e `AGENTS.md`, prevale il codice; aggiornare questo file quando l’architettura cambia in modo strutturale.

---

## 1. Cos’è dashV2 e a cosa serve

**dashV2** è la webapp di **replay interattivo** dei round del mercato Polymarket **BTC Up or Down 5m**, salvati in locale sotto `data/` come coppia `.bin` + `.txt`.

Permette di:

1. Caricare un round storico in memoria.
2. Riprodurre la timeline a **1 Hz** (o x2 / x5) lungo l’asse `sec` (secondi mancanti a scadenza: 300 → 0).
3. Vedere in sync: prezzo BTC Chainlink, delta vs PTB, quote Up/Down, ladder, volatilità, rischio Rq/Rs, DWinA/B, candele 5m causali.
4. Piazzare ordini simulati sul book CLOB del tick corrente (BUY walk ask + fee), chiuderli (SELL walk bid) o lasciarli andare a settlement a sec 0.
5. Persistere i risultati su un **ledger per account** in JSON sotto `dashv2/history/accounts/`.
6. Processo **bot** sempre attivo (co-controller Socket.IO): scatola vuota finché non si carica almeno una **Strategy**; ordini taggati `source: user|bot`, canale `consult.*` peer.
7. Processo **Engine** sempre attivo (pipe col server): shell stabile + **una** plugin (`replay` | `live` | …) scelta solo a startup da `setup.json`.

### Perché esiste (vs dash V1)

La V1 (`dash/` + `dash-api/`) separava web server e API in due stack; la comunicazione e il lifecycle erano più fragili.  
La V2 nasce da un disegno esplicito (vedi `docs/dash-prompt-v2.md`):

- **un solo entrypoint** (`python -m dashv2`);
- **tre processi** con ruoli netti (bridge UI, Engine+plugin, bot/strategy shell);
- **pipe unidirezionali** per IPC veloce e isolato (solo server ↔ Engine);
- UI statica offline (no CDN obbligatori), layout da mockup v38;
- **anti-spoiler** rigoroso fino a sec 0.

### Roadmap / stato

| Fase | Sorgente / feature | Stato |
|------|--------------------|-------|
| Replay file | Plugin `replay` (`.bin`/`.txt`) | Implementato |
| Engine shell + plugin | Processo `dashv2-engine` + load da `engine_plugin` | Implementato |
| Live Polymarket | Plugin `live` stub | Predisposto (no feed/trading reali) |
| Endpoint `/replay` e `/live` | Stessa UI, plugin diversa per entrypoint | Solo documentale |
| Bot processo fisso | Spawn con server/engine; Socket.IO `role=bot`; soft-crash + respawn | Implementato |
| Strategy load (shim) | `bot.select` → stato engine + forward `strategy.load` → plugin `*_bot.py` | Implementato (es. `random`) |
| Strategy types | DETERMINISTICA / INFERENZIALE / AGENTICA | Solo documentale (piano separato) |
| Consulto peer | `consult.send` / `consult.message` sul bridge | Predisposto (relay + hook plugin; UI chat da fare) |
| Tab AGENT (Backtest/Analyze) + RoundBatch | Job backtest/analyze sul **server** (`stats.*`, pool) | Implementato |

---

## 2. Principi architetturali

Questi vincoli **non** vanno indeboliti senza aggiornare esplicitamente questo documento e i test.

| # | Principio | Implicazione pratica |
|---|-----------|----------------------|
| P1 | **Fail-fast server+engine** | Se server o Engine muore, l’altro viene terminato (`__main__.py`). Il bot **non** è nel fail-fast: crash → log + respawn soft. |
| P2 | **Server = bridge** | `server.py` non simula clock replay né settlement UI; routing ruoli, ACL, consult relay, forward `strategy.load`, orchestrazione **Stats/agent** locali (no pipe). |
| P3 | **Engine = shell; plugin = dominio** | Il processo Engine parla via pipe col server. Round, clock, ordini, settlement, **account/history** vivono nella **plugin** attiva (`replay` / `live`). Una sola plugin per processo. |
| P4 | **Pipe unidirezionali** | Cmd solo server→Engine; evt (response + event) solo Engine→server. Il bot **non** usa le pipe: parla solo Socket.IO col server. |
| P5 | **Due co-controller Socket.IO** | `human_sid` + `bot_sid`; stessa priorità/latenza; ACL per ruolo (bot: solo order.* + sync + consult). |
| P6 | **Anti-spoiler** | Picker senza outcome; outcome UI solo a `round_end` / sec 0. |
| P7 | **Causalità timeline** | Chart e scrub non espongono tick futuri rispetto a `sec` di replay. |
| P8 | **Fee CLOB reale** | Walk su book del tick + `fee_rate` header `.bin`; **non** usare `gain%` del `.txt`. |
| P9 | **Riuso `src/`** | Nessun reader binario duplicato; `read_round`, walk CLOB, risk da moduli core. |
| P10 | **Config fail-hard** | Chiavi obbligatorie in `setup.json`; niente default silenziosi (`config.py`). |
| P11 | **Spawn, non fork** | `multiprocessing.set_start_method("spawn", force=True)` (Windows + isolamento pulito). |
| P12 | **Actor / source** | Bridge inietta `actor`; ordini hanno `source: user\|bot`; evento `action` per mutazioni. (Futuro multi-strategy: campo `strategy_id` aggiuntivo; oggi solo `source: bot`.) |
| P13 | **Bot = shell; Strategy = logica** | Il processo bot è sempre su; senza strategy non emette trade. Il server scambia messaggi di trading solo col bot, mai direttamente con una strategy. |
| P14 | **Niente hot-swap plugin Engine** | La plugin Engine si sceglie solo a startup (`engine_plugin` in setup). Cambio plugin ⇒ restart completo (rilegge setup). |

---

## 3. Vista d’insieme

```
  Browser (human) ──┐
                    ├── Socket.IO ──► ServerBridge ──pipe CMD──► Engine process
  Bot process ──────┘                      │                    + plugin (replay|live|…)
  (sempre spawnato)                        │
  + Strategy* dentro                       ├── broadcast eventi ──► human + bot
                                           │
                                           strategy.load = forward server→bot (no pipe)
                                           consult.* = peer relay (no pipe data)
                                           stats.* = batch locale sul server (no pipe)
                                             └─ ProcessPool → strategy/analyze workers
```

- Fail-fast: `dashv2-server` + `dashv2-engine`.
- Bot (`dashv2-bot`): processo strutturale; crash → soft (log + respawn); senza strategy connesso ma inerte.
- Engine (`dashv2-engine`): shell + **una** plugin da `engine_plugin` in `setup.json` (oggi tipicamente `"replay"`). Nessun hot-swap: cambio plugin ⇒ restart.
- Shell Engine senza plugin (`engine_plugin: null`): pipe viva, nessun dominio — utile come capacità; in pratica setup punta a `replay` o `live`.
- **Stats / RoundBatch:** i job vivono **solo nel processo server** (`RoundBatchRunner` + `ProcessPoolExecutor`). Engine e bot **non** partecipano; replay UI può restare attivo durante un batch.

**Nota lessicale — “Engine”:** processo OS stabile (`dashv2/engine/process.py`). Non confondere con la **plugin** (`replay` / `live`) né col server (solo bridge). Non confondere con `OrderEngine` in `orders.py` riusato headless nei worker batch.

Avvio: `dashv2.bat` oppure `python -m dashv2` dalla root repo → URL da `setup.json` (default `http://127.0.0.1:8780/`).

Dipendenze Python: `pip install -r dashv2/requirements.txt` (Flask-SocketIO, python-socketio, eventlet/threading).  
Frontend: nessun build step; HTML/CSS/JS + vendor locali sotto `dashv2/static/`.

---

## 4. Bootstrap e lifecycle dei processi

File: [`dashv2/__main__.py`](../dashv2/__main__.py)

### Sequenza di avvio

1. `mp.set_start_method("spawn", force=True)`.
2. `load_config()` da `dashv2/setup.json` (path risolti, `history_dir` creato se manca, `data_dir` deve esistere).
3. Se esiste `data_dir/restart` **prima** dello spawn → lo elimina (niente doppio boot da sentinella residua).
4. Creazione di **due** `mp.Pipe(duplex=False)`:
   - `eng_recv_cmd` ← `server_send_cmd` (comandi verso l’Engine);
   - `server_recv_evt` ← `eng_send_evt` (response ed eventi verso il server).
5. Avvio `Process(target=run_engine_process, name="dashv2-engine")`.
6. Avvio `Process(target=run_server_process, name="dashv2-server")`.
7. Avvio `Process(target=run_bot_process, name="dashv2-bot")` — sempre, anche senza strategy.
8. Il processo padre entra in un loop di watchdog ogni 2 s:
   - se esiste `data_dir/restart` → cancella la sentinella, terminate+join dei **tre** figli, `os.execv(python, ["-m", "dashv2"])` (reload completo);
   - se server o Engine non è `alive` → `_shutdown()` (terminate + join timeout 3 s) e `sys.exit(0)`;
   - se solo il bot non è `alive` → log soft + **respawn** del solo processo bot (dash continua).
9. SIGINT / SIGTERM → stesso `_shutdown` (termina anche il bot).

### Perché spawn + due pipe

- **spawn**: su Windows è l’unico metodo affidabile; evita stato ereditato da fork e rende i processi indipendenti.
- **Due pipe unidirezionali**: direzione del flusso esplicita; demux response/event sul lato server.
- **Bot fuori dalle pipe**: stesso trasporto del browser (Socket.IO).

### Cosa **non** fa il processo padre

Non inoltra messaggi, non conosce Socket.IO, non tocca i round. È solo launcher + fail-fast (server/Engine) + soft-respawn bot + restart su sentinella.

---

## 5. Protocollo IPC (`dashv2/ipc.py`)

Tutti i messaggi tra i due processi sono **dict JSON-serializzabili** (pickle via `multiprocessing.connection`).

### Envelope

| `kind` | Campi | Direzione |
|--------|-------|-----------|
| `request` | `request_id`, `cmd`, `payload` | server → data (pipe CMD) |
| `response` | `request_id`, `payload` **oppure** `error` | data → server (pipe EVT) |
| `event` | `name`, `payload` | data → server (pipe EVT) |

Factory: `make_request`, `make_response`, `make_error`, `make_event`.  
Predicate: `is_response`, `is_event`.

### Regole importanti

1. **Response ed event condividono la stessa pipe EVT.** Il server demultiplexa in `_evt_reader_loop`:
   - response → sblocca il `threading.Event` del `request_id` pendente;
   - event → `socketio.emit(name, payload, to=controller_sid)`.
2. Ogni request ha un `request_id` (UUID hex) usato per correlare la response.
3. L’Engine **non** scrive sulla pipe CMD; il server **non** scrive sulla pipe EVT.
4. Errori di comando: `make_error(request_id, message)` → il bridge li traduce in Exception / ack `{error: ...}` / evento `error` (solo per `round.load` async).

### Pattern speciale: `round.load`

Il load di un round può essere I/O pesante. Per non bloccare il thread Socket.IO:

1. Il browser emette `round.load`.
2. Il bridge risponde subito con ack `{ok: true}` e lancia un thread che chiama `_request_to_data(..., timeout=120)`.
3. L’engine, in `_handle_cmd`, per `round.load` invia **prima** la response IPC, **poi** esegue `after()` che emette session/chart/tick/orders/history/accounts.
4. Se il load fallisce, il bridge emette l’evento Socket.IO `error` (non un ack di errore, perché l’ack era già andato).

---

## 6. Processo SERVER — `ServerBridge`

File: [`dashv2/server.py`](../dashv2/server.py)  
Entry: `run_server_process(cfg, cmd_conn, evt_conn)`.

### Responsabilità

| Fa | Non fa |
|----|--------|
| Serve `static/` (route `/` → `index.html`) | Caricare / parsare round **per replay** (lo fa la plugin Engine) |
| Socket.IO verso il browser | Avanzare il clock replay |
| Tradurre emit client → `ipc.make_request` sulla pipe CMD | Simulare ordini / fee **nel replay live** |
| Tradurre response/event dalla pipe EVT → ack / emit | Anti-spoiler business |
| Enforce un solo controller | Persistenza history account (plugin replay) |
| Comandi `stats.*` / `agent.*` locali (no pipe) | Forward batch all’Engine |
| Orchestrazione RoundBatch (`ProcessPoolExecutor`) | Scrivere ledger account dai job Stats |

### Stack

- Flask con `static_folder=dashv2/static`, `static_url_path=""`.
- `SocketIO(..., cors_allowed_origins=[], async_mode="threading")`.
- Thread daemon `_evt_reader_loop` che fa `evt_conn.poll(0.1)` in loop.
- Job Stats: thread OS + `RoundBatchRunner` (pool da `stats_workers`); eventi `stats.job.*` emessi dal bridge.

### Controller session

- Connect con `auth.role == "bot"` → slot `bot_sid` (un solo bot).
- Altrimenti → slot `human_sid` (un solo browser).
- Secondo bot: `connect` rifiutato. Secondo human: **replace** dello slot (ri-connect dopo drop/zombie).
- Eventi engine: broadcast a **entrambi** i sid presenti.
- ACL: bot solo `order.*`, `session.sync`, `consult.send`; human tutto il resto + `bot.*`.
- Bridge inietta `actor: user|bot` su ogni request IPC (non spoofabile dal client).
- `consult.send`: peer relay sul bridge (**non** passa all’Engine); emit `consult.message` al peer e echo al mittente.
- Disconnect human: pause replay best-effort.
- Disconnect socket bot: log console + `bot.status` con `bot_connected: false`; server/data restano vivi; il processo bot ritenta la connect.
- `bot.select`: aggiorna stato in engine, poi **forward** `strategy.load` al `bot_sid` (niente spawn/kill processo).
- Al (ri)connect del bot: bridge fa `bot.list` IPC e re-forward `strategy.load` se c’è una strategy selezionata.

### Timeout

| Costante | Valore | Uso |
|----------|--------|-----|
| `_ACK_TIMEOUT_SEC` | 30 | Comandi sincroni |
| `_ROUND_LOAD_TIMEOUT_SEC` | 120 | Solo `round.load` async |

Timeout IPC → `Exception("ipc timeout waiting for {cmd}")` → ack `{error: "..."}` (o evento `error` per load).

### Comandi Socket.IO bindati

```
round.load, round.unload, rounds.list,
replay.play, replay.pause, replay.speed, replay.seek, replay.preview,
order.size, order.preview, order.place, order.close, order.cancel,
account.list, account.select, account.create, account.rename, account.update,
bot.list, bot.select, bot.set_active, session.sync,
stats.backtest.start, stats.analyze.start, stats.job.cancel,
stats.chat.send, stats.chat.history, stats.rules.apply,
stats.analyze.list, stats.analyze.delete,
stats.simulation.list, stats.simulation.load, stats.simulation.delete
```

Più peer relay (non IPC): `consult.send` → evento `consult.message`.  
Più locali (non IPC): `agent.*`, `stats.*` — gestiti nel bridge, **non** forward alla pipe Engine.

Stub engine `controller.claim` / `controller.release` esistono ma **non** sono esposti dal server.

### Linee guida per estendere il server

- Nuovo comando UI → ACL (`_HUMAN_CMDS` / `_BOT_CMDS`) **e** handler in engine (se tocca stato round). Eccezione: `stats.*` / `agent.*` restano **solo sul server**.
- Bridge: routing, timeout, ruoli, consult relay, forward strategy, orchestrazione Stats — non logica di settlement/clock replay e **non** spawn del processo bot.
- Nuovi eventi push di dominio replay: `make_event` dall’engine; broadcast automatico a human+bot. Eventi Stats: emit diretto dal bridge (`stats.job.*`, `stats.chat.*`, …).

---

## 7. Processo ENGINE — shell + plugin

Package: [`dashv2/engine/`](../dashv2/engine/)  
Entry: `run_engine_process` → carica **una** plugin da `cfg["engine_plugin"]` → `plugin.run()`.

### Ruoli

| Concetto | Cos’è | Dove vive |
|----------|-------|-----------|
| **Engine** | Processo OS sempre spawnato; parla solo via pipe col server | `process.py` / `run_engine_process` |
| **Plugin** | Dominio: round, clock, ordini, settlement, **account**, history | `plugins/replay.py`, `plugins/live.py`, … |
| **Contratto** | Interfaccia comune (trading + account + settlement + history) | `protocol.py` |

Analogia col bot: Engine : plugin = Bot : Strategy. Differenze: **una sola** plugin Engine; **nessun hot-swap** (solo startup / restart).

### Plugin `replay` (`ReplayEngine`)

Stato interno rilevante (invariato rispetto al motore replay precedente):

| Campo | Ruolo |
|-------|--------|
| `repo` | `RoundRepository` (indice + load) |
| `orders` | `OrderEngine` (posizioni in memoria) |
| `accounts_root` | `history_dir/accounts` — **account locale del plugin replay** |
| `active_account_id` | account selezionato (`_state.json`) |
| `loaded` | `LoadedRound \| None` |
| `sec` | secondi a scadenza (asse replay) |
| `playing` | clock attivo |
| `round_ended` | settlement già eseguito |
| `seq` | monotono su ogni tick pubblico (anche preview scrub) |
| `session_id` / `session_started_at_utc` | run corrente (nuovo a ogni `round.load` / restart; clear su `round.unload`) |
| `replay_speed` | 1, 2 o 5 |
| `selected_bot_id` / `bot_active` | strategy shim selezionata / master switch |
| `engine_plugin` / `round_source` / `account_backend` | `"replay"` / `"replay"` / `"local"` |

Loop, advance, settlement, tradable, helper tick: come prima (vedi sotto e sezioni ordini/history). Le regole account JSON attuali **appartengono al plugin replay**, non allo shell Engine né al futuro plugin live.

### Plugin `live` (`LiveEngine`)

Stub: stesso contratto IPC; `account_backend: polymarket`; trading/account reali non implementati. Avrà regole account diverse (wallet / API Polymarket) dietro la stessa interfaccia place/close/… .

### Endpoint futuri (solo documentale)

Stessa webapp base, due entrypoint HTTP che fissano la plugin Engine (e quindi richiedono processi/setup dedicati o restart con setup diverso):

| Endpoint | Plugin Engine | Note |
|----------|---------------|------|
| `/replay` (o root attuale) | `replay` | Round da `data/`, account ledger locale |
| `/live` | `live` | Feed/trading Polymarket, account live utente |

Niente switch plugin a runtime nella stessa istanza: un cambio implica **riavvio** e rilettura `setup.json` (o istanza separata per endpoint).

### Loop principale (plugin replay)

All’avvio: eventi `bootstrap` + `accounts`.

Poi loop infinito:

1. Drain comandi: `while cmd_conn.poll(0): _handle_cmd(recv())`.
2. Se `playing` e round caricato e non ended: se `monotonic() >= _next_tick_at` → `_advance_sec()` e riprogramma `_next_tick_at = now + 1.0/replay_speed`.
3. `sleep(0.02)` (poll ~50 Hz; tick effettivi a 1/speed Hz).

### Advance e fine round

- `_advance_sec`: se `sec == 1` → `_finish_round()`; altrimenti `sec -= 1`, emette tick + chart current + session.
- `_finish_round`:
  1. `playing=False`, `round_ended=True`, `sec=0`.
  2. `orders.settle_open(outcome, 0, final_chainlink)`.
  3. Append di **tutti** i `closed_orders` (manual + settlement) al ledger dell’account (`append_settled_orders`).
  4. Emit `orders`, `history`, `accounts`, `round_end`, `session`.

### Lifecycle di un round

```
round.load
  → loaded, sec=300, playing=True, nuova session_id, reset orders
  → response IPC, poi eventi UI
play / speed / seek / preview / place / close / cancel
  → mutano stato o emettono preview
sec arriva a 0 (play o seek)
  → _finish_round → persistenza ledger + round_end
play dopo ended
  → _restart_round (stesso loaded, clear positions, stesso session_id non rinnovato)
```

Note:

- **Seek a 0** durante un round non ended chiama `_finish_round` (settlement reale).
- **Seek post-end** con `sec!=0` fa `_restart_round` (nuova “partita” sullo stesso file).
- **Scrub** (`replay.preview`): emette `session`/`tick`/`chart`/`orders` con `"preview": true` **senza** mutare `self.sec` / `playing` / posizioni reali (solo `seq` avanza). Usato dallo slider durante il drag.

### Tradable / gate trading

- Tick pubblico: `tradable` se non partial/gap e BTC non stale-null.
- Session: `tradable` richiede anche `active_account_id` e `not round_ended` e `sec >= 1`.
- `order.place` / `close` / `cancel`: bloccati se `round_ended` o tick non tradable; place richiede account attivo.
- Switch account bloccato se ci sono open orders (`account_switch_locked`).

### Helper tick pubblico

- `_public_tick`: proietta il tick interno nel payload browser (quote in centesimi, risk per lato, DWin).
- `_dwin_public`: DWinA/B orientati al **segno del delta** (`dwin_ref_side`); il client inverte con `100-pct` per il lato opposto.
---

## 8. Round repository — `rounds.py`

### Indice

`RoundRepository._scan()`:

- glob `data_dir/**/bin/btc5m_*.bin`;
- chiave `market_start_ts` dal filename; dedupe (primo visto vince, scan per mtime desc);
- `valid` solo se esiste la coppia `.txt` (`txt_path_for_bin`);
- entry: `RoundIndexEntry(market_start_ts, label, day_utc, valid, reason)`.

API picker (anti-spoiler):

- `list_days()` → `{day_utc, count}`;
- `list_picker_day(day)` / `list_picker()` → **solo** ts, label, valid, reason (**mai** outcome, path, prezzi finali);
- `list_nav_ts()` → lista ts validi ordinati (prev/next UI).

### `LoadedRound`

Struttura in memoria dopo `load(mts)`:

| Campo | Contenuto |
|-------|-----------|
| header fields | `fee_rate`, `ptb_chainlink`, `outcome_*`, `final_chainlink`, start/end ts |
| `ticks_by_sec` | dict `sec →` campi UI/trading (quote, delta, vol, side_risk, dwin, flags) |
| `books_by_sec` | dict `sec → BookSnapshot` |
| `all_secs` | `set(range(1, 301))` |

### Merge bin + txt

1. `read_round(bin)` → header, ndarray ticks, list books (`src.binary_format`).
2. `parse_txt_data_rows(txt)` → vol + DWinA/B (e rq/rs parsati ma **non** usati nel tick dashboard).
3. `compute_side_risks(ticks, ptb)` da `src.risk` → Rq/Rs **per lato** (live-safe dal bin).
4. Per ogni riga: `sec = floor(secs_to_expiry + 0.5)`; merge; partial se quote NaN → `gap=True`; stale Chainlink se `(recv_ts_ms - chainlink_recv_ms) > stall_reconnect_sec * 1000` → `delta_usd=None`, `chainlink_btc=None`.

### Candele

- `candles(before_ts)`: tutte le candele OHLC disponibili da `data_dir` (cache in-process); se `before_ts` → solo `time < before_ts` (anti-spoiler). Idle: `before_ts=None`; round caricato: `before_ts=mts` + `current_candle`.
- `current_candle(loaded, sec)`: solo tick con `s >= sec` (asse countdown: presente + passato); open = PTB; se nessun prezzo → flat su PTB.

---

## 9. Ordini — `orders.py`

Classe `OrderEngine`: stato **solo in RAM** finché non arriva `_finish_round`.

### BUY

`preview` / `place` → `market_buy_walk(asks, size_usd, fee_rate, quote_ask=best_ask)` (`src.clob_api`).  
Fee Polymarket per livello inclusa nel budget.  
Ordine aperto: id, account_id, side, entry_sec, size, shares, entry BTC/price/fee, payout/profit if win, campi MTM.

### MTM e Close (SELL)

`_mtm`:

1. Se mercato “deciso” (`_settlement_pnl_if_certain`: mid vincente ≥ 0.97, perdente ≤ 0.05, …) → stima PnL ma `mtm_available=False` (Close disabilitato: non c’è liquidità bid utile).
2. Altrimenti `market_sell_walk(bids, shares, fee_rate)` → `mtm_available=True`, Close abilitato.
3. Fallimento walk → `mtm_usd=None`.

`close`: richiede `mtm_available`; `close_type="manual"`, `result="closed"`.

### Cancel

Rimuove da `open_orders` **senza** passare da closed/history.

### Settlement

`settle_open(outcome, sec, final_btc)`: won se `outcome == side`; exit 1.0/0.0; fee exit 0; `close_type="settlement"`.

### Seek causale — `prune_seek(sec)`

Asse countdown: `sec` alto = inizio round, `sec` basso = fine.

- Tiene open solo ordini con `entry_sec >= sec` (già piazzati “nel passato” del cursore).
- Close manuali con `exit_sec < sec` (chiusura ancora nel “futuro” rispetto al nuovo cursore) → **riaperti**.
- Settlement chiusi restano in closed.

### Scrub

`preview_snapshot`: MTM ipotetico senza mutare lo stato reale (usato da `replay.preview`).

---

## 10. History / account ledger — `history.py` (plugin replay)

Modulo di persistenza account del **plugin replay** (`account_backend: local`). Il plugin live userà un backend diverso dietro la stessa interfaccia account del protocollo Engine.

### Layout filesystem

```
dashv2/history/          # history_dir da setup.json (gitignored tipicamente)
  accounts/
    _state.json          # { active_account_id, saved_at_utc }
    account_<id>.json    # un file per account
  sessions/
    session_<id>.json    # registro sessione (account_id ownership alla mint)
  executions/
    <session_id>.jsonl   # exec log bot/engine
  agent/
    session_<id>/thread.json  # chat AI Agent per sessione
```

`SCHEMA_VERSION = 1`. Scrittura atomica: `.tmp` + `os.replace`.

### Sessioni (cittadino di prima classe)

Alla mint (`round.load` / `_restart_round`) l’engine scrive `history/sessions/session_{id}.json` con `account_id` attivo, `market_start_ts`, `started_at_utc`, `active_strategy_ids`.

- `round.unload`: scarica round dall’engine (`loaded=False`, clear `session_id`/ordini RAM); **non** cancella registro/exec/chat su disco. Rifiuta se open orders. UI: prima voce del dropdown Session in tab AGENT («Unload session»), non più pulsante in Accounts.
- Cambio account / NEW: vietati se `loaded`. Sblocco solo dopo unload (o avvio senza round).
- Dropdown sessioni AI Agent: `list_sessions_for_account(active_account_id)`.

### Schema account

```json
{
    "schema_version": 1,
    "id": "<12 hex>",
    "name": "...",
    "note": "...",
    "initial_balance_usd": 10000.0,
    "created_at_utc": "...Z",
    "updated_at_utc": "...Z",
    "orders": [ /* ledger entries immutabili in append */ ]
}
```

Ogni entry appendata a fine round porta: campi ordine + `market_start_ts`, `session_id`, `session_started_at_utc`, `outcome`, `saved_at_utc`. Solo `close_type in ("manual", "settlement")`.

### Quando si scrive su disco

**Solo** in `_finish_round` via `append_settled_orders`.  
I close manuali durante il round restano in `OrderEngine.closed_orders` fino al settlement, poi entrano nel ledger insieme agli settled.

### History verso UI (`_emit_history`)

1. Righe dal ledger dell’account attivo (`order_rows_from_ledger`).
2. Se round caricato e **non** ended: prepend delle closed live della sessione corrente (`order_rows_for_run` con `outcome=None` → anti-spoiler su outcome colonna).
3. Sort per session / market / entry_sec.

Esiste `visible_orders(...)` (nasconde ledger dello stesso `market_start_ts` finché il round non è settled) ed è **testata**, ma oggi **non** è collegata in `_emit_history`. L’anti-spoiler effettivo sulla history è: outcome nascosto nelle righe live fino a `round_end`; il ledger di sessioni precedenti dello stesso round resta visibile.

### Stats account

`compute_stats`: balance = initial + Σ pnl; win_rate su wins+losses; usata in `account_summary` e evento `accounts`.

---

## 11. Parser indicatori txt — `txt_rows.py`

`parse_txt_data_rows(txt_path) → dict[sec, dict]`.

| Campo estratto | Uso in dashboard |
|----------------|------------------|
| `vol` (`VW N`) | Signal card volatilità |
| `dwin_a`, `dwin_b_pct` | Signal DWin (orientati in engine) |
| `rq`, `rs` | Parsati ma **non** usati: Rq/Rs UI vengono da `compute_side_risks` sul bin |

Non estrae quote/delta/gain/btc (arrivano dal bin).

---

## 11bis. Comandi vs Eventi

Modello mentale della pipeline (sinistra ↔ destra):

```
  SINISTRA                         CENTRO                    DESTRA
  (controller)                     (bridge)                  (fonte di verità)

  Browser (human) ──┐
                    ├── Socket.IO ──► ServerBridge ──CMD──► Engine (+ plugin)
  Bot process ──────┘                      │               (replay | live | …)
                                           │
                    ◄── eventi Socket.IO ──┤◄── EVT ───────┘
                    ◄── ack/response ──────┘
```

### Visione simmetrica (sì, con tre precisazioni)

**Sì:** sul percorso round/trading la direzione è simmetrica e va preservata.

| | **Comando** | **Evento** |
|--|-------------|------------|
| Origine | Sinistra: browser **o** bot | Destra: Engine (plugin attiva) |
| Direzione | sinistra → destra | destra → sinistra |
| Scopo | *chiedere* una mutazione o una query di stato | *notificare* uno stato già deciso / avanzato |
| Esempi | `round.load`, `replay.seek`, `order.place`, `bot.select` | `tick`, `session`, `orders`, `round_end`, `bot.status` |
| Chi lo “possiede” | il controller che lo emette (human/bot) | solo l’engine; bridge e client non inventano stato di dominio |

Flusso tipico di un comando:

1. Browser o bot emette il nome Socket.IO (es. `order.place`).
2. Il bridge applica ACL, inietta `actor`, traduce in IPC `request` sulla pipe CMD.
3. L’engine esegue e risponde con IPC `response` (ack verso il mittente).
4. Se lo stato pubblico cambia, l’engine emette uno o più IPC `event` → broadcast Socket.IO a **entrambi** i controller a sinistra.

Flusso tipico di un evento (anche senza comando, es. clock 1 Hz):

1. L’engine avanza `sec` / MTM / settlement.
2. `make_event("tick"|"session"|…)` sulla pipe EVT.
3. Il bridge fa broadcast a human e bot: stessa timeline, stessa verità.

### Precisazioni (non rompono il modello, lo delimitano)

1. **Ack/response ≠ evento.** La risposta sincrona al comando torna a sinistra (destra→sinistra) ma è *correlata* al `request_id` del mittente; l’evento è un push di stato verso tutti i controller.
2. **Peer sul bridge (non attraversano l’engine):** `consult.send` / `consult.message` restano human↔bot sul ServerBridge. Sono laterali, non destra↔sinistra sul data path.
3. **Forward bridge→bot:** dopo un comando human che aggiorna lo stato in engine (es. `bot.select`), il bridge può emettere `strategy.load` solo verso il bot. La verità resta a destra; il forward è un side-channel operativo verso il processo bot.

### Regola pratica per estensioni

- Nuova *azione* del controller → **comando** (sinistra→destra), handler in engine, riga in §12 e/o §12B.
- Nuovo *fatto di stato* da mostrare/reagire → **evento** (destra→sinistra), `_emit_event` dall’engine, mai inventato dal browser o dal bot.
- Se qualcosa non è né comando di dominio né evento di stato (consult, forward strategy), documentarlo esplicitamente come eccezione di bridge.

I cataloghi concreti: §12 (browser↔server) e §12B (bot↔server).

---

## 12. Protocollo Socket.IO (browser ↔ server)

Il browser non parla mai direttamente con il processo Engine.  
I nomi comando Socket.IO coincidono con `cmd` IPC.

### Comandi (client → server)

Ack sincrono tranne `round.load` (ack immediato `{ok:true}`, errori via evento `error`).

| Comando | Payload tipico | Response tipica |
|---------|----------------|-----------------|
| `round.load` | `{market_start_ts}` | `{ok: true}` (async) |
| `round.unload` | `{}` | `{ok}` — scarica sessione; sblocca account |
| `rounds.list` | `{day_utc}` | `{ok, rounds:[{market_start_ts,label,valid,reason}]}` |
| `replay.play` | `{}` | `{ok, playing}` o `{ok, sec, playing, restarted}` |
| `replay.pause` | `{}` | `{ok, playing:false}` |
| `replay.speed` | `{speed:1\|2\|5}` | `{ok, replay_speed}` |
| `replay.seek` | `{sec, resume?}` | `{ok, sec, playing?}` |
| `replay.preview` | `{sec}` | `{ok, sec}` (+ eventi `preview:true`) |
| `order.size` | `{side, size_usd}` | `{ok}` |
| `order.preview` | `{size_up_usd, size_down_usd}` | `{ok, previews:{Up,Down}}` |
| `order.place` | `{side, size_usd}` | `{ok, order}` |
| `order.close` | `{order_id}` | `{ok, order}` |
| `order.cancel` | `{order_id}` | `{ok, order}` |
| `account.list` | `{}` | `{ok, accounts, active_account_id}` |
| `account.select` | `{account_id}` | `{ok, active_account_id}` — rifiutato se round loaded |
| `account.create` | `{name, initial_balance_usd, note?}` | `{ok, account}` — rifiutato se round loaded |
| `account.rename` | `{account_id, name}` | `{ok, account}` |
| `account.update` | `{account_id, name, initial_balance_usd, note?}` | `{ok, account}` |
| `bot.list` | `{}` | `{ok, bots, selected_bot_id, strategies, bot_active, ...}` |
| `bot.select` | `{bot_id\|null}` | `{ok, ...}` + stato engine + forward `strategy.load` al bot |
| `bot.set_active` | `{active: bool}` | `{ok, bot_active}` (master switch globale) |
| `session.sync` | `{}` | `{ok}` + re-push eventi |
| `consult.send` | `{text, ...}` | relay peer (no pipe data) |
| `stats.backtest.start` | `{strategy_id, day_from, day_to}` | `{ok, accepted}` — job su server (no pipe) |
| `stats.analyze.start` | `{analyze_id, day_from, day_to}` **oppure** `{analyze_id, simulation_id}` | `{ok, accepted}` |
| `stats.job.cancel` | `{}` | `{ok}` → evento `stats.job.cancelled` |
| `stats.chat.send` | `{text}` | `{ok, accepted}` — thread Stats |
| `stats.chat.history` | `{}` | `{ok, messages, busy}` |
| `stats.rules.apply` | `{rules, day_from, day_to, analyze_id?, name?}` **oppure** con `simulation_id` al posto del range | `{ok, accepted}` — codegen in thread OS; poi `stats.analyzes` + auto-run |
| `stats.analyze.list` | `{}` | `{ok, analyzes}` |
| `stats.analyze.delete` | `{analyze_id}` | `{ok}` + evento `stats.analyzes` |
| `stats.simulation.list` | `{}` | `{ok, simulations}` (include `has_orders`) |
| `stats.simulation.load` | `{simulation_id}` | `{ok, simulation}` — meta + rounds aggregati (senza hydratare tutti gli orders) |
| `stats.simulation.delete` | `{simulation_id}` | `{ok}` + evento `stats.simulations` |

I comandi `stats.*` e `agent.*` sono gestiti **localmente dal bridge** (non forward IPC all’Engine).

*Target (non ancora esposti come comandi human dedicati): `strategy.list` / `strategy.load` / `strategy.unload` / `strategy.set_active` — oggi il load passa da `bot.select` come shim.*

ACL: human → tutti i comandi sopra; bot → solo `order.*` trade/size/preview + `session.sync` + `consult.send`. Trade bot rifiutati se `bot_active=False`. Stats/agent: **human-only**.

Errori: `{error: string}` in ack, oppure evento `error` per load fallito.

### Eventi (server → client)

| Evento | Quando | Payload essenziale |
|--------|--------|-------------------|
| `bootstrap` | avvio / sync | `round_days`, `round_nav`, size default, host/port, accounts |
| `session` | ogni mutazione clock/account | `loaded`, `sec`, `progress`, `playing`, `round_ended`, `ptb`, `tradable`, `replay_speed`, `preview?` |
| `tick` | ogni secondo / scrub | BTC, delta, quote, vol, risk Up/Down, DWin, `previews`, `seq` |
| `chart` | load (full) o advance (current) | `previous?`, `current`, `full_reset`, `preview?` |
| `orders` | dopo place/close/MTM | sizes, `open[]`, `closed[]`, `preview?` |
| `history` | ledger + live closed | `rows[]`, `active_account_id` |
| `accounts` | CRUD / settle | lista + `active` con stats |
| `action` | dopo place/close/cancel | `actor`, `cmd`, `detail`, `sec` |
| `bot.status` | select / active / disconnect | `loaded`, `selected_bot_id`, `strategies[]`, `bot_active`, `reason?` |
| `consult.message` | relay `consult.send` | messaggio peer human↔bot |
| `round_end` | sec 0 | `outcome`, `final_chainlink`, `settled_orders` |
| `error` | load fallito (async) | `{message}` |
| `stats.job.progress` | durante batch | `{kind, done, total, errors}` |
| `stats.job.done` | fine batch ok | backtest: `{kind, table, summary, simulation_id, rounds}` (rounds slim, no orders); analyze: `{kind, markdown, summary}` |
| `stats.job.error` | job fallito / secondo start | `{message, kind}` |
| `stats.job.cancelled` | dopo cancel | `{kind}` |
| `stats.chat.message` | risposta chat Stats | `{message, proposed_rules?}` |
| `stats.chat.status` | thinking/idle | `{phase}` |
| `stats.analyzes` | lista moduli dopo apply/delete | `{analyzes}` |
| `stats.simulations` | lista sessioni dopo run/delete | `{simulations, selected_id?}` |

### Asse temporale UI

- Engine: `sec` = secondi a scadenza (300 → 0).
- Slider: `progress = 300 - sec` (0 a sinistra = inizio, 300 a destra = fine).
- Countdown string: `"{sec} | M:SS"`.

---

## 12B. Protocollo Socket.IO (bot ↔ server)

Il processo bot è un **secondo client** Socket.IO (non un browser): stesso bridge, stesso clock di eventi, ACL ristretta.  
Non usa le pipe IPC. Connect con `auth: { role: "bot" }`.

Senza strategy caricata il bot resta connesso e **inerte** (nessun `order.*` emesso dalle hook).

### Comandi (bot → server)

Ack come per l’human. Trade rifiutati dal bridge se `bot_active=False`.

| Comando | Payload tipico | Response tipica | Note |
|---------|----------------|-----------------|------|
| `order.size` | `{side, size_usd}` | `{ok}` | |
| `order.preview` | `{size_up_usd, size_down_usd}` | `{ok, previews}` | |
| `order.place` | `{side, size_usd}` | `{ok, order}` | `actor=bot` iniettato dal bridge |
| `order.close` | `{order_id}` | `{ok, order}` | può chiudere ordine aperto da altra strategy (futuro) |
| `order.cancel` | `{order_id}` | `{ok, order}` | |
| `session.sync` | `{}` | `{ok}` + re-push eventi | tipico al connect |
| `consult.send` | `{text, ...}` | `{ok}` | peer relay; `from` forzato a `bot` |

**Non ammessi** al bot (esempi): `round.*`, `replay.*`, `account.*`, `bot.select`, `bot.set_active`.

### Eventi (server → bot)

Stesso broadcast degli eventi engine verso l’human, **più** il forward dedicato strategy:

| Evento | Quando | Payload essenziale |
|--------|--------|-------------------|
| `bootstrap` | sync | come §12 |
| `session` | clock / account / bot_active | include `bot_active` per armare/disarmare trade |
| `tick` | 1 Hz / scrub | ignorare se `preview: true` |
| `chart` | load / advance | tipicamente ignorato dalle strategy |
| `orders` | mutazioni book posizioni | stato open/closed per decide close |
| `history` | ledger | opzionale |
| `accounts` | CRUD | opzionale |
| `action` | dopo place/close/cancel | feedback peer (anche ordini human) |
| `bot.status` | select / active | `selected_bot_id`, `strategies[]`, `bot_active` |
| `consult.message` | relay | messaggi human↔bot |
| `round_end` | sec 0 | settlement |
| `error` | load fallito | |
| `strategy.load` | dopo `bot.select` o (ri)connect | `{strategy_id: string\|null}` — **solo al bot_sid**, non passa dal data pipe |

### Flusso load strategy (oggi)

```
Browser --bot.select--> Server --IPC--> Engine (selected_bot_id, bot_active)
                              \--strategy.load--> Bot (load/unload plugin in-process)
Engine --bot.status--> Server --broadcast--> Browser + Bot
```

Target multi-strategy: più id attivi contemporaneamente; master `bot.set_active` globale + `active` per strategy; ordini ancora `source: bot` finché non si aggiunge `strategy_id` (piano separato).

### Target comandi futuri (documentati, non implementati)

| Direzione | Nome | Ruolo |
|-----------|------|-------|
| human→server | `strategy.list` / `strategy.load` / `strategy.unload` / `strategy.set_active` | API dedicata (sostituirà lo shim `bot.select`) |
| server→bot | `strategy.unload`, heartbeat | simmetrici a `strategy.load` |
| setup.json | chiave startup strategies | load allo start senza UI |

---

## 13. Frontend

Nessun bundler. Moduli ES in `static/js/`, vendor offline in `static/vendor/`.

| File | Ruolo |
|------|--------|
| `static/index.html` | DOM: header replay, tabs left (CANDLES / ACCOUNTS / STRATEGY / AGENT), pannello ordini right, modal account |
| `static/css/dashboard.css` | Stile (token/misure mockup v38) |
| `static/js/app.js` | Stato client, Socket.IO, binding controlli, CSV export |
| `static/js/render.js` | Aggiornamento DOM (tick, ladder, ordini, picker, history, accounts) |
| `static/js/chart.js` | Lightweight Charts v5 — candele 5m |

### AI Agent (tab AGENT)

Chat human-only con **Grok 4.5 High** (`agent_cursor_label` in setup), Cursor SDK come codegen (`reject_meta=False`).

| Pezzo | Path / comando |
|-------|----------------|
| Persistenza thread | `history/agent/session_{session_id}/thread.json` (`agents/agent_chat.py`) — chat a tema sessione |
| Registro sessioni | `history/sessions/session_{id}.json` (`sessions.py`); ownership `account_id` alla mint |
| Orchestrazione | `agents/agent_service.py` + `agents/common_prompt.md` + `agents/agent_system_prompt.md` (cita sempre `session_id` nelle analisi) |
| Tool round | `agents/agent_round_tools.py` |
| Exec log | `history/executions/{session_id}.jsonl` (`execution_log.py`); lista meta nel Context dropdown **filtrata per account** |
| Socket | `agent.chat.*` keyed su `session_id`; `agent.session.select` / `agent.session.delete` (cancella registro+chat+exec+ledger); `round.unload` sblocca account. |
| Turni lunghi | `run_turn` in **thread OS** (non greenlet); `agent.chat.status` con `detail` di fase (modello / tool / …); `agent.chat.history` ack include `busy`; UI poll history ogni 5s mentre busy; human reconnect = replace `human_sid`. |

Rules-first: proposte in chat (fence `rules`); apply solo con conferma UI o tool `strategy.apply_rules` + `confirm:true` → codegen update. Vietato write diretto del `.py`.

### Stats (sotto-tab AGENT Backtest/Analyze) — batch sul server

Design / piano: [`docs/superpowers/specs/2026-07-19-stats-tab-batch-design.md`](superpowers/specs/2026-07-19-stats-tab-batch-design.md), [`docs/superpowers/plans/2026-07-19-stats-tab-batch.md`](superpowers/plans/2026-07-19-stats-tab-batch.md).

#### Dove vivono i job

I job backtest/analyze sono orchestrati **solo dal processo server** (come `agent.*`):

- **non** passano dalla pipe IPC verso l’Engine;
- **non** coinvolgono il processo bot;
- usano `ProcessPoolExecutor` con `stats_workers` da `setup.json` (tipicamente 10);
- ogni worker carica un round da disco e esegue headless (stesso `OrderEngine` / fee / settlement del replay, senza Socket.IO).

Replay UI (Engine) può restare attivo durante un batch; I/O disco condiviso accettabile in v1.

#### Regole job

| Regola | Comportamento |
|--------|----------------|
| Un solo job alla volta | Secondo `*.start` mentre gira → `stats.job.error` |
| Cancel | `stats.job.cancel` → soft-cancel v1: pending futures cancellati; worker in-flight sul round corrente possono ancora finire. Poi `stats.job.cancelled` (**niente** `done` con tabella/Markdown parziali). Hard-kill dei processi worker: non in v1. |
| Size backtest | `default_order_size_usd` per Up e Down (non le size della sessione UI) |
| Ledger | I job **non** scrivono `history/accounts/` |
| After apply | `stats.rules.apply` → ack `{ok, accepted}`; codegen su thread OS; emit `stats.analyzes` (`applied_id`) + auto-run analyze su `day_from`/`day_to` **oppure** `simulation_id` |

#### Comandi e eventi `stats.*` (human-only)

Vedi tabelle §12. Riepilogo:

| Comando | Ruolo |
|---------|--------|
| `stats.backtest.start` | Range giorni + `strategy_id` → pool strategy |
| `stats.analyze.start` | Range + `analyze_id` → pool analyze; oppure `simulation_id` → merge orders da SQLite |
| `stats.job.cancel` | Annulla job corrente |
| `stats.chat.send` / `history` | Thread chat Analyze (non legato a `session_id` replay) |
| `stats.rules.apply` | Rules → ack accepted; codegen thread + auto-run (range o simulation) |
| `stats.analyze.list` / `delete` | CRUD moduli analyze |
| `stats.simulation.list` / `load` / `delete` | Sessioni backtest persistite (SQLite v2 + JSON v1 legacy) |

| Evento | Payload tipico |
|--------|----------------|
| `stats.job.progress` | `{kind, done, total, errors}` |
| `stats.job.done` | backtest: `{kind, table, summary, simulation_id, rounds}` (rounds slim); analyze: `{kind, markdown, summary}` |
| `stats.job.error` | `{message, kind}` (anche secondo start) |
| `stats.job.cancelled` | `{kind}` |
| `stats.chat.message` / `status` | risposta chat / thinking |
| `stats.analyzes` | lista moduli dopo apply/delete |
| `stats.simulations` | lista sessioni dopo run/delete (`selected_id` opzionale, `has_orders`) |

#### Flusso backtest

1. UI: tab AGENT → Backtest; range `day_from`/`day_to`; select strategy; Run.
2. Server: `list_batch_rounds` → tasks `{market_start_ts, bin_path, hour_utc, …}`.
3. `RoundBatchRunner` → worker `process_task` → `run_strategy_round` (hook strategy + `OrderEngine` + `orders`).
4. `reduce_strategy_rows` → 24 righe ore UTC (`UTC_HOUR_MARKETS`) + totale.
5. Persist `history/simulations/simulation_{id}.sqlite` (meta + rounds + orders) → emit `stats.job.done` (rounds slim) + `stats.simulations`.

#### Flusso analyze

1. Chat Stats → Applica rules → `stats_codegen` scrive `analyze_{id}.json` + `.py`.
2. Auto-run (o Run manuale) su range giorni **oppure** `simulation_id` (merge `orders` da SQLite).
3. Worker chiama `analyze_round(round_view)`; reduce via `reduce_results` o fallback Markdown.
4. Emit `stats.job.done` → UI `<pre class="stats-md">`.

#### Mappa file Stats / batch

| Pezzo | Path |
|-------|------|
| Package batch | `dashv2/batch/` |
| Listing range | `batch/listing.py` — `list_batch_rounds` |
| Runner + cancel | `batch/runner.py` — `RoundBatchRunner` |
| Worker pickleable | `batch/worker.py` — `process_task` |
| Strategy headless | `batch/strategy_job.py` + `batch/ctx.py` |
| Analyze per-round | `batch/analyze_job.py` |
| Reduce 24h / MD | `batch/reduce.py` + `batch/markets.py` (`UTC_HOUR_MARKETS`) |
| Chat + apply | `stats_service.py`; thread `history/stats/thread.json` |
| CRUD moduli | `stats_modules.py` — `history/stats/analyze_{id}.json` + `.py` |
| Sessioni backtest | `simulations.py` — `history/simulations/simulation_{id}.sqlite` (v2) + JSON v1 legacy read-only |
| Codegen | `agents/stats_codegen.py` + `agents/stats_system_prompt.md` |
| Socket handlers | `server.py` — `_STATS_CMDS`, orchestrazione job |
| UI | `static/index.html` (`#agent-tab` sotto-tab Backtest/Analyze), `app.js`, `render.js`, `dashboard.css` |

#### UI (segmented Backtest \| Analyze)

- Sotto-tab `#agent-backtest-tab` / `#agent-analyze-tab` dentro `#agentPane`; tab principale `#agent-tab` in `LEFT_TAB_IDS` + localStorage.
- Header condiviso: range giorni (default min/max da `round_days`).
- Backtest: date range + strategy/Run/Cancel nel header; Session (+ Delete), progress, tabella 24h + TOTAL + summary.
- Analyze: chat, Applica rules, select/delete moduli, dropdown Simulation opzionale, Markdown grezzo (niente vendor MD).

Ogni Run backtest crea `history/simulations/simulation_{id}.sqlite` (summary + table + rounds + orders). Selezionare una sessione Backtest ripristina strategy, range giorni e risultati aggregati. Analyze può riusare una session SQLite come contesto `orders`.

Drill tabella risultati (solo backtest, da `rounds` in memoria client):

1. **Ore** — 24 righe UTC + TOTAL; hover/click → livello slot
2. **Slot 5m** — sempre 12 righe (`HH:00–HH:05` …); hover/click → giorni
3. **Giorni** — una riga per giorno del slot (`YYYY-MM-DD · HH:MM–HH:MM`); click → `round.load` + tab Candles (play come load normale)

Navigazione indietro: breadcrumb nel titolo pannello. Riga TOTAL non cliccabile.

#### Smoke checklist (manuale)

```
1. Avvia dashv2, apri AGENT → Backtest
2. Range 1 giorno con round, seleziona strategy, Run
3. Progress avanza; tabella 24h popolata; totale coerente
4. Analyze: chiedi "conteggio inversioni majority_side ultimo minuto"; Applica; Markdown appare
5. Secondo Run mentre gira → errore
6. Cancel durante run → cancelled, no tabella parziale
```

### Stato client (`app.js`)

Campi tipici: `session`, `tick`, `orders`, `historyRows`, `accounts` / `activeAccount*`, `chartPrevious` / `chartCurrent`, `scrubbing`, `replaySpeed`, `roundDays` / `roundNav`, ecc.

Su `connect`: `session.sync` + sync speed da `localStorage` (`dashv2_replay_speed`); se c’è account attivo, `agent.chat.history` per riallineare messaggi/`busy`.

Slider: `pointerdown` → pause; `input` → `replay.preview`; `pointerup` → `replay.seek` + eventuale resume.

`round.load` è fire-and-forget (no promise ack); errori via evento `error`.

### Dove modificare cosa (UI)

| Area | File |
|------|------|
| Header / play / timeline / BTC | `index.html` + `render.js` (`renderTick`) + `app.js` |
| Chart | `chart.js` + eventi `chart` da engine |
| AI Agent chat | `index.html` (`#agentPane` sotto-tab SESSION CHAT / Backtest / Analyze) + `render.js` (`renderAgent*` / `renderStats*`) + `app.js` |
| Ladder / signal / BUY | `render.js` + previews da tick/order |
| Open orders / Close / Cancel | `render.js` (`renderOrders`) |
| History / CSV / session groups | `render.js` (`renderHistory`) + `app.js` |
| Accounts | `render.js` + comandi `account.*` |
| Bot / Strategy | tab STRATEGY + `renderBotPanel` + comandi `bot.*` |
| Stats (batch) | sotto-tab AGENT Backtest/Analyze + `renderStats*` + comandi `stats.*` (server-only) |
| Stile | `dashboard.css` |

---

## 14. Configurazione

File: [`dashv2/setup.json`](../dashv2/setup.json) caricato da [`dashv2/config.py`](../dashv2/config.py).

Chiavi obbligatorie (`_REQUIRED`):

| Chiave | Significato |
|--------|-------------|
| `data_dir` | Path relativo a `dashv2/` verso i round (es. `../data`) |
| `history_dir` | Path relativo ledger (es. `history`) |
| `host` / `port` | Bind HTTP |
| `default_order_size_usd` | Size iniziale Up/Down (anche size fissa dei job backtest Stats) |
| `stats_workers` | Worker `ProcessPoolExecutor` per RoundBatch sul server |
| `stall_reconnect_sec` | Soglia stale Chainlink (allineata al collector) |
| `engine_plugin` | `"replay"` \| `"live"` \| `null` — plugin caricata **solo a startup** (null = shell vuota) |
| `cursor_label` / `cursor_models` | Modello codegen strategie |
| `agent_cursor_label` | Modello chat AI Agent (es. `"Grok 4.5 High"`) |

Chiave mancante o `data_dir` assente → eccezione immediata.

Env vars previsti per live reale (non letti dallo stub): `POLY_API_KEY`, `POLY_API_SECRET`, `POLY_API_PASSPHRASE`, `POLY_PRIVATE_KEY`.

---

## 15. Dipendenze da `src/` (codice condiviso)

| Modulo | Uso | Perché |
|--------|-----|--------|
| `src.binary_format` | `read_round`, `OUTCOME_NAMES`, `txt_path_for_bin` | Formato `.bin` v6 canonico |
| `src.book` | `BookSnapshot` | Livelli ask/bid per walk |
| `src.clob_api` | `majority_side`, `market_buy_walk`, `market_sell_walk` | Stessa fee/walk del collector |
| `src.risk` | `compute_side_risks` | Rq/Rs per lato, live-safe |
| `src.delta_win` | `parse_vol_txt` (via txt_rows) | Token volatilità |
| `src.setup` | `VOLATILITY_WINDOWS_SEC`, `DELTA_WIN_TXT_COLUMNS` | Schema colonne txt |

**Regola:** se cambia la semantica del book o delle fee nel collector, la dashboard eredita automaticamente il comportamento — non duplicare formule in `dashv2/`.

---

## 16. Mappa file

| Percorso | Ruolo |
|----------|--------|
| `dashv2/__main__.py` | Launcher spawn + watchdog fail-fast (server/engine) + soft-respawn bot + restart sentinella |
| `dashv2/server.py` | Bridge Flask-SocketIO (human + bot, consult relay, forward strategy.load, stats.* locali) |
| `dashv2/engine/process.py` | Shell processo Engine (pipe, load plugin) |
| `dashv2/engine/protocol.py` | Contratto `EnginePlugin` (trading + account + settlement + history) |
| `dashv2/engine/plugins/replay.py` | Plugin replay (`ReplayEngine`) |
| `dashv2/engine/plugins/live.py` | Plugin live stub (`LiveEngine`) |
| `dashv2/ipc.py` | Envelope request/response/event |
| `dashv2/rounds.py` | Indice, load merge, candele |
| `dashv2/orders.py` | Simulazione CLOB (usata dal plugin replay) |
| `dashv2/history.py` | Account ledger JSON — **backend del plugin replay** |
| `dashv2/execution_log.py` | Jsonl esecuzione ordini per session_id |
| `dashv2/sessions.py` | Registro sessioni (ownership account) |
| `dashv2/agents/` | Package agenti: chat, codegen, Cursor SDK, prompt (vedi `agents/README.md`) |
| `dashv2/agents/agent_chat.py` / `agent_service.py` / `agent_round_tools.py` | Chat AI Agent + tool |
| `dashv2/agents/common_prompt.md` | Dominio condiviso (Polymarket, lessico UI, zone, rules/coded rules) |
| `dashv2/agents/agent_system_prompt.md` | Prompt agent-specific (COMMON + questo; IT, session, tools, rules-first) |
| `dashv2/stats_service.py` / `stats_modules.py` | Chat Stats + CRUD analyze |
| `dashv2/agents/stats_codegen.py` / `stats_system_prompt.md` | Codegen analyze |
| `dashv2/simulations.py` | Persistenza sessioni backtest SQLite (`history/simulations/`) |
| `dashv2/batch/__init__.py` | Package RoundBatch |
| `dashv2/batch/markets.py` | `UTC_HOUR_MARKETS` (24 etichette, allineate al picker JS) |
| `dashv2/batch/listing.py` | `list_batch_rounds(repo, day_from, day_to)` |
| `dashv2/batch/runner.py` | `RoundBatchRunner` — pool, progress, cancel |
| `dashv2/batch/worker.py` | `process_task` (entry pickleable; `load_bin` per task, no full scan) |
| `dashv2/batch/ctx.py` | `build_strategy_ctx` (mirror bot) |
| `dashv2/batch/strategy_job.py` | Backtest headless per round (`OrderEngine`) |
| `dashv2/batch/analyze_job.py` | Analyze per round + load `reduce_results` |
| `dashv2/batch/reduce.py` | Tabella 24h + Markdown fallback |
| `dashv2/txt_rows.py` | Parse indicatori dal `.txt` |
| `dashv2/config.py` + `setup.json` | Config fail-hard (`engine_plugin`, `agent_cursor_label`) |
| `dashv2/bots/` | Processo bot + plugin strategy shim (`bot_process.py`, `*_bot.py`) |
| `dashv2/static/index.html` | DOM (header replay, tabs CANDLES/ACCOUNTS/STRATEGY/AGENT, ordini) |
| `dashv2/static/css/dashboard.css` | Stile (token/misure mockup v38) |
| `dashv2/static/js/app.js` | Stato client, Socket.IO, binding, CSV, wire `stats.*` |
| `dashv2/static/js/render.js` | DOM tick/ladder/ordini/picker/history/accounts/Stats |
| `dashv2/static/js/chart.js` | Lightweight Charts v5 — candele 5m |
| `dashv2/static/vendor/` | Bootstrap, Icons, Socket.IO, Lightweight Charts (offline) |
| `dashv2/tests/**` | Unit test |
| `dashv2.bat` | Launcher Windows |
| `docs/dashv2-architecture.md` | Questo documento (canonico) |
| `docs/dash-prompt-v2.md` | Intent originale V2 |
| `docs/traccia.txt` | Backlog UI/feature |

---

## 17. Test e smoke

```text
python -m unittest discover -s dashv2/tests
```

| File | Copertura |
|------|-----------|
| `test_ipc.py` | Envelope |
| `test_ipc_pipe.py` | Direzione pipe response |
| `test_rounds.py` | Indice, picker anti-spoiler, load (se `data/` presente) |
| `test_clob_walk.py` | BUY/SELL walk |
| `test_seek_history.py` | prune_seek, cancel, account CRUD, payout/outcome rows, visible_orders |
| `test_dwin_public.py` | Proiezione DWin nel tick pubblico |
| `test_side_risk.py` | Risk per lato in tick |
| `test_bot_live.py` | Bot list/select/active + live stub + ACL agent/stats |
| `test_agent_chat.py` | Thread chat per session, registro sessions, exec log, tool parse, turn mock |
| `test_strategy_codegen.py` | Codegen parse/validate + clone |
| `test_batch_reduce.py` | Aggregazione 24h + `UTC_HOUR_MARKETS` |
| `test_batch_listing.py` | Filtro giorni `list_batch_rounds` |
| `test_batch_runner.py` | Pool / cancel `RoundBatchRunner` |
| `test_strategy_job.py` | Backtest headless un round |
| `test_analyze_job.py` | Analyze stub → markdown |
| `test_stats_acl.py` | `_STATS_CMDS` human-only |
| `test_stats_service.py` | Chat Stats + apply rules |
| `test_stats_codegen.py` | Codegen moduli analyze |

Smoke manuale replay: `dashv2.bat` → load → play → seek → BUY → close/cancel o settlement → history/CSV; tab AGENT con account attivo.

Smoke manuale **STATS** (vedi anche §13 Stats):

```
1. Avvia dashv2, apri AGENT → Backtest
2. Range 1 giorno con round, seleziona strategy, Run
3. Progress avanza; tabella 24h popolata; totale coerente
4. Analyze: chiedi "conteggio inversioni majority_side ultimo minuto"; Applica; Markdown appare
5. Secondo Run mentre gira → errore
6. Cancel durante run → cancelled, no tabella parziale
```

Non esiste oggi un test e2e Socket.IO/browser.

---

## 18. Guida all’estensione

### Aggiungere un comando

1. Se tocca round/clock/ordini/account: handler nella plugin Engine + nome in ACL bridge.
2. Se è `stats.*` / `agent.*`: handler **solo** in `server.py` (niente pipe).
3. Binding in `app.js` (`emitAck` o fire-and-forget).
4. Test unitario sul dominio toccato.
5. Aggiornare la tabella protocollo in questo documento.

### Aggiungere un evento push

1. `_emit_event("nome", payload)` dall’engine nei punti giusti del lifecycle.
2. `socket.on("nome", ...)` in `app.js` + render.
3. Nessuna modifica al bridge (inoltra già tutto).

### Aggiungere stato di dominio

- Vive nel processo **data** (`ReplayEngine` o modulo dedicato tipo `orders`/`history`).
- Esporre snapshot via eventi; mutazioni solo via comandi.
- Non tenere una seconda copia “ufficiale” nel browser o nel server.

### Modalità live / strategie (direzione futura)

Il contratto da preservare:

```
Browser  ↔  ServerBridge (invariato)  ↔  Engine + plugin (replay | live)
```

Idealmente la plugin continua a emettere gli stessi eventi (`tick`, `session`, `orders`, …) così il frontend e il bridge restano stabili. Cambia solo come si popola il round / lo stream secondario (e il backend account).

### Anti-spoiler in nuove feature

Qualsiasi UI che espone liste di round, history, nomi file, tooltip, chart “futuro”, deve rispettare:

- niente outcome / final price / path finché `round_ended` è false per il round attivo;
- picker solo tramite `list_picker*`;
- chart solo causale (`current_candle` già enforce).

### Cose da non fare

- Mettere clock/settlement/fee/account nel bridge (ok: ACL, consult relay, forward strategy, **orchestrazione Stats/agent**).
- Far parlare il browser con l’Engine senza passare dal bridge.
- Far parlare una Strategy direttamente col server (passa sempre dal processo bot) — eccezione: i worker batch importano la strategy **headless** senza Socket.IO.
- Orchestrare RoundBatch nell’Engine o nel bot (i job `stats.*` restano sul server).
- Mettere regole account replay nel plugin live (o viceversa): ogni plugin possiede il proprio backend.
- Hot-swap della plugin Engine a runtime (solo startup + restart).
- Usare `majority_gain` / `gain%` del txt come PnL ordini.
- Riempire buchi nelle previous candles.
- Introdurre default silenziosi in `setup.json` / `config.py`.
- Mettere il bot nel fail-fast server+Engine o nell’Engine (rompe consulto peer e crash soft).
- Far controllare replay (load/seek/play) al bot.
- Spawn lazy del bot dal server (il bot è spawnato solo dal launcher).
- Emittere `stats.job.done` con risultati parziali dopo cancel.

---

## 18bis. Bot processo + Strategy (`dashv2/bots/`)

### Ruoli

| Concetto | Cos’è | Dove vive |
|----------|-------|-----------|
| **Bot** | Processo OS sempre spawnato; client Socket.IO `role=bot` | `bot_process.py` / `run_bot_process` |
| **Strategy** | Logica decisionale caricata *dentro* il bot | moduli `strategy_{id}_v{N}.py` + JSON catalogo |
| **Engine (plugin)** | Fonte di verità round + `active_strategy_ids` / `bot_active` | plugin attiva in `dashv2-engine` |

Il server scambia comandi/eventi di trading **solo** col bot. La strategy non è un peer Socket.IO.

### Tipi di Strategy

| Tipo | Stato | Input tipico | Output |
|------|-------|--------------|--------|
| **DETERMINISTICA** | Implementata: `rules` → codegen Cursor → `.py` eseguito dal bot | tick pubblico (sec, quote bid/ask, Rq/Rs, vol, DWin, open_orders) | `order.place` / `close` / `cancel` + `strategy_id` |
| **INFERENZIALE** | Solo metadata catalogo (runtime TBD) | feature per tick | entrate/uscite |
| **AGENTICA** | Solo metadata catalogo (runtime TBD) | contesto round | decisioni open/close |

### Deterministic: rules → Python

1. UI modal: name, description, **rules** (testo) + **coded_rules** (readonly, post-codegen).
   - **Rename in-place:** cambio `name` su `strategy.update` (stesso `id`, tutte le versioni restano sotto quel nome).
   - **Clone:** `strategy.clone` → nuova strategy v1 (fork vero; source intatta; nome `… (copy)`).
2. Server (`strategy.create` / `update` se rules cambiano): Cursor SDK (`cursor_label` + `cursor_models` in `setup.json`) genera il modulo; progress via evento `strategy.generate`.
3. Seconda pass Cursor: dal `.py` → testo colloquiale `coded_rules` (sezioni `Apertura` / `Chiusura` / `Vincoli`, termini dashboard, senza variabili codice); fallimento → `coded_rules` vuoto, Python comunque salvato.
4. Persistenza: `history/strategies/strategy_{id}.json` (`rules`, `coded_rules`, `version`, `versions[]`, `module_file`) + `strategy_{id}_v{N}.py` (archivio immutabile per N).
5. UI modal: tab **Rules** | **Coded rules**; dopo codegen la modale resta aperta e passa a Coded rules.
4. Human `strategy.load` → engine aggiorna `active_strategy_ids` → server emit `strategy.sync` `{strategy_ids}` al bot.
5. Bot: `importlib` del `.py`, fan-out `on_tick` / `on_round_start` / `on_round_end`; crash per-strategy → skip tick (log).

Contratto modulo: `on_tick(ctx) -> list[dict]` (azioni `order.place|close|cancel`).
Su ogni `order.place` la strategy sceglie `size_usd` (float libero per ordine; può cambiare tra scommesse dello stesso round). Le size già aperte sono in `open_orders[].size_usd`.

Config codegen: `cursor_label` (es. `"Composer 2.5"`) punta a un `label` in `cursor_models` (`id` SDK + `params`). System prompt: `dashv2/agents/common_prompt.md` + `dashv2/agents/strategy_system_prompt.md` (riletti a ogni create/update deterministic) — lessico **dashboard → ctx** (Model A/B, Rq/Rs, zone, LIQ2, quota=ask, …). Shape tipate di `dwin_*` / `risk` / ecc. nel `_CONTRACT` di `agents/strategy_codegen.py`. Env: `CURSOR_API_KEY` (`.env`).

### Multi-strategy

Più id attivi contemporaneamente; fan-out su ogni tick. Ordini bot portano `strategy_id`.

Attivazione:

- master switch globale `bot.set_active` (implementato);
- coda attiva via `strategy.load` / `strategy.unload` (persistita in `_state.json`).

### Load / sync

1. **UI:** human `strategy.load` / `unload` → engine → server emit `strategy.sync` al bot.
2. **(Ri)connect bot:** server re-sync via `bot.list` + `strategy.sync`.

### File attuali

| File | Ruolo |
|------|--------|
| `strategies.py` | Repository JSON + `.py` |
| `agents/strategy_codegen.py` / `agents/cursor_client.py` | Generazione modulo via Cursor SDK |
| `agents/common_prompt.md` | Dominio condiviso (agente / codegen / coded rules) |
| `agents/coded_rules_prompt.md` | Reverse-pass Python→coded rules (COMMON + questo; placeholder `{{SOURCE}}`) |
| `agents/strategy_system_prompt.md` | Prompt codegen-specific (COMMON + questo; hot-reload pre-create) |
| `agents/README.md` | Mappa package agenti |
| `bots/runner.py` | importlib cache + dispatch hook |
| `bots/bot_process.py` | Processo bot Socket.IO + runner |
| `bots/protocol.py` | Contratto legacy `BotPlugin` (shim) |

- Toggle Active (`bot.set_active`): off → bot non emette trade + bridge/engine rifiutano `order.*` del bot; umano continua a tradare.

## 18ter. Plugin Engine live (`dashv2/engine/plugins/live.py`)

- Caricata se `engine_plugin: "live"` a startup (nessun hot-swap).
- Bootstrap/sync con `engine_plugin: live`, `account_backend: polymarket`.
- Altri comandi → errore `"live engine plugin not implemented"`.
- Account live Polymarket: da implementare dietro la stessa interfaccia account/trading del protocollo plugin.
- Ledger replay: campo `round_source` (`replay`\|`live`) sulle entry quando applicabile.

---

## 18quater. Parallelismo Bot/Strategy ↔ Engine/Plugin

| | Lato sinistro | Lato destro |
|--|---------------|-------------|
| Processo stabile | **Bot** | **Engine** |
| Logica caricabile | **Strategy** (anche più di una) | **Plugin** (una sola) |
| Quando si carica | Runtime (`strategy.load` / `bot.select`) o setup futuro | **Solo startup** (`engine_plugin`) |
| Senza carico | Bot connesso, inerte | Engine shell vuota (pipe ok, no dominio) |
| Account | Non possiede account | **Il plugin** possiede account + history + settlement |
---

## 19. Diagramma sequenza — load + tick + ordine

```
Browser          ServerBridge              Engine (plugin replay)
   |                  |                         |
   |-- round.load --->|                         |
   |<-- ack ok -------|                         |
   |                  |-- request round.load -->|
   |                  |                         | load bin+txt
   |                  |<-- response ok ---------|
   |                  |<-- event session -------|
   |<-- session ------|<-- event chart ---------|
   | Bot <-- same ----|<-- event tick ----------|
   |                  |         ...             |
   |-- order.place -->|  actor=user             |
   |                  |-- request place ------->|
   |                  |<-- orders + action -----|
   | Bot <-- action --|                         |
```

---

## 20. Checklist rapida per review di una PR dashv2

- [ ] Business logic round/ordini/account solo nella **plugin** Engine (non nello shell)? Eccezione documentata: batch Stats headless sul **server**.
- [ ] Nuovi comandi in ACL bridge + handler nella plugin **oppure** solo bridge se `stats.*`/`agent.*`?
- [ ] Eventi broadcast ok per human e bot (replay)? Eventi Stats emessi dal bridge?
- [ ] Anti-spoiler rispettato (picker, history, chart)?
- [ ] Ordini usano walk CLOB + `fee_rate`, con `source`/`actor`?
- [ ] Bot non controlla replay; attach strategy solo in pausa (non durante play)?
- [ ] Bot spawnato dal launcher (non lazy dal server)? Strategy solo dentro il bot (live)?
- [ ] Plugin Engine scelta solo a startup (niente hot-swap)?
- [ ] RoundBatch **non** nell’Engine; un job alla volta; cancel senza `done` parziale?
- [ ] Config: nessuna chiave nuova senza aggiornare `_REQUIRED` e `setup.json`?
- [ ] Test unitari per la parte di dominio toccata?
- [ ] Questo documento aggiornato solo dopo che il codice funziona?

---

*Ultimo allineamento al codice: Engine shell + plugin replay/live, `engine_plugin`, bot processo fisso + strategy.load, soft-respawn, consult relay, actor/source, tab AGENT (SESSION CHAT / Backtest / Analyze) + RoundBatch (`stats.*` sul server).*
