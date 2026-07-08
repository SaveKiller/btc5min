# Risposta m-composer — turno 01

- **meeting-id**: entry-indicators
- **agent**: m-composer
- **turno**: 01
- **generated_utc**: 2026-07-08T12:50:00Z

---

## Punto 01 — Catalogo indici candidati per timing entrata

### Premessa metodologica (ancorata a baseline)

I dati disponibili senza LOB offrono, **ogni secondo** (`sec` 300→1), le colonne: `quote` (UP/DOWN/----), prezzo in centesimi, `delta` ($ vs `ptb_chainlink`), `gain%` (ROI netto fee su puntata $100 sul lato majority), `btc` (chainlink). L'header fornisce `outcome`, `fee_rate=0.07`, PTB e prezzo finale — utili solo per **validazione a posteriori**, non per decisione live.

Evidenze quantitative sui 7 file di contesto (baseline + analisi locale):

| Fenomeno | Evidenza |
|----------|----------|
| `gain%` decresce col tempo | mediana bucket early 280–300 s: **76,1%**; mid 180–220 s: **43,8%**; final 1–30 s: **4,4%** |
| Rischio reversal | flip UP↔DOWN: **0–16** per round; 2 round con **26** righe `----` ciascuno |
| `|delta|` cresce dopo l'apertura | mediana early: **4$**; mid/late: **38–41$** |
| Gain negativo possibile | es. `btc5m_1783479900.txt` sec 6: `gain=-99,0%` con quote DOWN 100c |
| Range `gain%` | **0,0–89,6%** (baseline); un round arriva a **-99%** negli ultimi secondi |

Obiettivo operativo: per ogni secondo `t` calcolare uno o più **indici scalari** `I(t)` tali che, fissata una regola di entrata `I(t) ∈ Zona_ok`, si massimizzi il rendimento atteso su **288 round/giorno** minimizzando drawdown e flip post-entrata.

---

### Standardizzazione concetti tempo / rischio / rendimento

Per rendere comparabili indici eterogenei e aggregabili su migliaia di round, propongo il seguente **vocabolario canonico**:

| Simbolo | Nome | Definizione operativa (da `.txt`) | Range tipico (7 file) |
|---------|------|-----------------------------------|------------------------|
| `T` | Tempo normalizzato | `T = sec / 300` ∈ (0,1]; `T=1` = apertura, `T→0` = scadenza | 1/300 … 1 |
| `τ` | Tempo residuo | `τ = sec` (secondi alla scadenza) | 300 … 1 |
| `G` | Rendimento potenziale | `G = gain% / 100` (frazione ROI su $100, fee incluse) | -0,99 … 0,896 |
| `p` | Probabilità implicita | `p = cents / 100` del lato `quote` (se UP/DOWN); con `----` → **indice non definito** | 0,50 … 1,00 |
| `Δ` | Moneyness (distanza PTB) | `Δ = delta` ($ arrotondato chainlink − PTB) | circa -50 … +50 osservato |
| `|Δ|` | Magnitudine distanza | valore assoluto di `Δ` | early ~4$, late ~40$ |
| `S` | Side mercato | `quote` ∈ {UP, DOWN, ----} | — |
| `S*` | Side chainlink | `UP` se `btc ≥ ptb_chainlink`, else `DOWN` | derivabile da riga |
| `W` | Esito round | `outcome` ∈ {Up, Down} — solo backtest | — |
| `win(t)` | Esito ipotetico entrata | 1 se `S(t)=W`, else 0 — validazione | — |
| `R(t)` | Rischio reversal | proxy: flip count cumulato, instabilità quote, o `|dΔ/dt|` | round-dipendente |
| `EV(t)` | Valore atteso | `EV = win_prob · G_win − (1−win_prob) · 1` (perdita ≈ stake) | da stimare |

**Assi concettuali del trade-off** (come richiesto dal meeting):

1. **Asse tempo (`T`)**: entrare presto (`T` alto) → `G` tipicamente alto (mediana 76% early) ma `win_prob` incerta e `R` elevato (flip, `----`).
2. **Asse rendimento (`G`)**: `G` decresce monotonicamente in media verso la scadenza; negli ultimi 30 s la mediana è ~4% — poco upside residuo.
3. **Asse rischio (`R`)**: cresce con instabilità quote e vicinanza a PTB (`|Δ|` piccolo); negli ultimi secondi il rischio **operativo** (spread, quote mancanti, gain negativo) domina quello statistico.

**Convenzione aggregazione multi-round**: per ogni indice `I` e ogni `τ` (o bucket di `τ`), calcolare su `N` round:

- `μ_I(τ) = mean(I(τ))`, `σ_I(τ) = std(I(τ))`
- `P(win|τ, I∈Z) = fraction(rounds con win(t)=1 | I(t)∈Z)`
- `E[G|τ, Z] = mean(G(τ) · win(t) − penalty_loss)` con penalty_loss = 1 (100% stake) se si perde
- **Curva Pareto**: `(E[profit], σ_profit, freq_trade)` per soglia `I > θ`

Tutti gli indici sotto rispettano: **una riga = un valore**; aggregazione = statistiche per `τ` o per bucket `(τ_lo, τ_hi)`.

---

### Catalogo strutturato — indici candidati

Organizzati per famiglia. Per ciascuno: framework, formula, variazione riga-per-riga, aggregazione.

---

#### A. Indici rendimento puro (già nel feed)

##### A1 — Gain Index `G`

| Campo | Valore |
|-------|--------|
| **Framework** | ROI market-buy sul LOB majority (`market_buy_gain`, `clob_api.py`) |
| **Formula** | `G(τ) = gain% / 100` |
| **Variazione per riga** | Oscilla con prezzo centesimi e profondità LOB; correlato inversamente a `p` quando il mercato è coerente. Nei 7 file: alto all'inizio (50–86c, G~70–80%), crolla sotto 60s se il vincitore è quasi certo (p→100c, G→0–5%). |
| **Aggregazione** | `μ_G(τ)`, percentili; scatter `G(τ)` vs `win(t)` per calibrare se esiste un `G_min` utile. |

**Nota**: indice **necessario ma non sufficiente** — alto G early coesiste con alto rischio di reversal (es. round Down con flip=16).

---

#### B. Indici moneyness / distanza PTB (stile opzioni)

##### B1 — Raw Delta `Δ`

| Campo | Valore |
|-------|--------|
| **Framework** | Moneyness assoluta (digital option / barrier-style) |
| **Formula** | `Δ(τ) = round(btc − ptb_chainlink)` |
| **Variazione per riga** | Parte spesso da 0$ all'apertura; cresce in modulo man mano che BTC si allontana da PTB. Nei 7 file mediana `|Δ|`: 4$ early → 38–41$ mid/late. |
| **Aggregazione** | Distribuzione `|Δ(τ)|` condizionata a `win(t)`; probabilità di reversal vs `|Δ|`. |

##### B2 — Normalized Moneyness `M`

| Campo | Valore |
|-------|--------|
| **Framework** | Opzioni binarie — distanza normalizzata al tempo residuo (scaling √τ o τ) |
| **Formula** | `M(τ) = Δ / max(|Δ|_rolling, ε)` oppure `M(τ) = Δ / σ_Δ(τ)` dove `σ_Δ(τ)` è std storica di Δ a quel τ su N round |
| **Variazione per riga** | Early: M piccolo (vicino PTB). Late: M grande se il round è “deciso”. Permette confronto tra round con volatilità diversa. |
| **Aggregazione** | `P(win | |M| > θ, τ)` per τ; curva θ vs accuracy. |

##### B3 — Delta Velocity `V_Δ`

| Campo | Valore |
|-------|--------|
| **Framework** | Derivata temporale (momentum BTC vs PTB) |
| **Formula** | `V_Δ(τ) = Δ(τ) − Δ(τ+1)` (sec decresce → differenza “verso futuro” nel round) |
| **Variazione per riga** | Picchi quando BTC si muove rapidamente; segnala ingressi “su breakout” o rischio flip imminente. |
| **Aggregazione** | `mean(|V_Δ|)` per bucket τ; correlazione con flip entro i prossimi k secondi. |

---

#### C. Indici probabilità / mispricing (stile scommesse)

##### C1 — Implied Probability `p`

| Campo | Valore |
|-------|--------|
| **Framework** | Probabilità implicita mercato (scommesse / prediction markets) |
| **Formula** | `p(τ) = cents / 100` se `quote ∈ {UP,DOWN}` |
| **Variazione per riga** | Early spesso 50–56c; late converge a 95–100c sul lato vincente. Con `----`: **NaN / skip**. |
| **Aggregazione** | Calibration plot: `p(τ)` vs frequenza empirica `win(t)` su N round (Brier score per τ). |

##### C2 — Chainlink-Market Divergence `D`

| Campo | Valore |
|-------|--------|
| **Framework** | Arbitraggio informativo — divergenza tra oracle e book |
| **Formula** | `D(τ) = p(τ) − p_chain(τ)` dove `p_chain = 0.5 + sign(Δ)·f(|Δ|)` o semplicemente indicatore `1{S(τ) ≠ S*(τ)}` (disaccordo binario) |
| **Variazione per riga** | Non zero quando quote majority ≠ side chainlink (es. round 1783481100: flip a DOWN con Δ negativo ma outcome Up). Segnala **mispricing** o lag del book. |
| **Aggregazione** | `E[G | D > θ]` vs `E[G | D ≈ 0]`; hit rate quando si entra sul lato chainlink contro il mercato. |

##### C3 — Expected Value Index `EV`

| Campo | Valore |
|-------|--------|
| **Framework** | Teoria giochi / scommesse — valore atteso scommessa |
| **Formula operativa (backtest)** | `EV(τ) = p̂(τ) · (1/p(τ) − 1) − (1 − p̂(τ))` dove `p̂` = probabilità empirica di vincita condizionata a `(τ, Δ, p)` stimata su storico; in live: `p̂ ≈ p_chain` o modello calibrato |
| **Semplificazione live** | `EV_simple(τ) = G(τ) · I{S=S*} − 1 · I{S≠S*}` (proxy: guadagni solo se allineati a chainlink) |
| **Variazione per riga** | Positivo quando G alto e side coerente con movimento BTC; negativo su flip. |
| **Aggregazione** | `sum(EV(τ_entry))` per strategia; Sharpe su serie 288/giorno. |

---

#### D. Indici rischio / instabilità

##### D1 — Quote Instability `FI` (Flip Index)

| Campo | Valore |
|-------|--------|
| **Framework** | Rischio regime-switching |
| **Formula** | `FI(τ) = count({s ≥ τ : S(s) ≠ S(s+1), entrambi ∈ {UP,DOWN}})` cumulato dall'inizio round |
| **Variazione per riga** | Monotono non-decrescente verso τ=1. Nei 7 file: 0 (round stabili) fino a 16 (round caotici). |
| **Aggregazione** | `P(flip dopo τ | FI(τ)=k)`; filtrare ingressi con `FI(τ) ≤ θ`. |

##### D2 — Ambiguity Index `A` (righe `----`)

| Campo | Valore |
|-------|--------|
| **Framework** | Incertezza mercato (probabilità 50/50) |
| **Formula** | `A(τ) = 1` se `quote=----`, else `0`; oppure `A_cum(τ) = count(---- fino a τ)/ (300−τ+1)` |
| **Variazione per riga** | Cluster all'apertura (1783481100: sec 300–299 ----) o durante flip. Baseline: 2–26 righe `----` per file. |
| **Aggregazione** | `% round con A(τ)=1` per τ; regola: **non entrare se A(τ)=1**. |

##### D3 — Time-Scaled Risk `R_τ`

| Campo | Valore |
|-------|--------|
| **Framework** | Rischio che cresce con tempo residuo e vicinanza PTB (concetto meeting) |
| **Formula** | `R_τ(τ) = (1 − T) · w₁ + (1 − |M(τ)|) · w₂ + FI(τ)/FI_max · w₃` (pesi da calibrare) |
| **Variazione per riga** | Alto early con |Δ| basso; alto late per componente `(1−T)` se non ancora “deciso”. |
| **Aggregazione** | Heatmap `(τ, R_τ)` vs win rate. |

---

#### E. Indici rischio/rendimento combinati (deliverable esemplare)

##### E1 — Risk-Reward Ratio `RRR`

| Campo | Valore |
|-------|--------|
| **Framework** | Finanza — rapporto rendimento/rischio per secondo |
| **Formula** | `RRR(τ) = G(τ) / max(R_τ(τ), ε)` |
| **Variazione per riga** | Alto quando G alto e R basso — “sweet spot”. Early può avere RRR alto ma R reale (flip) sottostimato se FI non incluso. |
| **Aggregazione** | Trovare `τ*` che massimizza `median(RRR)` su N round con vincolo `P(win)>π`. |

##### E2 — Gain-over-Uncertainty `GU`

| Campo | Valore |
|-------|--------|
| **Framework** | Information ratio semplificato |
| **Formula** | `GU(τ) = G(τ) / (1 + FI(τ) + A(τ))` |
| **Variazione per riga** | Penalizza gain alto ma in fase ambigua. Esempio: sec 243–240 in 1783476600 (----, G~89%) → GU ridotto. |
| **Aggregazione** | Ranking secondi per GU; frequenza segnali/giorno. |

##### E3 — Kelly Fraction Proxy `K`

| Campo | Valore |
|-------|--------|
| **Framework** | Criterio Kelly (scommesse) |
| **Formula** | `K(τ) = max(0, (p̂·b − q) / b)` con `b = (1/p − 1)` payoff netto, `q = 1−p̂`; in prima approssimazione `p̂ = p` → `K = (p·(1/p−1) − (1−p))/ (1/p−1)` semplifica ma va calibrato con `p̂` empirico |
| **Variazione per riga** | Alto solo con edge reale; ~0 quando p≈1 e G≈0. |
| **Aggregazione** | Fraction of bankroll suggerita; filtrare `K > K_min`. |

---

#### F. Indici temporali / zone di ingresso

##### F1 — Time Decay of Gain `dG/dτ`

| Campo | Valore |
|-------|--------|
| **Framework** | Theta (opzioni) — erosione rendimento |
| **Formula** | `Θ(τ) = G(τ) − G(τ+1)` |
| **Variazione per riga** | Negativo in fase di convergenza; picchi positivi su movimenti BTC. |
| **Aggregazione** | Identificare τ dove `Θ ≈ 0` (gain “stabile”) vs `Θ << 0` (fuga del rendimento). |

##### F2 — Entry Window Score `EWS(τ_lo, τ_hi)`

| Campo | Valore |
|-------|--------|
| **Framework** | Ottimizzazione intervallo temporale |
| **Formula** | `EWS = mean_{τ∈[τ_lo,τ_hi]} [ GU(τ) · I{condizioni_ok} ]` |
| **Variazione** | Non per-riga singola ma per **finestra** — utile per regole “entra tra 180s e 120s”. |
| **Aggregazione** | Grid search su (τ_lo, τ_hi) su 98+ file → heatmap profit. |

##### F3 — Late-Entry Penalty `L`

| Campo | Valore |
|-------|--------|
| **Framework** | Costo opportunità / rischio operativo |
| **Formula** | `L(τ) = max(0, τ_target − τ)` oppure `L = G_early_max − G(τ)` (gain perso aspettando) |
| **Variazione per riga** | Cresce aspettando oltre il sweet spot. |
| **Aggregazione** | Bilanciare con RRR per trovare τ ottimo. |

---

#### G. Indici che richiedono LOB (`.bin`) — da richiedere esplicitamente

| Indice | Formula | Motivo LOB |
|--------|---------|------------|
| **Spread Index** | `(ask − bid) / mid` per lato majority | Spread non nel `.txt` |
| **Depth-Adjusted Gain** | `G` ricalcolato con `BET_USD` variabile vs profondità | Slippage reale oltre walk $100 |
| **Order Imbalance** | `(bid_size − ask_size) / (bid_size + ask_size)` | Segnale microstruttura |
| **Quote Staleness** | secondi dall'ultimo aggiornamento book | Lag vs chainlink |

Il manifest conferma: `.bin` in `data/bin/` ma non in context. Proposta: validare prima gli indici A–F su `.txt`, poi estendere con LOB per affinare `G` e spread.

---

### Ipotesi di soglie e zone temporali (da validare su storico)

| Zona | τ (sec) | T | Comportamento osservato (7 file) | Ipotesi operativa |
|------|---------|---|----------------------------------|-------------------|
| **Apertura** | 300–260 | 1,0–0,87 | G alto (med ~76%), |Δ| basso, possibili `----` | Solo se `FI=0` e `|Δ|>θ_Δ` dopo stabilizzazione |
| **Mid-round** | 259–120 | 0,86–0,40 | G medio (~44%), |Δ| cresce, flip possibili | Zona candidata principale per `GU` / `RRR` |
| **Pre-chiusura** | 119–60 | 0,40–0,20 | G in calo, direzione spesso chiara | Entrata “conviction” se `p>0.85` e `S=S*` |
| **Finale** | 59–1 | 0,20–0 | G basso (med ~4%), rischio quote rotte / gain negativo | **Evitare** salvo eccezioni `EV` alto; es. -99% gain sec 6 |

Soglie iniziali (da calibrare su ≥98 file, target 288/g):

- `FI_max = 2` (max 2 flip prima dell'entrata)
- `A(τ) = 0` (no ambiguità)
- `G_min = 0,15` (15% ROI minimo)
- `|Δ|_min`: da derivare come percentile 25 di |Δ| su round vincenti a τ dato

---

### Raccomandazioni — ordine di validazione su dati storici

Priorità basata su: (1) calcolabilità immediata da `.txt`; (2) potere discriminante osservato nei 7 file; (3) costo implementazione nel feed tick-by-tick.

| Priorità | Indice | Motivazione |
|----------|--------|-------------|
| **P0** | `G`, `GU`, `FI`, `A` | `G` già nel feed; `GU`/`FI`/`A` catturano il trade-off rendimento/instabilità evidente nei round con 16 flip e cluster `----` |
| **P0** | `EWS` su griglia τ | Risponde direttamente alla domanda “quando entrare”; su 98 file già disponibili |
| **P1** | `Δ`, `M`, `V_Δ` | Moneyness core per mercato “BTC vs PTB”; |Δ| passa da 4$ a 40$ — segnale forte |
| **P1** | `D` (divergenza chainlink/market) | Round 1783481100 mostra flip con outcome Up — edge potenziale |
| **P1** | `EV_simple` / calibration `p` vs `win` | Fondamento statistico su 288/giorno |
| **P2** | `RRR`, `K`, `Θ` | Affinamento dopo P0/P1; richiedono calibrazione pesi |
| **P3** | Spread, depth, imbalance | Richiedono `.bin`; utile per ultimi 60s dove gain% collassa e LOB fragile |

**Protocollo di validazione suggerito** (288 round/giorno):

1. **Parse batch** di tutti i `.txt` in `data/txt/` (98+ ora, migliaia poi).
2. Per ogni `(τ, indice I)`: calcolare `μ_I`, `P(win)`, `E[profit]` con entrata simulata a τ se `I∈Z`.
3. **Walk-forward**: calibrare soglie su giorno D, testare su D+1 (evitare overfit su 7 file).
4. **Metriche successo**: profit factor, max drawdown, trades/day, % round skipped (no signal).
5. **Output feed**: per ogni tick scrivere almeno `{G, FI, A, GU, Δ, D}` — estendibile.

---

### Obiezioni e limiti (onestà metodologica)

1. **7 file non bastano** per soglie definitive — le medie citate sono illustrative; la baseline indica 98 file in repo e 288/g target.
2. **`gain%` su majority side** non è il gain del **miglior** lato — se chainlink diverge, il gain mostrato può essere fuorviante (`D` mitiga).
3. **Look-ahead bias**: `outcome` e talvolta `final_price` non devono entrare in indici live.
4. **Gain negativo** (-99%) indica che il modello di costo a sec→0 non è banale — filtrare `p < 1` e quote valide.
5. **Senza LOB** non modelliamo slippage reale oltre il walk $100 già in `gain%`.

---

### Sintesi operativa

Il catalogo propone **15+ indici** raggruppati in 7 famiglie, con standardizzazione `(T, G, Δ, p, R, EV)`. Il trade-off tempo/rischio/rendimento emerso dai dati è netto: **G alto early, R alto (flip/----); G basso late, R operativo alto**. Per validazione immediata su storico: **`GU`, `FI`, `A`, finestra `EWS`, `Δ`/`D`** — tutti derivabili dai `.txt` esistenti senza LOB.
