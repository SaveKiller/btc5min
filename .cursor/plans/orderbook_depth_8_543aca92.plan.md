---
name: Orderbook depth 8
overview: Limitare lo snapshot salvato nel `.bin` ai top-8 livelli per lato, restando al campionamento 1 Hz attuale. Layout v6 invariato; i file storici full-depth restano leggibili. Workflow a due gate — (1) codice+test locale su un round intero, stop e OK utente; (2) deploy poly a metà round + verifica del primo round prodotto.
todos:
  - id: truncate-snapshot
    content: BOOK_DEPTH=8 + truncate_side in snapshot_books (book RAM resta full)
    status: completed
  - id: config-docs-test
    content: setup.json/setup.py se config; docs/round-format.md; unit test truncate/BBO
    status: completed
  - id: local-round-verify
    content: "Test locale: 1 round intero in cartella test → size/depth/verify; STOP e chiedere OK utente"
    status: completed
  - id: deploy-poly
    content: "SOLO dopo OK utente: sync+restart metà round; attendere 1° round; verify su poly"
    status: completed
isProject: false
---

# Depth 8 a 1 Hz (solo snapshot)

## Scope fissato

- **Campionamento:** invariato (1 tick/sec, [`SamplerThread`](src/round_runner.py)).
- **Profondità salvata:** max **8** livelli per lato (`up_bids/asks`, `down_bids/asks`).
- **Formato:** `.bin` v6 invariato (i conteggi uint16 già supportano N qualsiasi).
- **Storico:** **nessuna riscrittura** dei round già su disco (restano full-depth). Solo i round nuovi dal cutover collector.
- **Non incluso:** campionamento event-driven / BBO (piano separato [`event_bbo_tick_sampling_e3b2459e.plan.md`](.cursor/plans/event_bbo_tick_sampling_e3b2459e.plan.md)).

## Perché è lineare

Il book in RAM del CLOB resta **completo** (serve per applicare correttamente `price_change` su livelli profondi). Si tronca **solo al momento dello snapshot** in [`snapshot_books`](src/feed_clob.py):

```119:132:src/feed_clob.py
def snapshot_books(state: RoundState):
    ...
    return BookSnapshot(
        copy.deepcopy(up.bids), copy.deepcopy(up.asks),
        ...
```

`read_round` / dashboard / bot / `market_buy_walk` non assumono una profondità minima fissa: usano i livelli presenti. Quindi **zero cambi** a protocollo Socket.IO, asse `sec`, strategie, convert `.txt` (salvo `majority_gain` calcolato sul book troncato).

## Implementazione

### Gate A — codice + verifica locale (un solo step agente)

1. **Costante** `BOOK_DEPTH = 8` in [`src/book.py`](src/book.py) (o chiave `book_depth` in [`setup.json`](setup.json) letta da [`src/setup.py`](src/setup.py) — preferibile config se il collector su `poly` deve potersi ritoccare senza rebuild mentale).
2. Helper `truncate_side(levels, n, asks: bool) -> BookSide` (sort già garantito da `OrderBook`; slice `[:n]`).
3. In `snapshot_books`: passare ai 4 lati troncati; i campi `up_bid/up_ask/...` restano da `best_bid()` / `quote_ask()` sul book **pieno** in RAM (identici al top dello snapshot).
4. Docs: una riga in [`docs/round-format.md`](docs/round-format.md) (“snapshot top-N livelli, N=`book_depth`, default 8; file pre-cutover possono avere depth maggiore”).
5. Unit test: truncate + snapshot con book finto >8 livelli → counts ≤8 e BBO invariato.
6. **Test locale su un round intero** (obbligatorio, prima di qualsiasi touch a poly):
   - Cartella dedicata, es. `data/_depth8_test/` (o path temp) — **non** mischiare con `data/` di produzione locale se in uso.
   - Far girare il collector in locale per **un round completo** (`python -m src.main --once` oppure attendere un ciclo 5m con `--out` puntato alla cartella test).
   - Criteri di OK locale:
     - `.bin` scritto + `.txt` generato;
     - size file **≪** baseline full (~850 KB) → atteso ~**100–160 KB**;
     - `python -m src.reader <bin>` → avg levels per side **≤ 8**;
     - BBO nel record tick allineato al livello 0 dello snapshot;
     - `python -m src.verify <bin>` senza errori bloccanti;
     - lettura con `read_round` ok (replay/dashboard possono aprire il file).
   - Opzionale: confrontare size dello stesso `market_start_ts` già presente in `data/` (full) vs nuovo file test (depth 8).

Niente bump di `VERSION`, niente dual-mode replay, niente sentinella `data/restart` della dashboard (cambio solo collector).

### STOP obbligatorio — OK utente

Al termine del Gate A l’agente **si ferma**: riassume size/depth/verify del round di test e **chiede esplicitamente all’utente se procedere col deploy su poly**.  
**Nessun** rsync / `systemctl` / SSH su `ticksaver` finché l’utente non dà OK.

### Gate B — deploy poly (solo dopo OK)

Eseguire la procedura sotto. Dopo il restart:

1. Attendere il **primo round completo** prodotto dal nuovo codice (non il round skippato al cutover).
2. Verificare su poly gli stessi criteri del test locale (size ~147 KB, levels ≤8, `verify` ok).
3. Riportare all’utente l’esito; solo allora il task è chiuso.

## Cutover ticksaver su `poly` (CT 103)

Host: container `poly` (`10.1.1.73`), app `/opt/btc5min`, servizio systemd `btc5min.service` (alias SSH `ticksaver`). I dati restano in `/opt/btc5min/data`.

### Comportamento attuale allo stop

Da [`src/main.py`](src/main.py): su `SIGTERM`/`SIGINT` chiama `runner.request_stop()` su i `RoundRunner` vivi, ferma feed, poi `SystemExit` **subito**. I runner sono `daemon=True`. Il `.bin` si scrive **solo a fine round** (dopo sampling 300s + poll outcome fino a `outcome_wait_sec`) in [`round_runner.py`](src/round_runner.py). Kill a metà → buffer scartato, **nessun file**.

Al riavvio, se `now >= market_start_ts` il runner **skippa** il round già iniziato (`round skipped (already started)`). Quindi il round in corso al restart è perso due volte: non flushato dal vecchio processo, non ripreso dal nuovo.

L’orchestrator può avere **fino a 2** round spawnati: corrente + prossimo (`prep_ahead_sec` = 10). Restart negli ultimi ~10s del round (o nei primi secondi del successivo mentre il precedente è ancora in outcome/write) rischia **2 round** persi.

### Perdita attesa con restart “semplice”

| Momento del `systemctl restart` | Round persi (tipico) |
|--------------------------------|----------------------|
| A metà round A (B non ancora in prep) | **1** (A) |
| Ultimi ~10s di A / overlap A+B | **1–2** |
| Durante outcome/write di A mentre B campiona | **1–2** (A non scritto + B interrotto) |

Procedura minima accettata: sync codice → `systemctl restart btc5min` **a metà di un round** (es. ~sec 150 di countdown), lontano dalla finestra di overlap → **perdi esattamente 1 round**, poi verificare i successivi 2–3 con `verify` e size `.bin` (~150 KB invece di ~850 KB).

### Si può non perdere nessun round?

Opzioni:

1. **Graceful drain (consigliato se si vuole zero loss)** — piccolo cambio a `main.py` (e flag su orchestrator), **in scope cutover**:
   - su SIGTERM: `draining=True` → **non spawnare** nuovi round;
   - **non** uccidere subito i runner già partiti: attendere `join` fino a fine scrittura (timeout generoso: durata residua + `outcome_wait_sec`);
   - poi exit → systemd riavvia il binario nuovo;
   - il nuovo processo prende il round successivo al prep.
   - Se al segnale c’è solo il round corrente → **0 round persi** (aspetti fino a ~0–5 min).
   - Se sei già in overlap A+B → aspetti che finiscano entrambi (vecchio codice/depth), poi il nuovo codice parte sul round dopo → ancora **0 persi**, restart più lungo (~5–10 min).

2. **Hot-reload solo `book_depth` da `setup.json`** — utile *dopo* che il codice di truncate è già deployato (cambio 8↔altro senza restart). **Non evita** la perdita al *primo* deploy del truncate (serve comunque un restart per caricare il nuovo `.py`).

3. **Due collector in parallelo (blue/green)** — stessi token WS, due processi, merge file: fragile e fuori proporzione.

4. **Flush parziale a SIGTERM** — scrive un `.bin` incompleto: non è “zero loss” di qualità (fail `verify` / tick_count≠300); sconsigliato.

**Verdetto:** per un cambio così piccolo, **accettare 1 round perso** con restart a metà round è proporzionato. Il **graceful drain** vale la pena solo se si vuole abituare il collector a deploy a caldo senza buchi (~20–40 righe, riusabile per ogni futuro deploy su `poly`). Non vale blue/green.

**Scelta di piano:** documentare entrambe; in implementazione fare il truncate + procedura “perdi 1 round”; aggiungere graceful drain **solo se** richiesto esplicitamente al momento dell’esecution (default = non implementarlo in questo task).

### Procedura deploy operativa su poly (Gate B — solo dopo OK utente)

Riferimento sync: [`meetings/bug-poly-collector/context/deploy-ct-lan-poly.md`](meetings/bug-poly-collector/context/deploy-ct-lan-poly.md). Host SSH `ticksaver` → `root@10.1.1.73`, app `/opt/btc5min`, servizio `btc5min`.

**Prerequisito:** Gate A completato (round di test locale OK) **e** conferma esplicita dell’utente.

**Obiettivo cutover:** perdere **esattamente 1 round**, mai 2. Il restart va fatto **a metà del round corrente**, fuori dalla finestra di overlap.

#### Timeline di un round (perché “metà”)

I round partono ogni 5 minuti UTC (`:00`, `:05`, `:10`, …). Per un round che inizia a `T`:

| Istante | Cosa succede | Restart qui |
|---------|----------------|-------------|
| `T − 10s` | spawn prep del round (`prep_ahead_sec`) | rischioso se l’altro è ancora vivo |
| `T` … `T+60s` | inizio sampling | ok ma preferibile più al centro |
| **`T+90s` … `T+210s`** | **finestra sicura (metà)** — un solo runner in sampling, prossimo non ancora in prep | **qui** |
| `T+240s` … `T+289s` | avvicinamento a fine | evitare |
| `T+290s` … `T+300s` | **overlap**: round corrente + prep del successivo | **NO → fino a 2 persi** |
| `T+300s` … `T+300s+outcome_wait` | write/outcome del precedente mentre il nuovo campiona | **NO → fino a 2 persi** |

In pratica: i minuti UTC del blocco 5m devono essere **+1, +2 o +3** rispetto all’inizio slot (es. round `16:05` → restart tra `16:06:30` e `16:08:30`, ideale ~`16:07:30`).

#### Passi

1. **Sync codice (processo vecchio ancora in esecuzione — non restartare ancora)**  
   Da `F:\btc5min` (PowerShell / Git Bash), **senza** toccare `data/`:

```bash
# esempio rsync (Git Bash/WSL)
rsync -avz --exclude data --exclude .venv --exclude .git --exclude __pycache__ \
  --exclude dashv2/history --exclude .cursor \
  /f/btc5min/ ticksaver:/opt/btc5min/
```

   Oppure `scp` mirato almeno di `src/` + `setup.json` (se `book_depth` è in config). Il collector continua a scrivere full-depth finché non si riavvia.

2. **Aspettare la finestra di metà round**  
   Su poly:

```bash
ssh ticksaver
date -u
# secondi nel blocco 5m: ((minute*60+second) % 300)  → target ~90..210
python3 -c "import time; t=int(time.time()); print('utc', time.strftime('%H:%M:%S', time.gmtime(t)), 'offset_in_slot', t%300)"
```

   Procedi solo se `offset_in_slot` ∈ **[90, 210]**. Se sei a `<90` o `>210`, aspetta.  
   Cross-check log (countdown ~150):

```bash
tail -f /opt/btc5min/data/collector.log
# oppure: journalctl -u btc5min -f
```

3. **Restart immediato nella finestra**

```bash
systemctl restart btc5min
systemctl status btc5min --no-pager
```

4. **Verifica post-cutover (stessi criteri del test locale)**
   - Nei log: `round … skipped (already started)` per il round interrotto (atteso).
   - **Attendere** che finisca il **primo round completo** col nuovo codice (fino a ~5 min + eventuale outcome), non dichiarare successo sul solo restart.
   - Su quel `.bin` verificare come in locale:

```bash
ls -la /opt/btc5min/data/$(date -u +%Y-%m-%d)/bin/ | tail
cd /opt/btc5min && ./venv/bin/python3 -m src.reader data/.../btc5m_<ts>_....bin
# avg levels per side ≤ 8; size ~100–160 KB
./venv/bin/python3 -m src.verify data/.../btc5m_<ts>_....bin
```

   - Confrontare mentalmente con i numeri del Gate A; se size/depth/verify non allineati → fermarsi e segnalare all’utente (non “ok silenzioso”).

5. **Cosa non fare**
   - Non partire col Gate B senza OK utente dopo il test locale.
   - Non restartare negli ultimi ~60s del round né nei primi secondi dopo il boundary.
   - Non fare `restart` “alla cieca” subito dopo lo sync senza guardare `offset_in_slot`.
   - Non riscrivere/cancellare lo storico full-depth.

### Checklist rapida (due gate)

**Gate A (locale)**
1. Modifica codice depth 8 + unit test.
2. Un round intero in cartella test (`--out`).
3. Size ↓, levels ≤8, `verify` ok.
4. **STOP → chiedere OK all’utente.**

**Gate B (poly, solo dopo OK)**
1. Sync codice su `/opt/btc5min` (rsync/scp; non toccare `data/`).
2. Attendere `offset_in_slot` ∈ [90, 210] (metà round UTC).
3. `systemctl restart btc5min`.
4. Attendere 1° round completo post-skip; size/levels/`verify` come in locale.
5. Nessun rewrite dello storico.

## Conseguenze (misurate / attese)

Dati sui 2670 round locali già analizzati:

| Effetto | Valutazione |
|---------|-------------|
| **Spazio `.bin` nuovi** | ~865 KB → ~**147 KB**/round (**−83%**); archivio analogo 2256→~384 MB |
| **Quota BBO / UI** | **Invariata** (livello 0 identico; mismatch osservati = 0) |
| **Fill $100** (default dashboard) | ~99.4% tick fillabili ≈ full |
| **Fill $200** | 98.8% vs 99.3% full (−0.5 pp) |
| **Fill $500** | 95.6% vs 99.0% (−3.4 pp) — size grandi falliscono più spesso |
| **`majority_gain` / enrich** | Walk $100 su top-8: allineato al full nella quasi totalità dei tick |
| **Replay / bot / strategie** | Stesso clock 1 Hz; walk close/buy usano book più corto → stessi limiti size |
| **File storici** | Replay full-depth come oggi; mix depth nell’archivio è ok |
| **Verify / reader** | Nessun check “depth==full”; ok |
| **RAM collector** | Book live resta full; buffer round più leggero (~5–6× meno per gli snapshot) |
| **UI dashboard** | Nessun DOM orderbook; solo effetto indiretto su walk size grandi. La `reference-ladder` (delta vs PTB) **non** usa i livelli CLOB |
| **Cutover poly** | ≥1 round perso con restart semplice; 0 con graceful drain (opzionale) |

## Rischi residui

- Size bot/strategie `>>$200` su round nuovi: più `insufficient ask/bid liquidity` rispetto allo storico full.
- Analisi future che usano imbalance/depth oltre L8 sui file nuovi non avranno quei livelli (per design).
- Se qualcuno assume “tutti i `.bin` hanno ~45 livelli”, le medie depth calano dopo il cutover — documentare.
- Restart nella finestra di overlap (ultimi 10s / outcome) può costare **2** round se non si usa drain.

## Fuori scope esplicito

- Riscrittura/backfill storico a depth 8.
- Cambio frequenza campionamento.
- Modifiche dashv2 oltre all’effetto automatico del book letto.
- Blue/green dual collector.
- Graceful drain (fuori dal default di questo task; da fare solo su richiesta).
