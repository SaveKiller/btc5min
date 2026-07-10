---
name: Indice di rischio di perdita R
overview: Costruire un indice sperimentale R (1–9) del rischio che il lato maggioritario scelto perda al settlement, mantenendo probabilità continue fino alla visualizzazione. Pq0 (quota normalizzata) è il benchmark principale, Pz_W è la diagnostica fisica multi-finestra e una composita Rc verrà adottata solo se dimostra valore incrementale fuori campione. Il calcolo è live-safe, il .bin resta v6 e la label canonica è sempre l'outcome ufficiale dell'header.
todos:
  - id: fix-vol-window
    content: "Fix finestra look-ahead in compute_trailing_vol (passato: [sec, sec+W-1])"
    status: completed
  - id: freeze-contract
    content: Congelare target, label ufficiale, regole di eleggibilità e qualità
    status: pending
  - id: setup-risk
    content: Configurare V30/V60/V120 e chiavi risk_* obbligatorie in setup.json/src/setup.py
    status: completed
  - id: risk-baselines
    content: Implementare src/risk.py con Pq0 e Pz_W continui, score R e metadati di qualità
    status: pending
  - id: risk-tests
    content: Aggiungere test anti-look-ahead, batch-vs-live e casi tie/partial/stale/vol nulla
    status: pending
  - id: eval-preview
    content: Creare scripts/eval_risk.py e riprodurre la preview con ablation e pesi per round
    status: completed
  - id: convert-integration
    content: Integrare nel TXT solo Rq/Rd utili, eleggibilità e metadati versione
    status: completed
  - id: verify-outcome
    content: Rendere i mismatch prezzi Gamma diagnostici senza invalidare l'outcome ufficiale
    status: pending
  - id: regen-verify
    content: Rigenerare i TXT e verificare integrità binaria e test statistici dedicati
    status: completed
  - id: docs
    content: Aggiornare AGENTS.md e correggere il vecchio piano volatilità
    status: completed
  - id: massive-test
    content: Eseguire test cronologico multi-giornata, calibrazione e selezione della composita
    status: completed
  - id: policy-backtest
    content: Backtestare una decisione per round, EV, P&L e paper trading
    status: pending
isProject: false
---

# Indice R (1–9) del rischio di perdita a settlement

## Obiettivo

Per ogni tick eleggibile, stimare il rischio che una puntata sul lato maggioritario CLOB corrente perda al settlement. L'evento primario non è un semplice cambio temporaneo della maggioranza: è l'outcome ufficiale finale diverso dal lato scelto.

Il calcolo deve usare esclusivamente dati già disponibili alla riga corrente. Il `.bin` v6 resta canonico e invariato; probabilità, score R e diagnostica vengono derivati da `python -m src.convert` e dagli script di valutazione.

Finché non viene eseguita una calibrazione multi-giornata, R va chiamato **score sperimentale di rischio 1–9**, non probabilità calibrata.

## Decisioni corrette e vincolanti

- Target primario: perdita a settlement (`Y_loss`).
- Target secondario: futuro flip CLOB persistente (`Y_flip`), solo diagnostico e valutato separatamente.
- Label canonica: `outcome` dell'header, sempre considerato ufficiale, affidabile e definitivo perché proveniente da Polymarket.
- PTB live: `ptb_chainlink`, coerente con il delta mostrato nel TXT.
- Probabilità continue conservate fino all'ultimo passo; R è soltanto la loro visualizzazione per bucket.
- `Pq0` basata sulla quota normalizzata è il benchmark principale da battere.
- `Pz_W` resta una baseline/diagnostica fisica, calcolata per più finestre.
- `Rc` non è preselezionata. Verrà costruita e adottata solo se migliora `Pq0` fuori campione.
- `max(Rq, Rd)` può esistere soltanto come benchmark prudenziale `Rmax`, non come probabilità.
- Tick non eseguibili o con target indefinito non ricevono silenziosamente un rischio basso: mostrano `R=-` e un motivo.

## Stato attuale del repository

- Il fix live-safe della volatilità è già completato: `compute_trailing_vol` usa `sec_j ∈ [sec_i, sec_i + W − 1]`, cioè presente più passato sull'asse countdown.
- Il supporto multi-finestra esiste già in `src/setup.py` e `src/convert.py`; `setup.json` contiene attualmente soltanto `[60]`.
- La baseline fotografata dalla review comprende 263 round del 2026-07-09: è una sola giornata e non rappresenta regimi indipendenti.
- `src/risk.py`, `scripts/eval_risk.py`, colonne R e report riproducibili non esistono ancora.
- Il vecchio piano `volatility_indicator_ff2e0985.plan.md` conserva ancora la descrizione errata della finestra e va riallineato al codice.

## Target e label

### Target primario: perdita finale

Per una riga eleggibile al tempo `t`:

```text
Y_loss(t) = 1  se il lato maggioritario scelto a t è diverso da header.outcome
Y_loss(t) = 0  altrimenti
```

Questo è il target usato per Brier score, log loss, calibrazione, AUC e valutazione economica.

### Target secondario: flip persistente

`Y_flip(t)` vale 1 se, dopo `t`, compare una maggioranza CLOB opposta che supera una soglia di isteresi e persiste per il numero di secondi stabilito. Serve a descrivere l'instabilità del percorso, non sostituisce `Y_loss`.

Soglia di isteresi e persistenza devono essere parametri espliciti e versionati. Prima di congelarli, la preview confronterà più valori; non saranno nascosti come costanti arbitrarie nel codice.

### Outcome ufficiale dell'header

Per questo progetto non va applicata la “sanificazione” proposta al punto 7 della review:

- `header["outcome"]` è la fonte canonica e definitiva del settlement.
- `final_gamma`, `ptb_gamma`, `final_chainlink` e `ptb_chainlink` sono prezzi diagnostici, non fonti alternative della label.
- Un disaccordo fra outcome e segno di `final_gamma - ptb_gamma` non rende dubbio l'outcome e non esclude il round dal dataset.
- I quattro mismatch osservati nella review vanno interpretati come discrepanze fra campi prezzo/criteri di confronto, non come label errate.
- L'assenza di `final_gamma` non riduce l'affidabilità della label.
- Un round con `outcome=0` non è ancora etichettato e non entra nella valutazione; ogni outcome impostato a Up/Down è definitivo.
- Il controllo V13 di `src/verify.py` va trasformato da errore sull'outcome a warning diagnostico sui prezzi. V10 continua a verificare che l'outcome sia impostato.

## Separazione live/backtest e prevenzione del leakage

Il modulo live non deve ricevere `outcome`, `final_price`, `final_chainlink` o `final_gamma`. Riceve soltanto:

- tick osservati fino alla riga corrente;
- `ptb_chainlink`;
- statistiche di volatilità live-safe;
- eventualmente i book snapshot già osservati.

La label `header.outcome` entra esclusivamente in `scripts/eval_risk.py`, dopo il calcolo dei segnali.

`ptb_gamma` può essere confrontato offline in una sensitivity analysis, ma non può sostituire retroattivamente il PTB live. Se in futuro si userà Gamma live, dovrà essere registrato anche il timestamp della sua effettiva disponibilità.

## Modelli continui

### Pq0 — benchmark di mercato

Usare i mid non arrotondati e normalizzarli:

```text
up_mid   = (up_bid + up_ask) / 2
down_mid = (down_bid + down_ask) / 2
p_up     = up_mid / (up_mid + down_mid)
p_down   = 1 - p_up
q        = probabilità normalizzata del lato scelto
Pq0      = 1 - q
```

`Pq0` è la probabilità continua baseline di perdita implicita nel mercato. Lo score visuale corrispondente è `Rq = bucket(Pq0)`.

Una futura `Pq` corretta può usare, una feature alla volta:

1. slope o drawdown dei log-odds dello stesso lato corrente;
2. flip con isteresi e persistenza, evitando il rumore 49/51;
3. mismatch fra lato CLOB e segno del delta;
4. spread e affidabilità del book;
5. depth imbalance, liquidità e slippage del buy da $100.

I correttori non vengono sommati come punti R. Entrano nello spazio delle feature o dei log-odds e restano soltanto se battono `Pq0` sul holdout in un test di ablation.

### Pz_W — baseline fisica multi-finestra

Per ogni finestra W, usare dati float interni e `secs_to_expiry` non arrotondato:

```text
sigma_W         = deviazione standard per radice di secondo delle variazioni BTC valide
sigma_remaining = sigma_W * sqrt(secs_to_expiry)
delta_signed    = +delta per lato Up, -delta per lato Down
z_W             = delta_signed / sigma_remaining
Pz_W            = Phi(-z_W)
```

`Pz_W` stima, sotto il modello normale senza drift, la probabilità di trovarsi dal lato sbagliato al termine. Non è la probabilità di toccare il PTB durante il percorso e non è `Y_flip`.

Regole:

- usare il valore float non arrotondato, non il token intero `VW` del TXT;
- l'attuale `VW = std(delta) * sqrt(n_pairs)` va ricondotto a `sigma_W = VW / sqrt(n_pairs)`;
- invalidare la stima se la finestra non ha copertura temporale sufficiente o contiene un gap Chainlink stale;
- usare `chainlink_recv_ms` per misurare gap e campioni effettivamente nuovi;
- invalidare volatilità nulla/quasi nulla, senza produrre falsa certezza;
- calibrare in seguito la trasformazione normale, che non rappresenta salti e code pesanti.

Configurazione POC:

- `V30`: reattiva agli shock recenti;
- `V60`: baseline primaria mostrata nel TXT;
- `V120`: stima lenta del regime.

Lo script di valutazione confronterà inoltre rolling W15, W45, W90, EWMA con half-life 15/30/60 e W10 come controllo negativo. Confronterà anche, come esperimento separato, una realized variance per unità di tempo basata sui timestamp e sui log-price.

### Rc — composita differita

Nella prima implementazione non esiste una `Rc` operativa e non compare nel TXT. Il test massivo confronterà:

- `Pq0`;
- `Pq` con correttori validati;
- `Pz_W`;
- `Pq0` più una singola feature fisica;
- una composita regolarizzata multi-scala;
- `max(Pq, Pz)` soltanto come benchmark prudenziale.

Forma candidata:

```text
logit(Pc) =
    beta0
  + beta1 * logit(Pq0)
  + beta2 * z
  + beta3 * log(sigma_fast / sigma_slow)
  + beta4 * momentum_quota
  + beta5 * mismatch
```

`Rc` verrà adottata solo se migliora calibrazione e valore economico rispetto a `Pq0` su giornate mai viste.

## Eleggibilità e qualità

Separare sempre valore di rischio, qualità della componente ed eleggibilità dell'ingresso.

- Tick partial: maggioranza corrente e book eseguibile non sono osservabili; `Rq=-`, ingresso non eleggibile. Un eventuale `Pz` su lato stimato resta diagnostica offline e non autorizza un ingresso.
- Tie o fascia neutra attorno a 50c: target economicamente ambiguo; `Rq=-`, `Rd=-`, ingresso non eleggibile.
- Chainlink stale sulla riga o dentro la finestra: `Rd=-`; `Rq` può restare disponibile se il CLOB è completo.
- Storia insufficiente: `Rd=-` con motivo `insufficient_history`.
- Volatilità nulla/quasi nulla: `Rd=-` con motivo `zero_vol`.
- Book completo ma spread/liquidità insufficienti: rischio calcolabile come diagnostica, ingresso non eseguibile.

La soglia della fascia neutra, la copertura minima della finestra e le regole di liquidità devono essere esplicite in configurazione. Per la copertura si parte da un confronto fra 80% e 100% nella preview; il valore scelto viene poi congelato, senza fallback nel codice.

Motivi sintetici minimi: `partial`, `tie`, `stale`, `insufficient_history`, `zero_vol`, `book_unreliable`.

## Mappatura R=1–9

La trasformazione avviene soltanto dopo aver calcolato la probabilità continua:

```text
P continua -> eventuale calibrazione -> bucket R -> visualizzazione
```

Bucket preliminari:

- R=1: P < 1%
- R=2: 1% ≤ P < 2%
- R=3: 2% ≤ P < 4%
- R=4: 4% ≤ P < 7%
- R=5: 7% ≤ P < 12%
- R=6: 12% ≤ P < 20%
- R=7: 20% ≤ P < 30%
- R=8: 30% ≤ P < 42%
- R=9: P ≥ 42%

Questi limiti sono una convenzione preliminare, non sono validati dai 263 round di una sola giornata. Brier score e log loss si calcolano sulle probabilità continue, mai sui valori R. Il report conserva probabilità, R, numerosità e intervallo di Wilson per ogni bucket e può fondere bucket troppo vuoti.

## Configurazione e formato TXT

### setup.json / src/setup.py

Chiavi obbligatorie prima dell'integrazione nel TXT, senza default. I valori di copertura e fascia neutra vengono scelti dalla preview e poi scritti esplicitamente:

- `volatility_windows_sec: [30, 60, 120]`;
- `risk_model_version`;
- `risk_target: "settlement_loss"`;
- `risk_label_source: "polymarket_header_outcome"`;
- `risk_ptb_source: "chainlink"`;
- `risk_primary_vol_window_sec: 60`, validata come membro di `volatility_windows_sec`;
- `risk_min_vol_coverage_ratio`, congelata dopo la preview;
- `risk_tie_band`, congelata dopo la preview;
- `risk_probability_buckets`;
- eventuali parametri di isteresi/persistenza usati per il solo target diagnostico `Y_flip`.

Non creare un secondo elenco `risk_vol_windows_sec`: le finestre di rischio sono derivate da `volatility_windows_sec`, evitando configurazioni contraddittorie.

### Header TXT

Aggiungere:

- `risk_model_version`;
- `risk_status: experimental_uncalibrated` finché non esiste calibrazione holdout;
- `risk_target`;
- `risk_label_source`;
- `risk_ptb_source`;
- `risk_primary_vol_window_sec`;
- `risk_min_vol_coverage_ratio`;
- `risk_probability_buckets`;
- varianti effettivamente mostrate.

### Riga TXT

Dopo la preview, mostrare inizialmente solo i componenti utili alla lettura:

```text
... V30=18 V60=22 V120=31  Rq=5 Rd=4 eligible=full
... V30=--- V60=--- V120=---  Rq=5 Rd=- eligible=q_only(stale)
... V30=18 V60=22 V120=31  Rq=- Rd=- eligible=no(partial)
```

`Rd` nel TXT usa la finestra primaria W60; tutte le `Pz_W` rimangono disponibili nel report. Le probabilità continue restano nell'output JSON/CSV di valutazione. `Rc` non viene mostrata finché non è validata.

## Contratto del modulo

`src/risk.py` deve esporre un contratto esplicito simile a:

```python
compute_risk_state(ticks, ptb_chainlink, vol_stats_by_window, books=None)
```

Il risultato contiene:

- `Pq0` e `Rq`;
- `Pz_W` e `Rd_W`;
- qualità/eleggibilità per componente;
- motivo di indisponibilità;
- feature continue necessarie alla valutazione.

Outcome e prezzi finali non fanno parte della firma. I book restano opzionali finché spread/depth non entrano nel benchmark.

## File coinvolti

- `src/convert.py`: statistiche vol float/qualità, integrazione dei token R e header.
- `src/risk.py` (nuovo): probabilità continue, mapping R, eleggibilità e feature.
- `setup.json` e `src/setup.py`: finestre e parametri obbligatori/versionati.
- `scripts/eval_risk.py` (nuovo): label da header, ablation, calibrazione, metriche e report.
- `tests/test_risk.py` (nuovo): anti-leakage, equivalenza live/batch e casi limite.
- `src/verify.py`: V13 diagnostico sui prezzi, senza invalidare l'outcome ufficiale.
- `AGENTS.md`: semantica di R, label ufficiale, formule, qualità e comandi.
- `.cursor/plans/volatility_indicator_ff2e0985.plan.md`: correggere l'asse countdown ormai superato.
- `data/reports/risk_eval_<timestamp>.json`: report riproducibile con configurazione e versione.

## Preview attuale e baseline da riprodurre

La review ha prodotto risultati esplorativi su 263 round di una sola giornata, righe `sec=1..180`, escludendo partial, tie e Chainlink stale:

- tasso di perdita osservato: 19,53%;
- `Pq0`: Brier 0,13425, AUC 0,77560;
- `Pz_W60`: Brier 0,14592, AUC 0,74315;
- `Pz_W90`: Brier 0,14534, AUC 0,74321;
- `Pz_W120`: Brier 0,14548, AUC 0,74144;
- `max(Pq0, Pz_W90)`: Brier 0,13809, peggiore di `Pq0`;
- differenza W90-W60: -0,00060, IC cluster 95% [-0,00166, +0,00039].

Il minimo Brier fisico osservato cambia con l'orizzonte: W60 a 121–180 secondi, W90 a 61–120 e W120 sotto i 60 secondi. È un indizio a favore del confronto multi-scala, non una regola adattiva già validata.

Questi numeri:

- vanno riprodotti dal nuovo script prima di usarli;
- non dimostrano che W90 sia migliore di W60;
- mostrano che la baseline fisica è sottocalibrata e che il mercato contiene più informazione;
- non giustificano `max` come composita preferita;
- non trattano i tick dello stesso round come outcome indipendenti.

L'outcome usato nella preview e in ogni nuova valutazione resta quello ufficiale dell'header. Nessun filtro basato su `final_gamma` deve cambiare il dataset principale.

## Validazione POC

### Test funzionali e anti-leakage

- Modificare tutti i tick futuri rispetto a una riga e verificare che il risultato della riga non cambi.
- Confrontare calcolo batch e calcolo incrementale live.
- Verificare estremi `[sec, sec+W-1]`, ordine temporale e copertura reale.
- Testare tie, partial, stale corrente, gap stale interno, sigma nulla, mismatch e quote estreme.
- Verificare che i calcoli usino mid, delta, volatilità e `secs_to_expiry` non arrotondati.
- Verificare che `src/risk.py` non possa accedere a outcome o prezzi finali.
- Verificare mapping dei bucket sui valori di confine.

`python -m src.verify` resta necessario per l'integrità del `.bin`, ma non sostituisce i test statistici di R.

### Preview con ablation

Lo script deve rilevare dinamicamente i round disponibili e produrre risultati per:

- fasce 121–180, 61–120, 31–60 e 1–30 secondi;
- `Pq0`;
- ogni `Pz_W`;
- quota più una sola feature per volta;
- eventuale `Rmax` solo come benchmark;
- pesi uguali per round oltre alle metriche tick-level descrittive;
- copertura/eleggibilità per modello;
- Brier, log loss, reliability curve, calibration intercept/slope e AUC secondaria;
- stabilità per ora, quota e regime di volatilità.

La preview serve a trovare leakage, bug, feature inutili e casi limite. Non sceglie soglie definitive né una composita.

## Test massivo multi-giornata

2.000–3.000 round equivalgono a circa 7–11 giorni: sono sufficienti per una prima verifica, non per validare rischi sotto l'1%. Per una scelta operativa puntare ad almeno 30 giornate distinte.

Protocollo:

1. congelare specifica, feature e versione prima del vero holdout;
2. split cronologico per giornata, mai casuale per tick;
3. train iniziale, periodo successivo di calibrazione e holdout finale mai consultato;
4. conferma walk-forward;
5. bootstrap a cluster prima per giorno e poi per round;
6. confronti paired sugli stessi ingressi;
7. ablation rispetto a `Pq0`;
8. selezione di una sola versione operativa e nuova versione se cambia la formula.

Metriche:

- Brier e log loss;
- reliability curve, calibration intercept/slope;
- AUC come metrica secondaria;
- differenza incrementale rispetto a `Pq0`;
- copertura delle righe eleggibili;
- stabilità per giorno, fascia oraria, secondi, quota e regime;
- P&L, drawdown, hit rate e numero di entrate.

## Collegamento all'obiettivo economico

R misura il rischio, ma non determina da solo la convenienza. Con `g = majority_gain` e `p = probabilità calibrata di perdita`:

```text
EV = (1-p) * g - p
break-even: p < g / (1+g)
```

La strategia deve usare `EV_est`, liquidità e limite di rischio, includendo fee e slippage del market buy da $100.

Il backtest realistico usa una sola decisione per round, per esempio il primo secondo eleggibile che supera le soglie. Trattare ogni tick come puntata indipendente sovrastima l'evidenza. Dopo il backtest segue paper trading live prima di qualunque uso reale.

## Versionamento e riproducibilità

Ogni TXT/report registra:

- versione del modello;
- target e fonte label;
- sorgente PTB;
- finestre e parametri;
- stato calibrato/non calibrato;
- commit/versione del codice nel report massivo;
- intervallo date e split cronologico.

Lo stesso `.bin` può essere riconvertito con formule differenti: due score con versione diversa non devono apparire equivalenti.

## Esperimenti successivi

### Informazioni dal book

Dopo le baseline, testare separatamente spread, depth imbalance, profondità necessaria per $100, variazione della liquidità e differenza fra mid e prezzo eseguibile.

### Mercati 15m e 1h

Registrare quote simultanee e misurare il valore incrementale rispetto al 5m. Non assumere che il mercato più lungo compensi automaticamente una perdita: costi, correlazione e payoff congiunto devono essere backtestati.

## Sequenza di implementazione

1. ~~Correggere la finestra live-safe della volatilità~~ — completato.
2. Congelare target, label ufficiale e semantica di qualità/eleggibilità; definire le griglie sperimentali per tie e copertura.
3. Portare `volatility_windows_sec` a `[30, 60, 120]` e aggiungere i metadati `risk_*` già definitivi.
4. Esporre statistiche di volatilità float e qualità della finestra senza cambiare il `.bin`.
5. Implementare `Pq0`, `Pz_W`, mapping R e qualità in `src/risk.py`.
6. Aggiungere test anti-look-ahead, batch-vs-live e casi limite.
7. Implementare `scripts/eval_risk.py` e riprodurre la baseline della review.
8. Eseguire ablation; scegliere componenti, fascia neutra e copertura, quindi congelarne i valori obbligatori in `setup.json`.
9. Integrare inizialmente `Rq`, `Rd` W60 ed eleggibilità in `convert`.
10. Rendere V13 diagnostico e mantenere l'outcome dell'header come label definitiva.
11. Rigenerare i TXT, eseguire `verify` e la suite dedicata.
12. Aggiornare AGENTS.md e correggere il vecchio piano volatilità.
13. Distribuire sul container poly solo dopo validazione POC esplicita.
14. Congelare la versione e raccogliere almeno 30 giornate.
15. Eseguire test cronologico, calibrazione e selezione dell'eventuale Rc.
16. Backtestare la policy a una decisione per round e avviare paper trading.

## Rischi

- Una sola giornata non permette di validare calibrazione, bucket rari o stabilità fra regimi.
- I tick dello stesso round sono fortemente correlati.
- `Pz_W` assume dinamica normale senza drift e tende a essere ottimista in presenza di salti.
- Una composita può peggiorare il benchmark di mercato se aggiunge feature rumorose.
- Tie, partial, stall e copertura incompleta possono creare falsa sicurezza se non separati dal rischio.
- Cambiare soglie mentre si osserva il futuro holdout annulla il valore confermativo del test.
- Un risultato statisticamente migliore può non essere economicamente utile dopo fee, spread e slippage.

## Criterio finale di successo

Su giornate future e ingressi realmente eseguibili:

1. probabilità ben calibrate;
2. miglioramento misurabile rispetto a `Pq0`;
3. copertura e qualità esplicite;
4. EV e P&L positivi dopo fee e slippage;
5. stabilità fra giorni e regimi;
6. formula unica, semplice e versionata.