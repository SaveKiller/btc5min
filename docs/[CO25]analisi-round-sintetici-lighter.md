# Analisi: round sintetici da tick Lighter

**Data:** 10 Luglio 2026  
**Autore:** Composer (analisi), SaveKiller (richiesta)  
**Stato:** Valutazione completata — **favorevole con confini netti**

---

## 1. Sintesi esecutiva

L’idea di ricostruire **round sintetici da 5 minuti** dai tick top-of-book Lighter è **valida come dataset ausiliario**, non come sostituto dei round Polymarket.

| Verdetto | Dettaglio |
|----------|-----------|
| **Fare** | Costruire un DB di ~22k round con sec↓, PTB, delta, volatilità, outcome direzionale, fascia H |
| **Non fare** | Trattarli come round Polymarket; mischiarli nei report; calibrare strategie che dipendono da quote/CLOB |
| **Rischio principale** | *Basis risk* Lighter vs Chainlink sui round a **delta finale piccolo** (~7–15% delle finestre) |
| **Mitigazione** | Formato separato, flag di confidenza, uso esplicito per classi di analisi, validazione incrociata appena i due feed coincidono nel tempo |

Il progetto **usa già** i tick Lighter per le fasce orarie H (`hour_bands.json`, studio su 21 819 finestre). I round sintetici sono il passo naturale successivo sullo stesso percorso dati, con vincoli più stringenti su tutto ciò che tocca l’outcome di settlement.

---

## 2. Contesto e obiettivo

### 2.1 Situazione attuale

- **Round Polymarket reali:** 459 file `.bin` in `data/` (6–10 Luglio 2026), ~300 tick/round, quote UP/DOWN, book, Chainlink, gain%, indice R.
- **Tick Lighter:** 77 CSV in `H:\ticks\lighter-fullrawticks\btc` (settimane ISO 2615–2625), ~34 GB, 6 Aprile – 21 Giugno 2026.
- **Gap temporale:** ~15 giorni tra fine Lighter (21/06) e inizio Polymarket (06/07). **Oggi non esiste overlap** per validare outcome sintetico vs reale sugli stessi timestamp.

### 2.2 Cosa si vuole ottenere

Un feed “simile” ai round reali per:

- asse **sec** decrescente (300 → 1);
- **PTB** = mid Lighter all’inizio finestra;
- **delta** secondo per secondo vs PTB;
- **volatilità** V30/V60/V120 (e RV300) con la stessa metodologia del progetto;
- **outcome** UP/DOWN confrontando mid inizio e fine del blocco 5 min.

Obiettivo dichiarato: **statistica ausiliaria** in attesa di migliaia di round veri — non sostituire il campionamento Polymarket.

---

## 3. Dati disponibili (verificati)

### 3.1 Tick Lighter

```
H:\ticks\lighter-fullrawticks\btc\<settimana_ISO>\raw-btc-YYYY-MM-DD.csv
```

| Campo | Valore |
|-------|--------|
| Colonne | `timestamp` (ms UTC), `ask`, `bid`, `nonce` |
| Frequenza grezza | decine–centinaia di tick/sec (es. ~11,8M righe/giorno a giugno) |
| Resampling proposto | ultimo mid per secondo UTC: `(ask+bid)/2` |
| Finestre 5 min | allineate a multipli UTC (HH:00, :05, :10, …) — già in `iter_day_windows()` |

### 3.2 Finestre ricostruibili

Da `study_vol_h.py` / report `vol_h_study_20260710_131329.json`:

| Metrica | Valore |
|---------|--------|
| Giorni | 77 |
| Finestre totali | 22 176 |
| Scartate (coverage < soglia o NaN) | 357 (1,6%) |
| **Finestre utilizzabili** | **21 819** |
| Moltiplicatore vs round reali | **~47×** (21 819 / 459) |

Tempo di scansione completa su 77 CSV (solo delta/outcome): **~6,5 min** su disco locale — fattibile per batch periodici.

---

## 4. Cosa si può e non si può ricostruire

### 4.1 Affidabile (uso consigliato)

| Elemento | Motivazione |
|----------|-------------|
| **Traiettoria delta intra-round** | Coerente se PTB e prezzi usano la stessa fonte (Lighter) |
| **Volatilità V30/V60/V120, RV300** | Formula identica a `vol_stats.py` / `lighter_ticks.py`; dipende dai ritorni, non dal livello assoluto |
| **Confronto \|delta\| vs VW** | Pattern “movimento vs rumore recente” — core del progetto |
| **Fascia H** | Già derivata da Lighter; round sintetici la riusano, non la validano di nuovo |
| **Stagionalità / regime orario** | Distribuzione RV300 per ora/giorno, transizioni tra fasce H |
| **Rischio fisico Rz (senza Rq)** | `Pz = Φ(−z)` con sigma da vol Lighter e delta Lighter — **modello fisico**, non di mercato |
| **Momentum / mean-reversion del prezzo** | Dinamiche di breve periodo sul mid |

### 4.2 Parzialmente affidabile (con filtri)

| Elemento | Rischio | Mitigazione |
|----------|---------|-------------|
| **Outcome UP/DOWN** | Basis Lighter ≠ Chainlink; flip possibile se \|delta Chainlink\| è piccolo | `outcome_confidence` da \|delta_final\| Lighter; escludere `low` nelle analisi sensibili |
| **Bilancio UP/DOWN aggregato** | Possibile bias residuo sui round “coin flip” | Confronto distribuzionale (vedi §6); non usare per calibrazione P&L |
| **PTB “ufficiale” Polymarket** | PTB reale è Chainlink (o Gamma); PTB sintetico è mid Lighter a t₀ | Tenere `ptb_source: lighter_mid`; non confrontare delta assoluto cross-fonte senza correzione |

### 4.3 Non ricostruibile (vietato pretendere)

| Elemento | Perché |
|----------|--------|
| **Quote UP/DOWN, spread CLOB** | Proprietà del mercato Polymarket |
| **Book snapshot, depth, gain%** | Richiedono dati CLOB |
| **Rischio di mercato Rq** | Dipende dalla quota normalizzata del lato maggioritario |
| **Pattern `mismatch-quote-delta`** | Richiede quote + delta Chainlink (vedi `docs/patterns.txt`) |
| **Simulazione P&L con fee Polymarket** | Senza quote non ha senso economico |

---

## 5. Il dubbio centrale: due piattaforme, prezzi diversi

### 5.1 Natura del rischio

La paura è fondata ma **va raffinata**: non è “Lighter sbagliato”, è **basis risk tra feed**:

```
delta_lighter = (C₁ + b₁) − (C₀ + b₀) = delta_chainlink + (b₁ − b₀)
```

- `C` = prezzo “di riferimento” (vicino a Chainlink / aggregato CEX)
- `b` = scostamento Lighter vs quel riferimento

L’outcome **si inverte** rispetto a Chainlink quando:

```
|delta_chainlink| < |b₁ − b₀|   e   sign(delta_chainlink) ≠ sign(delta_lighter)
```

Quindi il problema non è la divergenza di *livello* (Lighter a +$20 vs Chainlink), ma la **variazione del basis in 5 minuti** combinata con un movimento BTC molto piccolo.

### 5.2 Ordine di grandezza atteso

| Fenomeno | Stima prudente |
|----------|----------------|
| Scostamento livello Lighter vs CEX/Chainlink | ~0,01–0,05% → **$7–$35** su BTC ~$70k (non critico da solo) |
| Drift del basis in 5 min (DEX arbitrato) | tipicamente **$1–$10**, episodi rari >$15 |
| Ampiezza movimento 5 min (mediana \|delta\|) | **~$39** (Lighter, 21 819 finestre) |

Su movimenti mediani, il basis drift è una frazione modesta. Il rischio si concentra nella **coda bassa** di \|delta\|.

### 5.3 Dove NON si falsano le statistiche

Anche se Lighter e Chainlink differiscono di qualche dollaro:

1. **Volatilità** — misura dispersione dei ritorni; resta stabile tra feed altamente correlati (stesso processo di prezzo, lag minimo).
2. **Forma della traiettoria intra-round** — correlazione attesa molto alta; utili per studi di *timing* fisico, non di pricing.
3. **Regimi orari (H)** — già validati con holdout su Lighter; indipendenti dall’oracolo Polymarket.

### 5.4 Dove SI può falsare

1. **Calibrazione della probabilità di vincita** su outcome settlement reale.
2. **Strategie sugli ultimi secondi** quando \|delta\| Chainlink è nell’ordine del basis drift.
3. **Qualsiasi analisi che usa quote** (in-out-early, mismatch, gain 15–20c) — **non applicabile** ai sintetici.

---

## 6. Evidenza empirica (oggi)

### 6.1 Distribuzione \|delta_final\| — Lighter vs Polymarket

Scansione completa Lighter (21 819 finestre, coverage ≥ 95%) vs 459 round Polymarket (Chainlink, `ptb_chainlink` / `final_chainlink`):

| Metrica | Lighter (sintetico) | Polymarket (reale) |
|---------|---------------------|---------------------|
| % UP | 49,93% | 50,76% |
| Mediana \|delta\| | **$38,80** | **$41,59** |
| % \|delta\| < $5 | 7,76% | 6,75% |
| % \|delta\| < $10 | 15,39% | 14,16% |
| % \|delta\| < $20 | 29,20% | 27,67% |
| Mediana RV300 (solo Poly) | — | $40,22 |

**Lettura:** le distribuzioni macro sono **molto simili**. Non provano concordanza outcome per round (mancano timestamp comuni), ma supportano l’uso di Lighter per **modelli di volatilità e di ampiezza tipica del movimento 5 min**.

### 6.2 Cosa manca ancora

| Validazione | Stato |
|-------------|-------|
| Matrice confusione outcome Lighter vs Chainlink **stesso `start_ts`** | **Impossibile oggi** (gap 15 giorni tra i dataset) |
| Confronto tick-by-tick Lighter vs Chainlink | Da fare appena entrambi i feed sono live sullo stesso periodo |
| Proxy intermedio | Opzionale: misurare \|basis drift\| Lighter vs Binance/CEX sui 77 giorni Lighter, e usare quella coda per stimare flip rate atteso |

---

## 7. Infrastruttura già presente

Il modulo `src/lighter_ticks.py` copre già:

| Funzione | Ruolo |
|----------|-------|
| `load_day_mid_by_sec()` | CSV → mid 1 Hz |
| `iter_day_windows()` | finestre 300 s allineate 5 min UTC |
| `fast_window_metrics()` | RV300, mediane V30/V60/V120 |
| `hour_band()` | fascia H da `hour_bands.json` |

`scripts/study_vol_h.py` dimostra la pipeline end-to-end su tutti i CSV. Per i round sintetici manca soprattutto:

1. iteratore globale + formato di output persistente;
2. calcolo per-tick di `sec`, `delta`, `VW` (come nel `.txt` v6, ma su mid Lighter);
3. metadata `source`, `outcome_confidence`, `coverage`;
4. eventuale script di validazione incrociata (quando ci sarà overlap).

---

## 8. Classificazione degli usi (cosa è “autentico” o meno)

### Tier A — Sicuri sui sintetici

- Esplorare distribuzione di RV300 / VW per H, ora, giorno
- Regole del tipo “se \|delta\| < V60 a sec=120, allora …” sul **prezzo fisico**
- Prototipare pipeline di analisi (aggregazioni, plotting, feature engineering)
- Addestrare modelli di **volatilità realizzata** o di **regime**

### Tier B — Utili ma con filtro `outcome_confidence ≥ medium`

- Statistiche condizionate all’outcome (es. P(UP \| H3, \|delta_120\| > X))
- Conteggi di “reversal” negli ultimi 60 s (solo su mid, non su quote)
- Calibrazione preliminare di Rz

### Tier C — Solo round Polymarket reali

- Qualsiasi strategia con quote, gain%, book walk
- Pattern catalogati in `docs/patterns.txt` (mismatch, in-out-early, …)
- Calibrazione di Rq e indice R completo
- Backtest economico con fee CLOB
- Decisioni operative di betting

**Regola pratica:** se l’analisi usa colonne `quote` o `gain%` del `.txt`, i sintetici **non entrano**.

---

## 9. Proposta operativa

### 9.1 Formato output (distinto dai `.bin` v6)

Non estendere il formato binario Polymarket. Usare **Parquet** (o CSV gzip) con namespace separato, es. `data/synthetic/lighter/`:

**Tabella `rounds`** (1 riga / finestra):

```python
{
    "start_ts": 1775433600,
    "source": "lighter_synthetic",
    "ptb_mid": 68980.55,
    "final_mid": 68992.10,
    "delta_final": 11.55,
    "outcome": "UP",              # UP se delta_final >= 0
    "outcome_confidence": "high", # da soglie su |delta_final|
    "rv300": 18.5,
    "v30_med": 12.3,
    "v60_med": 14.1,
    "v120_med": 16.8,
    "hour_band": 3,
    "coverage": 0.997,
    "dow": 0,
    "hour_utc": 0,
}
```

**Tabella `ticks`** (300 righe / round):

```python
{
    "start_ts": 1775433600,
    "sec": 240,                   # countdown
    "mid": 68985.10,
    "delta": 4.55,                # mid - ptb_mid
    "v30": 18, "v60": 22, "v120": 31,  # opzionale, stessa logica convert
}
```

### 9.2 Soglie `outcome_confidence` (iniziali, da ricalibrare)

| Livello | Condizione \|delta_final\| Lighter |
|---------|-------------------------------------|
| `high` | ≥ $10 |
| `medium` | $5 – $10 |
| `low` | < $5 |

Circa **~7,8%** delle finestre cade in `low` — escluderle nelle analisi che guardano l’outcome.

### 9.3 Regole di governance dati

1. **Mai** mescolare in SQL/Parquet unico senza colonna `source`.
2. Nei grafici e report: prefisso `[synthetic]` o colore diverso.
3. Script di analisi: accettare flag `--source poly|lighter|both` con default `poly`.
4. Avviare **subito** il campionamento Lighter in parallelo al collector Polymarket (se possibile) per chiudere il gap di validazione.

### 9.4 Stima effort

| Voce | Stima |
|------|-------|
| Script `scripts/build_synthetic_rounds.py` | ~150–250 righe, riuso `lighter_ticks.py` |
| Prima build completa | ~10–15 min (metriche complete) |
| Modifiche al collector | nessuna obbligatoria |
| Validazione incrociata | ~100 righe, da attivare con overlap ≥ 500 round |

---

## 10. Validazione futura (piano)

### 10.1 Quando i feed coincidono

Per ogni round Polymarket con `start_ts = T`:

1. Leggere mid Lighter a `T` e `T+300` (o sec 300 e sec 1 della griglia).
2. Calcolare `outcome_lighter`.
3. Confrontare con `outcome` header (Gamma / Chainlink).

Report atteso:

| | UP (Chainlink) | DOWN (Chainlink) |
|--|----------------|------------------|
| **UP (Lighter)** | TP | FP |
| **DOWN (Lighter)** | FN | TN |

Stratificare per \|delta_chainlink\| e per fascia H.

### 10.2 Metriche di successo (ipotesi da verificare)

| \|delta_chainlink\| | Accordo atteso |
|---------------------|----------------|
| < $5 | 70–85% |
| $5 – $10 | 90–95% |
| > $10 | > 97% |

Se l’accordo su `high` è sotto il 95%, restringere Tier B e alzare le soglie di confidenza.

### 10.3 Validazione proxy (opzionale, subito)

Sui 77 giorni Lighter, campionare coppie (t, t+300) e confrontare mid Lighter con prezzo Binance/Bybit storico (API o dump). Stima del drift massimo del basis → upper bound al flip rate senza round Polymarket.

---

## 11. Alternative considerate

| Alternativa | Pro | Contro |
|-------------|-----|--------|
| **Aspettare solo round Polymarket** | Massima autenticità | Settimane/mesi di buco statistico |
| **Usare solo Chainlink storico (senza Lighter)** | PTB allineato a Polymarket | Non avete 70 giorni di Chainlink 1 Hz locale; API esterne da integrare |
| **Simulare quote con modello logit su delta** | Permetterebbe fake Rq | Introduce ipotesi arbitrarie; rischio di **doppia falsificazione** |
| **Round sintetici Lighter (proposta)** | Volume, infrastruttura pronta, vol/regime affidabili | Outcome e PTB non “ufficiali”; niente CLOB |

**Raccomandazione:** procedere con i sintetici Lighter per **Tier A/B**, senza modelli di quote inventati.

---

## 12. Conclusione

| Domanda | Risposta |
|---------|----------|
| Ha senso l’idea? | **Sì**, come **database ausiliario** per volatilità, regime H, dinamica del delta fisico e prototipi analitici. |
| Il timore sui prezzi diversi è giustificato? | **Sì**, ma limitato ai round a **movimento piccolo** e a tutto ciò che lega outcome + quote; non invalida la volatilità né la maggior parte delle traiettorie. |
| Rischiamo statistiche “false”? | **Sì se usiamo male i dati** (Tier C). **No se rispettiamo i confini** (Tier A, filtri su outcome). |
| Precedente nel progetto? | **Sì** — le fasce H sono già costruite su Lighter con holdout; i round sintetici estendono lo stesso ragionamento con più attenzione al settlement. |

**Verdetto finale:** costruire i ~22k round sintetici **conviene**. Il beneficio statistico è grande; il bias è **localizzato, quantificabile e filtrabile**. La condizione non negoziabile è **onestà metodologica**: formato separato, niente quote fingute, validazione incrociata non appena Lighter e Polymarket condividono il calendario.

**Prossimo passo suggerito:** `scripts/build_synthetic_rounds.py` → Parquet in `data/synthetic/lighter/` → notebook o script di confronto distribuzionale con i 459 round reali (già allineati su mediana \|delta\| e RV300).

---

## Riferimenti interni

- `[DS4]analisi-round-sintetici-lighter.md` — analisi parallela (stesso tema)
- `src/lighter_ticks.py` — loader e metriche
- `scripts/study_vol_h.py` — studio H su Lighter
- `docs/indicatorH.md` — definizione fasce H
- `data/reports/vol_h_study_20260710_131329.json` — numeri coverage finestre
- `AGENTS.md` — formato round reali `.bin` v6 / `.txt`
