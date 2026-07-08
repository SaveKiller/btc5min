## Punto 01

Di seguito un catalogo strutturato di indici candidati per il timing di entrata nelle scommesse “BTC Up or Down 5m”. Ogni indice è calcolabile **a posteriori** sui file `.txt` a 1 Hz (colonne: `sec`, `quote`, `delta`, `gain%`, `btc`). Per ogni proposta vengono forniti: (1) framework teorico, (2) definizione operativa e formula, (3) comportamento riga per riga e modalità di aggregazione su molti round.

Le analisi sono ancorate ai fatti del file `baseline.md` (7 file di esempio, 300 righe ciascuno, fee 0.07, gain% 0–90%, quote 50–100 centesimi, delta da -60$ a +120$). Dove necessario per implementazioni più raffinate, si richiede esplicitamente l’accesso ai file `.bin` (LOB completo).

---

### 1. Indice di Rendimento/Rischio (RR Index)

- **Framework**: Teoria del portafoglio e trade‑off rischio‑rendimento. Si adatta al contesto binario: ogni secondo rappresenta una “posizione virtuale” con un rendimento potenziale (`gain%`) e un rischio associato alla probabilità di perdita.
- **Definizione operativa**:
  \[
  RR_t = \frac{\text{gain%}_t}{\sigma_{\text{loss}}}
  \]
  dove \(\sigma_{\text{loss}}\) è la deviazione standard dei `gain%` negativi (perdite) osservati su una finestra storica di \(N\) round allo stesso `sec`. In assenza di storici sufficienti, si usa una stima empirica: per esempio, su tutti i 7 file la perdita massima osservata è -99% (in realtà è un artefatto di prezzo >100c, ma può essere ignorato). Alternativa semplificata:
  \[
  RR_t = \frac{\text{gain%}_t}{1 - q_t}
  \]
  dove \(q_t\) è il prezzo della quota in frazione (es. 0.55 per 55c). Più alto è \(RR_t\), migliore è il rapporto rischio/rendimento.
- **Variazione riga per riga**: ad ogni secondo \(t\) (da 300 a 1) si calcola il valore istantaneo. Negli esempi, `gain%` è inversamente proporzionale al prezzo della quota; quindi \(RR_t\) tende a essere alto nelle fasi iniziali (gain% > 70%, quote basse) e basso verso la scadenza (gain% < 3%, quote vicine a 100c). Su round Down il comportamento è simmetrico (gain% riferito alla side vincente).
- **Aggregazione su molti round**: per ogni secondo si può calcolare la media e la deviazione standard di \(RR_t\) su tutti i round storici. Le soglie di ingresso (es. \(RR_t > 3\)) possono essere calibrate per massimizzare il gain atteso netto su un insieme di validazione.

---

### 2. Probabilità Implicita e Time Decay (IPTD)

- **Framework**: Teoria dei mercati predittivi e opzioni binarie. Il prezzo della quota (in centesimi) è direttamente la probabilità implicita che l’esito sia quello indicato dalla colonna `quote`. Confrontando questa probabilità con una **probabilità base** storica allo stesso `sec` si ottiene un indicatore di sovra/sotto‑prezzatura.
- **Definizione operativa**:
  \[
  \pi_t = \frac{\text{price\_cents}_t}{100}
  \]
  \[
  \text{IPTD}_t = \pi_t - \hat{p}_{\text{sec}}
  \]
  dove \(\hat{p}_{\text{sec}}\) è la probabilità storica che l’esito finale sia quello della `quote` attuale, data l’informazione disponibile al secondo \(t\). \(\hat{p}_{\text{sec}}\) si stima come frazione di round in cui la side finale era già corretta a quel secondo (sui dati storici). Un valore negativo di `IPTD` indica che la quota è **sottovalutata** (buona opportunità di entrata sul lato indicato).
- **Variazione riga per riga**: \(\pi_t\) oscilla tra 0.50 e 1.00 (o raramente oltre 1.00 nei file, dove compare “100c”). \(\hat{p}_{\text{sec}}\) tende a crescere verso la scadenza e a essere più stabile nelle fasi centrali. L’indicatore può passare da negativo a positivo durante ritracciamenti.
- **Aggregazione**: per ogni \(t\) si calcola la distribuzione di `IPTD` su migliaia di round. Le soglie (es. \(\text{IPTD} < -0.10\)) definiscono zone di ingresso favorevoli. La validazione si fa confrontando il gain% medio realizzato nelle entrate con soglia vs. casuali.

---

### 3. Distanza Normalizzata dal PTB (Normalized Delta, NΔ)

- **Framework**: Statistica e normalizzazione. `delta` è la distanza assoluta del BTC corrente dal PTB chainlink. La sua grandezza è poco informativa senza contesto di volatilità.
- **Definizione operativa**:
  \[
  NΔ_t = \frac{\text{delta}_t}{\text{std}(\text{delta})_{\text{sec}}}
  \]
  dove \(\text{std}(\text{delta})_{\text{sec}}\) è la deviazione standard di tutti i `delta` osservati allo stesso secondo \(t\) su un campione storico (almeno 100 round). In assenza, si può usare una finestra mobile intra‑round (es. ultimi 60 secondi).
- **Variazione riga per riga**: nei file visti, `delta` passa da +3$ a +120$ e da -60$ a +20$. Normalizzato, il valore segnala quanto il prezzo è lontano dalla media storica per quel secondo. \(NΔ > 2\) indica una distanza estrema (potenziale inversione).
- **Aggregazione**: su molti round si calcolano i percentili di \(NΔ\) e si associano a probabilità di vincita. Si possono definire zone “fredde” (NΔ vicino a 0) e “calde” (NΔ elevato). L’ingresso è consigliato quando il segno di \(NΔ\) è allineato all’esito finale (ma a posteriori si calibra).

---

### 4. Indice di Entropia / Incertezza (Entropy Index, EI)

- **Framework**: Teoria dell’informazione. L’incertezza sul risultato è massima quando la probabilità implicita è 0.5 (quote a 50c) e minima quando è prossima a 1 o 0.
- **Definizione operativa**:
  \[
  EI_t = -[\pi_t \log_2 \pi_t + (1-\pi_t) \log_2 (1-\pi_t)]
  \]
  dove \(\pi_t\) è la probabilità implicita dalla `quote` (side maggioritaria). Se `quote` è `----` si assume \(\pi_t = 0.5\) (entropia massima = 1). L’entropia è normalizzata tra 0 e 1.
- **Variazione riga per riga**: nei file, nei primi secondi l’entropia è spesso bassa (quote 51–55c), poi sale quando le quote si avvicinano a 50c (fasi di incertezza) e scende verso 0 a scadenza (quote 99c). L’indicatore segnala i momenti di maggiore confusione del mercato, potenzialmente favorevoli per entrate speculative early.
- **Aggregazione**: su tutti i round si costruisce la distribuzione di \(EI_t\) per ogni \(t\). Zone con \(EI > 0.9\) corrispondono a situazioni in cui il mercato è indeciso; storicamente, in tali frangenti la varianza del gain finale è maggiore. Può essere usato come filtro di rischio.

---

### 5. Volatilità Implicita dallo Spread (Richiede LOB)

- **Framework**: Trading di opzioni. La volatilità implicita si ricava dallo spread bid‑ask e dalla profondità del LOB. Disponibile solo dai file `.bin`.
- **Richiesta esplicita**: Per implementare questo indicatore servono i file `.bin` con l’order book completo (bid/ask per ogni secondo). Se approvato, si potrà calcolare:
  \[
  IV_t = f(\text{spread}_t, \text{depth}_t, \tau)
  \]
  dove \(\tau = \text{sec}/300\) è il tempo residuo normalizzato. Uno spread ampio segnala alta incertezza e potenziale elevato guadagno.
- **Nota**: Nei soli file `.txt` non è calcolabile. Viene menzionato come candidato futuro.

---

### 6. Indice di Momentum (MOM)

- **Framework**: Analisi tecnica. La variazione di `delta` (o del prezzo della quota) in una finestra breve cattura lo slancio del mercato.
- **Definizione operativa**:
  \[
  \text{MOM}_t = \text{delta}_t - \text{delta}_{t-5}
  \]
  (finestra di 5 secondi). Si può anche usare la differenza del prezzo della quota in centesimi.
- **Variazione riga per riga**: valori positivi indicano che il BTC si sta allontanando dal PTB nella direzione della side quotata; negativi indicano avvicinamento o inversione. Negli esempi, `MOM` ha picchi (es. +20$) durante i salti di prezzo.
- **Aggregazione**: si calcolano le correlazioni tra `MOM` e l’esito finale, e si definiscono soglie (es. `MOM > 5$`) che precedono di alcuni secondi un movimento decisivo.

---

### 7. Sharpe Ratio Istantaneo (ISR)

- **Framework**: Finanza quantitativa. Adattamento al contesto binario: il numeratore è il gain% atteso (differenza tra probabilità implicita e 1−π moltiplicata per 100?), il denominatore è la deviazione standard dei gain% su una finestra mobile intra‑round.
- **Definizione operativa**:
  \[
  \text{ISR}_t = \frac{\mathbb{E}[\text{gain}_t]}{\sigma_{\text{gain}}(w)}
  \]
  dove \(\mathbb{E}[\text{gain}_t] = (1 - 2\cdot\text{fee}) \cdot (2\pi_t - 1) \cdot 100\) (approssimazione lineare del payout netto fee) e \(\sigma_{\text{gain}}(w)\) è la deviazione standard dei `gain%` negli ultimi \(w\) secondi (es. 30).
- **Variazione riga per riga**: nelle fasi di trend stabile `ISR` è alto; nelle fasi di nervosismo si abbassa. Fornisce un segnale normalizzato che integra sia il rendimento che la volatilità recente.
- **Aggregazione**: su migliaia di round si calcolano i quantili di `ISR` per ogni sec e si identificano le regioni in cui lo Sharpe è superiore alla mediana storica.

---

### Raccomandazioni per la Validazione

1. **Priorità alta**: RR Index (indice 1) e `IPTD` (indice 2) – utilizzano solo dati `.txt` già disponibili e hanno interpretazione diretta. Calibrarli sui 98 file esistenti per trovare soglie empiriche.
2. **Priorità media**: Normalized Delta e Entropy Index – complementano gli indicatori precedenti e possono essere calcolati senza LOB.
3. **Priorità bassa (dipende da LOB)**: Volatilità implicita – richiedere i `.bin` una volta validati gli altri.
4. **Cross‑validazione**: per ogni indice, suddividere i round storici in training (70%) e test (30%). Misurare il gain medio e lo Sharpe delle entrate ipotetiche generate dalle soglie proposte, confrontandoli con entrate casuali o a tempo fisso.

Tutti gli indici proposti possono essere calcolati **secondo per secondo** e poi aggregati (media, dev.std, percentili) su finestre mobili o su interi round per calibrare le soglie decisionali. Il catalogo qui presentato costituisce la base per la successiva implementazione in pipeline e la scrittura di un report di validazione.