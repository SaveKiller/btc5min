# Report turno 01 — entry-indicators

- **generated_utc**: 2026-07-08T12:55:00Z
- **meeting-id**: entry-indicators
- **turno**: 01
- **participants**: m-composer, m-gpt, m-gemini, m-grok, m-sonnet, m-deepseek, m-glm, m-kimi, m-minimax
- **baseline**: `context/baseline.md`
- **input**: 9 risposte `response-m-*-turn01.md`

---

## Sintesi esecutiva

Il consenso tra i 9 partecipanti è netto: **il timing di entrata non si risolve guardando solo `gain%` o il prezzo quote**, perché entrambi sono la stessa informazione contabile (probabilità implicita + fee). Il vero problema è stimare **P(vittoria | stato al secondo t)** e confrontarla con la **probabilità di break-even** `p_be = 1/(1+g)`.

**Indice cardine per la decisione:** Expected Value `EV(t) = p_est(t)·g_t − (1−p_est(t))`, con `p_est` da:
- modello first-passage / survival (`p_surv`, Cushion `C(t)`, moneyness normalizzata), oppure
- tabelle empiriche `P_hist(sec, Δ, C, …)` su storico (98 file oggi, target 288/giorno).

**Filtri operativi condivisi:** escludere righe `quote=----`, flip frequenti, gain < 2% con quote > 95c, zone finali illiquide (sec < 30–60).

**Zona temporale candidata principale:** sec **120–240** (trade-off gain/rischio migliore); early (300–240) solo con segnali direzionali forti; late (< 60) quasi sempre a basso rendimento.

**Priorità validazione immediata (solo `.txt`):** EV + calibrazione `p_est`, stabilità quote (FI/QSI), allineamento delta (ADD/Cushion), backtest walk-forward sui **98 file** in `data/txt/`.

**Richiesta trasversale:** accesso ai **98 `.bin`** per spread, depth, slippage reale — edge sui `.txt` può sparire in esecuzione.

---

## Punto 01 — Catalogo indici e standardizzazione

### 1. Premessa condivisa (ancorata a baseline)

| Fatto | Valore (baseline) |
|-------|-------------------|
| Campionamento | 1 Hz, 300 righe/round, `sec` 300→1 |
| Campi per riga | `quote`, centesimi, `delta`, `gain%`, `btc` |
| `fee_rate` | 0.07 (tutti i 7 file contesto) |
| `gain%` | ROI netto fee su $100, lato majority (`market_buy_gain`) |
| `delta` | `round(btc − ptb_chainlink)` — **non** vs `ptb_price` |
| Outcome | vs `ptb_price` (5 Up, 2 Down nel campione) |
| Produzione | 98 `.txt` + 98 `.bin`; target 288 round/giorno |
| LOB | solo in `.bin`, non in context |

**Evidenza quantitativa (m-composer, sui 7 file):**
- `gain%` mediano: ~**76%** (sec 280–300) → ~**44%** (180–220) → ~**4%** (ultimi 30s)
- `|delta|`: mediana ~**4$** early → ~**38–41$** mid/late
- Flip UP↔DOWN: **0–16** per round; righe `----`: **2–26** per file

---

### 2. Standardizzazione concetti tempo / rischio / rendimento

Vocabolario unificato proposto (merge m-composer, m-gpt, m-kimi, m-sonnet):

| Simbolo | Nome | Definizione |
|---------|------|-------------|
| `τ` / `T` | Tempo residuo | `τ = sec`; `T = sec/300` |
| `g` / `G` | Rendimento potenziale | `g = gain%/100` |
| `c` / `p` | Prezzo / prob. implicita | `p = c/100` (lato majority) |
| `p_be` | Break-even | `p_be = 1/(1+g)` |
| `δ` / `Δ` | Distanza PTB | `delta` dal file ($ vs ptb_chainlink) |
| `p_est` | Prob. vittoria stimata | modello o tabella storica |
| **Edge** | Vantaggio | `p_est − p_be` (o `p_est − p`) |
| **EV** | Valore atteso | `p_est·g − (1−p_est)` |
| **Rischio** | Ribaltamento | flip, volatilità, vicinanza PTB, `----` |

**Trade-off standardizzato (5 zone — m-sonnet, m-glm, m-minimax):**

| Zona | sec | Gain tipico | Rischio | Strategia |
|------|-----|-------------|---------|-----------|
| Z1 Early | 300–240 | 70–89% | +++ | Solo con segnale forte (C, MOM, stabilità) |
| Z2 Mid-early | 240–180 | 40–70% | ++ | Zona candidata principale |
| Z3 Mid | 180–120 | 20–50% | + | Sweet spot EV + direzione |
| Z4 Late | 120–60 | 5–25% | basso | Solo se `p_est` >> `p_be` |
| Z5 Terminal | <60 | 0–5%, `---` | operativo | Evitare (gain marginale, LOB fragile) |

---

### 3. Insight critico — tautologia gain / probabilità

**Insight unico m-sonnet** (confermato da m-gpt, m-kimi): `gain%` e `P_impl = c/100` sono **algebraicamente equivalenti** (`G = (100/c − 1)×(1−fee)`). Analizzarli da soli **non produce edge** — descrivono solo il prezzo del mercato.

**Implicazione operativa:** il catalogo deve distinguere:
1. **Indici descrittivi** (G, p, θ) — utili per feed e visualizzazione
2. **Indici predittivi** (C, σ, MOM, FI) — stimano `p_est` indipendentemente dal prezzo
3. **Indici decisionali** (EV, Kelly, edge) — combinano `p_est` con `g`

---

### 4. Catalogo indici candidati (merge per famiglia)

#### Famiglia A — Rendimento e probabilità implicita (già nel feed)

| ID | Nome | Formula | Note |
|----|------|---------|------|
| A1 | Gain `G` | `gain%/100` | Necessario, non sufficiente |
| A2 | Prob. implicita `p` | `c/100` | Tautologico con A1 |
| A3 | Break-even `p_be` | `1/(1+g)` | Soglia minima probabilità |
| A4 | Risk/Reward grezzo | `g/(1−p)` o `1/g` | m-deepseek RR, m-kimi IND-09 |
| A5 | Reward/secondo `η` | `g/τ` | m-kimi ETA — urgenza temporale |

**Variazione riga-per-riga:** G e p decrescono verso scadenza; negli ultimi secondi possono comparire gain negativi o `---` (quote saturate).

**Aggregazione:** curve `μ_G(τ)`, `μ_p(τ)` per bucket sec su N round; scatter vs outcome.

---

#### Famiglia B — Moneyness, delta, allineamento PTB

| ID | Nome | Formula | Proponente |
|----|------|---------|------------|
| B1 | Delta grezzo `Δ` | `delta` dal file | tutti |
| B2 | **ADD** (delta corretto) | `(δ_shown + ptb_gap)/σ` con `ptb_gap = ptb_price − ptb_chainlink` | **m-glm** (unico) |
| B3 | **Cushion `C(t)`** | `sign(side)·Δ / σ_BTC(30)` | **m-sonnet** (priorità feed live) |
| B4 | Moneyness `Z` / `M` | `Δ/(σ·√τ)` o `Δ/σ_rem(τ)` | m-gpt, m-minimax B1, m-gemini TDI |
| B5 | TDI (time-decay) | `\|Δ\|/√sec` | m-gemini, m-grok |
| B6 | Allineamento DTE | `q·δ` o `z_δ = q·δ/σ` | m-kimi IND-03, m-gpt |
| B7 | Divergenza chainlink/mercato `D` | `p − p_chain` o disaccordo side | m-composer C2 |

**Insight unico m-glm:** in round come `1783476900`, `ptb_gap ≈ +13$` — `delta_shown` positivo ma BTC è sul PTB reale. **ADD corregge** questa discrepanza; senza correzione `p_est` è distorta.

**Variazione:** `|Δ|` cresce nel round; vicino PTB (C≈0) rischio massimo di reversal.

**Aggregazione:** `P(win | C, τ)`, matrice `(sec, Δ)` empirica (m-gemini, m-kimi).

---

#### Famiglia C — Volatilità, momentum, stabilità

| ID | Nome | Formula | Proponente |
|----|------|---------|------------|
| C1 | σ_BTC rolling | `std(btc, window w)` | m-sonnet B1, m-minimax B6 |
| C2 | σ_quote | `std(c, window w)` | m-sonnet B2 |
| C3 | MOM | `(btc_t − btc_{t−k})/k` allineato a side | tutti |
| C4 | Accelerazione | `MOM(t) − MOM(t+k)` | m-sonnet C2 |
| C5 | Whipsaw | `σ / max(|m|,1)` | m-gpt |
| C6 | **Flip Index FI** | flip cumulati UP↔DOWN | m-composer D1 |
| C7 | **Stabilità QSI** | `1 − flips/k` | m-glm B3, m-gpt stability |
| C8 | Ambiguity `A` | righe `----` | m-composer D2 |
| C9 | Confidenza feed `C` | `QI·exp(−Run/τ)` | m-minimax B7 |
| C10 | Entropia EI | `-p log p − (1−p)log(1−p)` | m-deepseek |

**Variazione:** FI monotono; σ e MOM oscillano; cluster `----` all'apertura o sui flip.

**Aggregazione:** win rate condizionato a FI≤θ, QSI>0.7; correlazione MOM con flip entro k sec.

---

#### Famiglia D — Opzioni / teoria probabilistica

| ID | Nome | Formula | Proponente |
|----|------|---------|------------|
| D1 | Theta `Θ` | `−Δg/Δsec` | m-composer F1, m-glm TDA, m-sonnet D1 |
| D2 | Gamma proxy | `exp(−z²/2)/σ` o `\|ΔP_impl/ΔBTC\|` | m-gpt, m-sonnet D2 |
| D3 | **Survival `p_surv`** | `Φ(q·δ / (σ·√τ))` | m-kimi IND-06 |
| D4 | Hazard | `P(flip finale \| stato, τ, …)` | m-gpt |
| D5 | IPTD / mispricing | `p − p̂_hist(sec)` | m-deepseek, m-grok IPE |
| D6 | Inefficienza | `P_impl − P_teorica(BS)` | m-sonnet D3 |
| D7 | Wait efficiency | `(Δrisk)/(Δgain perso)` | m-gpt |

**Insight m-sonnet:** il round è formalmente un'**opzione binaria** cash-or-nothing; Cushion ≈ d2 semplificato.

---

#### Famiglia E — Decisione / edge / sizing

| ID | Nome | Formula | Priorità |
|----|------|---------|----------|
| E1 | **EV** | `p_est·g − (1−p_est)` | **P0 — cardine** |
| E2 | Edge | `p_est − p_be` | P0 |
| E3 | Kelly | `(p·b − q)/b`, frazionale ¼K | P2 |
| E4 | RRR / GU | `g/(1+FI+A)`; `g/R_τ` | m-composer E1–E2 |
| E5 | Entry score | `ev·stability/(1+gamma+whipsaw)` | m-gpt |
| E6 | EOS / CPA / I(sec) | compositi pesati | m-glm D1, m-minimax B10 |
| E7 | EPR | expected profit per regola (sec*, soglia) | m-minimax B11 |
| E8 | ZES | z-score gain vs μ(sec) | m-glm D2 |

**Regola composita esempio (m-kimi):**
```
NO se c=50 (----), c>95 & g<2%, Risk > P90
EV = p_surv·g − (1−p_surv); ENTRY se EV > 0.05
```

---

#### Famiglia F — LOB / microstruttura (richiede `.bin`)

| Indice | Descrizione | Richiede |
|--------|-------------|----------|
| Spread | `(ask−bid)/mid` | `.bin` |
| Depth / imbalance | pressione bid/ask UP vs DOWN | `.bin` |
| Slippage / fillability | walk book reale vs gain% txt | `.bin` |
| IV da spread | volatilità implicita | `.bin` |

**Consenso:** validare prima indici A–E su `.txt`; poi affinare con LOB. **Richiesta esplicita** da m-glm, m-deepseek, m-minimax, m-kimi IND-13.

---

### 5. Ipotesi soglie e zone (da calibrare — non definitive)

| Parametro | Ipotesi iniziale | Fonte |
|-----------|------------------|-------|
| `FI_max` | ≤ 2 flip prima entrata | m-composer |
| `QSI_min` | ≥ 0.7 (10s window) | m-glm, m-gpt |
| `G_min` | ≥ 15% (mid) o ≥ 2% (late) | m-composer, m-kimi |
| `EV_min` | > 0.05 (5% edge) | m-kimi |
| `C_min` | > 1.5 per late entry | m-sonnet |
| `sec window` | ingresso 120–240 o 180–91 | maggioranza |
| Esclusioni | `----`, c≥99c, sec<30 | tutti |

---

### 6. Aggregazione su molti round — metodo condiviso

1. **Dataset flat:** una riga per (round, sec) con tutti gli indici + outcome
2. **Statistiche per bucket:** `(sec_bin, C_bin, p_bin, …)` → win_rate, mean(g), EV
3. **Walk-forward:** calibra su D, testa su D+1 (no random split puro)
4. **Metriche:** EV/trade, profit factor, max drawdown, trades/giorno, Brier/calibration
5. **Baseline:** entrata fissa sec=300 vs sec=60 vs random
6. **Output feed:** minimo `{G, Δ, C, σ, FI, EV}` quando `p_est` calibrato

---

### 7. Raccomandazioni validazione — priorità unificate

| Tier | Indici | Dati | Obiettivo |
|------|--------|------|-----------|
| **P0** | EV, p_be, FI/A/QSI, ADD/C, EWS griglia sec | 98 `.txt` | Curva gain, filtri, prima stima p_est |
| **P1** | p_surv/Cushion, MOM, D (divergenza), IPTD/mispricing | 98+ `.txt` | Calibrazione P_hist vs p |
| **P2** | Θ, Kelly, compositi (EOS, I(sec)), hazard | 500+ round | Affinamento timing intra-finestra |
| **P3** | Spread, depth, slippage | `.bin` | Eseguibilità reale |

**Timeline dati (m-sonnet):**
- 98 file: σ, C vs outcome, QR
- ~1000 file (~3–4 giorni @288/g): griglia P_hist(sec, C)
- 5000+ file: Kelly positivo, BS calibrato

---

### 8. Insight unici per partecipante

| Agente | Contributo distintivo |
|--------|----------------------|
| **m-sonnet** | Tautologia G↔P_impl; **Cushion C(t)** come indice live prioritario; P_div = P_hist − P_impl come edge reale |
| **m-glm** | **ADD** e ptb_gap: delta file ≠ distanza outcome; EOS composito; 10 indici strutturati |
| **m-composer** | Statistiche quantitative 7 file; vocabolario (T,G,Δ,p,R,EV); GU, EWS, griglia zone |
| **m-gpt** | Gerarchia p_hat→edge→filtri; hazard/survival; `entry_score = ev·stability/(1+gamma+whipsaw)` |
| **m-gemini** | TDI = \|Δ\|/√sec; matrice probabilità empirica (sec×delta) |
| **m-grok** | 6 indici compatti (TDI, IPE, RVS, DGM, RAES, ZTS) con soglie numeriche iniziali |
| **m-deepseek** | RR, IPTD, entropia EI, ISR (Sharpe istantaneo); split 70/30 |
| **m-kimi** | Catalogo IND-01…13; SURV first-passage; regola composita esplicita; tier validazione |
| **m-minimax** | B1–B11 + EPR; indice sintetico I(sec); piano aggregazione N×300; richieste formali meeting |

---

### 9. Dubbi aperti e rischi (merge)

1. **Campione:** 7 file insufficienti per soglie; 98 file ok per POC, migliaia per produzione
2. **ptb_price vs ptb_chainlink:** convenzione outcome vs delta — **ADD** necessario (m-glm)
3. **Look-ahead:** outcome solo per validazione, mai in indici live
4. **Gain negativo (-99%):** artefatti quote 100c / esecuzione — filtrare
5. **Efficienza mercato:** se p_est ≈ p sempre → EV ≈ 0; il progetto cerca **systematic mispricing**
6. **Cross-market 15m/1h:** non trattato — da meeting futuro (m-sonnet)
7. **fee_rate variabile?** da verificare su storico (m-grok)

---

### 10. Deliverable turno 01 — stato

| Deliverable | Stato |
|-------------|-------|
| Catalogo strutturato indici | ✅ ~40+ indici in 6 famiglie |
| Definizioni formali | ✅ formule operative per famiglia |
| Standardizzazione concetti | ✅ vocabolario + zone Z1–Z5 |
| Ipotesi soglie/zone | ✅ ipotesi iniziali (da calibrare) |
| Priorità validazione | ✅ tier P0–P3 |
| Richiesta `.bin` | ✅ esplicita da 4+ agenti |

**Prossimo passo operativo consigliato:** script backtest su 98 file → tabella `P(win | sec, ADD, C)` + curva EV per sec → conferma/refutazione zona 120–240.

---

## Riferimenti risposte agenti

- `responses/response-m-composer-turn01.md`
- `responses/response-m-gpt-turn01.md`
- `responses/response-m-gemini-turn01.md`
- `responses/response-m-grok-turn01.md`
- `responses/response-m-sonnet-turn01.md`
- `responses/response-m-deepseek-turn01.md`
- `responses/response-m-glm-turn01.md`
- `responses/response-m-kimi-turn01.md`
- `responses/response-m-minimax-turn01.md`
