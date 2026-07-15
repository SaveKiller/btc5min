---
name: account-tabs-layout
overview: Riorganizzare la dashboard mantenendo invariato l’header Replay e il pannello Orders, con area centrale a due colonne full-height. Introdurre account persistenti in JSON, ognuno con metadati, ledger di tutte le scommesse completate e statistiche derivate.
todos:
  - id: account-repository
    content: Sostituire la persistenza per run con repository JSON per account e metriche derivate.
    status: completed
  - id: engine-protocol
    content: Integrare selezione/gestione account nel protocollo, negli ordini e nel settlement.
    status: completed
  - id: two-panel-layout
    content: Riorganizzare HTML/CSS in layout full-height a due pannelli con tabs Bootstrap.
    status: completed
  - id: account-client
    content: Implementare UI ACCOUNTS, modali, rendering e placeholder NO ORDERS.
    status: completed
  - id: tests-smoke
    content: Aggiornare i test di history/seek e validare il flusso completo.
    status: completed
isProject: false
---

# Layout dashboard e account persistenti

## Obiettivo
- Conservare invariato l’header Replay e il pannello Orders; rendere la workspace sottostante composta da due pannelli affiancati fino al fondo del viewport.
- Trasformare la colonna sinistra in Bootstrap tabs: `CANDLES` e `ACCOUNTS`.
- Sostituire i JSON per singola run con un JSON mutabile per account, senza importare i file legacy esistenti.

## Decisioni confermate
- I file history legacy restano un archivio non visualizzato; non vengono migrati.
- Al primo avvio non esiste un account: compare l’invito a crearlo e BUY resta disabilitato.
- La balance è informativa: non limita l’importo dell’ordine; viene aggiornata con il PnL realizzato.
- Vittorie/sconfitte: un ordine chiuso manualmente è una vittoria/sconfitta in base al suo PnL reale; gli ordini a PnL zero non contano.
- Ogni ordine è assegnato all’account selezionato all’acquisto. Non è possibile cambiare account con ordini aperti.
- Il ledger e le metriche persistenti vengono aggiornati solo a `sec 0`; chiusure manuali durante il replay rimangono dati live per rendere seek/restart reversibili.
- Nuovo account: nome, balance iniziale e nota. I tre campi sono modificabili in seguito tramite un pulsante esplicito `Modifica account`; `Rinomina` resta dedicato al nome.

## Persistenza e protocollo
- Rifattorizzare [F:\btc5min\dashv2\history.py](F:\btc5min\dashv2\history.py) in repository account, usando `history/accounts/account_<id>.json`; il nome file deriva da un ID stabile, quindi il rename non sposta file.
- Ogni file conterrà schema/versione, `id`, nome, nota, balance iniziale, timestamp e un unico ledger `orders`. Le statistiche esposte saranno calcolate dal ledger: balance corrente, PnL realizzato, gain %, vittorie, sconfitte, win rate, numero ordini, capitale puntato e puntata media.
- A settlement, [F:\btc5min\dashv2\engine.py](F:\btc5min\dashv2\engine.py) raggrupperà gli ordini chiusi per `account_id` e li aggiungerà atomicamente ai rispettivi JSON. Il `account_id` sarà assegnato in [F:\btc5min\dashv2\orders.py](F:\btc5min\dashv2\orders.py) al momento del BUY.
- Esporre i comandi Socket.IO `account.list`, `account.select`, `account.create`, `account.rename` e `account.update`, inoltrati senza logica business da [F:\btc5min\dashv2\server.py](F:\btc5min\dashv2\server.py). Bootstrap/session/history includeranno account selezionato, elenco sintetico e payload della pagina ACCOUNTS.
- Preservare l’anti-spoiler: gli ordini del round corrente entrano nel JSON e nella history persistente solo dopo settlement. La tabella mostrerà anche `Payout` (risultato ipotetico se mantenuto fino al termine) accanto al PnL effettivamente realizzato.

## UI e layout
- Ristrutturare [F:\btc5min\dashv2\static\index.html](F:\btc5min\dashv2\static\index.html): sotto l’header invariato, due pannelli `left` e `right` con altezza disponibile del viewport. Il sinistro conterrà `nav-tabs` Bootstrap e due `tab-pane`.
- `CANDLES` ospiterà il grafico attuale senza la history. `ACCOUNTS` conterrà tre pannelli verticali: gestione (dropdown, contatore account, Nuovo, Rinomina, Modifica), riepilogo dell’account selezionato, tabella history con Export CSV.
- Mantenere il pannello destro funzionalmente uguale. La sezione Open orders crescerà fino al bordo inferiore e, con lista vuota, mostrerà un placeholder centrato `NO ORDERS`; con ordini aperti mostrerà invece le card esistenti.
- Aggiornare [F:\btc5min\dashv2\static\css\dashboard.css](F:\btc5min\dashv2\static\css\dashboard.css) con layout flex/grid a viewport, overflow interno per tabella e lista ordini, e breakpoint che conservino un’interfaccia usabile su viewport stretti.
- Estendere [F:\btc5min\dashv2\static\js\app.js](F:\btc5min\dashv2\static\js\app.js) e [F:\btc5min\dashv2\static\js\render.js](F:\btc5min\dashv2\static\js\render.js) per stato account, modali Bootstrap, comandi account, tabella filtrata per account e blocco della dropdown mentre esistono ordini aperti.

## Validazione
- Aggiornare [F:\btc5min\dashv2\tests\test_seek_history.py](F:\btc5min\dashv2\tests\test_seek_history.py) e aggiungere test repository per CRUD account, aggiornamento atomico del ledger, metriche e filtro anti-spoiler.
- Verificare il flusso: nessun account → crea → seleziona → BUY → chiusura manuale → blocco selezione con ordine aperto → settlement → aggiornamento balance/stats/history → modifica e rename account.
- Eseguire `python -m unittest discover -s dashv2/tests` e smoke manuale della UI a viewport desktop e stretto.