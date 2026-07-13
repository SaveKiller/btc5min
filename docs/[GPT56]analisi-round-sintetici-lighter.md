# Analisi dei round sintetici BTC 5m ricostruiti dai tick Lighter

**Data:** 10 luglio 2026  
**Autore:** GPT-5.6  
**Esito:** idea valida e utile, ma come dataset ausiliario; la soluzione migliore è un dataset ibrido con percorso Lighter e label ufficiali Chainlink/Polymarket.

---

## 1. Conclusione

Conviene costruire i round storici dai tick Lighter.

Non conviene però considerarli copie dei round Polymarket né usarli per simulare direttamente il profitto di una strategia. Mancano infatti quote UP/DOWN, spread e profondità del CLOB Polymarket, fee effettive, slippage e possibilità reale di esecuzione.

Il dataset è invece molto adatto a studiare:

- dinamica del delta durante i 300 secondi;
- volatilità trailing `V30/V60/V90/V120`;
- probabilità fisica dell'outcome in funzione di tempo residuo, delta e volatilità;
- momentum, mean reversion e cambi di segno;
- differenze per ora UTC, giorno della settimana e fascia H;
- stabilità delle regole su decine di migliaia di finestre.

La preoccupazione sulle due fonti di prezzo è corretta, ma oggi è possibile misurarla invece di stimarla: Gamma conserva `priceToBeat`, `finalPrice` e outcome ufficiale dei mercati Polymarket appartenenti allo stesso periodo dei tick Lighter.

Il confronto storico diretto mostra:

- **21.890 round accoppiati** Lighter–Polymarket;
- **95,788%** di outcome Lighter uguali all'outcome ufficiale;
- correlazione tra movimento BTC a 5 minuti Lighter e Chainlink: **0,99544**;
- errore medio del movimento: **+$0,004**, quindi nessun bias direzionale aggregato rilevabile;
- errore assoluto mediano: **$4,63**;
- errore assoluto al 95° percentile: **$15,49**;
- 922 outcome discordanti, quasi simmetrici: 473 falsi DOWN e 449 falsi UP.

Quindi Lighter è un proxy molto buono della **direzione fisica del BTC**, ma non è affidabile per assegnare autonomamente l'outcome quando il movimento finale è piccolo.

La raccomandazione più importante è questa:

> usare il percorso secondo per secondo di Lighter come insieme di feature, ma usare l'outcome storico ufficiale Gamma/Chainlink come label ogni volta che è disponibile.

In questo modo non serve inventare l'outcome: il percorso resta proxy, ma il target statistico è autentico.

---

## 2. Dati effettivamente disponibili

In `H:\ticks\lighter-fullrawticks\btc` sono presenti:

- 77 file giornalieri;
- periodo dal 6 aprile al 21 giugno 2026;
- colonne `timestamp`, `ask`, `bid`, `nonce`;
- tick ordinati con timestamp Unix in millisecondi;
- copertura teorica di `77 × 288 = 22.176` finestre da 5 minuti.

Lo studio H già eseguito nel progetto ha trovato:

- 22.176 finestre teoriche;
- 21.819 finestre con griglia completa a 1 Hz;
- 357 finestre scartate per secondi mancanti.

Il dataset finale dei round sintetici non deve quindi essere dichiarato automaticamente di 22.176 round. Deve essere l'intersezione fra:

1. percorso Lighter con qualità sufficiente;
2. PTB e finale Lighter campionati correttamente;
3. metadati ufficiali Gamma disponibili;
4. eventuali ulteriori filtri su gap, spread o staleness.

---

## 3. La differenza di livello fra i prezzi non è il vero problema

Indichiamo con:

- `C(t)` il prezzo ufficiale Chainlink;
- `L(t)` il mid top-of-book Lighter;
- `b(t)` la differenza di livello fra le due fonti;
- `e(t)` il rumore microstrutturale del book Lighter.

Possiamo scrivere:

```text
L(t) = C(t) + b(t) + e(t)
```

Il movimento sui cinque minuti è:

```text
ΔL = ΔC + [b(T+300) - b(T)] + [e(T+300) - e(T)]
```

Una differenza costante di $20, $40 o $60 fra i due prezzi **si annulla** nel delta. Ciò che può cambiare l'outcome è la variazione della differenza fra le fonti durante i cinque minuti, insieme al rumore del top-of-book e alla diversa temporizzazione dei feed.

Il confronto empirico conferma questo punto:

- basis di livello `Lighter − Chainlink`, mediana: **−$14,99**;
- intervallo 5°–95° percentile del basis: **−$66,87 / +$66,59**;
- errore medio del movimento a cinque minuti: **+$0,004**;
- deviazione standard dell'errore del movimento: **$8,38**.

Il basis assoluto può quindi essere ampio, ma la sua variazione sui cinque minuti è molto più piccola e non mostra un bias direzionale aggregato.

---

## 4. Validazione storica diretta contro Polymarket

### 4.1 Metodo

Per ogni confine temporale `B` multiplo di 300 secondi è stato selezionato il record Lighter:

```text
argmax tick.timestamp tale che tick.timestamp <= B
```

Il prezzo Lighter usato al confine è:

```text
lighter_mid = (ask + bid) / 2
```

Per ciascun round `[T, T+300]`:

```text
delta_lighter = lighter_mid(T+300) - lighter_mid(T)
delta_chainlink = Gamma.finalPrice - Gamma.priceToBeat
```

L'outcome sintetico è stato poi confrontato con l'outcome settled del mercato Polymarket. Nei 21.890 round accoppiati non è emerso alcun caso in cui il segno di `finalPrice - priceToBeat` fosse incoerente con l'outcome ufficiale.

### 4.2 Risultati complessivi

- Round Gamma con PTB e finale utilizzabili: **21.891**.
- Round accoppiati con entrambi i confini Lighter: **21.890**.
- Outcome concordi: **20.968**.
- Outcome discordanti: **922**.
- Accuratezza del proxy Lighter: **95,788%**.
- Outcome ufficiali UP: **50,142%**.
- Outcome Lighter UP: **50,032%**.
- Correlazione dei delta: **0,99544**.

Il primo round dell'archivio non è stato accoppiato perché il PTB causale richiede l'ultimo tick precedente al confine iniziale, che si trova nel giorno non disponibile.

Matrice degli errori:

- ufficiale UP, Lighter UP: 10.503;
- ufficiale UP, Lighter DOWN: 473;
- ufficiale DOWN, Lighter UP: 449;
- ufficiale DOWN, Lighter DOWN: 10.465.

La quasi perfetta simmetria dei due tipi di errore è importante: Lighter non sembra introdurre un falso vantaggio sistematico verso UP o DOWN sull'intero periodo.

### 4.3 Errore sul movimento a cinque minuti

Definendo:

```text
move_error = delta_lighter - delta_chainlink
```

si ottiene:

- media: **+$0,004**;
- mediana: **−$0,016**;
- MAE: **$5,92**;
- errore assoluto mediano: **$4,63**;
- errore assoluto p90: **$12,28**;
- errore assoluto p95: **$15,49**;
- errore assoluto p99: **$23,42**.

Il massimo errore osservato è molto più alto, **$199,16**. È compatibile con un caso anomalo o un gap del feed, ma andrebbe ispezionato singolarmente prima di attribuirgli una causa. Per questo ogni round deve conservare metriche di qualità e non soltanto il prezzo ricampionato.

### 4.4 Outcome in funzione del movimento ufficiale

Accordo fra outcome Lighter e outcome ufficiale:

- `|delta Chainlink| < $1`: **50,9%**;
- `$1 ≤ |delta| < $2`: **64,0%**;
- `$2 ≤ |delta| < $5`: **71,9%**;
- `$5 ≤ |delta| < $10`: **88,1%**;
- `$10 ≤ |delta| < $20`: **97,6%**;
- `$20 ≤ |delta| < $50`: **99,87%**;
- `$50 ≤ |delta| < $100`: **99,96%**;
- `|delta| ≥ $100`: **99,97%**.

Questo risultato identifica chiaramente il dominio del problema: la discordanza non è distribuita uniformemente; è quasi tutta concentrata nei round che terminano vicino al PTB.

### 4.5 Affidabilità deducibile dal solo delta Lighter

Se non fosse disponibile l'outcome ufficiale, una soglia sul delta finale Lighter produrrebbe:

- `|delta Lighter| ≥ $5`: accordo **98,36%**, copertura **92,05%**;
- `|delta Lighter| ≥ $7,5`: accordo **99,11%**, copertura **88,21%**;
- `|delta Lighter| ≥ $10`: accordo **99,50%**, copertura **84,39%**;
- `|delta Lighter| ≥ $15`: accordo **99,80%**, copertura **77,04%**;
- `|delta Lighter| ≥ $20`: accordo **99,92%**, copertura **70,20%**.

Queste soglie sono molto più fondate di classi arbitrarie `low/medium/high`, ma restano risultati in-sample del periodo aprile–giugno. Devono essere rivalidate su settimane future.

Quando Gamma fornisce l'outcome ufficiale, la soglia non va usata per sostituire la label: è preferibile conservare anche i casi difficili, perché sono proprio quelli più rilevanti vicino al settlement.

### 4.6 Qualità temporale e spread Lighter

Ai confini dei round:

- età mediana dell'ultimo tick Lighter: **9 ms**;
- p95: **139 ms**;
- p99: **296 ms**;
- 21.870 round su 21.890 hanno entrambi i confini con età massima non superiore a 1 secondo.

Limitando il confronto a questi 21.870 round:

- accordo outcome: **95,798%**;
- MAE del movimento: **$5,88**;
- errore assoluto p95: **$15,40**.

Gli errori fra le fonti non sono quindi spiegati principalmente dai pochi gap estremi.

Spread Lighter osservato ai confini:

- mediana: **$0,70**;
- p95: **$6,50**;
- p99: **$7,90**.

Il midpoint riduce il rumore bid/ask, ma nei momenti di spread ampio rimane una componente d'incertezza di alcuni dollari.

### 4.7 Stabilità giornaliera

L'accordo giornaliero non è costante:

- mediana fra i giorni: **96,47%**;
- 5° percentile: **91,99%**;
- 95° percentile: **98,33%**;
- giorno peggiore: **90,28%**;
- giorno migliore: **99,31%**.

Questo impedisce di trattare il 95,788% come una costante universale. L'errore dipende dal regime di mercato e va valutato con split temporali a blocchi.

---

## 5. Un'opportunità migliore dei round puramente sintetici

Per lo stesso periodo sono disponibili i dati ufficiali storici dei mercati:

- `Gamma.eventMetadata.priceToBeat`;
- `Gamma.eventMetadata.finalPrice`;
- outcome settled UP/DOWN.

Il dataset consigliato è quindi ibrido:

```text
percorso intraround: Lighter top-of-book mid
PTB proxy:          Lighter al confine T
delta intraround:   Lighter(t) - Lighter(T)
volatilità:         Lighter, calcolata solo sul passato
label:              outcome ufficiale Polymarket/Gamma
PTB/finale audit:   valori ufficiali Chainlink da Gamma
```

Questo assetto offre due vantaggi:

1. mantiene circa ventimila percorsi completi secondo per secondo;
2. elimina quasi completamente il rischio di addestrare il modello su outcome falsi.

Non si deve correggere linearmente il percorso Lighter affinché termini sul `finalPrice` ufficiale. Una correzione del tipo:

```text
correzione(t) = t / 300 × errore_finale
```

userebbe il futuro per modificare i tick precedenti e introdurrebbe leakage. I valori ufficiali finali devono essere label e audit, non input disponibile durante il round.

---

## 6. Cosa è trasferibile e cosa non lo è

### 6.1 Utilizzo raccomandato

I round Lighter possono essere usati per stimare:

```text
P(outcome ufficiale UP | sec, delta_lighter, V30, V60, V120, H, calendario)
```

e per studiare:

- probabilità di attraversare nuovamente il PTB;
- probabilità di mantenere il segno fino al settlement;
- rischio condizionato a `delta / V`;
- dipendenza dal tempo residuo;
- sequenze di accelerazione, inversione e compressione della volatilità;
- differenze fra regimi H e sessioni UTC.

Sono particolarmente adatte feature normalizzate:

- delta in basis point;
- `delta / VW`;
- z-score rispetto alla volatilità trailing;
- variazioni per secondo normalizzate per prezzo;
- distanza dal PTB in unità di sigma attesa fino alla scadenza.

Queste feature trasferiscono meglio fra periodi con livelli BTC diversi e fra Lighter e Chainlink.

### 6.2 Utilizzo con cautela

La volatilità per-secondo Lighter non è stata validata direttamente contro la volatilità Chainlink sullo stesso periodo, perché Gamma espone i prezzi ufficiali ai confini ma non l'intero percorso a 1 Hz.

La correlazione dei delta finali è molto alta, ma non dimostra automaticamente che:

- `V30` Lighter sia numericamente uguale a `V30` Chainlink;
- gli spike arrivino nello stesso secondo;
- il ritardo relativo dei feed sia costante;
- le probabilità calcolate nei secondi finali siano perfettamente trasferibili.

I round Lighter possono quindi fornire una forte prior per la componente statistica di `Rs`, ma non possono riprodurre direttamente l'attuale `Rs`: manca infatti il lato maggioritario scelto dalle quote Polymarket. Si può stimare `P(UP)` e trasformarla nel rischio del lato selezionato soltanto quando, nel round reale, quel lato è noto. La calibrazione finale deve comunque avvenire sui round Chainlink reali.

### 6.3 Utilizzo non valido

Da Lighter non si possono ricostruire:

- quote UP/DOWN Polymarket;
- lato maggioritario del mercato;
- `Rq`;
- spread e profondità CLOB Polymarket;
- `majority_gain`;
- fill di un market buy da $100;
- fee e slippage effettivi;
- reazione delle quote al delta Chainlink;
- profitto netto di una strategia.

Di conseguenza, i round sintetici non possono dimostrare da soli l'esistenza di un edge economico. Possono stimare una probabilità fisica; il profitto nasce soltanto dal confronto fra quella probabilità, la quota acquistabile e i costi di esecuzione osservati nei round reali.

---

## 7. Semantica temporale corretta

Questo è il principale rischio implementativo.

La funzione attuale `load_day_mid_by_sec()` conserva l'ultimo mid presente in ciascun secondo. Per il secondo `T`, quel valore è normalmente successivo al confine `T` e vicino a `T+1`.

Non bisogna quindi calcolare l'outcome come:

```text
mids[T+299] - mids[T]
```

perché:

- il primo valore è successivo al PTB ufficiale;
- l'ultimo valore precede il vero confine finale `T+300`;
- si introduce uno spostamento temporale fino a circa un secondo su entrambi i lati.

La ricostruzione corretta deve usare 301 confini:

```text
k = 0 ... 300
sample(k) = ultimo mid Lighter con timestamp <= T+k secondi
sec_to_expiry = 300-k
```

Quindi:

```text
ptb_lighter   = sample(0)
final_lighter = sample(300)
outcome       = final_lighter >= ptb_lighter
```

Regole necessarie:

- nessun nearest-neighbor che possa prendere un tick futuro;
- nessuna interpolazione usando il punto successivo;
- conservare `sample_age_ms` per ogni secondo;
- segnalare gap e secondi mancanti;
- unire correttamente due file giornalieri nei round a cavallo della mezzanotte;
- condividere lo stesso campione di confine fra finale del round precedente e PTB del successivo.

Per imitare visivamente i file reali si possono mostrare i tick `sec=300...1` e tenere `final_lighter` nell'header. Nel formato analitico è però più chiaro conservare esplicitamente tutti i punti `0...300`.

---

## 8. Formato dati raccomandato

I dati sintetici non devono essere scritti come `.bin` v6 canonici. Quel formato implica quote, book e semantica Polymarket; riempirlo di `NaN` renderebbe facile mescolare accidentalmente dati reali e proxy.

È preferibile un archivio separato, per esempio:

```text
data_synthetic/lighter/
    rounds.parquet
    ticks.parquet
    gamma_events_raw.jsonl
    build_metadata.json
```

Oppure un singolo database DuckDB, se si preferisce interrogare direttamente milioni di righe.

### 8.1 Campi per round

Campi minimi consigliati:

```text
start_ts
end_ts
source_path = lighter_topbook_mid
label_source = gamma_chainlink_official
ptb_lighter
final_lighter
delta_lighter
outcome_lighter
ptb_chainlink_gamma
final_chainlink_gamma
delta_chainlink_gamma
outcome_official
outcome_agreement
move_error
coverage_1hz
max_sample_age_ms
max_gap_ms
spread_median
spread_p95
hour_utc
dow_utc
hour_band
quality_status
```

Se Gamma non contiene i metadati:

```text
label_source = lighter_proxy
outcome_official = null
```

Questi round non devono essere uniti silenziosamente ai round con label ufficiale.

### 8.2 Campi per tick

```text
start_ts
elapsed_sec
sec_to_expiry
sample_ts_ms
sample_age_ms
lighter_bid
lighter_ask
lighter_mid
delta_lighter
V30
V60
V90
V120
vol_coverage
stale
```

Le volatilità devono restare live-safe: al tick `k` possono usare soltanto campioni con timestamp non successivo a `T+k`.

---

## 9. Metodo statistico

Ventimila round consecutivi non equivalgono a ventimila osservazioni indipendenti. Volatilità, trend e liquidità sono autocorrelati; inoltre 300 secondi consecutivi dello stesso round non sono 300 esempi indipendenti.

Servono quindi:

1. **split cronologico per settimane**, mai split casuale per tick;
2. **block bootstrap per giorno o settimana** per gli intervalli d'incertezza;
3. un holdout temporale mai usato nella scelta di soglie o feature;
4. risultati separati per fascia H, feriale/weekend e regime di volatilità;
5. controllo del multiple testing quando si provano molte regole;
6. confronto con baseline semplici, non soltanto con accuracy complessiva.

Baseline minime:

- sempre UP / sempre DOWN;
- segno del delta corrente;
- modello normale già implicito in `Rs`;
- probabilità per bucket di `sec`, `delta/V60` e H;
- modello addestrato su Lighter e valutato su veri round Chainlink.

Metriche utili:

- Brier score;
- log loss;
- reliability/calibration curve;
- AUC solo come diagnostica;
- accuracy per bucket di probabilità;
- stabilità per settimana;
- differenza rispetto alla quota Polymarket, valutata esclusivamente sui round reali.

---

## 10. Piano di utilizzo consigliato

### Fase A — Costruzione storica

- Ricostruire la griglia causale a 301 punti.
- Calcolare delta e volatilità trailing.
- Scaricare e archiviare i metadati Gamma per gli stessi slug.
- Produrre label ufficiali e campi di audit.
- Scartare o separare round con gap eccessivi.

### Fase B — Studio fisico

- Stimare `P(UP)` e `P(perdita del lato scelto)` da delta, tempo, volatilità e H.
- Usare split temporali e calibrazione out-of-sample.
- Identificare poche regole robuste, evitando migliaia di combinazioni opportunistiche.

### Fase C — Transfer su Chainlink

- Applicare senza riaddestramento iniziale le regole ai round reali accumulati.
- Misurare lo shift di distribuzione fra feature Lighter e Chainlink.
- Ricalibrare probabilità e soglie, senza cambiare retroattivamente il holdout.

### Fase D — Verifica economica

- Collegare la probabilità fisica alle quote e al book Polymarket reali.
- Simulare fill, fee, slippage e disponibilità della quota.
- Valutare PnL soltanto sui round reali.

---

## 11. Miglioramento da iniziare subito

Conviene registrare contemporaneamente, per i nuovi round:

- percorso Chainlink già raccolto dal progetto;
- mid Lighter sullo stesso asse temporale;
- timestamp di ricezione e timestamp fonte;
- spread Lighter.

L'overlap live permetterà di misurare direttamente:

- errore di `delta(t)` a ogni secondo residuo;
- differenza fra `V30/V60/V120` Lighter e Chainlink;
- lead/lag fra i due feed;
- comportamento specifico negli ultimi 10–20 secondi;
- stabilità della mappa di trasferimento nel tempo.

Gamma consente già di validare i confini storici; l'overlap live completerà la validazione del percorso intraround.

---

## 12. Decisione finale

**GO** alla costruzione dei round Lighter, con queste condizioni:

- dataset e naming separati dai round reali;
- campionamento causale sui confini esatti;
- percorso Lighter, label ufficiale Gamma quando disponibile;
- qualità e provenienza esplicite in ogni round;
- uso per probabilità fisica e generazione di ipotesi;
- validazione finale e PnL soltanto su Polymarket/Chainlink reali.

**NO-GO** a:

- trattare i round Lighter come round Polymarket autentici;
- fondere i due dataset senza campo fonte;
- dichiarare affidabile la volatilità Chainlink solo perché quella Lighter è simile;
- calcolare un backtest economico senza quote e book Polymarket;
- forzare il percorso Lighter a coincidere con il finale ufficiale usando informazione futura.

Il valore dell'idea è alto: permette di iniziare subito lo studio della dinamica BTC a cinque minuti su circa ventimila esempi. Il risultato non sostituisce i round reali, ma può ridurre molto lo spazio delle ipotesi e far sì che i dati Polymarket futuri vengano usati per validare poche strategie plausibili invece che per cercarle da zero.

