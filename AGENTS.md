## Regole globali

All'inizio di ogni task, **leggi e applica** `C:\Users\savea\.cursor\AGENTS.global.md` (regole di comportamento, comunicazione e sviluppo comuni a tutti i progetti). In caso di conflitto tra regole globali e quelle qui sotto, **vincono le regole di questo file**.

## BTC5MIN

In questo progetto l'agente e l'utente devono studiare il meccanismo di variazione di ask e bid della scommessa del "BTC Up or Down 5m" 
esistente in polymarket:

"[https://polymarket.com/event/btc-updown-5m-1783238400](https://polymarket.com/event/btc-updown-5m-1783238400)"

### Collector

Lo studio deve comprendere una raccolta di tutte le scommesse di questa
pagina che si susseguono ogni 5 minuti. Deve salvare l'intero lob al timestamp e il tempo (in sec) mancante alla scadenza della scommessa.
Allo scadere questi dati vanno scritti in un file binario rileggibile 
in seguito. 

### Strategies

In base a tutti questi file di log poi si dovranno elaborare
strategie per capire se e quando puntare per poter avere un gain che va
al di là della semplice applicazione statistica della vincita. 
Cioè l'obbiettivo del progetto è proprio trovare un  meccanismo di entrata
nela scommessa che permetta di avere un bilancio positivo oltre
le normali vincite/perdite che si annullano a vicenda.

### Dashboard

E' inclusa una webapp dashboard che permetta di eseguire i replay dei round in una ui personalizzata e completa di tutte le info possibili, sia quelle fornite dall'api di polymarket sia info statistiche calcolate successivamente.


### Note round persi (obbligo agente)

Ogni volta che, per qualsiasi motivo (deploy, restart, bug, gap su disco, procedura manuale), l’agente **si accorge** che uno o più round 5m non sono stati salvati, deve subito scrivere una nota in `docs/` con nome:

`nota-round-persi-GG-MM-AA.md`

(es. [`docs/nota-round-persi-18-07-26.md`](docs/nota-round-persi-18-07-26.md)). La nota deve riportare almeno: macchina/path dati, quanti round, `market_start_ts` e ora UTC, causa nota, timeline utile alle analisi future. Non basta menzionarlo in chat.

---



## Dashboard (replay round)

Interfaccia web per **replay** dei round salvati in `data/`: timeline 1 Hz (anche x2/x5), chart candele BTC, ladder delta, quote Up/Down, indicatori dal `.txt` (vol, Rq/Rs, DWinA/B), simulazione ordini sul book `.bin` con fee CLOB, ledger account in `dashv2/history/accounts/`, processi **Engine** + **bot** sempre spawnati (`dashv2/engine/` con plugin `replay`|`live`, `dashv2/bots/`).

**Avvio:** `dashv2.bat` oppure `python -m dashv2` dalla root repo → apre `http://127.0.0.1:8780/` (host/porta in `dashv2/setup.json`).

**Dipendenze Python:** `pip install -r dashv2/requirements.txt` (Flask-SocketIO, eventlet). Nessuna build frontend: HTML/CSS/JS serviti da `dashv2/static/`.

### Restart automatico (obbligo agente)

Il launcher (`dashv2/__main__.py`) poll ogni **2 s** il file sentinella **`data/restart`** (path = `data_dir/restart` da `dashv2/setup.json`).

Comportamento del launcher:

1. All’avvio, **prima** di spawnare server/engine/bot: se `restart` esiste → lo elimina (niente doppio boot).
2. In loop: se trova `restart` → lo cancella, termina i tre processi (server/engine/bot), `os.execv` di `python -m dashv2` (reload completo codice + config).

**Cosa deve fare l’agente** dopo modifiche che richiedono riavvio del processo Python:

- Creare un file **vuoto** `data/restart` (es. `New-Item` / `touch` / scrittura vuota).
- Non chiedere all’utente di chiudere la finestra e rilanciare il batch.
- Serve per: `dashv2/*.py`, `dashv2/bots/*`, `dashv2/setup.json`, e in generale qualsiasi cambio backend già caricato in memoria.
- **Non** creare la sentinella per sole modifiche a `dashv2/static/**` (HTML/CSS/JS): basta refresh browser.
- Non commitare `data/restart` (la cartella `data/` è già gitignored).

**Obbligo in ogni risposta dopo una modifica:** dichiarare esplicitamente cosa serve all’utente, una di:

- **refresh browser** — solo static (`dashv2/static/**`)
- **restart server** — solo backend (sentinella `data/restart` già creata dall’agente)
- **entrambi** — backend + static (sentinella + refresh)
- **niente** — docs/test/file non runtime, o cambio già attivo senza reload

### Architettura e mappa file

Se il task tocca processi, IPC, layout moduli, config o dove vivere il codice dashv2, **leggi e applica** [`docs/dashv2-architecture.md`](docs/dashv2-architecture.md) (tre processi: server + engine + bot, pipe, mappa file, principi P1–P13).

### Codice condiviso con il collector (`src/`)

La dashboard **non** legge i file round da sola con logica duplicata: riusa moduli core del progetto.


| Modulo `src/`                                  | Uso in dashboard                                       |
| ---------------------------------------------- | ------------------------------------------------------ |
| `[src/binary_format.py](src/binary_format.py)` | `read_round()`, path `.txt`                            |
| `[src/book.py](src/book.py)`                   | `BookSnapshot`                                         |
| `[src/clob_api.py](src/clob_api.py)`           | `majority_side`, `market_buy_walk`, `market_sell_walk` |
| `[src/risk.py](src/risk.py)`                   | `compute_side_risks` (Rq/Rs per lato)                  |
| `[src/setup.py](src/setup.py)`                 | `VOLATILITY_WINDOWS_SEC`, `DELTA_WIN_TXT_COLUMNS`      |


Ordini simulati: walk sul book ask/bid del tick corrente con `fee_rate` dell’header `.bin` — **non** il `gain%` precomputato nel `.txt`.

### Protocollo Socket.IO

Se il task richiede comandi/eventi Socket.IO, ACL human/bot, payload o asse temporale UI (`sec` / seek / preview), **leggi e applica** le sezioni 12 e 12B di [`docs/dashv2-architecture.md`](docs/dashv2-architecture.md).

### Layout UI (dove modificare cosa)

- **Header** (timestamp, picker round, play/pause/speed, timeline, prezzo BTC): `index.html` + `render.js` (`renderTick`, picker) + `app.js` (slider seek/preview)
- **Chart candele**: `chart.js` + eventi `chart` in engine (`RoundRepository.candles`, `current_candle`); tutte le candele disponibili (≤ round corrente in replay)
- **Ladder delta / countdown / PTB**: `render.js` (`renderTick`)
- **Pulsanti BUY Up/Down, size, signal card** (vol, Rq, Rs, DWin): `index.html` + `render.js` (`applyButtonPreviews`, signal) + `orders.py` / `engine.py` (`_public_tick`, `_orient_dwin`)
- **Open orders + Close / Cancel**: `render.js` (`renderOrders`) + `orders.py`
- **Accounts**: `render.js` + comandi `account.*`
- **Bot / Strategy**: tab STRATEGY — `render.js` (`renderBotPanel`) + comandi `bot.*`; icona `bi-cpu` verde/rosso con lo switch
- **Agent**: tab AGENT — sotto-tab SESSION CHAT (chat Grok keyed su `session_id`), Backtest e Analyze (ex STATS); `agent.chat.*` / `agent.rules.apply` / `stats.*` in `app.js` + `dashv2/agents/` / `stats_service.py`
- **Closed order history + Export CSV**: `render.js` (`renderHistory`) + `history.py`; CSV generato lato client in `app.js`
- **Stile / responsive**: `dashboard.css`



### Anti-spoiler

Fino al settlement del round in replay: il picker espone solo timestamp/label (`RoundRepository.list_picker_day`); outcome e prezzi finali restano nascosti. In history, le closed live della sessione corrente hanno `outcome=None` finché non si arriva a sec 0; il ledger su disco si aggiorna solo a fine round.

### Test e smoke


| Comando                                       | Uso                                                                              |
| --------------------------------------------- | -------------------------------------------------------------------------------- |
| `python -m unittest discover -s dashv2/tests` | Test round load, IPC, seek/history/account, CLOB walk, DWin, risk, bot/live stub |
| `dashv2.bat`                                  | Smoke manuale: load round → play → seek → BUY → close/cancel o settlement → history/CSV |


Per modifiche alla dashboard: partire da questa sezione e da [`docs/dashv2-architecture.md`](docs/dashv2-architecture.md); non cercare altre cartelle `dash*` nel repo.

---



## Formato file del round (bin e txt)

Se il task richiede di leggere, scrivere, parsare o validare file `.bin` / `.txt` dei round Polymarket, **leggi e applica** [`docs/round-format.md`](docs/round-format.md) (struttura binaria v6, colonne `.txt`, campionamento, strumenti CLI, note per strategie).

---



## Round sintetici Lighter (feed `.txt` ausiliario)

Se il task riguarda build, backfill, analisi o studio dei round sintetici Lighter (dataset `.txt` ausiliario, `src/listats`, delta_win su Lighter), **leggi e applica** [`docs/lighter-rounds.md`](docs/lighter-rounds.md).

---

In lan, nella macchina preoxmox, esiste un container debian chiamato
poly (proxmox id 103, ip 10.1.1.73) che è pensata per stare attiva 24h e salvara i tick di questo progetto. In questa macchina deve essere presente un app "btc5min" dentro opt che parte all'avvio come servizio e scrive nella propria cartella data i file bin e txt dei vari round in modo continuativo.

Deploy / cutover del collector su poly: vedi [`docs/nota-ticksaver-deploy.md`](docs/nota-ticksaver-deploy.md).


## Sanity check round

Se l'utente chiede un **sanity check** (o controllo/sanità dei file round), **leggi e applica** [`docs/sanity-check-round.md`](docs/sanity-check-round.md) ed esegui tutti i controlli descritti (log collector Chainlink, quote partial CLOB, criteri di esito).
