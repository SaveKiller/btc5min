# Report Turno 01 — Indici di timing entrata per BTC Up/Down 5m

**Meeting:** `entry-indicators`  
**Turno:** 01  
**Deliverable:** catalogo strutturato di indici candidati, definizioni formali, ipotesi di soglie/zone temporali, raccomandazioni su quali validare per prime sui dati storici.

---

## Punto 01 — Catalogo strutturato di indici candidati

### 1.1 Fatti ancorati al baseline (contesto e dati disponibili)

Il presente catalogo si basa sui fatti seguenti, ricavati da `baseline.md` e dai 7 file `.txt` in `context/`:

* Ogni round dura **300 secondi**, campionati a **1 Hz** (`sec` da 300 a 1).
* Colonne disponibili ogni secondo: `time`, `quote` (UP/DOWN/----), **prezzo quote in centesimi** (`c_t`), `delta` (`δ_t = BTC − PTB` arrotondato in $), `gain%` (`g_t` già netto della fee), `btc`.
* `fee_rate = 0.07` su tutti i 7 file.
* Il `gain%` rappresenta il **rendimento netto** se si scommette sul lato *majority* al secondo `t` e il round finisce a favore di quel lato; in caso di perdita la perdita è ~ −100% (o −99% nelle ultime righe ad alta quota).
* I file `.bin` (LOB completo) esistono in `data/bin/` (98 file) ma **non sono nel contesto**; quindi il catalogo privilegia indici calcolabili da `.txt`, con una sezione separata per indici che richiederebbero esplicitamente i `.bin`.
* Scala reale: **288 round/giorno**, attualmente **98 file** storici disponibili per backtest.
* Nei 7 file di esempio: 5 esiti `Up`, 2 `Down`; `gain%` varia da ~0% a ~89,6%; le righe `----` segnano incertezza o assenza di quotazione.

Da questi fatti emerge il **trade-off fondamentale** che gli indici devono quantificare:

> **Troppo presto** → `gain%` alto ma alta probabilità di ribaltamento.  
> **Troppo tardi** → `gain%` basso (spesso < 1%) e poco spazio per errore.  
> L’obiettivo è trovare la zona/il segnale in cui il **guadagno atteso** (`EV`) è massimo.

---

### 1.2 Notazione condivisa

Per ogni secondo `t` (con `t = sec`, tempo residuo decrescente 300 → 1) definiamo:

| Simbolo | Significato |
|---|---|
| `c_t` | prezzo quote in centesimi del lato majority (50 = `----`, 100 = certezza) |
| `q_t` | lato majority: `+1` per UP, `−1` per DOWN, `0` per `----` |
| `g_t` | `gain% / 100`, rendimento netto decimale se vince il lato su cui entriamo |
| `L` | perdita in caso di sconfitta: `L ≈ 1.0` (100% della puntata) |
| `δ_t` | `BTC − PTB` in dollari (dal file) |
| `B_t` | prezzo BTC (`btc`) |
| `τ_t` | tempo residuo = `t` secondi |
| `p_be(t)` | probabilità di break-even implicita: `p_be(t) = 1 / (1 + g_t)` |
| `p_imp(t)` | probabilità implicita dal prezzo: `p_imp(t) = c_t / 100` |
| `σ_t(W)` | deviazione standard rolling dei ritorni BTC su finestra `W` |
| `Φ(·)` | CDF della normale standard |

---

### 1.3 Concetti standardizzati

1. **Reward = `g_t`**  
   Il guadagno potenziale è dato direttamente dalla colonna `gain%`. È decrescente in `c_t`.

2. **Break-even probability = `p_be(t)`**  
   La probabilità effettiva di vincita necessaria per avere rendimento atteso nullo.  
   Esempio: `g_t = 0.76` → `p_be = 0.563`; `g_t = 0.009` → `p_be = 0.991`.

3. **Rischio = probabilità di ribaltamento**  
   Dipende da: tempo residuo `τ`, distanza `δ_t`, volatilità recente `σ_t`, stabilità della quotazione (`flip_rate`).

4. **Edge = stima probabilità reale − probabilità di break-even**  
   `Edge(t) = p_est(t) − p_be(t)`. Se `Edge > 0`, l’ingresso ha EV positivo.

5. **Tempo / urgenza**  
   Più `τ` è grande, maggiore il reward ma maggiore il rischio. La pendenza di `g_t` nel tempo (`time-decay`) indica quanto velocemente il mercato sta convergendo.

---

### 1.4 Catalogo degli indici candidati

#### IND-01 — MPR: Market Price / Implied Probability

**Framework:** Teoria delle scommesse / probabilità implicita.  
**Formula:**

```text
p_imp(t) = c_t / 100
p_be(t)   = 1 / (1 + g_t)
```

**Lettura riga per riga:**  
A ogni secondo `c_t` aumenta se il mercato diventa più confidente; `g_t` diminuisce. Confrontando `p_be(t)` e `p_imp(t)` si vede se il mercato richiede più o meno probabilità di quanto ne basti per pareggiare.

**Aggregazione storica:**  
Per ogni bucket di `c_t` (es. 51–55c, 56–65c, 66–80c, 81–95c, 96–100c) calcolare:

* numero di campioni,
* win rate realizzato del lato majority,
* `EV = win_rate * g_medio − (1 − win_rate) * L`.

**Soglie/zone temporali (ipotesi):**

| Prezzo `c_t` | Interpretazione |
|---|---|
| 51–55c | rewarding, validare se `p_est > 56–58%` |
| 56–75c | zona bilanciata, backtest principale |
| 76–90c | overconfidence, solo se `δ_t` molto favorevole |
| 91–100c | guadagno residuo < 2%, richiede accuratezza > 95–98% |

**Priorità validazione:** **Alta** — richiede solo `quote`, `gain%`, `outcome`.

---

#### IND-02 — ETA: Expected Time Advantage (reward per secondo residuo)

**Framework:** Trade-off tempo/rendimento.  
**Formula:**

```text
η_t = g_t / τ_t
```

**Lettura riga per riga:**  
Al secondo 300 con `g_t = 0.77` → `η ≈ 0.0026`; al secondo 60 con `g_t = 0.05` → `η ≈ 0.0008`.  
Indica quanto “premio” otteniamo per ogni secondo di esposizione.

**Aggregazione storica:**  
Distribuzione di `η_t`; correlare con win rate per bucket di `τ`. Cercare soglie `η_min` per cui `EV > 0`.

**Soglie/zone temporali (ipotesi):**

* `η_t > 0.003` → entry premio-alto → validare nelle prime 180s.
* `η_t < 0.0005` → entry poco attrattivo (solitamente ultimi 60s a quota alta).

**Priorità validazione:** **Media** — complementare a EV, non sufficiente da solo.

---

#### IND-03 — DTE: Delta-to-Edge / Allineamento prezzo-fondamentale

**Framework:** Mispricing tra posizione BTC e quotazione majority.  
**Formula:**

```text
Alignment(t) = q_t * δ_t
```

Se `q_t = +1` (UP) e `δ_t > 0`, il BTC è già sopra PTB → allineamento positivo.  
Se `q_t = −1` (DOWN) e `δ_t < 0`, allineamento positivo.

Variante normalizzata per volatilità:

```text
z_δ(t) = q_t * δ_t / σ_t(W)
```

**Lettura riga per riga:**  
Una quotazione cheap (`c_t` basso) associata a `Alignment` positivo grande indica possibile sottovalutazione. Una quotazione alta (`c_t > 90c`) con `Alignment` negativo indica overconfidence.

**Aggregazione storica:**  
Bucket di `z_δ` e `c_t`; calcolare win rate ed EV condizionale.

**Soglie/zone temporali (ipotesi):**

* `z_δ > +1.5` e `c_t < 70c` → possibile forte edge.
* `Alignment < 0` e `c_t > 85c` → evitare (divergenza).
* Escludere sempre `q_t = 0` (`----`).

**Priorità validazione:** **Alta** — sfrutta `delta` e `btc`, dati già presenti.

---

#### IND-04 — MOM: Momentum BTC

**Framework:** Analisi tecnica / trend short-term.  
**Formula:**

```text
v_t(k) = (B_t − B_{t−k}) / k        [USD/s]
a_t(k) = v_t(k) − v_{t−k}(k)        [accelerazione]
MOM_score(t) = q_t * v_t(k)
```

**Lettura riga per riga:**  
Se il lato majority è UP e `v_t` è positivo, il trend favorisce l’ingresso. Se `v_t` è negativo, il rischio di ribaltamento aumenta.

**Aggregazione storica:**  
Per bucket di `MOM_score` e `τ`, calcolare win rate ed EV.

**Soglie/zone temporali (ipotesi):**

| Zona | `v_t(k)` minimo favorevole |
|---|---|
| 300–240s | `q_t * v_t > 0.10 $/s` |
| 240–120s | `q_t * v_t > 0.05 $/s` |
| 120–60s | `q_t * v_t > 0.02 $/s` |
| <60s | richiedere `q_t * v_t > 0` e `c_t` non troppo alta |

**Priorità validazione:** **Alta** — dati disponibili, utile a filtrare false partenze.

---

#### IND-05 — VOL: Volatilità realizzata e stabilità della quotazione

**Framework:** Misura di rischio dinamica.  
**Formula:**

```text
r_t      = B_t − B_{t−1}
σ_t(W)   = sqrt( mean_{i=0..W−1} (r_{t−i} − μ)^2 )
flip_t   = (# cambi q_t in ultimi F secondi) / F
Risk_t   = σ_t(W) * sqrt(τ_t) * (1 + flip_t)
```

**Lettura riga per riga:**  
Alta volatilità e frequenti flips UP↔DOWN aumentano il rischio di entrare su un lato che poi perde la maggioranza.

**Aggregazione storica:**  
Distribuzione di `Risk_t`; correlare con la probabilità di ribaltamento.

**Soglie/zone temporali (ipotesi):**

* `Risk_t` nel quintile superiore → filtro di esclusione, salvo EV molto alto.
* `flip_t > 0.3` (più di 10 flips in 30s) → evitare entry finché non si stabilizza.

**Priorità validazione:** **Media** — utile come filtro, ma richiede calibrazione sui 98 file.

---

#### IND-06 — SURV: Probabilità di sopravvivenza / first-passage (stile opzioni digitali)

**Framework:** Probabilità che BTC finisca sopra/sotto PTB, approssimando i ritorni come Brownian motion con drift nullo (poi estendibile con drift da MOM).  
**Formula:**

```text
p_surv(t) = Φ( q_t * δ_t / (σ_t(W) * sqrt(τ_t)) )
```

Per UP: `q_t=+1`; per DOWN: `q_t=−1`.  
`Φ` è la CDF normale; `σ_t(W)` da IND-05.

**Lettura riga per riga:**  
Stima la probabilità che il lato majority vinca. Se `p_surv` supera sia `p_imp` che `p_be`, c’è edge.

**Aggregazione storica:**  
Per bucket di `p_surv`, calcolare win rate realizzato: serve a validare se l’assunto Browniano è calibrato sui dati storici.

**Soglie/zone temporali (ipotesi):**

* `p_surv > 0.65` e `c_t < 65c` → entry attraente.
* `p_surv < 0.55` ma `c_t > 85c` → forte overconfidence, evitare.

**Priorità validazione:** **Alta** — è il componente “stima probabilità” per EV e Kelly.

---

#### IND-07 — EV: Expected Value (indice di decisione principale)

**Framework:** Criterio del valore atteso / utility theory.  
**Formula:**

```text
EV_t = p_est(t) * g_t − (1 − p_est(t)) * L
```

Dove `p_est(t)` può essere:

* `p_surv(t)` da IND-06, oppure
* una probabilità empirica calcolata sui dati storici condizionata a `{c_t, z_δ, τ, MOM_score}`.

**Lettura riga per riga:**  
A ogni secondo calcola il PnL atteso netto. Se `EV_t > 0` (tolleranza minima), il segnale è “entra”.

**Aggregazione storica:**  
Per ogni regola di ingresso, calcolare:

```text
win_rate = # esiti corretti / # trades
avg_pnl = mean(g_t su vincite) * win_rate − L * (1 − win_rate)
```

**Soglie/zone temporali (ipotesi):**

* `EV_t > 0.05` (5% di edge) → entry.
* `EV_t > 0.10` → entry aggressiva.
* `EV_t < 0` → non entrare.

**Priorità validazione:** **Massima** — questo è l’indice mediante cui giudicare tutti gli altri.

---

#### IND-08 — KEL: Kelly Fraction

**Framework:** Criterio di Kelly per gestione taglia / accettazione trade.  
**Formula:**

```text
f*_t = (p_est(t) * (1 + g_t) − 1) / g_t
```

Se `f*_t > 0`, il trade ha edge. In pratica usare **frazionale Kelly** (`f*_t / 4`) per robustezza.

**Lettura riga per riga:**  
Valuta non solo se entrare ma quanto conviene in termini di crescita ottimale del capitale. Per sizing fisso può essere usato come filtro (`f*_t > 0`).

**Aggregazione storica:**  
Distribuzione di `f*_t`; correlare con realized EV.

**Soglie/zone temporali (ipotesi):**

* `f*_t > 0.10` → accettabile.
* `f*_t < 0` → rifutare.
* Applica cap massimo per evitare leva eccessiva su `g_t` molto alto.

**Priorità validazione:** **Media** — complementare a EV.

---

#### IND-09 — RR: Risk/Reward da `gain%`

**Framework:** Misura diretta del premio per unità di rischio.  
**Formula:**

```text
RR_t = 1 / g_t          # rischio $1 per guadagnare g_t
```

**Lettura riga per riga:**  
`g_t` alto → `RR` basso (buono in termini puri di reward). `g_t` basso → `RR` altissimo (es. 1/0.009 ≈ 111), richiede accuratezza quasi perfetta.

**Aggregazione storica:**  
`RR` medio per trade vincenti vs perdenti.

**Soglie/zone temporali (ipotesi):**

* `g_t < 0.02` (gain < 2%) → evitare salvo `p_est > 0.98`.
* `g_t > 0.15` (gain > 15%) → reward interessante, ma richiede più filtri.

**Priorità validazione:** **Media** — semplice ma va combinato con probabilità.

---

#### IND-10 — QRS: Quote Regime Stability

**Framework:** Analisi del regime di mercato / stabilità della quotazione.  
**Formula:**

```text
regime_len(t) = numero di secondi consecutivi con lo stesso q_t
price_trend(t,k) = (c_t − c_{t−k}) / k
QRS_t = regime_len(t) / (1 + |price_trend(t,k)|)
```

**Lettura riga per riga:**  
Una maggioranza stabile per molti secondi e con prezzo che cambia lentamente riduce il rischio di “falso segnale”.

**Aggregazione storica:**  
Win rate condizionato a `QRS_t` alto/basso.

**Soglie/zone temporali (ipotesi):**

* `regime_len > 15s` e `|price_trend| < 0.5 c/s` → regime stabile.
* `regime_len < 5s` → aspettare conferma.

**Priorità validazione:** **Media/Bassa** — filtro utile, da calibrare dopo EV e DTE.

---

#### IND-11 — TDS: Time-Decay Slope (pendenza del gain)

**Framework:** Misura di urgenza / velocità di convergenza del mercato.  
**Formula:**

```text
gain_slope(t,k) = (g_t − g_{t−k}) / k
urgency(t) = −gain_slope(t,k) / (1 + c_t/100)
```

**Lettura riga per riga:**  
Se `g_t` scende rapidamente, il mercato sta confermando un lato e il prezzo si sta rivalutando: c’è urgenza ad entrare prima che il gain collassi. Se `g_t` sale, il mercato sta diventando più incerto.

**Aggregazione storica:**  
Correlare `urgency` con EV realizzato.

**Soglie/zone temporali (ipotesi):**

* `urgency > 0.005` e `q_t` allineato a MOM/DTE → entry rapida.
* `gain_slope > 0` (gain in crescita) → mercato incerto, attendere.

**Priorità validazione:** **Media** — può anticipare buoni punti di ingresso nelle prime 180s.

---

#### IND-12 — CPA: Composite Price-Alignment Score

**Framework:** Indice sintetico che combina prezzo, delta, momentum, volatilità e stabilità.  
**Formula (proposta da calibrare):**

```text
CPA_t = w1 * z_δ(t) + w2 * MOM_score(t) / σ_t(W) + w3 * (1 − c_t/100) + w4 * QRS_t_norm
```

`w1...w4` da stimare regressione/ottimizzazione sui 98 file storici.

**Lettura riga per riga:**  
Un `CPA_t` elevato indica che il prezzo è ancora basso, il movimento BTC favorevole, la volatilità controllata e il regime stabile.

**Aggregazione storica:**  
Regressione logistica della vittoria sui componenti di CPA; ottimizzazione pesi massimizzando EV.

**Soglie/zone temporali (ipotesi):**

* `CPA_t > soglia_90_percentile` → entry.
* I pesi possono variare per zona temporale (più peso a MOM in apertura, più a `z_δ` e QRS in chiusura).

**Priorità validazione:** **Bassa** — da sviluppare dopo aver validato i singoli componenti.

---

#### IND-13 — LOB: Indici di microstruttura (richiede `.bin`)

**Framework:** Market microstructure / order book.  
**Indici possibili:**

* Bid-ask spread (anche implicito se disponibile).
* LOB imbalance: `(volume_bid_UP − volume_ask_UP) / totale`.
* Order flow: variazione di volume negli ultimi secondi.
* Book pressure: differenza tra migliori bid/ask.

**Lettura riga per riga:**  
Richiede parsing del file `.bin` (non incluso nel contesto). Utile per anticipare ribaltamenti prima che `quote` cambi.

**Aggregazione storica:**  
Correlare imbalance/volume con successiva variazione di `quote` ed esito.

**Soglie/zone temporali (ipotesi):**

* Valutare solo se i `.bin` vengono resi disponibili.
* Filtro high-priority: entrare solo se il book conferma la direzione di `quote`.

**Priorità validazione:** **Bassa / futura** — candidato avanzato, richiede dati aggiuntivi.

---

### 1.5 Esempio di regola decisionale composita

Una possibile pipeline di ingresso (da validare):

```text
IF c_t = 50c (----) → NO ENTRY
IF c_t > 95c AND g_t < 0.02 → NO ENTRY (reward troppo basso)
IF Risk_t > 90° percentile storico → NO ENTRY
IF z_δ(t) < 0 AND c_t > 85c → NO ENTRY
ELSE
    EV_t = p_est(t) * g_t − (1 − p_est(t)) * L
    IF EV_t > 0.05 AND QRS_t sopra mediana → ENTRY
```

Dove `p_est(t)` può essere `p_surv(t)` o una tabella empirica condizionata.

---

### 1.6 Piano di validazione storica e raccomandazioni

**Ordine di validazione consigliato:**

1. **Tier 1 — Inizio immediato**
   * **IND-07 EV** con `p_est` grezzo = `p_imp(t)` (baseline pessimistica) e con `p_surv(t)` (IND-06).
   * **IND-02 MPR**: tabella accuratezza per bucket di `c_t` e `τ`.
   * **IND-09 RR**: confronto `g_t` vs accuratezza richiesta.

2. **Tier 2 — Dopo 2-3 giorni di dati**
   * **IND-03 DTE** e **IND-04 MOM**; validare combinazione `z_δ + MOM`.
   * **IND-05 VOL** come filtro di esclusione.

3. **Tier 3 — Ottimizzazione**
   * **IND-10 QRS**, **IND-11 TDS**.
   * **IND-08 KEL** per sizing / soglie.
   * **IND-12 CPA** composito.

4. **Tier 4 — Dati aggiuntivi**
   * **IND-13 LOB** se si richiedono/esplicitano i file `.bin`.

**Metodologia di backtest sui 98 file:**

1. Costruire un dataset flat: una riga per ogni secondo di ogni round, con tutti gli indici e l’esito.
2. Per ogni indice/candidato, calcolare:
   * `win_rate` per bucket,
   * `avg_pnl` = `win_rate * mean(g_t|win) − (1 − win_rate) * L`,
   * `profit_factor` = profitto totale / perdite totali,
   * `max_drawdown` e consecutive losses.
3. Usare **walk-forward** per evitare overfitting: calibrare soglie sui primi N file, testare sui successivi.
4. Data la frequenza di 288 round/giorno, verificare la **stabilità nel tempo** (volatilità del BTC cambia; le soglie potrebbero dover essere adattive).
5. Confrontare ogni strategia con una **baseline**: “entra sempre al secondo 300 sulla majority” e “entra sempre al secondo 60 sulla majority”.

**Metriche di valutazione:**

* `EV` medio per trade.
* Sharpe dei rendimenti (time-weighted).
* Percentuale di round operabili (escludere `----` e quote troppo alte).
* Drawdown massimo e sequenze di perdite.

---

### 1.7 Soglie/zona temporali di partenza (ipotesi da calibrare)

| Zona temporale | `τ` | Comportamento atteso | Strategia indicativa |
|---|---|---|---|
| **Apertura** | 300–240s | `g_t` alto, alta variabilità | Entrare solo con forte `z_δ` e MOM favorevole; EV deve essere sicuro |
| **Prima metà** | 240–120s | Buon compromesso gain/rischio | Zona principale per l’ingresso; combinare EV + DTE + MOM |
| **Seconda metà** | 120–60s | Convergenza del mercato, `g_t` in calo | Entrare solo se `c_t` non troppo alta e `δ_t` conferma |
| **Chiusura** | <60s | Reward quasi nullo o quotazione bloccata | Evitare se `g_t < 2%` o `c_t` = 100c / `----`; eccezione: alta certezza con `p_surv > 0.95` e `g_t > 1%` |

---

### 1.8 Conclusione e prossimi passi

Il catalogo fornisce un insieme coerente di indici, tutti calcolabili a posteriori (e quindi integrabili nel feed tick-by-tick) a partire dai file `.txt`. L’indice cardine è **EV (IND-07)**, alimentato da una stima affidabile di probabilità come **SURV (IND-06)** o da tabelle empiriche. Gli indici **DTE (IND-03)** e **MOM (IND-04)** sono i filtri direzionali più promettenti, mentre **MPR (IND-02)** e **VOL (IND-05)** permettono di scartare condizioni poco remunerative o troppo rischiose.

**Prossimo passo consigliato:**  
Eseguire il backtest sui **98 file storici** per:
1. validare la tabella `c_t` → win rate → EV;
2. calibrare `σ_t(W)` e la formula `p_surv(t)`;
3. determinare le soglie definitive di ingresso per EV (IND-07) e CPA (IND-12).