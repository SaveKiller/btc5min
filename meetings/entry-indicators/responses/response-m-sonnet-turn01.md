# Risposta m-sonnet — meeting entry-indicators — Turno 01

- **agent**: m-sonnet
- **generated_utc**: 2026-07-08T12:49:00Z
- **turno**: 01
- **punti trattati**: Punto 01 (unico)

---

## Punto 01 — Catalogo indici candidati per il timing di entrata

### 0. Premessa metodologica

I 7 file di esempio confermano alcune strutture fondamentali su cui costruire tutti gli indici:

- **Relazione gain%/prezzo**: strettamente inversa e deterministica. Dato prezzo `P_c` in centesimi:
  `G(t) = (100/P_c − 1) × (1 − fee_rate)` con `fee_rate = 0.07`
  Quindi G(t) è ridondante rispetto a `P_c`: conosce uno, conosce l'altro. È ugualmente utile usare
  il prezzo quote in centesimi come input primario.

- **Struttura temporale**: `sec` va da 300 a 1. Nei 7 file tutti i round hanno esattamente 300 tick.
  Alla fine (sec ≈ 15–28) quote diventa `---` e gain% scompare: la liquidità si prosciuga.

- **Delta**: `Δ(t) = BTC(t) − ptb_chainlink`. Non è la distanza dal PTB dell'outcome
  (che è `ptb_price` o `ptb_chainlink`): è la distanza in dollari della quotazione corrente dal
  riferimento Chainlink di inizio round. È il segnale diretto sulla "posizione" rispetto all'outcome.

- **Fee implicita**: 7% fisso → il breakeven a puntata identica è P_c > 53c circa
  (`1/1.07 ≈ 0.935` → ci serve vincere >93.5% con P_c=100c per coprire la fee; ma a P_c=53c,
  gain ≈ (100/53−1)×0.93 ≈ 75.5%, quindi si vince meno del doppio).

---

### 1. Indici di base (Gruppo A) — direttamente computabili dal feed

#### A1. Gain Potential `G(t)`

**Formula:**
```
G(t) = (100 / P_c(t) − 1) × (1 − 0.07)
```
dove `P_c(t)` è il prezzo in centesimi della quota majority al secondo `t`.

**Variazione per riga:** segue direttamente P_c(t); decresce monotonicamente in media
avvicinandosi alla scadenza ma con forte rumore locale (vedi oscillazioni nei file Down).

**Aggregazione su N round:** distribuzione di G per ogni valore di `sec` → media e percentili
costruiscono la curva G_expected(sec) = curva di riferimento per l'eccesso/difetto.

**Trade-off:** G(t) alto ↔ rischio alto. È la metrica più immediata del rendimento potenziale
ma non misura il rischio intrinseco: serve sempre un complemento.

---

#### A2. Probabilità implicita `P_impl(t)`

**Formula:**
```
P_impl(t) = P_c(t) / 100
```

Rappresenta la stima di mercato che la scommessa majority vinca. Nei file osservati:
- sec=300: P_impl ≈ 0.50–0.55 (alta incertezza all'inizio)
- sec=1–20: P_impl ≈ 0.97–0.99 (mercato quasi certo)
- `----` (P_c=50c): mercato completamente neutro → P_impl = 0.50

**Trade-off:** P_impl basso = G alto ma mercato incerto. P_impl alto = G basso ma segnale forte.

---

#### A3. Frazione temporale residua `T(t)`

**Formula:**
```
T(t) = sec(t) / 300
```

Normalizza il tempo: T=1 a inizio round, T→0 a fine round.

**Ruolo:** puro fattore di rischio temporale. A parità di P_impl, T alto implica molte
opportunità di inversione del BTC → rischio più alto. Usato come variabile di controllo
in tutte le regressioni.

---

#### A4. Delta normalizzato `Δ_norm(t)`

**Formula:**
```
Δ(t) = BTC(t) − ptb_chainlink          [già nel file, in $]
Δ_norm(t) = Δ(t) / σ_BTC(t, 30)       [normalizzato sulla vol locale 30s]
```

Indica "quanto è lontano" il prezzo BTC corrente dal riferimento di inizio round,
in unità di deviazione standard calcolata sulla finestra mobile degli ultimi 30 secondi.

**Interpretazione:** se quote = UP e Δ_norm > 0, BTC è già sopra PTB → segnale favorevole.
Se Δ_norm >> 1 e sec è basso, outcome quasi certo.

---

### 2. Indici di rischio/volatilità (Gruppo B)

#### B1. Volatilità locale BTC `σ_BTC(t, k)`

**Formula:**
```
σ_BTC(t, k) = std(BTC(t), BTC(t+1), ..., BTC(t+k−1))
```
(finestra scorrevole degli ultimi k secondi; k consigliati: 10, 30, 60)

**Ruolo:** misura l'incertezza del prezzo BTC in quel momento del round.
Alta σ_BTC → alta probabilità che BTC cambi posizione rispetto al PTB → alto rischio scommessa.

**Aggregazione su N round:** per ogni `sec` si può calcolare σ_BTC media storica → curva di
riferimento. Un valore molto alto rispetto alla media storica segnala un round "nervoso".

**Trade-off:** σ_BTC alta con sec alto = massimo rischio. σ_BTC bassa con sec basso =
rischio minimo (outcome quasi bloccato).

---

#### B2. Volatilità del prezzo quote `σ_P(t, k)`

**Formula:**
```
σ_P(t, k) = std(P_c(t), P_c(t+1), ..., P_c(t+k−1))
```

Misura quanto oscilla il prezzo di mercato della scommessa. Una σ_P alta significa che
il mercato è instabile e cambia valutazione frequentemente → segnale di incertezza elevata.

Nei file Down osservati (1783476900, 1783479900), σ_P a sec=300–250 è tipicamente più alta
che nei file Up fortemente direzionali → potenziale discriminatore statistico.

---

#### B3. Cushion (Margine di sicurezza) `C(t)`

**Formula:**
```
C(t) = Δ(t) / σ_BTC(t, 30)    [se quote = UP; invertire segno se quote = DOWN]
```
Equivalente a un "numero di sigma" tra la posizione corrente e la "zona di pericolo" (PTB).

**Interpretazione:**
- C > 2: BTC è 2 σ lontano dal PTB, outcome quasi certo → basso rischio, basso gain
- C ≈ 0: BTC è esattamente a PTB → massima incertezza
- C < 0: BTC è "dalla parte sbagliata" rispetto alla quota → scommessa contro trend corrente

**Questo è probabilmente l'indice più potente** per stimare la certezza dell'outcome
in un qualsiasi momento del round, indipendente dal tempo residuo.

**Trade-off:** C alto con G basso = scommessa quasi sicura ma poco redditizia.
C basso con G alto = scommessa speculativa, forte gain se indovinata.

---

#### B4. Quote Reversal Rate `QR(t, k)`

**Formula:**
```
flips(t, k) = numero di cambi direzione (UP↔DOWN o con ----) negli ultimi k secondi
QR(t, k)    = flips(t, k) / k
```

Alta QR = mercato indeciso, cambia continuamente la maggioranza. Bassa QR = mercato
stabile su una direzione.

**Dai file osservati:** nei round Down (1783476900), i flips sono molto più frequenti
(26 righe `----`) rispetto ai round Up stabili (6 righe `----` in 1783476600) →
QR potrebbe discriminare i round ad alto rischio.

---

### 3. Indici di momentum e trend (Gruppo C)

#### C1. Momentum BTC `MOM(t, k)`

**Formula:**
```
MOM(t, k) = (BTC(t) − BTC(t+k)) / k    [variazione media per secondo]
```
(derivata prima approssimata su finestra k)

**Interpretazione:** positivo = BTC sta salendo in questa finestra. Se quote = UP e MOM > 0,
la tendenza supporta l'outcome → vantaggio informativo.

**Nota:** su dati 1 Hz con 30 secondi di finestra, MOM misura la "velocità" del prezzo BTC.
Combinato con C(t) permette di distinguere situazioni statiche (BTC fermo lontano da PTB)
da situazioni in movimento (BTC che si avvicina o allontana da PTB).

---

#### C2. Accelerazione BTC `ACC(t)`

**Formula:**
```
ACC(t) = MOM(t, 5) − MOM(t+5, 5)    [derivata seconda approssimata]
```

Misura se BTC sta accelerando o decelerando nella direzione corrente.
ACC < 0 con MOM > 0 = BTC sta perdendo slancio verso UP → potenziale inversione imminente.

Utile come early warning di inversione, specialmente a sec 60–120 dove il momentum
rimanente ha ancora effetto sull'outcome.

---

#### C3. Conviction Persistence `CP(t, k)`

**Formula:**
```
CP(t, k) = (numero di sec negli ultimi k con stessa direzione di quote(t)) / k
```

CP=1 = la direzione corrente è stabile da k secondi.
CP=0 = direzione corrente appena cambiata, storia recente contraria.

**Trade-off:** CP alto + P_impl alto + sec basso = segnale molto forte per entrare
sul lato majority (ma gain già basso). CP basso = segnale debole.

---

### 4. Indici ispirati alla teoria delle opzioni (Gruppo D)

Il round Polymarket "BTC Up/Down 5m" è formalmente identico a una **opzione binaria cash-or-nothing**:
- **Sottostante**: prezzo BTC (Chainlink oracle)
- **Strike**: ptb_chainlink (prezzo BTC all'inizio del round)
- **Scadenza**: sec=1 (tra T=300/86400 giorni ≈ 0.00347 giorni)
- **Payoff**: 1$ se BTC_final > ptb_chainlink (Up) oppure < ptb_chainlink (Down)
- **Prezzo mercato**: P_c(t)/100 = P_impl(t)

Il prezzo teorico di un'opzione binaria (approssimazione Black-Scholes):

```
P_teorica(t) = N(d2)

d2 = [ ln(BTC(t)/ptb_chainlink) + (−½ σ²_annualiz × T_residuo) ] / (σ_annualiz × √T_residuo)
```

dove N() è la CDF della normale standard, σ_annualiz è la volatilità annualizzata del BTC
(es. 60% annuo = 0.60), T_residuo = sec(t) / (365×24×3600).

In pratica per sec=60 (T = 60/31536000 ≈ 1.9×10⁻⁶ anni) e σ_BTC locale:

```
σ_eff = σ_BTC(t, 30) / BTC(t)   [in termini relativi, stima locale]
d2(t) = Δ_norm(t) / σ_P_eff × √(1/T_residuo) ≈ C(t) × f(sec)
```

**Questa equivalenza è fondamentale**: C(t) (Cushion) e P_teorica(t) sono quasi la stessa cosa,
con P_teorica come versione continua e calibrata di C(t).

---

#### D1. Theta (decadimento temporale) `θ(t)`

**Formula:**
```
θ(t) = −ΔG(t)/Δsec  ≈  [G(t+1) − G(t−1)] / 2
```

Misura di quanti punti percentuali diminuisce il gain per ogni secondo che passa.
Equivale all'"options theta".

**Dai file osservati:** θ è alto nelle zone centrali (sec 60–120) dove la curva di G(t)
ha la pendenza massima, e basso agli estremi (sec 300 e sec < 30).

**Utilità:** zone con θ basso + G ancora buono = "sweet spot" per l'entrata
(il tempo rimanente non brucia il gain troppo velocemente).

---

#### D2. Gamma implicito `Γ(t)`

**Formula:**
```
Γ(t) = |ΔP_impl / ΔBTC|    [sensibilità del prezzo quote a $1 di movimento BTC]
```

Γ alto = un piccolo movimento del BTC cambia drasticamente la probabilità implicita → zona ad alto rischio.
Γ basso = il prezzo è insensibile al BTC locale → outcome già determinato.

**Nota:** nei round con sec basso e C alto, Γ è basso (i movimenti BTC non cambiano più il
verdetto del mercato). Nei round con sec alto e C≈0, Γ è massimo.

---

#### D3. Inefficienza di mercato `Ineff(t)`

**Formula:**
```
Ineff(t) = P_impl(t) − P_teorica(t)
```

Se `Ineff > 0`: mercato sopravvaluta il lato majority rispetto al modello teorico
→ il lato minority è a sconto → opportunità di valore sul lato contrario.
Se `Ineff < 0`: mercato sottovaluta il majority → entrare sul majority dà edge teorico.

**Questo è l'indice chiave per l'edge**: serve costruire P_teorica(t) calibrata
sui dati storici reali (98 file già disponibili, migliaia in futuro).
La divergenza sistematica Ineff(t) ≠ 0 è il segnale di inefficienza sfruttabile.

**Nota importante:** Ineff è calcolabile solo dopo calibrazione della volatilità BTC
storica per fascia oraria e giorno della settimana.

---

### 5. Indici di edge e valore atteso (Gruppo E)

#### E1. Expected Value `EV(t)`

**Formula:**
```
EV(t) = P_true(t) × G(t) − (1 − P_true(t))
```

dove `P_true(t)` è la probabilità empirica stimata da dati storici con le stesse condizioni
(stesso `sec`, stessa zona di C, stesso regime di volatilità).

Se EV(t) > 0 → la scommessa ha valore atteso positivo a quel preciso secondo.

**Problema**: P_true(t) richiede aggregazione su centinaia di round con le stesse
caratteristiche → non disponibile subito, ma costruibile progressivamente.

**Nota**: se il mercato fosse perfettamente efficiente, P_impl(t) = P_true(t)
e EV(t) ≡ 0 sempre. L'obiettivo del progetto è trovare le condizioni sistematiche
in cui P_impl ≠ P_true.

---

#### E2. Kelly Fraction `K(t)`

**Formula:**
```
b = G(t)             [odds netti per unità scommessa]
p = P_true(t)
q = 1 − p

K(t) = (p × b − q) / b = p − q/b
```

K(t) > 0 → edge positivo, vale la pena scommettere (con dimensionamento proporzionale a K).
K(t) ≤ 0 → no edge, non entrare.

**La Kelly fraction** è anche una misura di quanto "conviene" scommettere in quel momento:
K(t) = 0.05 significa scommettere 5% del bankroll.

**Limitazione**: come EV, richiede P_true stimato da dati storici.

---

#### E3. Divergenza probabilità `P_div(t)`

**Formula:**
```
P_hist(sec_bucket, C_bucket) = win_rate storico per round con sec ≈ sec(t) e C ≈ C(t)
P_div(t) = P_hist − P_impl(t)
```

Questo è un approccio non-parametrico, alternativo a D3. Non richiede modello teorico
(Black-Scholes) ma solo dati storici catalogati per bucket (es. 10 bucket di sec × 5 bucket di C).

**Priorità alta per validazione**: con 288 round/giorno, in 30 giorni si hanno ~8640 round
→ statisticamente sufficienti per riempire una griglia di bucket con ~10-20 esempi per cella.

---

### 6. Standardizzazione dei concetti chiave

Il meeting richiede di standardizzare il trade-off tempo/rischio/rendimento. Propongo questa
tassonomia operativa:

#### 6.1 Zone temporali standardizzate

| Zona | sec | T_norm | G tipico | Caratteristica |
|------|-----|--------|----------|----------------|
| **Z1 Early** | 300–200 | 1.0–0.67 | 50–89% | Massima incertezza; BTC ha tempo illimitato per invertire |
| **Z2 Middle** | 200–120 | 0.67–0.40 | 25–55% | Incertezza media; trend inizia a definirsi |
| **Z3 Late** | 120–60 | 0.40–0.20 | 10–30% | Bassa incertezza; segnale moderatamente affidabile |
| **Z4 Terminal** | 60–20 | 0.20–0.07 | 2–15% | Alta certezza; gain basso; ottima solo con C alto |
| **Z5 Frozen** | <20 | <0.07 | 0–3% o `---` | Mercato illiquido; spread allargato; evitare |

Questi range sono derivati dall'osservazione diretta dei 7 file. La calibrazione esatta
andrà fatta sui 98+ file disponibili.

---

#### 6.2 Triangolo fondamentale del trade-off

```
           GAIN%
              ↑
     Z1 ●────────── alta incertezza
        │           (mercato quasi 50/50)
     Z2 ●
        │
     Z3 ●
        │
     Z4 ●────────── bassa incertezza
        │           (mercato quasi certo)
              ↓
           RISCHIO
```

**Assioma 1 — Decadimento temporale del gain:**
`G(t) ≈ (100/P_equilibrio − 1) × (1 − fee) × f(sec, Δ)`
In media, G decresce con sec decrescente in modo sigmoide.

**Assioma 2 — Relazione gain/probabilità:**
`G(t) = (1/P_impl(t) − 1) × (1 − fee)` (identità contabile — nessuna informazione extra)
Il gain è solo la riformulazione algebrica del prezzo quota.

**Assioma 3 — Rischio residuo:**
`Rischio(t) ≈ σ_BTC(t) × √sec(t) / |Δ(t)|`
Combinazione di volatilità locale, tempo residuo e distanza dal PTB.
Questo è il vero indice di rischio non tautologico (non ridondante con G(t)).

**Conclusione chiave**: G(t) e P_impl(t) sono **tautologicamente** legati al prezzo.
Per costruire edge, si deve confrontare P_impl con una stima indipendente P_true.
Gli indici utili sono quelli che contribuiscono a stimare P_true: C(t), σ_BTC, QR, CP, MOM.

---

#### 6.3 Matrice rischio/rendimento per zona temporale

| Zona | Rischio | Rendimento | Strategia suggerita |
|------|---------|------------|---------------------|
| Z1 | +++ | +++ | Solo con segnale forte (C > 2, MOM direzionale, CP > 0.8) |
| Z2 | ++ | ++ | Con C > 1.5 + σ_BTC bassa + QR < 0.02 |
| Z3 | + | + | Sweet spot: C > 1 sufficiente; θ ancora accettabile |
| Z4 | basso | basso | Quasi sicuro se C > 2; ma G < 10% → serve large volume |
| Z5 | ? | quasi 0 | Evitare: mercato illiquido, gain irrisorio |

---

### 7. Catalogo sintetico degli indici (riepilogo)

| ID | Nome | Formula | Dato necessario | Complessità calcolo |
|----|------|---------|-----------------|---------------------|
| A1 | Gain Potential | `(100/P_c − 1)×0.93` | P_c | bassa |
| A2 | Probabilità implicita | `P_c/100` | P_c | bassa |
| A3 | Tempo residuo norm. | `sec/300` | sec | bassa |
| A4 | Delta norm. | `Δ/σ_BTC(30)` | Δ, BTC | media |
| B1 | Volatilità BTC locale | `std(BTC[t..t+k])` | BTC | bassa |
| B2 | Volatilità quote | `std(P_c[t..t+k])` | P_c | bassa |
| B3 | Cushion | `Δ/σ_BTC(30)` con segno | Δ, BTC | media |
| B4 | Quote Reversal Rate | `flips/k` | quote | bassa |
| C1 | Momentum BTC | `(BTC(t)−BTC(t+k))/k` | BTC | bassa |
| C2 | Accelerazione BTC | `ΔMOM` | BTC | bassa |
| C3 | Conviction Persistence | `same_dir_count/k` | quote | bassa |
| D1 | Theta | `−ΔG/Δsec` | G | bassa |
| D2 | Gamma implicito | `|ΔP_impl/ΔBTC|` | P_c, BTC | media |
| D3 | Inefficienza mercato | `P_impl − P_teorica` | tutti + calibr. | alta |
| E1 | Expected Value | `P_true×G − (1−P_true)` | P_true storico | alta |
| E2 | Kelly Fraction | `p − q/b` | P_true storico | alta |
| E3 | P-divergenza storica | `P_hist_bucket − P_impl` | 1000+ round | molto alta |

---

### 8. Priorità di validazione storica

Le raccomandazioni seguono il criterio: **massimo insight con meno dati e meno complessità**.

#### Priorità 1 (Immediata — 7 file disponibili)

**Curva G(sec)**: fitting della curva gain% media in funzione di sec su tutti i file disponibili.
Identificare il range di confidenza e gli outlier. Costruisce il riferimento base.

**Curva P_impl(sec)**: identica struttura su prezzo quote. Verifica l'ipotesi che
P_impl segua un percorso prevedibile avvicinandosi alla scadenza.

---

#### Priorità 2 (Breve termine — 98 file già disponibili)

**Cushion C(t) vs outcome**: per ogni secondo dei 98 file, calcolare C(t) e confrontarlo
con l'outcome del round. Obiettivo: verificare che C(t) > 1.5 a sec < 60 predica
l'outcome con accuratezza > 80%.

**σ_BTC(t,30) per fascia temporale**: distribuzione della volatilità locale per zona.
Identificare soglie "alta volatilità" vs "bassa volatilità" per ciascuna zona Z1–Z4.

**QR(t,30) vs outcome stability**: verificare se i round con alto QR a sec 200–100
hanno outcome più imprevedibile (e quindi se QR è utile come filtro di ingresso).

---

#### Priorità 3 (Medio termine — 1000+ file, ~3–4 giorni di raccolta a 288/giorno)

**P_hist per bucket (sec, C)**: costruire la tabella `P_win(sec_bucket, C_bucket)` empirica.
Griglia suggerita: 6 zone sec × 5 zone C = 30 celle, ~33 round per cella con 1000 round totali.

**Confronto P_hist vs P_impl**: questo è il test dell'inefficienza di mercato.
Se P_hist ≠ P_impl sistematicamente in certi bucket → edge reale identificato.

**σ_BTC vs G eccesso**: verificare se in round con σ_BTC alta il mercato
"sotto-prezza" il rischio (G troppo basso) o viceversa.

---

#### Priorità 4 (Lungo termine — 5000+ file, calibrazione completa)

**Modello opzione binaria calibrato**: stimare σ_implied(fascia_ora, giorno_sett.)
e costruire P_teorica(t) calibrata. Confronto sistematico con P_impl per zona temporale.

**Kelly positivo / P_div significativo**: con P_true stimata accuratamente,
calcolare EV e Kelly per ogni (sec, C) bucket. Identificare le celle con K > 0.
Queste definiscono le finestre di entrata con edge statistico reale.

**Strategia di hedge con round 15m/1h**: valutare correlazione tra round 5m consecutivi
e round 15m/1h per eventuali coperture della perdita attesa.

---

### 9. Raccomandazione operativa

**L'indice più urgente da implementare nel feed live è il Cushion `C(t)`**, perché:
1. È calcolabile in tempo reale senza dati storici (richiede solo BTC e Δ correnti)
2. Ha interpretazione diretta (sigma dal PTB)
3. È il predittore più diretto dell'outcome residuo
4. Ha la formula più semplice da scrivere nel codice di raccolta tick

In un secondo momento: aggiungere `σ_BTC(t,30)`, `QR(t,30)`, `CP(t,30)` nel file binario
come campi extra del tick, per poter fare validazione a posteriori su tutti i round già raccolti.

**Il vero edge** emergerà solo dalla tabella P_hist vs P_impl, che richiede i dati storici.
Gli indici A–C sono gli ingredienti per costruire quella tabella; D–E sono il suo utilizzo finale.

---

## Osservazioni finali

1. **Attenzione alla tautologia**: gain% e P_impl sono la stessa grandezza riformulata.
   Nessun segnale di trading emerge dalla loro analisi da soli. Il gain% è solo la "promessa"
   del mercato, non un'opportunità.

2. **La vera domanda** è: a ogni secondo `t`, con le condizioni osservate (sec, C, σ_BTC, QR...),
   qual è la **vera probabilità** di vincita? Se quella probabilità è diversa da P_impl,
   esiste edge. Tutto il lavoro analitico converge su questo punto.

3. **I file binari (.bin) con LOB completo** potrebbero aggiungere indici chiave:
   spread bid/ask, depth ratio, imbalance ordini. Da richiedere esplicitamente per
   la Priorità 3 se i risultati di C(t) e P_hist mostrano promessa.

4. **Nota sui round Down**: nei 7 file, 2 su 7 (28.6%) sono Down. La baseline conferma
   5 Up / 2 Down. La distribuzione storica reale su 98 file andrà verificata —
   un bias statistico nella raccolta dati o nel mercato stesso sarebbe importante da rilevare.
