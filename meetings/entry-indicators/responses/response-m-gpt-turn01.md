# Risposta m-gpt — turno 01

- **meeting-id**: entry-indicators
- **turno**: 01
- **agente**: m-gpt

## Punto 01

### Premessa ancorata alla baseline

La baseline fissa alcuni vincoli importanti: i file in `context/` sono 7 round `.txt`, tutti con 300 righe a 1 Hz, `sec` da 300 a 1, `fee_rate=0.07`, `gain%` gia' netto fee e calcolato sul lato majority, `delta` come distanza in dollari da `ptb_chainlink`, `quote` come majority side (`UP`, `DOWN`, `----` o lato parziale con prezzo mancante). Gli outcome sono 5 Up e 2 Down; il campione e' quindi utile per progettare gli indici, non per fissare soglie definitive.

La stessa baseline indica anche che in produzione esistono gia' 98 `.txt` e 98 `.bin`, e che il target operativo e' 288 round/giorno. Quindi gli indici sotto vanno pensati come feature riga-per-riga, poi calibrati su migliaia di round. I `.txt` bastano per timing, direzione, distanza da PTB, rendimento potenziale e validazione ex-post; i `.bin` con LOB completo servono invece per profondita', slippage, spread reale e fillability.

### Notazione comune

Per ogni riga `t` del round:

- `sec_t`: secondi residui alla scadenza.
- `side_t`: `+1` se `quote=UP`, `-1` se `quote=DOWN`, `0` se `quote=----`.
- `price_t`: prezzo della quota in centesimi / 100, quando presente.
- `gain_t`: `gain% / 100`, gia' netto fee.
- `delta_t`: BTC chainlink corrente meno PTB chainlink, arrotondato in dollari.
- `m_t = side_t * delta_t`: distanza allineata alla quote; positiva se il lato quotato e' anche il lato attualmente in vantaggio.
- `y_t`: a posteriori, `1` se `side_t` coincide con `outcome`, altrimenti `0`.
- `ret_t = y_t * gain_t - (1 - y_t)`: ritorno netto della puntata fatta in quella riga.

Per le righe `----` o con prezzo/gain mancante non conviene forzare una decisione direzionale: sono feature di instabilita' e liquidita', non segnali di ingresso diretti.

### Catalogo indici candidati

#### 1. Break-even probability ed edge empirico

Framework: betting odds, value betting, opzioni binarie.

Formula:

- `p_be_t = 1 / (1 + gain_t)`
- `p_hat_t = P(y=1 | sec_bin, m_bin, gain_bin, vol_bin, stability_bin, momentum_bin)`
- `edge_t = p_hat_t - p_be_t`
- `ev_t = p_hat_t * (1 + gain_t) - 1`

Interpretazione: `gain_t` dice quanto si vince se si ha ragione, ma da solo non dice se conviene entrare. La quota e' interessante solo quando la probabilita' empirica stimata `p_hat_t` supera la probabilita' di pareggio `p_be_t`. Questo e' il primo indice da validare perche' trasforma il problema in value betting misurabile.

Variazione riga per riga: a ogni secondo cambia `gain_t`, cambia il lato quotato, cambia `m_t` e quindi cambia sia `p_be_t` sia la cella statistica da cui stimare `p_hat_t`.

Aggregazione su molti round: raggruppare per `sec` o fasce temporali, bin di `m_t`, bin di `gain_t`, quote side, volatilita' recente e stabilita'. Per ogni cella calcolare `count`, `win_rate`, `avg_gain`, `avg_ret`, `median_ret`, drawdown e intervallo di confidenza. Una cella e' tradabile solo se ha edge positivo con campione sufficiente.

#### 2. Indice rischio/rendimento istantaneo

Framework: risk/reward trading, scommesse a quota variabile.

Definizioni:

- `risk_t = 1 - p_hat_t`
- `rr_t = risk_t / max(gain_t, epsilon)`
- `tension_t = gain_t * 4 * p_hat_t * (1 - p_hat_t)`
- `entry_score_t = ev_t / (1 + rr_t)`

`rr_t` e' un indice "meno e' meglio": misura quanta probabilita' di perdere si accetta per unita' di gain. `tension_t` e' invece coerente con l'esempio guida: alto significa contemporaneamente rendimento potenziale alto e incertezza alta; utile per classificare le zone, non per entrare automaticamente. `entry_score_t` e' la versione operativa: entrare solo se positivo e stabile.

Variazione riga per riga: all'inizio spesso `gain_t` e' alto ma `p_hat_t` dovrebbe essere poco discriminante; molto tardi `risk_t` scende ma anche `gain_t` collassa. L'obiettivo e' trovare la zona in cui `ev_t` resta positivo prima che il rendimento venga consumato.

Aggregazione: produrre curve per `sec`: media/percentili di `gain_t`, `risk_t`, `rr_t`, `ev_t`, piu' la quota di righe con `entry_score_t > 0`.

#### 3. Moneyness digitale: distanza normalizzata da PTB

Framework: opzioni digitali/binarie, distanza dallo strike.

Formula:

- `m_t = side_t * delta_t`
- `sigma_rem(sec) = std(final_delta - delta_t | sec)` stimata storicamente
- `z_t = m_t / sigma_rem(sec_t)`
- `p_model_t = Phi(z_t)` come baseline probabilistica grezza

Il PTB e' lo strike della scommessa. Una `quote=UP` con `delta=+40$` e una `quote=DOWN` con `delta=-40$` hanno entrambe `m_t=+40$`: sono entrambe "in the money" per il lato quotato. `z_t` rende confrontabili round con volatilita' diversa e tempi residui diversi.

Variazione riga per riga: se `m_t` cresce e `sec_t` scende, il lato quotato diventa piu' protetto; se `m_t` scende verso zero, il rischio gamma aumenta. Il dato va aggiornato ogni secondo, idealmente con finestre rolling di volatilita' recente.

Aggregazione: per ogni `sec` stimare la distribuzione storica di `final_delta - delta_t`, poi calibrare `P(outcome=side | z_bin, sec_bin)`. Il valore di `z` non va usato come soglia assoluta prima della calibrazione.

#### 4. Gamma proxy / rischio di attraversamento PTB

Framework: gamma delle opzioni digitali, boundary risk.

Formula operativa semplice:

- `gamma_proxy_t = exp(-0.5 * z_t^2) / max(sigma_rem(sec_t), epsilon)`
- alternativa POC: `boundary_risk_t = 1 / (1 + abs(m_t)) * sqrt(sec_t)`

Nelle opzioni digitali la sensibilita' massima e' vicino allo strike, cioe' quando `delta` e' vicino a zero. Qui significa che anche pochi dollari di BTC possono ribaltare il risultato. Un ingresso con gain alto ma `gamma_proxy` alto e' probabilmente una scommessa quasi casuale.

Variazione riga per riga: `gamma_proxy_t` dovrebbe esplodere quando il round resta vicino a PTB negli ultimi 60-120 secondi. Se il gain e' alto proprio perche' il mercato e' indeciso, l'indice evita di confondere payout alto con valore atteso positivo.

Aggregazione: misurare win rate e flip rate per bin di `gamma_proxy_t`; validare soglie del tipo "non entrare se gamma proxy nel quartile peggiore salvo edge empirico molto alto".

#### 5. Theta del gain: costo dell'attesa

Framework: theta/options decay, optimal stopping.

Formula:

- usando l'ordine cronologico `tau = 300 - sec`: `dgain_1s_t = gain_t - gain_{t-1}`
- `reward_decay_w_t = gain_t - gain_{t-w}`
- `wait_cost_t = max(0, gain_{t-1} - gain_t)`
- `risk_decay_t = risk_{t-1} - risk_t`
- `wait_efficiency_t = risk_decay_t / max(wait_cost_t, epsilon)`

L'idea e' misurare se aspettare un secondo compra abbastanza riduzione di rischio rispetto al rendimento perso. Se `wait_efficiency` e' alta, conviene aspettare; se e' bassa e `ev_t` e' gia' positivo, conviene entrare.

Variazione riga per riga: nei file di esempio si vede spesso che quando la quota va verso 97-99c il gain scende a 0.9-2.9%; il rischio puo' essere minore, ma il reward diventa quasi nullo. L'indice deve identificare il punto prima del collasso del gain.

Aggregazione: per ogni fascia `sec` calcolare la variazione media del gain nei successivi 1, 5, 10, 30 secondi e confrontarla con la riduzione osservata del loss rate.

#### 6. Stabilita' della quote e flip rate

Framework: market microstructure semplificata, hazard di reversal.

Formula su finestra `w` secondi:

- `same_side_ratio_w = count(side_i == side_t) / w`
- `flip_count_w = count(side_i != side_{i-1} and side_i != 0 and side_{i-1} != 0)`
- `no_quote_ratio_w = count(side_i == 0 or gain_i missing) / w`
- `stability_t = same_side_ratio_w * (1 - no_quote_ratio_w)`

Il campione mostra righe `----` e righe con `gain=---`, oltre a quote parziali negli ultimi secondi. Questo e' un segnale importante: non e' solo direzione, e' qualita' del mercato. Un lato che cambia spesso o passa da `UP` a `DOWN` negli ultimi secondi va trattato come fragile anche se il gain sembra alto.

Variazione riga per riga: aggiornare `stability_t` su finestre 5, 10, 30 secondi. Una possibile regola e' richiedere stabilita' crescente prima dell'entrata.

Aggregazione: per ogni `sec_bin` e `stability_bin`, misurare win rate e ritorno medio. Validare se `stability_t >= 0.7` o `>= 0.8` migliora l'EV.

#### 7. Momentum allineato e accelerazione

Framework: trend following, momentum intraday, drift vs noise.

Formula:

- `d_delta_w_t = delta_t - delta_{t-w}`
- `momentum_w_t = side_t * d_delta_w_t`
- `accel_w_t = momentum_w_t - momentum_w_{t-w}`

Se il lato quotato e' `UP`, momentum positivo significa BTC si allontana sopra PTB; se e' `DOWN`, momentum positivo significa BTC si allontana sotto PTB. Questo indice evita di comprare un lato solo perche' e' attualmente avanti, ma con movimento contrario.

Variazione riga per riga: calcolare finestre 5, 15, 30 secondi. Momentum breve positivo ma momentum 30s negativo segnala rimbalzo fragile; momentum multi-finestra positivo segnala conferma.

Aggregazione: stimare ritorno medio per combinazioni `m_bin x momentum_5 x momentum_30`. Il momentum non deve sostituire l'edge, ma filtrare le entrate.

#### 8. Volatilita' recente e whipsaw risk

Framework: realized volatility, noise filter.

Formula:

- `vol_w_t = std(diff(btc), window=w)`
- `whipsaw_t = vol_w_t / max(abs(m_t), 1)`
- `vol_regime_t = percentile(vol_w_t | sec_bin)`

Quando il prezzo BTC si muove molto rispetto alla distanza da PTB, la posizione e' vulnerabile a ribaltamenti. La volatilita' va normalizzata su `abs(m_t)`: 10 dollari di volatilita' sono poco se il lato e' avanti di 80 dollari, molto se e' avanti di 5.

Variazione riga per riga: `whipsaw_t` sale quando il prezzo resta vicino a PTB o quando arrivano movimenti rapidi. In quei momenti un gain alto puo' essere solo compensazione del rischio reale.

Aggregazione: validare filtri tipo `whipsaw_t < 0.5` o sotto il 60-esimo percentile della fascia temporale, sempre con campione sufficiente.

#### 9. Hazard di permanenza del lato vincente

Framework: survival analysis, hazard model.

Formula:

- stato: `alive_t = 1` se il lato corrente resta vincente fino a scadenza
- `hazard_t = P(side finale cambia | stato_t, sec_t, m_t, momentum_t, vol_t, stability_t)`
- `survival_t = product(1 - hazard_i)` fino alla scadenza

Questa e' una formulazione piu' robusta di `p_hat`: non chiede solo "vinco da qui?", ma "quanto e' probabile che il lato venga ribaltato prima della fine?". E' particolarmente adatta ai round 5m, dove il rischio principale e' un crossing del PTB negli ultimi secondi.

Variazione riga per riga: ogni secondo aggiorna l'hazard. Se `hazard_t` scende mentre `gain_t` e' ancora accettabile, nasce una finestra di entrata.

Aggregazione: costruire curve hazard per tempo residuo e stato. Utile per soglie temporali: ad esempio scoprire se tra 90 e 45 secondi l'hazard scende abbastanza da compensare la perdita di gain.

#### 10. Mispricing market-vs-history

Framework: calibrazione probabilistica, Brier/log loss.

Formula:

- `p_market_t` puo' essere approssimato da `p_be_t` o da `price_t`, ma va scelto e verificato.
- `mispricing_t = p_hat_t - p_market_t`
- `calibration_error = avg(y_t - p_market_t)` per bin
- `brier = avg((y_t - p_market_t)^2)`

Se il mercato e' ben calibrato, le quote Polymarket includono gia' il rischio. Il progetto cerca proprio eventuali zone in cui la calibrazione non e' perfetta: per esempio determinati secondi residui o combinazioni `delta/momentum` in cui il mercato paga troppo rispetto alla probabilita' storica.

Variazione riga per riga: il mispricing puo' aprirsi e chiudersi velocemente. Va loggato nel feed come feature, non solo calcolato a posteriori.

Aggregazione: tabelle di calibrazione per `sec_bin`, `price_bin`, `z_bin`, `stability_bin`; validare con split temporale, non random puro, per evitare leakage.

#### 11. Kelly frazionale e sizing della puntata

Framework: Kelly criterion, bankroll management per scommesse.

Formula:

- `b_t = gain_t`
- `kelly_t = (p_hat_t * b_t - (1 - p_hat_t)) / b_t`
- usare solo `kelly_t > 0`, poi frazione ridotta: `stake_fraction = 0.25 * kelly_t` o cap fisso.

Questo non sceglie il momento, ma trasforma l'indice di edge in dimensione della puntata. E' utile perche' evita di trattare tutte le entrate positive allo stesso modo. Nel progetto pero' va validato dopo aver stimato bene `p_hat_t`, altrimenti amplifica l'errore.

Variazione riga per riga: se il gain scende, a parita' di probabilita' il Kelly scende; se il rischio stimato scende piu' rapidamente del gain, puo' salire.

Aggregazione: simulare bankroll, max drawdown, ruin probability e distribuzione dei rendimenti per stake fisso, Kelly frazionale e stake cap.

#### 12. Indici LOB da richiedere ai `.bin`

Framework: microstructure, execution quality.

Questi non sono calcolabili dai `.txt` del contesto, ma la baseline dice che i `.bin` esistono e contengono LOB completo:

- `spread_t`: best ask - best bid sul lato da comprare.
- `depth_100_t`: size disponibile entro costo compatibile con puntata $100.
- `slippage_t`: differenza tra prezzo teorico e prezzo medio eseguito.
- `fillability_t`: indicatore di possibilita' di entrare realmente al gain mostrato.
- `lob_imbalance_t`: pressione bid/ask tra UP e DOWN.

Questi indici sono necessari prima di passare da backtest teorico a trading reale. Un edge positivo nei `.txt` puo' sparire se il LOB non consente fill o se lo slippage consuma il gain.

### Zone temporali iniziali da validare

Queste soglie sono ipotesi operative, non conclusioni statistiche:

- `sec 300-181`: zona ad alto gain e alta casualita'. Da usare per studio della calibrazione, non come prima zona di ingresso, salvo `edge_t` molto alto, `m_t` gia' significativo e momentum allineato.
- `sec 180-91`: zona probabilmente piu' interessante per il trade-off. Qui il campione mostra spesso gain ancora non collassato ma informazioni direzionali gia' piu' chiare. Prima candidata per validazione.
- `sec 90-31`: zona di conferma. Rischio inferiore, ma gain spesso molto basso; entrare solo se `ev_t` resta positivo e il gain non e' gia' sotto soglia minima.
- `sec 30-1`: zona problematica. Nei file compaiono spesso `gain=---`, prezzi 99-100c e persino gain negativi o nulli da saturazione/esecuzione. Da trattare piu' come zona di exit/no-trade o hedge che come ingresso primario, finche' non si usa il LOB.

Soglie iniziali ragionevoli da testare:

- escludere righe con `quote=----`, prezzo mancante o `gain` mancante;
- escludere prezzi `>= 99c` e `gain <= 1%` per strategie direzionali normali;
- richiedere `edge_t > 0` e preferibilmente `ev_t > 0.02` prima dei costi operativi;
- richiedere `stability_10 >= 0.7` o `stability_30 >= 0.7`;
- richiedere `m_t > 0` oppure `z_t > 0`, salvo strategie contrarian esplicitamente validate;
- penalizzare `gamma_proxy` alto e `whipsaw_t` alto;
- validare separatamente finestre `180-91` e `90-31`, perche' hanno profili rischio/rendimento diversi.

### Come scrivere gli indici nel feed tick-by-tick

Per ogni riga del feed futuro aggiungerei almeno:

- `aligned_delta = side * delta`
- `gain`
- `p_break_even`
- `vol_5`, `vol_15`, `vol_30`
- `momentum_5`, `momentum_15`, `momentum_30`
- `stability_10`, `stability_30`
- `no_quote_ratio_30`
- `whipsaw_15`
- `z_moneyness` quando `sigma_rem(sec)` e' calibrata
- `gamma_proxy`
- `p_hat`, `edge`, `ev`, dopo la prima fase di calibrazione storica
- `entry_score`

Gli indici calcolabili solo a posteriori (`p_hat`, `edge`, `ev`) diventano live appena esiste una tabella/modello addestrato sui round storici precedenti.

### Validazione statistica

La validazione va fatta con backtest walk-forward:

1. ordinare i round nel tempo;
2. usare una finestra storica per stimare `p_hat`, `sigma_rem`, soglie e calibrazione;
3. testare solo su round successivi;
4. ripetere avanzando la finestra;
5. confrontare entry fissa per fascia temporale, entry per `edge`, entry per `z`, entry con filtri momentum/stability, entry con LOB quando disponibile.

Metriche minime:

- ritorno medio per trade;
- win rate;
- profit factor;
- max drawdown;
- numero trade/giorno;
- EV per fascia `sec`;
- calibrazione `p_hat` vs outcome;
- sensitivity delle soglie;
- performance separata Up/Down;
- performance in round vicini a PTB vs round direzionali.

### Priorita' di validazione

1. **Edge empirico + break-even probability**: e' il nucleo del problema; senza edge positivo non c'e' strategia.
2. **Moneyness normalizzata `z_t` + gamma proxy**: porta nel sistema il concetto da opzioni digitali e standardizza la distanza da PTB rispetto al tempo residuo.
3. **Stability, flip rate e no-quote ratio**: nei file di esempio le quote instabili e mancanti sono frequenti abbastanza da dover diventare filtro primario.
4. **Momentum e whipsaw risk**: servono per distinguere vantaggio reale da oscillazione casuale intorno a PTB.
5. **Theta del gain / wait efficiency**: utile per scegliere il secondo preciso dentro una finestra gia' favorevole.
6. **LOB dagli `.bin`**: necessario prima di considerare eseguibile qualsiasi edge trovato sui `.txt`.
7. **Kelly frazionale**: solo dopo aver dimostrato calibrazione stabile di `p_hat`.

### Sintesi operativa

L'indice principale non dovrebbe essere un singolo rapporto `gain/rischio`, ma una piccola gerarchia: prima stimare `p_hat`, poi confrontarla con `p_be`, poi filtrare per moneyness, gamma, stabilita', momentum e liquidita'. La forma piu' compatta per decidere e':

`entry_score_t = ev_t * stability_t / (1 + gamma_proxy_t + whipsaw_t)`

con:

`ev_t = p_hat_t * (1 + gain_t) - 1`

Questo produce un catalogo standardizzato: il gain misura il premio, `p_hat/p_be` misura il valore, `z/gamma` misura il rischio da opzione digitale, `stability/flip/no_quote` misura affidabilita' del segnale, `theta` misura il costo dell'attesa. La prima validazione dovrebbe concentrarsi su `sec 180-91` e `sec 90-31`, evitando di ottimizzare troppo sui 7 file di esempio e usando i 288 round/giorno come base statistica reale.
