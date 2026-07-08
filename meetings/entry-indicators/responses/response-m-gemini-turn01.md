# Risposta m-gemini — Turno 01

**Path confermato**: `f:\btc5min\meetings\entry-indicators\responses\response-m-gemini-turn01.md`
**Sintesi**: Ho analizzato il contesto (incluso `baseline.md` e i file `.txt` campionati a 1 Hz) per definire un catalogo di indici candidati per il timing di entrata ottimale nei round "BTC Up or Down 5m" su Polymarket.

---

## Punto 01: Catalogo Indici Candidati e Framework di Timing

Per massimizzare il guadagno atteso e minimizzare il rischio in un orizzonte di 5 minuti (300 secondi), propongo i seguenti indici basati su framework mutuati dal trading ad alta frequenza (HFT), dal pricing delle opzioni binarie e dall'analisi statistica.

### 1. Indice di Decadimento Temporale (Time-Decay o Theta Equivalente)
* **Framework teorico**: Nelle opzioni, il "Theta" misura la perdita di valore temporale. In Polymarket, il tempo residuo (`sec`) agisce in modo non lineare sulla probabilità di ribaltamento del risultato. Più ci si avvicina a `sec = 1`, minore è la probabilità che un `delta` (distanza dal PTB) venga colmato.
* **Formula operativa**: `TDI (Time-Decay Index) = |delta| / sqrt(sec)`
  *(Ispirato alla volatilità che scala con la radice quadrata del tempo)*
* **Dinamica secondo-per-secondo**: All'inizio (`sec` vicino a 300), il denominatore è grande, quindi il TDI è basso, indicando alta incertezza. Verso la fine (`sec` vicino a 1), se `|delta|` rimane costante, il TDI esplode, segnalando che il vantaggio è statisticamente "sicuro".
* **Aggregazione**: Su migliaia di round, si può mappare la distribuzione del TDI per ogni secondo e calcolare la percentuale di "ribaltamenti" (inversioni di `outcome`) per ogni decile di TDI.

### 2. Indice di Rendimento Aggiustato per il Rischio (Risk-Adjusted Gain Index - RAGI)
* **Framework teorico**: Basato sull'Indice di Sharpe o sul Criterio di Kelly. Valuta se il rendimento potenziale (`gain%`) giustifica il rischio di perdita totale, pesato per la probabilità implicita espressa dal mercato.
* **Formula operativa**: `RAGI = (gain% / 100) * Prob_Vittoria - (1 - Prob_Vittoria)`
  *Dove `Prob_Vittoria` può essere stimata dal prezzo delle quote (es. `prezzo_quote / 100` se normalizzato, oppure derivata dal `delta` storico).*
* **Dinamica secondo-per-secondo**: Il `gain%` tende a diminuire man mano che il `delta` si allarga a favore di una direzione e il tempo scade. Il RAGI fluttua: picchi positivi indicano inefficienze del mercato (quote che pagano troppo rispetto alla reale probabilità di vittoria in quel secondo).
* **Aggregazione**: Identificare i secondi esatti (es. tra `sec=120` e `sec=60`) in cui il RAGI medio storico è massimizzato prima che le quote crollino.

### 3. Indice di Inerzia del Prezzo (Price Momentum Index - PMI)
* **Framework teorico**: Micro-trend following. Il prezzo di BTC ha un'inerzia a brevissimo termine. Se il `delta` sta crescendo rapidamente nella direzione della scommessa, il rischio di un'inversione improvvisa è minore rispetto a un `delta` statico.
* **Formula operativa**: `PMI = (delta_t - delta_{t-k}) / k`
  *Dove `k` è una finestra temporale breve (es. 5 o 10 secondi).*
* **Dinamica secondo-per-secondo**: Un PMI positivo e crescente (concorde con la direzione della scommessa) indica un trend forte. Un PMI che rallenta suggerisce un possibile ritracciamento.
* **Aggregazione**: Calcolare la correlazione tra il PMI a `sec=150` e l'esito finale. Su 288 round giornalieri, si possono isolare i pattern di momentum che portano a vittorie sicure.

### 4. Indice di Disallineamento Quote-Delta (Quote-Delta Mispricing - QDM)
* **Framework teorico**: Arbitraggio statistico. Il mercato Polymarket (le quote) potrebbe reagire in ritardo rispetto ai movimenti reali del sottostante (il `delta` di BTC).
* **Formula operativa**: `QDM = | (prezzo_quote_implicito) - f(delta, sec) |`
  *Dove `f(delta, sec)` è un modello di probabilità empirica derivato dallo storico.*
* **Dinamica secondo-per-secondo**: Se il `delta` cambia improvvisamente ma il `quote` (e quindi il `gain%`) non si aggiorna istantaneamente (magari per mancanza di liquidità nel LOB), il QDM genera un segnale di entrata.
* **Aggregazione**: Analizzare i file storici per trovare la latenza media del mercato rispetto al chainlink e sfruttare i picchi di QDM.

---

## Raccomandazioni per la Validazione e Calibrazione

Essendo disponibili 288 file al giorno, la validazione deve essere rigorosa e data-driven:

1. **Matrice di Probabilità Empirica**: Usare lo storico per costruire una matrice 2D `(sec, delta)`. Per ogni cella, calcolare la percentuale di round che si sono conclusi con un `outcome` coerente col segno del `delta`. Questo fornirà la funzione `f(delta, sec)` reale, priva di assunzioni teoriche.
2. **Backtesting Soglie di Entrata**: Testare i 4 indici proposti simulando entrate fisse. Ad esempio: "Entra UP se `sec < 120`, `TDI > soglia_X` e `gain% > soglia_Y`". Calcolare il PnL netto (considerando le fee dello 0.07 già incluse nel `gain%`).
3. **Analisi dei Falsi Positivi (Ribaltamenti Tardivi)**: Isolare i round in cui un indicatore dava un segnale forte ma l'esito si è ribaltato negli ultimi secondi. Studiare se il `PMI` (momentum) avrebbe potuto prevedere l'inversione.
4. **Integrazione del LOB (File `.bin`)**: Sebbene non inclusi nel contesto attuale, i file binari saranno cruciali per validare la *fattibilità* dell'entrata. Un segnale perfetto è inutile se il LOB non ha liquidità sufficiente per assorbire la scommessa al prezzo desiderato.
