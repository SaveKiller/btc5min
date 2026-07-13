# DWinA vs DWinB — guida alla scelta

Documento dedicato al confronto tra le due colonne **delta_win v2** nei feed `.txt` dei round BTC Up or Down 5m. Per la specifica tecnica dell’artifact e i comandi di fit/backfill vedi [`indicator_delta_win.md`](indicator_delta_win.md).

---

## Cosa misurano (in comune)

Entrambe stimano la **probabilità che il lato indicato dal segno del delta** vinca l’**outcome ufficiale Gamma** a settlement:

| Segno delta | Lato predetto |
|-------------|---------------|
| `delta ≥ 0` | **Up** |
| `delta < 0`  | **Down** |

Regole condivise:

- **Non** è la quota CLOB del lato maggioritario (`quote` / `gain%`): delta_win parla del lato “fisico” (Chainlink vs PTB), non del consenso di mercato.
- **Intervallo attivo:** da `delta_win_sec_start` a `delta_win_sec_end` inclusi, ogni secondo (default **240 → 5** in `setup.json`). Sopra `sec_start` le colonne sono vuote (solo spazi).
- **Label di training:** su round Lighter sintetici, `y_win = 1` se quel lato coincide con `outcome` Gamma; round con `outcome_agreement: nan` esclusi.
- **Eleggibilità runtime** (gate identico per A e B): delta non stale, tutte le finestre di volatilità `V30`–`V120` calcolabili, nessun tick Chainlink stale nella finestra `V120` trailing sul checkpoint. Se il gate fallisce → `---` in entrambe le colonne.
- **Artifact:** `models/delta_win_v2.json` (versione 2), con hash `hour_bands` e intervallo `sec` allineati a `setup.json`.

---

## DWinA — pool empirico per fascia H

**Nome artifact:** `delta_band_lookup`  
**Idea:** “Negli round passati, in questa fascia oraria **H**, a questo secondo **sec**, con un delta di questa grandezza, quanto spesso il lato delta ha vinto?”

### Calcolo al fit (`study_delta_win_v2.py`)

Per ogni combinazione **(H, sec, center_d)** con `H ∈ {1…6}`, `sec` nell’intervallo configurato, `center_d ∈ {0…150}`:

1. Si prendono tutti i campioni di training Lighter con stessa `intraday_h`, stesso `sec`, e `|delta|` nella finestra fissa  
   `[center_d − half_base, center_d + half_base]` clampata a `0…150`  
   (`half_base` = `delta_win_window_half_base`, default **2** → finestra ±2 USD implicita).
2. `n` = numero di campioni nel pool.
3. Se `n ≥ delta_win_window_min_samples` (default **30**):  
   `p_win = media(y_win)` sul pool.  
   Lo slot viene salvato in `delta_window_by_sec_h[H][sec][center_d]` con `{p_win, n, lo, hi, half}`.
4. Se `n > 0` ma sotto soglia: lo slot esiste ma **senza** `p_win` (runtime mostra solo `[n=N*]`).
5. Se `n = 0`: nessuno slot → runtime `---`.

La stratificazione per **H** (fascia oraria da `hour_bands.json`, vedi [`indicatorH.md`](indicatorH.md)) è parte del modello: lo stesso `|delta|` e `sec` in H2 vs H6 possono avere `p_win` diversi perché il regime di volatilità atteso differisce.

### Calcolo al runtime (feed reale o Lighter)

1. `H` da header `intraday: Hk` o `hour_band(market_start_ts)`.
2. `d = min(|delta|, 150)` (clamp).
3. Lookup `delta_window_by_sec_h[H][sec][d]`.
4. Formattazione cella:
   - `87% [n=39]` — `p_win` arrotondato a intero % + dimensione pool reale.
   - `    [n=29*]` — pool presente ma `n` sotto soglia: **nessuna %** (spazi al posto del numero), asterisco = campioni insufficienti.
   - `---` — nessun dato storico per quella cella.

### Cosa **non** usa DWinA

- Le colonne `V30`–`V120` del round corrente (servono solo al gate di eleggibilità, non entrano nella formula).
- La quota CLOB o il book.

---

## DWinB — regressione logistica + calibrazione isotonica

**Nome artifact:** `logistic_isotonic`  
**Idea:** “A questo **sec**, data la grandezza del delta **e** quanto BTC si è mosso di recente (**vol**), e in quale fascia **H** siamo, qual è la probabilità calibrata di vittoria del lato delta?”

### Calcolo al fit

Per ogni `sec` nell’intervallo, un modello separato su **tutti** i campioni di training (tutte le H insieme):

**Feature** (vettore per ogni campione):

| Feature | Trasformazione |
|---------|----------------|
| `\|delta\|` | `log1p(|delta|)` |
| `V30`, `V60`, `V90`, `V120` | `log1p(vol)` per ciascuna finestra |
| Fascia H | one-hot su H1…H6 |

Pipeline per `sec`:

1. `LogisticRegression` su train.
2. Probabilità grezze sul train dello stesso `sec`.
3. `IsotonicRegression` per calibrare le probabilità (curve `iso_x` / `iso_y` nell’artifact).

### Calcolo al runtime

Al momento del feed **non c’è più apprendimento**: si applica una formula deterministica con i coefficienti già salvati in `models/delta_win_v2.json` (implementazione in `src/delta_win.py` → `predict_delta_win_b`).

1. Si costruisce il vettore feature dal round corrente (`|delta|`, vols arrotondate, H).
2. **Combinazione lineare** con i pesi appresi al fit:  
   `x = β₀ + β₁·log1p(|delta|) + β₂·log1p(V30) + … + β₆·one_hot(H)`  
   (prodotto scalare tra feature e `coef` + `intercept` dell’artifact).
3. **Sigmoide:** `p_raw = 1 / (1 + e^(−x))` → numero tra 0 e 1.
4. **Calibrazione isotonica:** interpolazione lineare di `p_raw` sulla curva fissa `iso_x` → `iso_y` (stessi nodi salvati al fit per quel `sec`).
5. Formattazione: `round(p_win × 100)%` (intero) oppure `---` se manca vol o delta stale.

Stessi input → stessa percentuale, sempre.

### È machine learning? Random Forest? Chi “sceglie” la %?

| Domanda | Risposta |
|---------|----------|
| È machine learning? | **Sì**, supervised learning classico: classificazione binaria (il lato delta vince / non vince) addestrata su round Lighter storici. |
| È Random Forest? | **No**. Al fit si usa `LogisticRegression` di scikit-learn (`scripts/study_delta_win_v2.py`). |
| La % viene scelta da un processo inferenziale? | **No** in senso “decisionale”. Al runtime non c’è ragionamento sul round: solo applicazione di pesi fissi e curve di calibrazione. |
| È un calcolo matematico preciso? | **Sì** al runtime: prodotto scalare + sigmoide + interpolazione su curva pre-calcolata. |

**Due fasi distinte:**

| Fase | Cosa succede |
|------|----------------|
| **Training (offline)** | Per ogni `sec`, `LogisticRegression.fit` su feature + label `y_win`; poi `IsotonicRegression` sulle probabilità grezze del train. Output: `coef`, `intercept`, `iso_x`, `iso_y` nell’artifact. |
| **Runtime (ogni tick)** | Lookup del blocco `logistic_by_sec[sec]` e formula sopra. Nessun aggiornamento dei pesi, nessuna scelta discreta tra percentuali predefinite. |

La calibrazione isotonica **non** aggiunge nuove feature: riallinea le probabilità grezze del logistico ai win rate osservati sul train (per quel `sec`), così che una stima “80%” significhi circa 80% di vittorie sul campione di addestramento a parità di score.

**Confronto con DWinA su questo punto:** DWinA **non** è ML — è statistica descrittiva (media del win rate in un bucket). DWinB **sì** è ML, ma al feed è un **calcolatore deterministico** con parametri congelati.

### Cosa aggiunge rispetto ad A

- **Volatilità intra-round** (trailing, live-safe): due round con stesso `sec`, stesso `|delta|`, stessa H ma V60 diversa possono avere DWinB diversa.
- **Smoothing implicito** via modello parametrico: non dipende da un singolo bucket empirico stretto.

---

## Confronto sintetico

| Aspetto | DWinA | DWinB |
|---------|-------|-------|
| Tipo | Lookup empirico | Modello parametrico + calibrazione |
| Machine learning | No (media su pool storico) | Sì (logistic + isotonic); **non** Random Forest |
| Runtime | Tabella precalcolata | Formula fissa (sigmoide + interpolazione) |
| Input principali | `sec`, `\|delta\|`, **H** | `sec`, `\|delta\|`, **V30–V120**, **H** |
| Trasparenza | Mostra `[n=N]` del pool | Solo % |
| Copertura dati scarsi | `---` o `[n=N*]` | Di solito sempre una % se eleggibile |
| Sensibilità al regime orario | Esplicita (tabelle separate per H) | H come feature, pool condiviso per sec |
| Sensibilità alla vol corrente | No | Sì |
| Variazione secondo-per-secondo | Può “saltare” tra sec adiacenti (tabelle diverse) | Più continua tra sec (modelli correlati) |

---

## Punti di forza e di debolezza

### DWinA

**Punti di forza**

- **Interpretabilità diretta:** la % è il win rate storico osservato nel pool, non un’estrapolazione.
- **Controllo della fiducia:** `[n=N]` dice subito quanti casi supportano la stima; `[n=N*]` segnala esplicitamente dati insufficienti.
- **Regime orario:** tabelle per H catturano che “+40$ a sec=90” non significa la stessa cosa nel weekend calmo (H1) e nel picco US/EU (H6).
- **Robustezza locale:** dove il pool è grande, la stima non dipende da ipotesi di forma funzionale.

**Punti deboli**

- **Granularità:** finestre ±2 su `|delta|` possono essere rumorose dove i dati sono pochi (H6, sec estremi, delta rari).
- **Buchi di copertura:** più `---` e `*` in fasce H con meno round storici o combinazioni sec/delta rare.
- **Discontinuità nel tempo:** a parità di delta fisso, passando da sec 91 a 90 la % può cambiare bruscamente perché cambia la cella della lookup (analisi: `scripts/analyze_dwin_a_sec_jumps.py`).
- **Cieca alla vol del round corrente:** non distingue un delta “tranquillo” da uno in mercato molto nervoso nello stesso secondo.

### DWinB

**Punti di forza**

- **Contesto di volatilità:** incorpora V30–V120; utile quando il movimento vs PTB va letto rispetto al rumore recente (coerente con l’uso comparativo `|delta|` vs `VW` nel feed).
- **Copertura più uniforme:** se il gate di eleggibilità passa, quasi sempre c’è una % (niente asterisco).
- **Generalizzazione:** il logistico interpola tra osservazioni; meno dipendente da un singolo bucket stretto.
- **Coerenza tra secondi:** transizioni sec→sec generalmente più morbide.

**Punti deboli**

- **Scatola nera relativa:** non si vede quanti campioni “pesano” sulla stima; serve il report offline per Brier/log-loss.
- **Rischio di over/under-confidence:** la calibrazione isotonica è in-sample sul train Lighter; sui reali Polymarket può deviare (valutare con `eval_delta_win_v2_compare.py`).
- **Dipendenza dalle vol:** se le vol sono basse per poco movimento reale ma il delta è già grande, il modello può reagire in modo non intuitivo senza guardare anche `|delta|` e la quota.
- **Meno “onesta” sui dati scarsi:** restituisce sempre un numero anche dove A mostrerebbe prudenza (`*`).

---

## Quando preferire l’uno o l’altro

### Preferire **DWinA** quando…

- Serve una **stima empirica leggibile** (“in passato, in questa fascia H, a questo sec e con delta simile, è uscito così”).
- Il trading guarda **disallineamenti delta vs quota** e vuoi un riferimento storico **per fascia oraria** (es. stesso delta in H6 vs H2).
- La decisione richiede **soglie di fiducia sul campione:** ignorare o scontare celle con `[n=N*]` o `n` basso (es. `n < 50`).
- Si analizzano **pattern per bucket di |delta|** (probe: `scripts/probe_delta_win_bands.py`).
- La vol intra-round è già valutata separatamente (colonne `VW`) e non si vuole “doppio conteggio” nella probabilità.

### Preferire **DWinB** quando…

- Conta il **contesto di movimento recente** del BTC nello stesso round (mercato nervoso vs piatto).
- Serve **sempre un numero** nel range sec attivo (dashboard, alert automatici) e si accetta meno trasparenza sul supporto dati.
- Si confrontano round con **stesso delta ma vol diversa** (es. delta +30$ con V60=15 vs V60=45).
- Le celle DWinA sono spesso `---` o `*` (H rara, sec finale, delta estremo) ma il round è ancora eleggibile.
- Si vuole una curva **più continua** lungo il countdown (meno salti tra secondi contigui).

### Usare **entrambi** quando…

- **Concordanza forte** (A e B alti e allineati, `n` grande): segnale più solido che il lato delta è favorito rispetto alla sola lettura della quota.
- **Divergenza A vs B:** caso da studiare manualmente.
  - A alto, B basso: storico favorevole per H/sec/delta, ma vol corrente o calibrazione spingono verso il dubbio.
  - A basso o `*`, B alto: pochi precedenti nel bucket, ma il modello vede vol/regime favorevole — **maggiore cautela**.
  - A `---`, B con %: solo B disponibile; pesare meno senza supporto empirico locale.
- **Delta vs quota:** es. quota DOWN 60c ma delta positivo; DWinA sulla UP dà la stima “fisica” storica, DWinB la aggiusta per la vol del momento (vedi anche `docs/patterns.txt`).

---

## Regole pratiche di lettura nel feed

1. **Guardare sempre `n` in DWinA** prima di fidarsi della %. Un `87% [n=35]` è informativo; `87% [n=500]` molto di più.
2. **Non usare DWinA con `[n=N*]`** come se fosse una probabilità: è solo un avviso di campione insufficiente.
3. **Confrontare con `|delta|` e `VW`:** se `|delta| < V60`, il movimento può essere ancora nel rumore; DWinB reagisce a questo più di A.
4. **Confrontare con `quote`:** delta_win non sostituisce il mercato; misura il lato Chainlink vs PTB. Gap grande tra quota maggioritaria e DWin alto sul lato delta è il pattern strategico centrale del progetto.
5. **Fascia H:** in header `intraday: Hk`; per lo stesso orologio UTC, DWinA cambia tabella — è voluto.

Esempio concettuale (stesso round, sec=90):

```text
sec  ...  delta   DWinA              DWinB   btc      vol
 90  ...  +45$    82% [n=120]         78%    97280$   V30 12 V60 28 ...
```

Qui A dice che storicamente (H, sec=90, |delta|≈43–47) il lato Up ha vinto ~82% su 120 casi; B, con vol più alta, abbassa leggermente a 78%.

---

## Come decidere oggettivamente quale pesare di più

Il codice **non** sceglie automaticamente A o B. Per dati reali Polymarket (label Gamma affidabile):

```bash
python scripts/eval_delta_win_v2_compare.py [data_dir]
```

Report in `data/reports/delta_win_compare_<timestamp>.json`: Brier e log-loss overall e per `sec` / `intraday_h`. Il metodo con Brier più basso è mediamente più calibrato sul campione valutato.

Sul train Lighter (holdout ultime 2 settimane, `study_delta_win_v2.py`):

- Confronto **globale vs per-H** per A: la stratificazione H migliora tipicamente il Brier rispetto a un unico pool (vedi `global_vs_per_h` nel report di studio).
- Holdout stampa `band_brier` (A) vs `logistic_brier` (B): utile come prima indicazione, ma i round reali restano il test decisivo.

**Configurazione colonne** in `setup.json` → `delta_win_txt_columns`:

| Valore | Effetto |
|--------|---------|
| `["a", "b"]` | Entrambe (default) |
| `["a"]` | Solo DWinA |
| `["b"]` | Solo DWinB |

---

## Limiti comuni (non specifici di A o B)

- Addestrati su **Lighter sintetico**; su Polymarket reale possono esserci shift di microstruttura, latenza Chainlink, partial CLOB.
- Valgono solo nel range **sec** configurato (default ultimi 235 secondi del round).
- `|delta| > 150` viene trattato come 150 in lookup (clamp).
- Le % nei `.txt` dopo convert/backfill sono **enrichment** dall’artifact corrente: non usarle per misurare la bontà del modello sullo stesso dataset Lighter usato al fit (leakage in-sample).
- Outcome nei reali: preferire round con `ptb_gamma` / `final_gamma` presenti per validazione esterna.

---

## Riepilogo decisionale

| Obiettivo | Colonna consigliata |
|-----------|---------------------|
| Massima trasparenza e fiducia sul campione | **DWinA** (+ controllo `n`) |
| Contesto volatilità del round in corso | **DWinB** |
| Regime orario (weekend vs picco US/EU) | **DWinA** (tabelle per H); B usa H come feature |
| Segnale robusto per automazione | **Concordanza A+B** con `n` alto |
| Dati scarsi / H6 / delta estremi | Leggere A per onestà (`*`, `---`); B come stima ausiliaria con cautela |
| Scelta basata su performance misurata | Report `delta_win_compare_*.json` sui reali |

Per implementazione e comandi di manutenzione: [`indicator_delta_win.md`](indicator_delta_win.md).  
Per il significato di **H**: [`indicatorH.md`](indicatorH.md).
