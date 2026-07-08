## Punto 01

### Analisi preliminare ancorata ai fatti (baseline.md)

Prima di proporre gli indici, riassumo i fatti oggettivi rilevanti estratti da `baseline.md` e confermati dai 7 file `.txt`:

**Struttura dati confermata:**
- 7 file, 300 righe ciascuno, `sec` da 300 → 1
- Campi per riga: `sec`, `time`, `quote` (UP/DOWN/----), prezzo in centesimi, `delta`, `gain%`, `btc`
- `fee_rate` = 0.07 su tutti i file
- `delta` = `round(chainlink_btc - ptb_chainlink)` in $ — **non** vs `ptb_price`
- `gain%` = ROI su $100 netto fee, lato majority
- `outcome` determinato da `final_price` vs `ptb_price` (non vs `ptb_chainlink`)
- 5 Up, 2 Down; `gain%` range 0–89.6%; righe `----` (probabilità pari) presenti in numero variabile (2–26 per file)
- File `.bin` con LOB completo esistenti ma non in contesto

**Discrepanza chiave osservata:** `ptb_price` ≠ `ptb_chainlink` in diversi file. Es. file `1783476900`: `ptb_price=62854.37`, `ptb_chainlink=62841.00` (Δ=13$). Questo significa che il `delta` mostrato non è la distanza dal prezzo che determina l'esito, ma da un riferimento diverso. Questa differenza è una fonte di informazione (o di rumore) da tenere conto.

---

### Catalogo di indici candidati per il timing di entrata

Propongo 10 indici, organizzati in 4 famiglie concettuali.

---

#### Famiglia A — Indici di valore/rendimento (analogo option pricing)

##### A1. Expected Value istantaneo (EV)

**Tecnica:** Valore atteso della scommessa al secondo *t*, calcolato come EV = p_win × payout − p_lose × stake. Il payout è implicito nel `gain%` e nel prezzo quote; la probabilità di vincita può essere stimata in due modi: (a) dal prezzo di quote stesso (implied probability), o (b) da una probabilità empirica calibrata su storico.

**Definizione operativa:**

```
quote_price(t) = prezzo in centesimi al secondo t (es. 53c → 0.53)
implied_prob(t) = quote_price(t) / 100
payout(t) = 1 / quote_price(t)            # multiplo su stake
gain_fraction(t) = gain%(t) / 100          # già netto fee

# EV usando implied probability (auto-referenziata, serve come sanity check):
EV_implied(t) = implied_prob(t) × (1 + gain_fraction(t)) − (1 − implied_prob(t))
             = implied_prob(t) × payout(t) − (1 − implied_prob(t))

# EV usando probabilità empirica calibrata:
EV_empirical(t) = p_emp(t, δ, σ) × (1 + gain_fraction(t)) − (1 − p_emp(t, δ, σ))
```

dove `p_emp(t, δ, σ)` è la frequenza storica di esito corretto per round con simile `sec`, `delta` e volatilità realizzata.

**Variazione riga per riga:** `quote_price` e `gain%` cambiano ogni secondo. All'inizio (sec 300) quote ≈ 50–55c, gain% ≈ 70–90%; verso la fine (sec 30–60) quote → 90–99c, gain% → 0.9–8%. L'EV_implied è teoricamente ≈ 0 se il mercato è efficiente, ma EV_empirical può essere positivo/negativo se c'è edge.

**Aggregazione su molti round:** Per ogni `sec` (o bucket di sec), calcolare la media di EV_empirical sui round storici. Il grafico EV medio vs `sec` rivela la zona temporale con EV positivo. Ipotesi: l'EV è massimo in una finestra intermedia (né troppo presto, né troppo tardi).

**Soglia proposta:** Entrare quando `EV_empirical(t) > threshold` (es. > 0.02, ovvero +2% atteso). Da calibrare su 288 round/giorno.

---

##### A2. Risk-Adjusted Gain Index (RAGI)

**Tecnica:** Rapporto tra rendimento potenziale e una misura di rischio. Ispirato al Sharpe ratio ma applicato al singolo round. Il rendimento è `gain%`; il rischio è stimato dalla volatilità realizzata del BTC nel round fino al secondo *t*.

**Definizione operativa:**

```
σ_realized(t) = stdev(btc[t-k : t])   # k=10 o 20 secondi, rolling
ragi(t) = gain_fraction(t) / (σ_realized(t) × sqrt(sec_remaining / 300))
```

Il termine `sqrt(sec_remaining / 300)` scala il rischio per il tempo residuo (analogo alla radice del tempo-to-maturity nelle opzioni). Con poco tempo residuo, anche un σ alto ha meno tempo di manifestarsi.

**Variazione riga per riga:** All'inizio (sec 300), gain% alto ma σ ha poco campione e tempo residuo massimo → RAGI moderato. A metà round, gain% medio e σ stabilizzato → RAGI può essere massimo. Alla fine, gain% → 0 → RAGI → 0.

**Aggregazione:** Calcolare RAGI medio per bucket di `sec` su tutti gli round. La curva RAGI vs sec identifica il punto ottimale medio di entrata. Da validare se il picco è stabile across round.

---

#### Famiglia B — Indici di probabilità/direzione (analogo delta delle opzioni)

##### B1. Adjusted Delta Distance (ADD)

**Tecnica:** Distanza normalizzata tra BTC corrente e PTB, corretta per la discrepanza `ptb_price` vs `ptb_chainlink`. È l'indicatore più direttamente legato all'esito.

**Definizione operativa:**

```
delta_true(t) = btc(t) − ptb_price           # distanza dal prezzo che determina esito
delta_shown(t) = btc(t) − ptb_chainlink       # come da file (campo delta)
ptb_gap = ptb_price − ptb_chainlink           # discrepanza fissa per round

add(t) = delta_true(t) / σ_5min_BTC           # normalizzazione per volatilità tipica
       = (delta_shown(t) + ptb_gap) / σ_5min_BTC
```

dove `σ_5min_BTC` è la deviazione standard storica del movimento di BTC in 5 minuti (es. $15–30, da calibrare).

**Variazione riga per riga:** `delta_shown` cambia ogni secondo col prezzo BTC; `ptb_gap` è costante per round. ADD positivo → favorevole a Up; negativo → favorevole a Down. |ADD| crescente nel tempo → esito sempre più determinato.

**Aggregazione:** Per ogni valore di ADD al secondo *t*, calcolare la frequenza storica di esito Up. Questo genera una curva di calibrazione `P(Up | ADD, sec)`. Da qui si deriva la probabilità empirica per l'EV (A1).

**Osservazione dai dati:** Nel file `1783476900` (Down), `ptb_gap = 62854.37 − 62841.00 = +13.37$`. Al sec 300, `delta_shown = +13$` ma `delta_true = 62854.36 − 62854.37 = −0.01$` → BTC è essenzialmente sul PTB. L'ADD usando `delta_shown` senza correzione sarebbe ingannevole.

---

##### B2. Quote-Implied Probability Gap (QIPG)

**Tecnica:** Differenza tra la probabilità implicita nel prezzo di quote e la probabilità empirica stimata dal delta/volatilità. Un gap positivo significa che il mercato sottostima la probabilità reale → opportunità di value bet.

**Definizione operativa:**

```
implied_prob(t) = quote_price(t) / 100        # 53c → 0.53
empirical_prob(t) = P(esito = quote_side | ADD(t), sec(t))   # da calibrazione storica
qipg(t) = empirical_prob(t) − implied_prob(t)
```

**Variazione riga per riga:** Quando BTC si muove decisamente in una direzione, `empirical_prob` sale ma il mercato (quote) potrebbe non aver ancora aggiornto → QIPG positivo. Quando il mercato ha già pricingato, QIPG → 0.

**Aggregazione:** QIPG medio per bucket sec. Se QIPG è sistematicamente positivo in certe zone temporali, c'è un edge exploitable. Da confrontare con la velocità di aggiornamento del LOB.

**Nota:** Richiede LOB per calcolare `implied_prob` con precisione (mid bid/ask). Dai file `.txt` si ha già il prezzo majority, sufficiente per una prima stima.

---

##### B3. Quote Stability Index (QSI)

**Tecnica:** Misura la stabilità della direzione majority (UP/DOWN) in una finestra rolling. Flip frequenti indicano incertezza → alto rischio; stabilità indica trend consolidato.

**Definizione operativa:**

```
# Per ogni secondo t, considera gli ultimi k secondi:
window = quote_side[t-k : t]           # sequenza di UP/DOWN/----
flips(t) = count di cambi UP→DOWN o DOWN→UP nella finestra
qsi(t) = 1 − flips(t) / k              # 1 = perfettamente stabile, 0 = caotico
```

**Variazione riga per riga:** All'inizio del round, flip frequenti (BTC vicino al PTB, direzione incerta) → QSI basso. Man mano che il trend si consolida, QSI → 1.

**Aggregazione:** QSI medio per bucket sec. Correlazione tra QSI al momento di entrata e probabilità di vincita. Ipotesi: entrare quando QSI > 0.7 (direzione stabile da ≥7 degli ultimi 10 secondi).

---

#### Famiglia C — Indici di momentum/volatilità

##### C1. BTC Velocity (VEL)

**Tecnica:** Velocità di variazione del prezzo BTC, come proxy di momentum direzionale.

**Definizione operativa:**

```
vel(t) = (btc(t) − btc(t−k)) / k          # $/sec, k=5 o 10
vel_normalized(t) = vel(t) / σ_5min_BTC    # normalizzato
```

**Variazione riga per riga:** VEL positiva → BTC sta salendo (favorevole a Up); negativa → sta scendendo. Può cambiare segno più volte nel round.

**Aggregazione:** Per round vinti, confrontare il segno e magnitudo di VEL al momento di entrata. Combinare con ADD: se ADD e VEL concordano (stessa direzione), maggiore confidenza.

---

##### C2. Realized Range Ratio (RRR)

**Tecnica:** Range realizzato del BTC nel round fino al secondo *t*, normalizzato per il range tipico atteso in 5 min. Indica se la volatilità è alta o bassa rispetto alla norma.

**Definizione operativa:**

```
range_so_far(t) = max(btc[300:t]) − min(btc[300:t])
expected_range_5min = valore storico (es. $40)
rrr(t) = range_so_far(t) / expected_range_5min
```

**Variazione riga per riga:** Cresce monotonicamente durante il round (il range può solo allargarsi). RRR > 1 → volatilità above average.

**Aggregazione:** RRR alto all'inizio del round + |ADD| alto → il movimento è già forte e potrebbe consolidarsi. RRR alto + ADD ≈ 0 → movimento ampio ma direzione incerta (whipsaw risk). Da combinare con QSI.

---

##### C3. Time-Decay Acceleration (TDA)

**Tecnica:** Analogico alla theta delle opzioni. Misura quanto rapidamente il gain% (potenziale rendimento) sta decadendo. Un TDA alto significa che si sta perdendo valore rapidamente aspettando.

**Definizione operativa:**

```
theta(t) = −d(gain%)/dt ≈ −(gain%(t) − gain%(t+k)) / k     # k=5 sec
# Oppure in termini di quote price:
theta_quote(t) = (quote_price(t−k) − quote_price(t)) / k    # $/sec di aumento quote
```

**Variazione riga per riga:** Theta è tipicamente basso all'inizio (gain% scende lentamente) e accelera verso la fine (gain% → 0 rapidamente quando quote → 99c). Il punto di flesso indica dove il decay inizia a superare il benefit dell'attesa.

**Aggregazione:** Curva media di theta vs sec su tutti i round. Il punto dove theta supera una soglia (es. 1%/sec) delimita il "deadline" per entrare con gain ancora significativo.

---

#### Famiglia D — Indici compositi di timing

##### D1. Entry Opportunity Score (EOS)

**Tecnica:** Indice composito che combina EV, stabilità direzionale, e tempo residuo in un singolo score. È l'indice "guida" richiesto dal meeting: alto = buona opportunità di entrata (gain ragionevole + rischio controllato).

**Definizione operativa:**

```
EOS(t) = w1 × EV_empirical(t)
       + w2 × QSI(t)
       + w3 × min(gain_fraction(t), g_max) / g_max
       − w4 × (1 − QSI(t)) × RRR(t)
       − w5 × max(0, −|ADD(t)| × penalty_near_zero)

# Pesi iniziali suggeriti:
w1=0.4, w2=0.2, w3=0.2, w4=0.1, w5=0.1
g_max = 0.5  # normalizza gain% al 50%
```

**Variazione riga per riga:** EOS è basso all'inizio (EV incerto, QSI basso), cresce quando direzione e delta si consolidano ma gain% è ancora alto, poi decresce quando gain% → 0. Il picco di EOS indica il momento ottimale di entrata.

**Aggregazione:** Per ogni round, identificare il sec con EOS massimo e verificare se l'esito è stato vincente. Confrontare la win-rate a diversi threshold di EOS.

---

##### D2. Z-Score Entry Signal (ZES)

**Tecnica:** Standardizzazione z-score del gain% condizionato al secondo, per identificare occasioni dove il gain è anomalo (più alto del normale per quel punto temporale).

**Definizione operativa:**

```
μ_gain(sec) = media storica di gain% a quel sec
σ_gain(sec) = deviazione standard storica di gain% a quel sec
zes(t) = (gain%(t) − μ_gain(sec(t))) / σ_gain(sec(t))
```

**Variazione riga per riga:** ZES > 0 → gain% sopra la media per quel secondo (mercado meno convinto della direzione → potenzialmente più profitto se si ha un edge direzionale). ZES < 0 → gain% sotto la media (mercato già convinto → meno opportunità).

**Aggregazione:** Combinare ZES con un segnale direzionale (ADD o VEL). Entrare quando: ZES > 1 (gain anomalo) AND |ADD| > threshold (direzione chiara). Questo identifica round dove il mercato sottostima una direzione forte.

---

### Standardizzazione dei concetti chiave

Dagli indici emergono i concetti richiesti:

| Concetto | Indice che lo cattura | Interpretazione |
|----------|----------------------|-----------------|
| Entrare troppo presto → rischio alto | QSI basso, RRR non stabilizzato, EV empirico incerto | Sec 300–240: direzione non consolidata, gain alto ma p_win ≈ 50% |
| Entrare troppo tardi → gain basso | TDA alto, gain% → 0, quote → 99c | Sec < 60: quasi certo ma rendimento ≤ 2% |
| Zona ottimale intermedia | EOS massimo, RAGI massimo | Sec ~120–200: gain 15–40%, direzione emergente |
| Value bet (mercato sbaglia) | QIPG > 0, ZES > 1 + ADD forte | Quota più alta del normale con direzione chiara |

### Ipotesi di zone temporali (da validare)

Basandomi sui 7 file di esempio, osservo pattern ricorrenti:

| Zona | Sec range | gain% tipico | Caratteristica |
|------|-----------|-------------|----------------|
| **Early** | 300–240 | 70–89% | Quote 50–56c, alta casualità, `----` frequente |
| **Mid-early** | 240–180 | 40–70% | Quote 56–70c, trend inizia a emergere |
| **Mid** | 180–120 | 20–50% | Quote 64–80c, direzione più chiara |
| **Mid-late** | 120–60 | 5–25% | Quote 80–95c, alta confidenza ma gain basso |
| **Late** | 60–1 | 0–5% | Quote 95–99c, quasi certo, gain marginale |

**Ipotesi iniziale:** la zona **Mid-early to Mid** (sec 240–120) offre il miglior trade-off rischio/rendimento, con EV potenzialmente positivo se si ha un edge direzionale (ADD + VEL concordanti).

### Raccomandazioni su quali validare per prime

**Priorità 1 (validare subito, basate solo su dati `.txt`):**
1. **ADD (B1)** — correzione delta per ptb_gap; è la base per ogni probabilità empirica
2. **QSI (B3)** — facile da calcolare, cattura stabilità direzionale
3. **TDA (C3)** — identifica il deadline temporale per entrare
4. **EV_empirical (A1)** — richiede calibrazione di p_emp(ADD, sec) ma è l'indice decisionale principale

**Priorità 2 (valide ma richiedono più dati):**
5. **RAGI (A2)** — richiede stima di σ_realized rolling
6. **EOS (D1)** — composito, va calibrato dopo aver validato i componenti
7. **ZES (D2)** — richiede sufficiente storico per μ/σ per secondo

**Priorità 3 (potenzialmente utili, richiedono LOB `.bin`):**
8. **QIPG (B2)** — migliorato con mid bid/ask reale dal LOB
9. **VEL (C1)** e **RRR (C2)** — utili ma secondari rispetto ad ADD

**Richiesta esplicita:** Per validare QIPG con precisione e per esplorare indicatori basati sulla profondità del book (bid-ask spread, volume imbalance, slippage reale), **richiedo l'accesso ai file `.bin`** con LOB completo per gli stessi 7 round di esempio.

### Deliverable summary

| Indice | Famiglia | Formula core | Input necessari | Output |
|--------|----------|-------------|-----------------|--------|
| EV | A | p × payout − (1−p) | gain%, quote_price, p_emp | valore atteso $ |
| RAGI | A | gain / (σ × √(sec/300)) | gain%, btc, sec | score rischio-rendimento |
| ADD | B | (delta + ptb_gap) / σ_5min | btc, ptb_price, ptb_chainlink | z-score direzionale |
| QIPG | B | p_emp − implied_prob | quote_price, ADD, sec | gap probabilità |
| QSI | B | 1 − flips/k | quote_side rolling | [0,1] stabilità |
| VEL | C | Δbtc / k | btc rolling | $/sec momentum |
| RRR | C | range / expected_range | btc, storico | ratio volatilità |
| TDA | C | −Δgain% / Δsec | gain% rolling | %/sec decay |
| EOS | D | combinazione pesata | tutti sopra | score composito |
| ZES | D | (gain − μ) / σ | gain%, storico per sec | z-score anomalia |

**Prossimo passo:** calcolare ADD, QSI, TDA ed EV empirico sui 98 file `.txt` disponibili in `data/txt/` per generare le prime curve di calibrazione `p_emp(ADD, sec)` e identificare le soglie operative.