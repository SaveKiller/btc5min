# Risposta Turno 01 — `entry-indicators`

> Fonte fatti: `context/baseline.md` (Fase 0, generato 2026-07-08T12:48:00Z), `context/00-manifest.md`, `meeting.md`.
> Tutti i valori, definizioni operative e dipendenze dati citati nel seguito sono ancorati a quanto verificato in baseline.md (7 file `.txt` da 300 righe, `fee_rate=0.07`, `gain%` 0.0–89.6%, 5 Up / 2 Down, `delta=round(chainlink_btc - ptb_chainlink)`, `quote` = majority side da mid LOB, scala 98 file in `data/txt/` e target 288/giorno).

---

## Punto 01

**Quesito (meeting.md, Punto 01).** Produrre un catalogo strutturato di indici/indicatori — calcolabili a posteriori su ogni riga (1 Hz) e poi integrabili nel feed tick-by-tick — che consentano di scegliere **quando** entrare in una scommessa Polymarket "BTC Up or Down 5m", standardizzando i concetti di trade-off rischio/rendimento/tempo. Per ogni indice: (1) tecnica o framework teorico di riferimento, (2) indici/indicatori con formula o definizione operativa, (3) variazione riga per riga e metodi di aggregazione su molti round. Esplorare tecniche da scommesse, statistica/matematica, trading di opzioni. Produrre ipotesi di soglie/zone temporali e raccomandazioni su quali validare per prime.

### A. Framework teorici di riferimento

Tre famiglie, applicate al mercato in esame:

1. **Trading di opzioni binarie / digitali.** Un contratto Up/Down con scadenza fissa a 5 minuti è una *binary option* at-the-money al PTB. Sono quindi importabili i concetti di *moneyness*, *time decay* (theta), *probability of profit*, *expected value* e *Greeks* (delta, gamma, vega) calcolati su un modello di prezzo sottostante (es. GBM risk-neutral su BTC chainlink).
2. **Teoria delle scommesse.** Quote in centesimi = probabilità implicita dal book. Edge = differenza tra probabilità del modello e probabilità implicita; *value bet* = edge>0. Criterio di dimensionamento: *Kelly fraction* (e frazioni conservative, es. ¼ Kelly).
3. **Statistica dei prezzi e microstruttura.** Volatilità realizzata (rolling, multiscala), drift normalizzato per tempo residuo, mean-reversion vs momentum, martingala vs trend, e — solo con i `.bin` — spread bid-ask, profondità LOB, imbalance.

### B. Catalogo indici candidati

Ogni indice produce una **serie di 300 valori per round** (una per ogni `sec ∈ {300,…,1}`) e, su *N* round, una **matrice N×300** su cui si calcolano statistiche, distribuzioni, correlazioni con `outcome` e curve di selezione.

#### B1. Distanza normalizzata dal PTB (moneyness proxy)

- **Tecnica/framework.** Modello GBM risk-neutral: il sottostante `btc(sec)` a `T−sec` secondi dalla scadenza è distribuito come N(ptb, σ²·(sec/300)). Si misura di quanti "deviazioni standard" il prezzo corrente è spostato dal PTB.
- **Definizione operativa.**
  - `σ̂` = stima di volatilità (es. std dei rendimenti log di `btc` su finestra mobile di 30 s o 60 s; vedi B6).
  - `m(t) = btc(t) − ptb_price` (in $).
  - **Indice moneyness**: `Z_ptb(sec) = m(sec) / (ptb_price · σ̂ · √(sec/300))`.
- **Variazione riga per riga.** A `sec` grande (round iniziato da poco) la `√(sec/300)` è ≈1 e `Z_ptb` è dominato dalla distanza corrente in unità di vol. Avvicinandosi a `sec=1`, lo stesso `$` di spostamento conta molto di più (denominatore collassa a `ptb·σ̂·√(1/300)` ≈ `ptb·σ̂·0.058`).
- **Aggregazione.** Per ogni `sec` fisso: istogramma di `Z_ptb | outcome=Up` e `Z_ptb | outcome=Down`. Stima di `p_model(Up | Z_ptb, sec)` via regressione logistica o isotonica → usata in B3.
- **Dipendenze dati.** Solo `.txt` (campi `btc`, `ptb_price`, `sec`).

#### B2. Probabilità implicita dalla quota di mercato

- **Tecnica/framework.** Conversione *quote → probabilità implicita* del bookmaker, con aggiustamento per *overround* (vig) e fee Polymarket.
- **Definizione operativa.** Sia `q(sec) ∈ [1, 99]` il prezzo in centesimi del lato majority a quel secondo (colonna `quote`).
  - `p_impl(sec) = q(sec) / 100` (probabilità implicita "grezza" lato majority).
  - `p_impl_net(sec) = p_impl(sec) · (1 − fee_rate) + 0.5 · fee_rate` (correzione lineare per fee simmetrica; `fee_rate=0.07` da baseline).
  - Riga con `quote = ----`: `p_impl = NaN`; trattata come *missing* e *imputata* (B7) oppure esclusa dall'aggregazione.
- **Variazione riga per riga.** A parità di BTC, `q` oscilla per microstruttura; a `sec` grandi ci si attende `q ≈ 50` con alta varianza, a `sec` piccoli `q` converge verso 100 (o 0) all'avvicinarsi della certezza dell'esito.
- **Aggregazione.** Distribuzione di `p_impl_net(sec)` stratificata per `outcome`. Curva empirica `Pr(outcome=Up | p_impl_net > x, sec)` per validare la calibrazione del book.
- **Dipendenze dati.** Solo `.txt`.

#### B3. Edge e indice di value-bet atteso per secondo

- **Tecnica/framework.** *Value betting* applicato a opzione binaria: l'edge è la differenza tra la probabilità "vera" stimata da un modello e quella implicita dal book, moltiplicata per il payoff netto.
- **Definizione operativa.** Per il lato majority `side ∈ {Up, Down}`:
  - `p_side(sec) = modello calibrato di P(outcome=side | btc(sec), sec)` (input B1 + storia round; in prima istanza: regressione logistica su `Z_ptb` e `sec`).
  - `payoff_net(sec) = (100 − q(sec)) / q(sec) · (1 − fee_rate)` se vinci, `−1` se perdi.
  - **EV per $1 puntato**: `EV(sec) = p_side · payoff_net − (1 − p_side) · 1`.
  - **Edge normalizzato per unità di tempo residuo**: `EdgeT(sec) = EV(sec) / √(sec/300)`. Più alto = miglior rapporto rischio/rendimento *per secondo speso ad aspettare*.
  - **Indice guida (rischio/rendimento per-secondo)**: `R(t) = EV(sec) / std(payoff)` con `std(payoff) = √(p·(1−p)) · (100/q − 1 + 1)` (deviazione del payoff binario). `R > 0` ⟹ value-bet; `R > k` (es. `k=0.5`) ⟹ soglia operativa.
- **Variazione riga per riga.** `EdgeT` è alto quando `p_side` è molto disallineata da `q` e/o `sec` è piccolo (segnale "tardivo ma pulito"). È penalizzato dalla `√(sec)` per non sovrastimare entrate precoci rumorose.
- **Aggregazione.** Per ogni `sec`: media e quantili di `R` su round con `outcome=Up` vs `Down`. Curva ROC al variare della soglia `R>k` per predire `outcome` e scegliere *k* ottimale.
- **Dipendenze dati.** Solo `.txt`; per la calibrazione di `p_side` servono i 98 (e poi migliaia di) file storici.

#### B4. Theta-proxy: decadimento del rendimento potenziale

- **Tecnica/framework.** Il `gain%` già presente nei `.txt` (definito in baseline come *ROI netto fee su puntata simbolica $100 sul lato majority*) è analogo al *time value* di un'opzione: parte alto se la direzione è già segnata, decade verso il P&L a scadenza. Misurarne la derivata rispetto a `sec` identifica la "corsa" del tempo.
- **Definizione operativa.**
  - `g(sec) = gain%` (colonna del `.txt`).
  - **Theta proxy**: `Θ(sec) = −(g(sec) − g(sec+1))` (variazione di `gain%` perdendo 1 secondo).
  - **Theta medio su finestra `w`**: `Θ_w(sec) = −(g(sec) − g(sec+w)) / w`.
  - **Indice di "convenienza temporale"**: `CT(sec) = Θ_w(sec) / |R(sec)|` (decadimento per unità di edge). Alto = stai perdendo valore velocemente rispetto al segnale.
- **Variazione riga per riga.** `Θ` è prossimo a 0 in zone di equilibrio (prezzo stabile, quote stabili) e mostra picchi in corrispondenza di spike di `btc` o di switch di `quote` (Up→---- o ----→Down). Nelle righe `----` (fino a 26 in un file, 2 in un altro — vedi baseline) `g` non è calcolabile: si gestisce con *forward-fill* breve (≤3 s) o esclusione.
- **Aggregazione.** Distribuzione di `Θ` per `sec` e per `outcome`. Identificazione di *bande di sec* in cui `Θ` ha varianza minima (zone "tranquille" dove il decadimento è prevedibile).
- **Dipendenze dati.** Solo `.txt`.

#### B5. Drift normalizzato e momento di "rottura"

- **Tecnica/framework.** In GBM, il drift atteso è nullo sotto misura risk-neutral; sotto misura *fisica* (reale) il segno e l'intensità del drift sui secondi residui sono informativi sulla *direzione probabile*.
- **Definizione operativa.**
  - **Drift cumulato normalizzato**: `D(sec) = (btc(sec) − ptb_price) / sec` (in $/s).
  - **Drift istantaneo**: `d(sec) = (btc(sec) − btc(sec+5)) / 5` (variazione su 5 s).
  - **Indice di rottura (breakout)**: `B(sec) = sign(D(sec)) · |D(sec)| / σ̂_local(sec)`. `|B|>2` ⟹ movimento anomalo rispetto al rumore locale.
  - **Momentum persistente**: `M(sec) = media_mobile(d, 20s) / σ̂_local`.
- **Variazione riga per riga.** `D` e `d` cambiano segno e magnitudine ad ogni tick; `B` e `M` sono versioni *filtrate* adatte a decisione.
- **Aggregazione.** Per ogni `sec`: tasso di `outcome=Up` condizionato a `B>k`. Stima di una soglia `k*` che separa Up da Down con miglior rapporto veri positivi / falsi positivi.
- **Dipendenze dati.** Solo `.txt`.

#### B6. Volatilità realizzata multiscala

- **Tecnica/framework.** Stima rolling della varianza dei ritorni log di BTC; è l'input σ̂ usato in B1, B5 e B9 e corrisponde alla *vega* implicita di un'opzione binaria breve.
- **Definizione operativa.**
  - `r(sec) = ln(btc(sec)/btc(sec+1))`.
  - `σ²_w(sec) = (1/(w−1)) · Σ (r(sec+i) − r̄)²` su finestra `w ∈ {10, 30, 60, 120}`.
  - **σ̂(sec)** = `√(σ²_30(sec))` (default).
  - **Indice di regime**: `Reg(sec) = σ²_10(sec) / σ²_60(sec)`. `Reg>1` ⟹ regime in espansione (più rischio *e* più informazione), `Reg<1` ⟹ regime in contrazione.
- **Variazione riga per riga.** `σ̂` cambia lentamente nei primi secondi (campione piccolo), poi si stabilizza. `Reg` è più reattivo.
- **Aggregazione.** Distribuzione di `σ̂(sec)` per `outcome` e per `sec`. Calibrazione di σ̂ come predittore di `|delta_final|` (validazione ex-post).
- **Dipendenze dati.** Solo `.txt`.

#### B7. Qualità del segnale e gestione `quote=----`

- **Tecnica/framework.** Le righe con `quote=----` (baseline: da 2 a 26 per file) sono periodi in cui il book è ~50/50 o LOB non quotato. Vanno trattate come *missing*, non come *informazione neutra*.
- **Definizione operativa.**
  - `Q(sec) = 1` se `quote ∈ {Up, Down}`, `0` se `quote = ----`.
  - **Quoting intensity**: `QI(sec) = media_mobile(Q, 10s)` in `[0,1]`.
  - **Run di indeterminatezza**: `Run(sec) = lunghezza dello streak corrente di `quote=----`.
  - **Indice di confidenza feed**: `C(sec) = QI(sec) · exp(−Run(sec)/τ)`, con `τ ≈ 5 s` (costante di decadimento da calibrare).
- **Variazione riga per riga.** `C` decade durante run lunghi di `----`; risale rapidamente quando le quote tornano.
- **Aggregazione.** Frequenza empirica di `----` per `sec` e per `outcome`; stima di `τ` che meglio separa round "puliti" da round "sporchi". Gate operativo: `C(sec) > c*` per autorizzare l'entrata.
- **Dipendenze dati.** Solo `.txt`.

#### B8. Kelly fraction per secondo

- **Tecnica/framework.** Criterio di Kelly per scommesse a esito binario: dimensione ottimale della puntata data l'edge.
- **Definizione operativa.** Lato majority:
  - `b(sec) = payoff_net(sec)` (= `(100 − q) / q · (1 − fee)`).
  - `p = p_side(sec)` (da B3).
  - `f*(sec) = max(0, (p · (b+1) − 1) / b)`.
  - **Frazione operativa**: `f_op(sec) = ¼ · f*(sec)` (¼ Kelly, conservativo).
- **Variazione riga per riga.** `f*` è 0 quando non c'è edge (`p ≤ 1/(b+1) = q/100`), positivo altrimenti. Cade a zero in regime `quote=----` perché `p` non è affidabile (interazione con B7).
- **Aggregazione.** Su tutti i round: distribuzione di `f*` per `sec`. Backtest: applicare `f_op(sec)` *come se* si entrasse al `sec` indicato, simulare payoff con `outcome` noto → curva equity per `sec` di entrata.
- **Dipendenze dati.** Solo `.txt`.

#### B9. Convexità del payoff rispetto al sottostante

- **Tecnica/framework.** *Gamma* di un'opzione binaria: la seconda derivata del payoff rispetto al sottostante è massima *at-the-money* (vicino a PTB) e decade man mano che ci si allontana. È un indicatore di *quale lato del PTB* vale di più aspettare.
- **Definizione operativa.** Approssimazione discreta su finestra `w=10 s`:
  - `Γ(sec) ≈ |g(sec) − 2·g(sec−w/2) + g(sec−w)| / (Δbtc_w)²`.
  - **Indice at-the-money-ness**: `ATM(sec) = Γ(sec) / max(Γ osservato nel round)`. Vicino a 1 = siamo in zona PTB; vicino a 0 = lontani dal PTB (esito quasi deciso).
- **Variazione riga per riga.** `Γ` è alto a inizio round (payoff molto sensibile al sottostante) e decade monotonicamente nella zona "vicino a scadenza con esito deciso". Mostra picchi in corrispondenza di attraversamenti del PTB.
- **Aggregazione.** Per ogni `sec`: `ATM(sec)` medio per `outcome` Up vs Down. Conferma (o smentisce) che la zona ATM coincide con `gain%` intermedio e `quote≈50`.
- **Dipendenze dati.** Solo `.txt`.

#### B10. Indice di trade-off tempo/rischio/rendimento (sintesi)

- **Tecnica/framework.** Composizione dei precedenti in un *indice guida* unico, analogo all'esempio del meeting: più alto ⟹ più rischio *e* più guadagno potenziale; più basso ⟹ meno rischio *e* meno guadagno.
- **Definizione operativa.**
  - `S(sec) = α · |R(sec)| + β · Θ_w(sec) − γ · (1 − C(sec))`,
    con `α,β,γ ≥ 0` da calibrare. Interpretazione: *segnale* (edge), *costo del tempo* (theta), *costo di affidabilità* (qualità feed).
  - `T(sec) = sec / 300` ∈ (0,1] (tempo residuo normalizzato).
  - **Indice finale per secondo**: `I(sec) = S(sec) · √(T(sec))`. La `√` replica la penalizzazione tempo di B3.
- **Variazione riga per riga.** `I` cala al crescere di `sec` (più tempo residuo = meno informativo per secondo) e sale con l'edge, penalizzato da feed rumoroso.
- **Aggregazione.** Per `outcome`: media e IQR di `I(sec)`; soglia `I > I*` selezionata massimizzando expected profit per round (definito in B11).
- **Dipendenze dati.** Solo `.txt`.

#### B11. Expected Profit per round (metrica di validazione)

- **Tecnica/framework.** Misura di efficacia della regola "entra a `sec*` se `I(sec*) > I*`".
- **Definizione operativa.** Per ogni `sec` di ingresso ipotetico:
  - `E[Profit | sec, I>I*](round) = p(Up|I>I*,sec) · payoff_net_up(sec) · 𝟙(entra su Up) + …` mediato su tutti i round storici.
  - **EPR(sec)**: expected profit per round della regola. Si sceglie `sec*` che massimizza `EPR` e `I*` che lo massimizza condizionatamente.
- **Variazione riga per riga.** Non è una serie per-round ma una curva aggregata `EPR(sec)` su tutto il dataset.
- **Aggregazione.** È *essa stessa* l'aggregato: curva `EPR vs sec` per diverse soglie `I*`, con bande di confidenza bootstrap sui 98+ file.
- **Dipendenze dati.** Solo `.txt`.

### C. Indici che richiedono i file `.bin` (richiesta formale)

I seguenti indici **non** sono calcolabili dai soli `.txt` e richiedono esplicitamente i `.bin` in `data/bin/` (98 file disponibili; ne serviranno molti di più nel tempo, target 288/giorno):

1. **Mid-LOB spread e micro-spread.** `Spread_up(sec) = (best_ask_up − best_bid_up)`, idem Down. Spread alti = bassa liquidità = `I(sec)` da penalizzare ulteriormente.
2. **Profondità e imbalance.** `Depth_imbalance(sec) = (bid_size_up − ask_size_up) / (bid_size_up + ask_size_up)`. Forte imbalance in direzione del majority = segnale di *microstruttura* che anticipa il movimento del prezzo.
3. **Walk-the-book reale.** In baseline è citato `src/clob_api.py::market_buy_gain()` (ROI su walk LOB, `BET_USD=100`): ricalcolare il *gain%* riga per riga su LOB effettivamente osservato è il benchmark più realistico per `gain%` di B4 e per la validazione di B11.
4. **Hit ratio e queue position.** Quante quote sono state *consumed* dal LOB tra `sec` e `sec−1`; rileva la *velocità* con cui il mercato sta scommettendo su un lato.
5. **Stale-quote detection.** Quote `----` nei `.txt` (fino a 26 righe su 300 in un file, vedi baseline) possono dipendere da LOB vuoto: il `.bin` dice se l'assenza di quote è *tecnica* (order book vuoto) o *informativa* (50/50 vero).

**Richiesta esplicita al meeting:** autorizzare l'accesso a `data/bin/` (98 file) e, se possibile, ai `.bin` di almeno 5 giorni completi (≥1440 file) per validare gli indici B1–B10 in parallelo agli omologhi microstrutturali sopra elencati.

### D. Zone temporali ipotizzate (da validare)

Basandomi sull'osservazione che il `gain%` osservato parte da 0.9–2.9% (vicino al costo di fee) e può arrivare a 86–89% (alta confidenza direzionale) — vedi baseline — propongo la seguente partizione, da verificare sui 98+ file:

| Zona | `sec` | Caratteristiche attese | Indici dominanti |
|------|-------|------------------------|------------------|
| **Early / rumorosa** | 300–200 | `quote=----` frequenti (fino a 26/300 righe), `gain%` instabile, `Θ` alto in valore assoluto | B4, B7 (gate), B6 (calibrazione σ̂) |
| **Mid / formazione** | 200–100 | Trend si chiarisce, `B` e `M` diventano predicibili, `Γ` decresce | B1, B5, B9 |
| **Late / conferma** | 100–30 | `q` converge verso 90+, `gain%` alto e meno volatile, edge decresce | B3, B8 (Kelly) |
| **Final / freeze** | 30–1 | `gain%` vicino a 86–89%, edge quasi nullo, `C(sec)` spesso alto | B2 (calibrazione finale), B11 (verifica EPR) |

Ipotesi di soglia iniziale (da rifinire su 98 file): **entrare in zona Mid–Late, `sec ∈ [120, 30]`, con `I(sec) > I*` calibrato per massimizzare EPR**.

### E. Aggregazione su molti round (piano di calcolo)

Per ciascun indice B1–B10, dato l'insieme dei round storici (`N` = 98 oggi, *target ≥ migliaia*):

1. **Matrice indice × tempo**: per ogni round `r` e ogni `sec`, valore `idx(r, sec)`. Dimensione `N × 300`.
2. **Statistiche per `sec`**: media, mediana, IQR, std, quantili 5/25/50/75/95, stratificate per `outcome` ∈ {Up, Down}.
3. **Heatmap `sec × round`**: visualizzazione della serie; cluster di pattern simili (es. "entrate vincenti Mid-Late con B>2").
4. **Curve di calibrazione**: `Pr(outcome=Up | idx(sec)=x)` stimate via regressione logistica o isotonica; errore di calibrazione (Brier, log-loss) per ogni `sec`.
5. **Backtest EPR** (B11) su tutta la matrice; bootstrap a blocchi (blocchi di 1 ora) per bande di confidenza; walk-forward sui 98 file.
6. **Confronto Up vs Down**: per ogni `sec`, test di differenza delle distribuzioni (Mann-Whitney) e AUC del predittore `idx` per `outcome`.
7. **Selezione finale**: per ogni `sec*` candidato ∈ {300, 240, 180, 120, 90, 60, 30, 10}, stimare EPR e scegliere il migliore.

### F. Raccomandazioni di priorità di validazione

Ordine consigliato (alto ROI di calcolo, bassa dipendenza da `.bin`):

1. **B2 + B3 (Edge / value-bet) + B11 (EPR)** — cuore decisionale, calcolabili subito sui 98 file. Permettono di stabilire se e *dove* nel `sec` esiste un edge medio positivo.
2. **B1 + B6 (moneyness + vol)** — forniscono `σ̂` e `p_side` stabili per B3. Basso costo, alta riutilizzabilità.
3. **B7 (qualità feed)** — gate operativo, essenziale per non confondere `----` informativi con rumore.
4. **B4 (theta) + B5 (drift/breakout)** — affinano la *tempistica* (scegliere `sec*` esatto, non solo la zona).
5. **B8 (Kelly) + B9 (convexità) + B10 (indice sintetico)** — affinamento finale, dimensionamento puntata, robustezza.
6. **Indici microstrutturali da `.bin`** (Sez. C) — da avviare in parallelo non appena i `.bin` sono autorizzati; in particolare *depth imbalance* e *walk-the-book* per validare `gain%` e completare la validazione di B11.

### G. Rischi e limiti (da explicitare nel deliverable)

- **Campione limitato**: 7 file in context, 98 in `data/txt/`, 5 Up / 2 Down nel campione. Le soglie e i pesi `α,β,γ` di B10 non sono calibabili in modo affidabile su 98 file; servono migliaia (target 288/giorno, ovvero ~10.000 in 5 settimane).
- **Selezione sopravvissuta**: usare `outcome` noto per scegliere `sec*` introduce *look-ahead bias*. La procedura corretta è walk-forward con finestre di training/test.
- **Quote `----` non informative**: l'imputazione o l'esclusione può distorcere stime di `p_impl`; gestirle con B7 e documentare la scelta.
- **Modello di prezzo**: B1 assume GBM; deviazioni sistematiche (salti, drift di periodo) vanno testate e il modello aggiornato di conseguenza.
- **Fee e payout reali**: i `.bin` permettono di misurare il *gain% effettivo* su walk LOB, più realistico del `gain%` arrotondato dei `.txt`.

### H. Richieste formali al meeting

1. **Conferma ambito**: gli 11 indici B1–B11 coprono l'esempio guida (indice rischio/rendimento per secondo) e vanno nella giusta direzione? Servono altri framework (es. *reinforcement learning* per la scelta di `sec*`, oppure *optimal stopping* di tipo *free-boundary*)?
2. **Accesso `data/bin/`**: si autorizza l'uso dei 98 file `.bin` oggi, con piano di estensione ai prossimi 1440+ (5 giorni)?
3. **Cadenza di produzione**: i 288 round/giorno sono il *throughput* di raccolta atteso (quindi ~10.000 in 5 settimane)? Serve un *freeze* del dataset di calibrazione iniziale?
4. **Convention di segno per `delta`**: baseline conferma `delta = round(chainlink_btc − ptb_chainlink)` (Up positivo se BTC > PTB); confermare che `outcome=Up` ⟹ `final_chainlink > ptb_chainlink` è la convenzione usata nella pipeline.
5. **Metriche di successo**: il meeting conferma che l'obiettivo è *massimizzare EPR* (B11) *e* minimizzare la varianza di EPR (robustezza)? Solo profitto medio, o anche *Sharpe-like ratio*?

---

*Fine Turno 01. Output salvato in `meetings/entry-indicators/responses/response-m-minimax-turn01.md`.*