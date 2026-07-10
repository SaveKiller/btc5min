# Valutazione critica del piano «Indice di rischio R»

Piano esaminato: `indice_di_rischio_r_8a292845.plan.md`  
Data della revisione: 10 luglio 2026

## Giudizio sintetico

Il piano ha una buona struttura da POC: separa un segnale fisico (`Rd`) da uno di mercato (`Rq`), mantiene il calcolo live-safe, lascia invariato il `.bin` e rimanda correttamente la calibrazione a un archivio più grande.

Non lo implementerei però nello stato attuale come se producesse già un indice probabilistico affidabile. Ci sono quattro problemi sostanziali:

1. la variabile da prevedere non è definita in modo univoco: «la quota cambia maggioranza» e «la puntata perde al settlement» sono eventi diversi;
2. `Rq` e `Rc` perdono la semantica di probabilità perché applicano correzioni e `max` dopo la trasformazione in bucket 1–9;
3. la preferenza dichiarata per `Rc = max(Rd, Rq)` non è ancora giustificata e la preview indipendente svolta in questa revisione dà anzi un primo segnale contrario;
4. `V60` è trattato come scelta già fissata, mentre la finestra deve essere confrontata con periodi più brevi e più lunghi, soprattutto per il valore incrementale che porta rispetto alla quota di mercato.

Il giudizio complessivo è quindi: **piano promettente e utile come base, ma da correggere prima dell'implementazione**. Implementarlo così com'è produrrebbe un numero molto preciso nell'aspetto, ma non ancora rigorosamente interpretabile.

## Cosa terrei

- Calcolo esclusivamente con informazioni disponibili alla riga corrente.
- `.bin` v6 canonico invariato e indicatori derivati in `convert`.
- Separazione iniziale tra fisica del prezzo e informazione del mercato.
- Esposizione temporanea di più varianti durante la fase sperimentale.
- Valutazione per fasce di secondi mancanti.
- Test futuro su migliaia di round con holdout.
- Valutazione economica finale basata sul prezzo realmente eseguibile e sulle fee.

## Stato reale del repository da riallineare nel piano

### Il fix look-ahead di V60 è già presente

Il prerequisito indicato come ancora `pending` non corrisponde allo stato corrente del codice. In `src/convert.py`, `compute_trailing_vol` usa già:

```python
hi = sec_i + window_sec - 1
idxs = [j for j in range(n) if sec_i <= secs[j] <= hi]
```

Sull'asse countdown è la finestra corretta: presente più passato osservato. Anche i TXT attuali mostrano `V60=---` all'inizio del round, non un valore calcolato col futuro.

Modifica proposta:

- segnare `fix-vol-window` come completato o rimuoverlo dal piano;
- non modificare nuovamente quella disuguaglianza;
- correggere anche il vecchio piano `volatility_indicator_ff2e0985.plan.md`, che conserva ancora la descrizione errata `[sec_i-W+1, sec_i]`.

### Il supporto multi-finestra esiste già

`src/setup.py` e `src/convert.py` supportano già un array di finestre; oggi `setup.json` contiene soltanto `[60]`. Per confrontare i periodi non serve riprogettare il formato: basta estendere la configurazione e l'analisi.

Eviterei due configurazioni indipendenti che possano contraddirsi. `risk_vol_windows_sec` dovrebbe essere derivato o validato rispetto a `volatility_windows_sec`; l'eventuale finestra primaria operativa va dichiarata separatamente e versionata.

### La numerosità indicata è superata, ma il limite statistico resta

Nella cartella canonica `data/2026-07-09/bin` risultano ora:

- 263 round completati con outcome;
- 260 con `final_gamma` disponibile;
- 4 dei 260 discordanti fra `outcome` dell'header e segno di `final_gamma - ptb_gamma`;
- tutti appartenenti alla stessa giornata.

Il piano parla ancora di 198 round. Il numero va aggiornato, ma la conclusione non cambia: una sola giornata non rappresenta regimi, orari e condizioni di mercato differenti. I quattro mismatch sono già circa l'1,5% dei round con Gamma: un rumore di label superiore alla fascia nominale R=1, quindi da risolvere prima di qualsiasi calibrazione fine.

### L'indice R non è ancora implementato

Tutti i todo del piano sono ancora pending. Non esistono `src/risk.py`, `scripts/eval_risk.py`, colonne R nei TXT o report versionati che rendano riproducibili le statistiche citate nel piano. La presente valutazione riguarda quindi la specifica e una preview indipendente, non un'implementazione esistente.

## Correzioni concettuali necessarie

### 1. Definire due target distinti

Il prompt originale usa «inversione» in due sensi:

- **flip di quota**: il lato maggioritario CLOB cambia almeno una volta dopo l'ingresso;
- **perdita finale**: l'outcome ufficiale è diverso dal lato maggioritario al momento dell'ingresso.

Non sono equivalenti. Un round può fare `Up → Down → Up` e far vincere la puntata iniziale pur avendo avuto un flip intermedio.

La differenza è già ampia nei dati esplorativi: a `sec=180` la perdita finale è circa `25,6%`, mentre almeno un successivo flip CLOB raw compare nel `46,2%` dei round; a `sec=120` sono rispettivamente `19,4%` e `35,6%`. Questi valori non sono stime generalizzabili, ma dimostrano che i due label non sono intercambiabili.

Raccomandazione:

- target primario per la strategia: `Y_loss(t) = 1` se il lato scelto a `t` perde al settlement;
- target secondario diagnostico: `Y_flip(t) = 1` se in futuro compare almeno una maggioranza opposta, con una regola di persistenza;
- chiamare il primo **rischio di perdita a settlement**, non rischio di flip;
- valutare i due target separatamente. Un solo R non deve mescolarli.

La formula `P_inv = Φ(-z)` del piano stima, sotto le sue assunzioni, la probabilità di trovarsi dal lato sbagliato alla scadenza. Non stima la probabilità di attraversare almeno una volta il PTB prima della scadenza. Per un Brownian motion senza drift, con distanza positiva dalla barriera:

```text
P(terminale oltre la barriera) = Φ(-z)
P(toccare la barriera entro T)  = 2 Φ(-z)
```

Il secondo risultato, inoltre, non coincide comunque con un flip della quota CLOB.

### 2. Conservare probabilità e score continui fino all'ultimo passo

Il piano dichiara che tutte le varianti stimano `P_inv`, ma poi:

- `Rq` trasforma subito `P_mkt` in R e aggiunge punti ordinali;
- `Rc` prende il massimo tra due categorie.

Dopo queste operazioni non esiste più una probabilità calibrata. Di conseguenza il Brier score citato nel piano non è definito in modo corretto, a meno di assegnare arbitrariamente una probabilità rappresentativa a ogni categoria.

Raccomandazione:

1. calcolare e conservare un valore continuo per ogni variante;
2. applicare eventuali correttori nello spazio delle feature o dei log-odds;
3. calibrare il valore continuo;
4. trasformare in R=1–9 soltanto per la visualizzazione;
5. calcolare Brier score e log loss sulla probabilità continua, non su R.

### 3. Non dichiarare ancora Rc come variante preferita

`max(Rd, Rq)` è comprensibile come allarme prudenziale, ma non come combinazione probabilistica:

- amplifica il rumore della componente peggiore;
- non tiene conto della forte correlazione tra quota, delta e volatilità;
- tende a sovrastimare il rischio;
- può scartare proprio le entrate che avrebbero valore atteso positivo;
- su un tick partial usa una valutazione fisica pur in assenza di un book eseguibile.

Nella preview svolta per questa revisione, il semplice `max(Pq0, Pz90)` ha un Brier di `0,13809`, peggiore del `0,13425` del solo baseline di mercato `Pq0`. Non è la stessa identica implementazione di `Rc` prevista dal piano, ma basta a mostrare che il `max` non deve essere promosso a scelta preferita senza test out-of-sample.

Raccomandazione:

- mantenere `Rd` e `Rq` separati nella fase corrente;
- chiamare l'eventuale `Rmax` «score prudenziale», non probabilità;
- costruire `Rc` solo col database grande, ad esempio con una regressione logistica piccola e regolarizzata, seguita da calibrazione:

```text
logit(Pc) =
    β0
  + β1 logit(Pq0)
  + β2 z
  + β3 log(sigma_fast / sigma_slow)
  + β4 momentum_quota
  + β5 mismatch
```

Il confronto decisivo non è «Rc è migliore di Rd», ma «aggiungere le feature fisiche migliora davvero il baseline di mercato su giornate mai viste?».

### 4. Correggere la costruzione di Rq

`P_mkt = 1-q` è un buon benchmark, ma `q` dovrebbe essere calcolato sui valori non arrotondati e normalizzato:

```text
p_up = up_mid / (up_mid + down_mid)
p_down = 1 - p_up
q = probabilità normalizzata del lato scelto
Pq0 = 1 - q
```

Modifiche suggerite ai correttori:

- il deterioramento deve seguire la probabilità dello **stesso lato attuale**, non il massimo maggioritario che può riferirsi a lati diversi;
- i flip vicino a 50c richiedono isteresi e persistenza, altrimenti il rumore `49/51` produce falsi flip;
- usare variazioni di log-odds o slope per secondo, più confrontabili tra quote diverse;
- aggiungere spread e affidabilità del book; in futuro, depth imbalance e slippage dai book snapshot;
- aggiungere ogni feature separatamente e verificarne il valore con un test di ablation;
- non sommare punti R scelti a mano se si vuole continuare a chiamare il risultato probabilità.

### 5. Definire esplicitamente righe non eleggibili

- `---- 50c`: non esiste una maggioranza economicamente sensata; non va trattata silenziosamente come Up.
- Tick partial: non è osservabile la maggioranza corrente e manca un book eseguibile.
- Chainlink stale o finestra di volatilità contaminata da uno stall: la componente fisica non è affidabile.
- Volatilità nulla o quasi nulla: senza una regola esplicita, `z` esplode e produce falsa certezza.

Raccomandazione:

- separare `risk_value` da `entry_eligible`;
- emettere `R=-` quando il target non è definito o l'ingresso non è eseguibile;
- se utile, mostrare `Rd` sui partial solo come diagnostica fisica, ma non usarlo come fallback di `Rc` per autorizzare una puntata;
- salvare un motivo sintetico: `partial`, `tie`, `stale`, `insufficient_history`;
- definire una soglia minima di copertura della finestra e non soltanto `volatility_min_changes: 5`.

### 6. Fissare la sorgente PTB senza leakage

Il delta del TXT usa intenzionalmente `ptb_chainlink`, mentre `ptb_gamma` può essere patchato più tardi. Un backtest che usasse sempre il valore Gamma finale rischierebbe di attribuire alle righe passate un'informazione che live non era ancora disponibile.

Raccomandazione:

- usare `ptb_chainlink` per la baseline coerente con il flusso live attuale;
- usare l'outcome Gamma come label quando disponibile;
- eseguire una sensitivity analysis sulle differenze Chainlink/Gamma;
- non cambiare sorgente PTB a metà archivio senza versionare il modello;
- se in futuro si vuole usare Gamma live, registrare anche il timestamp in cui il PTB ufficiale diventa disponibile.

### 7. Sanificare l'outcome usato come label

La sola presenza di `final_gamma` non rende automaticamente affidabile l'`outcome` già scritto nell'header. Nei dati correnti ci sono quattro discordanti. Inoltre `src/market.py` può inferire Up/Down da `outcomePrices >= 0.9` anche quando non trova ancora un mercato esplicitamente chiuso: è un percorso da investigare, non una prova già conclusiva della causa.

Prima della calibrazione:

- definire una fonte canonica di settlement;
- includere nel dataset principale soltanto round ufficialmente chiusi e coerenti;
- escludere o revisionare i quattro mismatch e i tre senza `final_gamma`;
- eseguire `verify` e una sensitivity analysis sui round vicini al PTB;
- non pretendere di distinguere rischi sotto l'1% finché il tasso di label dubbie non è molto inferiore.

## Analisi specifica del periodo V60

### Cosa significa realmente cambiare W

Il valore attuale è circa:

```text
VW = std(variazioni a 1 secondo nella finestra W) × sqrt(n_variazioni)
```

`V30`, `V60` e `V120` non sono direttamente confrontabili come livello di volatilità, perché il loro valore cresce fisiologicamente con `sqrt(W)`. Per confrontare il regime veloce e quello lento va usata la volatilità per radice di secondo:

```text
sigma_W = VW / sqrt(n_variazioni)
```

Un rapporto grezzo `V30/V120` sarebbe fuorviante: in un regime perfettamente stazionario vale già circa `sqrt(30/120) = 0,5`. Il rapporto informativo è `sigma_30/sigma_120`.

Per `Rd` va inoltre usato il valore float interno, non il `VW` intero arrotondato nel TXT:

```text
sigma_remaining = sigma_W × sqrt(secondi_mancanti)
z_W = delta_signed / sigma_remaining
Pz_W = Φ(-z_W)
```

Questa forma rende evidente che W è il periodo usato per **stimare il tasso di volatilità corrente**, mentre i secondi mancanti definiscono l'orizzonte della previsione.

### Preview indipendente sulle finestre disponibili

È stato eseguito un confronto preliminare sui 263 round canonici della giornata:

- righe considerate: `sec` 1–180;
- esclusi tick partial, tie e righe correnti con Chainlink stale;
- 39.358 osservazioni per-secondo;
- target: perdita finale del lato maggioritario corrente;
- formula fisica: modello normale senza drift;
- label usato: `outcome` memorizzato nell'header; sono quindi inclusi tre outcome senza `final_gamma` e i quattro mismatch appena descritti;
- le osservazioni dello stesso round sono fortemente correlate: i 39.358 tick non equivalgono a 39.358 outcome indipendenti.

| Finestra | P perdita media stimata | Brier ↓ | AUC ↑ |
|---:|---:|---:|---:|
| W10 | 12,10% | 0,15850 | 0,69469 |
| W15 | 12,93% | 0,15418 | 0,71048 |
| W20 | 13,47% | 0,15166 | 0,71968 |
| W30 | 14,14% | 0,14893 | 0,73151 |
| W45 | 14,61% | 0,14677 | 0,73968 |
| W60 | 14,93% | 0,14592 | 0,74315 |
| W90 | 15,34% | 0,14534 | 0,74321 |
| W120 | 15,60% | 0,14548 | 0,74144 |

Il tasso di perdita osservato sulle stesse righe è `19,53%`: tutte le versioni fisiche risultano sottocalibrate. Il baseline di mercato normalizzato `Pq0` ottiene Brier `0,13425` e AUC `0,77560`, quindi in questa preview la quota contiene più informazione del solo modello fisico.

Limitando il calcolo ai round con `final_gamma` presente, ma mantenendo il label dell'header, i Brier fisici sono `0,14648` per W60, `0,14592` per W90 e `0,14608` per W120: la graduatoria esplorativa resta invariata, ma questa non sostituisce la sanificazione dei label.

Il vantaggio apparente di W90 su W60 è molto piccolo. Con media uguale per round e bootstrap a cluster di round:

```text
Brier(W90) - Brier(W60)  = -0,00060
IC 95%                   = [-0,00166, +0,00039]

Brier(W120) - Brier(W60) = -0,00039
IC 95%                   = [-0,00194, +0,00107]
```

Entrambi gli intervalli includono zero. Inoltre il bootstrap fra round della stessa giornata non misura la variabilità fra giornate.

Per fascia temporale, il minimo Brier fisico tick-level della preview è:

| Secondi mancanti | Finestra migliore nella preview | Brier |
|---:|---:|---:|
| 121–180 | W60 | 0,15632 |
| 61–120 | W90 | 0,13781 |
| 31–60 | W120 | 0,12938 |
| 1–30 | W120 | 0,14866 |

Questa variazione suggerisce di testare un modello multi-scala o un'interazione tra W e tempo residuo, ma non giustifica una regola adattiva costruita su una sola giornata.

### Conclusione onesta su V60

- Non c'è evidenza sufficiente per dire che V60 sia il periodo ottimo.
- Non c'è neppure evidenza sufficiente per sostituirlo con V90 o V120.
- V10–V20 sono sensibilmente più rumorosi nella preview.
- W60 è una baseline ragionevole.
- W90–W120 meritano il confronto come stime lente.
- Una coppia fast/slow può descrivere meglio un'esplosione recente di volatilità rispetto a una sola finestra.

### Configurazione sperimentale consigliata

Per la lettura umana e il POC:

```json
"volatility_windows_sec": [30, 60, 120]
```

Interpretazione:

- `V30`: reattiva agli shock recenti;
- `V60`: baseline intermedia;
- `V120`: regime più stabile, interamente disponibile dall'inizio della zona operativa `sec <= 180` nei round completi.

Per lo script massivo conviene confrontare un insieme più ampio:

```text
rolling W: 15, 30, 45, 60, 90, 120
EWMA half-life: 15, 30, 60
```

W10 può restare come controllo negativo, non come candidato principale.

Il modello multi-scala non dovrebbe sommare direttamente `V30`, `V60` e `V120`. Feature utili sono:

```text
sigma_30
sigma_60
sigma_120
vol_acceleration = log(sigma_30 / sigma_120)
z_30, z_60, z_120
```

La scelta finale deve premiare la finestra o combinazione che migliora **out-of-sample il modello basato sulla quota**, non quella che ottiene il miglior risultato stand-alone su Rd.

### Migliorare la qualità della volatilità

La stima dovrebbe usare i timestamp Chainlink disponibili:

- controllare copertura temporale effettiva della finestra;
- invalidare o segnalare una finestra che contiene un gap stale rilevante, anche se il feed è tornato fresco sulla riga corrente;
- valutare il collasso dei campioni con lo stesso `chainlink_recv_ms`;
- confrontare la formula attuale con una realized variance per unità di tempo:

```text
variance_rate_W = somma((delta log-price)^2) / somma(delta_t)
sigma_remaining = sqrt(variance_rate_W × secondi_mancanti)
```

La versione a log-price è più naturale per confrontare settimane in cui BTC si trova a livelli di prezzo diversi. Va testata, non assunta superiore a priori.

`volatility_min_changes: 5` indica soltanto che il calcolo numerico è possibile: non rende cinque variazioni una vera stima V60 o V120. Infatti oggi V60 può comparire dopo pochi secondi dall'apertura. Per R serve una condizione più forte, per esempio copertura temporale pari ad almeno l'80–100% di W; altrimenti `Pz_W` deve restare non disponibile. Nella zona `sec <= 180` una W120 è nominalmente completa nei round da 300 tick, ma la copertura va comunque verificata in presenza di gap.

Il vecchio piano volatilità promette anche `VW=---` dopo almeno quattro BTC identici consecutivi, ma questa regola non è implementata. Non la introdurrei meccanicamente: valori ripetuti possono dipendere dalla cadenza del feed. È preferibile classificare la qualità tramite `chainlink_recv_ms`, durata reale dei gap e copertura della finestra.

## Revisione proposta delle tre varianti

### Rd — mantenere come baseline fisica

Mantenere `Rd`, ma:

- chiamare l'output continuo `Pz_W`;
- calcolarlo per più W nello script di valutazione;
- distinguere probabilità terminale e first-passage;
- calibrare empiricamente la trasformazione normale, perché salti e code pesanti rendono `Φ` troppo ottimista;
- valutare momentum separatamente invece di nasconderlo nella volatilità;
- usare `secs_to_expiry` float come orizzonte T, lasciando `sec` arrotondato alla sola visualizzazione;
- usare solo dati interni non arrotondati.

### Rq — farne il benchmark principale

Partire da `Pq0 = 1-q_normalizzata`. Aggiungere poi una feature alla volta:

1. slope/drawdown della probabilità dello stesso lato;
2. flip con isteresi e persistenza;
3. mismatch tra lato quota e segno del delta;
4. spread;
5. book imbalance e profondità, se si decide di usare anche i `.bin`.

Ogni aggiunta deve battere `Pq0` sul holdout. Se non lo fa, va rimossa.

### Rc — differire la scelta

Nella fase preview mostrare le componenti, ma non proclamare un vincitore. Nel test massivo confrontare:

- `Pq0`;
- `Pq` con correttori;
- `Pz_W`;
- `Pq + una sola feature fisica`;
- composita regolarizzata multi-scala;
- `max` soltanto come benchmark prudenziale.

La variante composita va adottata solo se migliora calibrazione e valore economico fuori campione.

## Mappatura R=1–9

I bucket proposti possono essere mantenuti come convenzione preliminare, ma va eliminata la frase «coerenti con le frequenze empiriche osservate». Con 263 outcome di una sola giornata non è possibile validare in modo credibile, per esempio, una fascia sotto l'1%.

Regola proposta:

```text
probabilità continua calibrata -> bucket R -> sola visualizzazione
```

Nel report di valutazione vanno conservati:

- probabilità continua;
- R;
- numerosità per bucket;
- intervallo di Wilson;
- eventuale fusione di bucket adiacenti troppo vuoti.

Se il risultato non è calibrato, va chiamato **score di rischio 1–9**, non probabilità di rischio.

## Piano di validazione corretto

### Preview attuale

Scopo: trovare bug, leakage, feature inutili e casi limite. Non scegliere soglie definitive.

Test minimi:

- modificare tutti i tick futuri rispetto a una riga e verificare che R su quella riga non cambi;
- confrontare calcolo batch e calcolo incrementale live;
- verificare ordine temporale, estremi delle finestre e copertura;
- testare tie, partial, stale, sigma nulla, mismatch e quote estreme;
- usare soltanto label Gamma ufficialmente chiusi e coerenti come analisi principale; provisional e mismatch in sensitivity analysis separate;
- verificare che il risultato non dipenda dai valori arrotondati del TXT.

`python -m src.verify` controlla il `.bin`, ma non valida la correttezza statistica di R. Servono test dedicati.

### Test massivo

Il campione indipendente è principalmente il **round**, non il tick. Migliaia di righe dello stesso round non devono produrre intervalli di confidenza artificialmente stretti.

Inoltre, i dati attuali sono già stati usati per osservare pattern, scegliere formule e proporre soglie: sono un insieme esplorativo/train, non un holdout. Il primo vero test confermativo deve usare giornate raccolte dopo il congelamento della specifica.

Con circa 288 round al giorno, 2.000–3.000 round corrispondono soltanto a circa 7–11 giorni, non a molte settimane. Sono sufficienti per una prima verifica, ma non per dichiarare stabile una fascia di rischio sotto l'1%. Per una scelta operativa più credibile punterei ad almeno 30 giornate distinte, mantenendo comunque un holdout cronologico; il numero di regimi e giorni conta più del numero grezzo di tick.

Protocollo raccomandato:

1. split cronologico per giornate, mai split casuale per tick;
2. tuning iniziale su giorni train;
3. calibrazione su giorni successivi separati;
4. holdout finale mai consultato durante la scelta;
5. walk-forward come conferma;
6. bootstrap a cluster prima per giorno e poi per round;
7. confronto paired tra modelli sugli stessi ingressi.

Metriche:

- calibrazione: Brier, log loss, reliability curve, calibration intercept/slope;
- discriminazione: AUC, ma solo come metrica secondaria;
- valore incrementale: differenza rispetto a `Pq0`;
- stabilità: giorno, fascia oraria, secondi mancanti, quota e regime di volatilità;
- copertura: percentuale di righe eleggibili;
- economia: P&L, drawdown, hit rate e numero di entrate.

Va valutata anche una policy realistica con **una sola decisione per round**: per esempio primo secondo eleggibile che soddisfa le soglie. Valutare ogni tick come una puntata indipendente sovrastima gravemente l'evidenza.

## Collegare R al vero obiettivo economico

R misura il rischio, ma non decide da solo se la puntata conviene. Se `g` è `majority_gain` come ROI in caso di vincita e `p` è la probabilità calibrata di perdita:

```text
EV = (1-p) × g - p
break-even: p < g / (1+g)
```

Questo confronto è più utile di una regola rigida come «entra solo con R <= 3». Due puntate con lo stesso rischio possono avere convenienza opposta se quota, fee, spread e profondità sono diverse.

Raccomandazione:

- tenere R come misura di rischio;
- tenere `gain%` come misura del payoff;
- aggiungere in analisi un `EV_est`;
- definire la strategia su `EV_est`, liquidità e limite di rischio;
- includere fee e slippage del market buy da $100 già disponibili nel progetto.

## Sequenza di lavoro sostitutiva

1. **Riallineare il piano allo stato corrente**
   - fix V già completato;
   - 263 round correnti;
   - correggere il vecchio piano volatilità.
2. **Congelare le definizioni**
   - target primario `Y_loss`;
   - target secondario `Y_flip`;
   - regole per tie, partial, stale e copertura.
3. **Costruire baseline continue**
   - `Pq0`;
   - `Pz_W` per W candidati;
   - nessun bucket o correttore additivo in questa fase.
4. **Aggiungere test anti-look-ahead e casi limite**.
5. **Eseguire la preview con ablation**
   - quota sola;
   - fisica sola per ogni W;
   - quota più una feature alla volta;
   - output per fascia temporale ed equal-weight per round.
6. **Mostrare R sperimentali**
   - R derivato dalle probabilità continue;
   - tutte le componenti nel report;
   - nel TXT soltanto le colonne davvero utili alla lettura.
7. **Raccogliere più giornate senza ritoccare continuamente le soglie**.
8. **Eseguire test cronologico massivo e calibrazione**.
9. **Selezionare una sola versione operativa e versionarla**.
10. **Backtestare una policy di ingresso realistica e poi fare paper trading live**.

### Contratto del modulo da correggere

La firma proposta `compute_risk_indices(ticks, vols)` non contiene il PTB necessario a Rd e non lascia spazio alle feature del book. Un contratto più esplicito dovrebbe ricevere almeno `ptb_used`, tick e volatilità; i book possono restare opzionali finché non entrano in Rq.

Il calcolo live non deve ricevere `outcome`, `final_price` o `final_gamma`: questi campi appartengono soltanto allo script di valutazione. Questa separazione strutturale riduce il rischio di leakage accidentale.

## Aggiunte utili al progetto

### Versionamento e riproducibilità

Ogni TXT/report dovrebbe indicare:

- `risk_model_version`;
- finestre e parametri;
- target;
- sorgente PTB usata;
- versione/commit del codice nel report massivo.

Lo stesso `.bin` può essere riconvertito in futuro con formule diverse: senza versione, due R con lo stesso nome non sarebbero confrontabili.

### Indicatore di qualità separato

Un R basso non è affidabile se il dato sottostante è scadente. Aggiungere un flag di qualità/eligibilità evita di confondere «rischio basso» con «modello senza informazioni».

### Informazione dal book

Il `.bin` contiene snapshot completi. Dopo la baseline TXT, meritano un test:

- spread;
- depth imbalance;
- profondità necessaria per $100;
- variazione della liquidità;
- differenza fra mid e prezzo eseguibile.

Queste feature possono spiegare quando la quota è affidabile oppure fragile.

### Mercati 15m e 1h

L'allineamento con mercati 15m/1h può essere utile come contesto, ma va trattato come esperimento successivo:

- registrare le quote simultaneamente;
- usare soltanto informazioni disponibili nello stesso istante;
- misurare il valore incrementale rispetto al mercato 5m;
- non assumere che una posizione più lunga compensi automaticamente la perdita del 5m;
- includere costi, correlazione e payoff congiunto prima di chiamarla copertura.

### Criterio finale di successo

Il successo non è avere un R monotono sui dati usati per costruirlo. È ottenere, su giornate future:

1. probabilità ben calibrate;
2. miglioramento misurabile rispetto alla sola quota;
3. entrate realmente eseguibili;
4. EV e P&L positivi dopo fee e slippage;
5. stabilità fra regimi e giorni.

## Verdetto finale

Terrei l'architettura generale e le due sorgenti informative, ma cambierei la priorità:

1. `Pq0/Rq` come benchmark da battere;
2. `Rd` come diagnostica fisica multi-finestra;
3. `Rc` come esperimento da costruire e validare, non come vincitore già scelto.

Per la volatilità manterrei V60, affiancandole V30 e V120 nel POC. I dati attuali non dimostrano un periodo migliore; mostrano invece che le finestre lunghe sono leggermente più stabili e che la possibile informazione utile è soprattutto nel confronto fast/slow. La decisione finale sul periodo deve attendere dati multi-giornata e deve basarsi sul miglioramento incrementale oltre la quota di mercato.
