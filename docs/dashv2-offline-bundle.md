# dashV2 — bundle offline per PC locale

Guida per **replicare la dashboard replay** (`dashv2`) su un altro computer Windows/Linux, **senza collector** e **senza sync LAN** dal server poly (`10.1.1.73`).

L'obiettivo è che il destinatario possa aprire `http://127.0.0.1:8780/`, caricare i round da `data/`, fare replay, simulare ordini, backtest e usare le stesse funzioni del PC di sviluppo.

**Applicativo e round sono separati:** lo zip contiene solo codice e configurazione; i file round in `data/` vanno forniti e aggiornati con procedure manuali dedicate.

---

## Per l'agente (procedura rapida)

**Script (PC sorgente, root repo):**

| Script | Uso |
|--------|-----|
| [`scripts/dashv2_pack.py`](../scripts/dashv2_pack.py) | Crea zip applicativo (senza round in `data/`) |
| [`scripts/dashv2_pack.bat`](../scripts/dashv2_pack.bat) | Shortcut → `dist/btc5min-dashv2-offline.zip` (accetta argomenti, es. `--hide-tabs`) |
| [`requirements-dashv2-offline.txt`](../requirements-dashv2-offline.txt) | Dipendenze pip per il PC destinatario |

**Primo invio** — pacchetto applicativo (codice + `.env` + `INSTALL.md`, senza round):

```powershell
python scripts/dashv2_pack.py --output dist/btc5min-dashv2-offline.zip
python scripts/dashv2_pack.py --output dist/btc5min-dashv2-offline.zip --hide-tabs backtest_analysis round_chat
```

**Round** — copiare manualmente (o con altro strumento) sotto `data/YYYY-MM-DD/bin|txt/` sul PC destinatario. Non esiste più uno script di packaging tick nel repo.

Note operative:

- **Non** includere collector né sync da poly: fuori scope per PC fuori LAN (`scripts/sync_pack.py` è solo per LAN/poly).
- Lo zip applicativo è dell'ordine di pochi MB; i round possono essere molti GB e vanno gestiti a parte.
- `.env` nel pacchetto: non pubblicare lo zip su canali non fidati.
- `hide_tabs` / `all_tabs` in `dashv2/setup.json`: restart server (`data/restart`), non solo refresh browser.

Dettagli sotto: contenuto zip, installazione destinatario, tab nascoste, limitazioni.

---

## Cosa serve (panoramica)

| Componente | Obbligatorio | Note |
|------------|--------------|------|
| Python **3.11+** | sì | 3.12 consigliato; testato anche su 3.14 |
| Cartella `dashv2/` | sì | Server web, engine replay, bot, UI statica |
| Cartella `src/` | sì | Moduli condivisi: lettura `.bin`, CLOB walk, risk, delta_win |
| `setup.json` (root repo) | sì | Parametri risk/vol/delta_win; `ticks_root` non usato in replay ma richiesto da `src/setup.py` |
| `dashv2/setup.json` | sì | `data_dir`, porta, plugin `replay`, **`hide_tabs`** (tab da nascondere) |
| `hour_bands.json` | sì | Artefatto delta_win v2 |
| `models/delta_win_v2.json` | sì | Modello DWinA/B (colonne nel `.txt`) |
| `data/YYYY-MM-DD/bin\|txt/` | sì (a parte) | Coppie round Polymarket (`.bin` + `.txt`); **non** nello zip applicativo |
| `dashv2.bat` | consigliato | Avvio rapido su Windows |
| `.env` con `CURSOR_API_KEY` | sì (pacchetto) | Incluso nello zip; tab AGENT / codegen / analyze |
| Collector `src/main.py` | no | Non incluso nel bundle |
| Sync da poly | no | Fuori scope per PC fuori LAN |

---

## Struttura dati (`data/`)

Formato canonico (vedi [`round-format.md`](round-format.md)):

```
data/
  _ticks_stub/          ← placeholder in setup.json root (nello zip)
  YYYY-MM-DD/           ← round forniti separatamente
    bin/btc5m_<market_start_ts>_<HHMM>.bin
    txt/btc5m_<market_start_ts>_<HHMM>.txt
```

La dashboard replay oggi indicizza **solo** i file `btc5m_*.bin` (mercato BTC 5m). Altri asset (`eth5m`, …) possono essere presenti in `data/` ma non compaiono nel picker finché non si estende `RoundRepository`.

---

## File codice inclusi nel bundle

### `dashv2/` (intera app)

- Entrypoint: `python -m dashv2` o `dashv2.bat`
- Config: `dashv2/setup.json` → `data_dir: "../data"`
- UI: `dashv2/static/` (HTML/CSS/JS + vendor locali, nessuna build)
- Storico simulazioni: `dashv2/history/` (vuota nel pacchetto iniziale; si popola a runtime)

**Esclusi dal pacchetto:** `dashv2/tests/`, `dashv2/history/*`, `__pycache__/`, **tutti i round in `data/`** (solo `data/_ticks_stub/.keep`).

### `src/` (sottoinsieme replay)

Moduli usati direttamente o in transitivo da dashV2:

| Modulo | Uso |
|--------|-----|
| `binary_format.py` | `read_round()`, path `.txt` |
| `book.py` | `BookSnapshot`, LOB |
| `clob_api.py` | walk ask/bid, `majority_side` |
| `risk.py` | Rq/Rs per tick |
| `delta_win.py` | parse colonne DWin dal `.txt` |
| `delta_win_bands.py` | supporto delta_win |
| `vol_stats.py` | finestre volatilità |
| `lighter_ticks.py` | banda oraria (import lazy da delta_win) |
| `setup.py` | costanti da `setup.json` root |

Non servono per il replay: `main.py`, `round_runner.py`, `feed_*`, `market.py`, `gamma_patch.py`, ecc.

Nel pacchetto si include comunque **tutta** `src/` per semplicità (~2 MB).

### Root repo

| File | Ruolo |
|------|-------|
| `setup.json` | Config collector condivisa; dashV2 legge risk/vol/delta_win |
| `hour_bands.json` | Hash bande orarie delta_win |
| `models/delta_win_v2.json` | Modello calibrato |
| `requirements-dashv2-offline.txt` | Dipendenze pip unite (dashv2 + numpy) |

---

## Dipendenze Python

```bash
pip install -r requirements-dashv2-offline.txt
```

Contenuto tipico:

- `flask`, `flask-socketio`, `python-socketio`, `eventlet` — server web
- `numpy` — risk / delta_win
- `python-dotenv`, `cursor-sdk` — opzionali per funzioni AI (`.env`)

**Non** servono `httpx`, `websocket-client`, `scikit-learn` del `requirements.txt` collector.

---

## Creare il pacchetto (PC sorgente)

Dalla root del repo:

```powershell
# Zip applicativo (codice, senza round in data/)
python scripts/dashv2_pack.py --output dist/btc5min-dashv2-offline.zip

# Con tab sperimentali già nascoste in dashv2/setup.json
python scripts/dashv2_pack.py --output dist/btc5min-dashv2-offline.zip --hide-tabs backtest_analysis round_chat
```

Oppure: `scripts\dashv2_pack.bat`

`--hide-tabs` accetta le chiavi di `all_tabs` in `dashv2/setup.json` (es. `backtest_analysis`). Se omesso, il pacchetto copia `hide_tabs` dal repo di sviluppo.

Lo script genera anche `INSTALL.md` dentro lo zip con istruzioni per il destinatario.

---

## Round sul PC destinazione

1. Estrarre lo zip applicativo in `C:\btc5min` (o equivalente).
2. Copiare i round sotto `data/YYYY-MM-DD/bin` e `data/YYYY-MM-DD/txt` (merge, non sovrascrivere altri giorni se non serve).
3. Avviare `dashv2.bat`.

**Aggiornamenti round:** stessa procedura manuale (nuovi giorni in `data/`). Non c'è script di packaging tick in questo repo.

---

## Installazione sul PC destinazione (tester Windows)

Istruzioni complete in **`INSTALL.md`** dentro lo zip. Per un tester non tecnico:

1. Installare Python 3.11+ da [python.org](https://www.python.org/downloads/) con **"Add python.exe to PATH"** (solo se non già presente).
2. Estrarre lo zip in una cartella senza spazi (es. `C:\btc5min`).
3. **Doppio click su `install.bat`** (una volta; crea la cartella `.venv` e installa i pacchetti).
4. Copiare i round ricevuti nella cartella `data/`.
5. **Doppio click su `dashv2.bat`** → browser su `http://127.0.0.1:8780/`.

`dashv2.bat` usa `.venv\Scripts\python.exe` se presente (come sul PC dev).

Verifica rapida: nel picker round compare l'ultimo giorno in `data/`; caricare un round → play → timeline avanza.

---

## Configurazione post-install

| File | Cosa controllare |
|------|------------------|
| `dashv2/setup.json` | `host`/`port` (default `127.0.0.1:8780`), `data_dir`, **`hide_tabs`** |
| `setup.json` | `ticks_root` nel pacchetto è `data/_ticks_stub` (placeholder; replay non lo usa) |
| `.env` | Incluso nel pacchetto (`CURSOR_API_KEY`) |

Dopo modifiche a `dashv2/*.py` o `dashv2/setup.json`: creare file vuoto `data/restart` per reload (vedi `AGENTS.md`).

### Tab nascoste (`hide_tabs`)

In `dashv2/setup.json`:

- **`all_tabs`**: elenco di riferimento di tutte le tab disponibili (non modificarlo a mano salvo aggiornamenti di versione dashV2).
- **`hide_tabs`**: tab da **non** mostrare. Lista vuota = tutte visibili.

| Chiave in `all_tabs` | Tab UI |
|--------|--------|
| `candles` | CANDLES |
| `accounts` | ACCOUNTS |
| `strategy` | STRATEGY |
| `backtest` | BACKTEST |
| `backtest_analysis` | BACKTEST ANALYSIS |
| `round_chat` | ROUND CHAT |

Esempio per utente esterno (nascondere funzioni sperimentali):

```json
"hide_tabs": ["backtest_analysis", "round_chat"]
```

Non si possono nascondere tutte le tab; voci in `hide_tabs` devono essere presenti in `all_tabs`. Dopo la modifica serve **restart server** (`data/restart`).

---

## Cosa non è incluso / limitazioni

- **Collector live** e feed Polymarket real-time (`engine_plugin: live` è stub).
- **Sync automatico** da poly (PC fuori LAN).
- **Round** nello zip applicativo (vanno forniti separatamente).
- Round **mancanti** nel dataset: il picker li mostra come slot vuoti (`missing round`).
- Storico account replay (`dashv2/history/`) parte vuoto; ogni PC ha ledger proprio.
- Il pacchetto include `.env` con credenziali: **non pubblicare** lo zip su canali non fidati.

---

## Riferimenti

- Architettura dashV2: [`dashv2-architecture.md`](dashv2-architecture.md)
- Formato round: [`round-format.md`](round-format.md)
- Avvio e restart: [`AGENTS.md`](../AGENTS.md) (sezione Dashboard)
- Script packaging: [`scripts/dashv2_pack.py`](../scripts/dashv2_pack.py)
