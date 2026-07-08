# Risposta m-grok — Turno 01 — meeting entry-indicators

## Punto 01

### Analisi del problema
I file `.txt` in `context/` mostrano campionamento 1 Hz (300 righe) di quote UP/DOWN su Polymarket BTC 5m. Ogni riga ha: `sec` (residuo), `quote` (prezzo centesimi), `delta` (distanza da ptb_price), `gain%` (netto fee), `btc`. Header contiene outcome noto a posteriori (Up/Down), ptb_price, fee_rate=0.07.

Obiettivo: indici calcolabili live (o a posteriori per training) che segnalino **momento ottimale di entrata** per massimizzare E[gain] - risk. Trade-off classico: entrata precoce → alta varianza/randomness; tardiva → bassa upside.

Contesto: 288 round/giorno, migliaia di file storici per statistiche, calibrazione soglie, validazione out-of-sample.

### Proposte di indici (tecniche, formule, per-secondo, aggregazione)

**1. Time Decay Index (TDI) — framework opzioni (theta-like) + betting urgency**
- Tecnica: analogia con theta decay opzioni; in scommesse, valore atteso decade con tempo residuo.
- Indice: `TDI(t) = gain%(t) * (sec(t) / 300) ^ alpha` con alpha=0.5 o 1 (da calibrare).
- Per riga: calcola su ogni sec; sale quando gain alto e tempo ancora sufficiente.
- Aggregazione: media TDI per bucket temporali (0-60s, 60-120s, ...); win-rate condizionato a TDI > threshold su N round; correlazione TDI vs |outcome - prediction|.

**2. Implied Probability Edge (IPE) — market efficiency / mispricing**
- Tecnica: da betting odds e statistica (Kelly, edge detection).
- Formula: `p_up = quote_up / 100`; `p_down = 1 - p_up`; `edge = |p_up - 0.5| - fee_adjust`; `IPE = edge * (1 - |delta| / ptb_range)`.
- Per riga: IPE alto indica quote "storta" rispetto delta BTC/PTB.
- Aggregazione: istogramma IPE vs frequenza vincita; threshold IPE > 0.08 su ultimi 50 round come trigger.

**3. Realized Volatility / Spread Volatility (RVS) — opzioni (vega) + risk management**
- Tecnica: vega exposure + risk of large moves near expiry.
- Indice: `RVS(t) = std( delta[t-30:t] ) / mean(gain%[t-30:t])` (finestra 30s rolling).
- Per riga: alto RVS = alta incertezza → posticipa entrata.
- Aggregazione: distribuzione RVS per esito (Up vs Down); zone temporali con RVS basso (es. sec 120-60) come sweet spot.

**4. Delta-Gain Momentum (DGM) — momentum trading + mean-reversion**
- Tecnica: technical analysis su LOB proxy (delta) e prezzo quote.
- Formula: `DGM(t) = (gain%(t) - gain%(t-5)) / |delta(t) - delta(t-5)|` (5s momentum).
- Per riga: segno positivo indica convergenza quote-delta favorevole.
- Aggregazione: hit-rate DGM > 0 su round storici; lag analysis (DGM anticipa inversioni quote?).

**5. Risk-Adjusted Entry Score (RAES) — Sharpe-like per trade singolo**
- Tecnica: risk-adjusted return (Sharpe / Sortino per scommesse).
- Formula: `RAES(t) = gain%(t) / (1 + |delta(t)| / ptb_price + 0.01 * (300 - sec(t)))`.
- Per riga: normalizza upside vs rischio (delta + time pressure).
- Aggregazione: ranking round per RAES massimo; curva equity simulata con entry a RAES > media storica.

**6. Zone Temporali Statistiche (ZTS) — clustering + regime detection**
- Tecnica: unsupervised (k-means su features) o supervised (decision tree su outcome).
- Indice: bucket fisso o dinamico: early (sec>240), mid (120-240), late (<120); o ML: probabilità vincita | sec, delta, gain%.
- Per riga: probabilità condizionale P(outcome=Up | sec, IPE, RVS).
- Aggregazione: tabella win-rate per zona su 1000+ round; calibration plot.

### Deliverable atteso — catalogo strutturato
- **Catalogo indici**: 6 proposti sopra, con formula esatta, pseudocode calcolo rolling, iperparametri (alpha, window).
- **Ipotesi soglie/zone**: TDI>0.4, IPE>0.08, RVS<1.2, RAES>1.5; zone mid (sec 180-90) prioritarie.
- **Raccomandazioni validazione**:
  1. Backtest su 5000 round: hit-rate, expectancy, max drawdown per indice.
  2. Correlazione indici (evitare multicollinearità).
  3. Live simulation: threshold trigger + position sizing (Kelly fraction).
  4. Feature importance: se si passa a modello ML (XGBoost/LightGBM) su features derivate.
- **Note file .bin**: per indici avanzati (order flow imbalance, microprice) richiedere LOB completo; qui basati solo su txt.

### Obiezioni / punti aperti
- I 7 file di esempio sono pochi per calibrazione; servono statistiche su migliaia di round.
- `outcome` noto solo post-facto: per live serve proxy (es. delta normalizzato).
- Fee_rate fisso 7% ma varia? Verificare.
- Interazione con 15m/1h round (cross-market hedge) non coperta qui — da Punto futuro.

Confermo path scritto: `f:\btc5min\meetings\entry-indicators\responses\response-m-grok-turn01.md`

Sintesi: catalogo 6 indici timing (TDI, IPE, RVS, DGM, RAES, ZTS) con formule per-secondo, tecniche da opzioni/betting, aggregazione storica e deliverable validazione su scala 288 round/giorno.