# Analisi: Round Sintetici da Tick Lighter

**Data:** 10 Luglio 2026
**Autore:** Claude (analisi), SaveKiller (richiesta)
**Stato:** Proposta valutata — favorevole con precauzioni

---

## 1. Contesto

Il progetto **btc5min** salva tutti i round da 5 minuti di Polymarket (BTC 5min UP/DOWN) per creare strategie di betting basate sulla statistica dei round passati. I round vengono salvati su disco secondo per secondo.

Il collettore è partito da poco (6 Luglio 2026). Serviranno **settimane o mesi** per accumulare un numero significativo di round reali. Abbiamo però **77 giorni di tick top-of-book** del DEX Lighter, che potremmo usare per ricostruire round sintetici e fare statistica ausiliaria nell'attesa.

---

## 2. Dati Disponibili

### 2.1 Round Polymarket (reali)

| Caratteristica | Dettaglio |
|---|---|
| **Periodo** | 6 – 10 Luglio 2026 (5 giorni) |
| **Round totali** | ~583 (459 live + 124 backup) |
| **Formato** | Binario `.bin` v6 + testuale `.txt` |
| **Tick per round** | ~300 (1 al secondo) |
| **Fonte prezzo BTC** | Chainlink (oracolo) |
| **Dati per tick** | Quote UP/DOWN, book snapshot completi, gain%, chainlink_btc |
| **Outcome** | Gamma API (primario) o Chainlink (fallback) |
| **Contenuto header** | PTB, final_price, outcome, fee_rate |

### 2.2 Tick Lighter (DEX)

| Caratteristica | Dettaglio |
|---|---|
| **Periodo** | 6 Aprile – 21 Giugno 2026 (77 giorni) |
| **File** | 77 CSV, organizzati per settimana ISO (2615–2625) |
| **Dimensione totale** | ~34 GB |
| **Tick per giorno** | 5M – 20M (60–240 tick/sec a seconda del giorno) |
| **Colonne** | `timestamp` (ms Unix UTC), `ask`, `bid`, `nonce` |
| **Fonte prezzo** | Lighter DEX (top-of-book, non oracolo) |
| **Copertura** | 24 ore/giorno, tutti i giorni |

### 2.3 Finestre 5min Ricostruibili

```
77 giorni × 288 finestre/giorno = ~22.176 round sintetici
```

**Moltiplicatore vs round reali: ~38×** (22.176 vs 583)

---

## 3. Cosa Si Può e NON Si Può Ricostruire

### ✅ Affidabile

| Metrica | Note |
|---|---|
| **Mid price** | `(ask + bid) / 2` per ogni secondo |
| **Delta dal PTB** | Differenza mid corrente vs mid di inizio round |
| **Volatilità V30, V60, V90, V120** | Calcolate sui mid Lighter, metodologia identica a `vol_stats.py` |
| **RV300** | Realized volatility sulla finestra di 300 secondi |
| **Outcome direzionale** | UP se `mid_final >= mid_iniziale`, altrimenti DOWN |
| **Distribuzione UP/DOWN** | Per ora, giorno della settimana, regime H |
| **Assegnazione H-band** | Già implementata in `lighter_ticks.py` |
| **Statistiche di momentum / mean reversion** | Basate sul delta secondo per secondo |
| **Stagionalità** | Pattern intraday, differenze weekend/feriali |

### ⚠️ Con Caveat

| Metrica | Caveat |
|---|---|
| **Outcome per round a basso delta** | Se `|delta_final| < ~$5`, l'outcome sintetico può differire da quello reale. Aggiungere flag `outcome_confidence: low` |
| **Frequenza UP vs DOWN** | Possibile piccolo bias sistematico, da validare appena ci sono abbastanza round reali |

### ❌ NON Ricostruibile

| Metrica | Perché |
|---|---|
| **Quote UP/DOWN** | Non abbiamo il book del CLOB Polymarket |
| **Book snapshot (depth)** | Dati proprietari Polymarket |
| **Gain% implicito** | Dipende dalle quote UP/DOWN |
| **Rischio Rq** | Basato sulla concentrazione del book (Pq0 = 1 - normalized quote) |
| **Fee rate** | Specifico di Polymarket |
| **Comportamento del CLOB** | Liquidity, spread, depth |

---

## 4. Il Rischio di Distorsione (Price Divergence)

### 4.1 La preoccupazione

Due piattaforme diverse (Polymarket/Chainlink e Lighter) battono prezzi leggermente diversi. Le statistiche su dati non autentici potrebbero essere falsate.

### 4.2 Analisi del rischio

**Entità della divergenza —** Chainlink aggrega diversi exchange centralizzati (Binance, Coinbase, Kraken, etc.). Lighter è un DEX il cui prezzo arbitraggio contro gli exchange centralizzati. Il mid price di Lighter tipicamente sta entro lo **0.01% – 0.05%** dal prezzo medio di mercato. Su BTC a $65.000 sono circa **$3 – $30** di differenza.

**Impatto sull'outcome —** Per un'opzione binaria 5 minuti, quello che conta è la **direzione** del movimento, non il livello assoluto. La differenza tra Chainlink e Lighter è quasi sempre molto inferiore all'ampiezza del movimento in 5 minuti.

**Dove il bias può manifestarsi —** L'unico punto critico è l'outcome quando il delta è molto piccolo:

```
Se BTC si muove di +$2 su Chainlink ma di -$1 su Lighter in 5 minuti,
l'outcome sintetico sarà DOWN mentre quello reale sarebbe UP.
```

**Quanto è frequente?** Su 22.176 finestre, quelle con `|delta| < $5` sono stimabili intorno al **10-15%**. Per le altre ~19.000 finestre con movimenti più ampi, l'outcome sintetico è quasi certamente corretto.

**La volatilità è praticamente identica —** La deviazione standard dei ritorni a 1 secondo su Lighter sarà quasi indistinguibile da quella su Chainlink, perché:
- I ritorni sono calcolati sul mid price della stessa fonte
- La volatilità di breve periodo dipende dalla dinamica dei prezzi, non dal livello assoluto
- I calcoli V30/V60/V90/V120 e RV300 sono quindi **affidabili**

### 4.3 Tabella riepilogativa del bias

| Metrica | Rischio bias | Affidabilità |
|---|---|---|
| Volatilità (V30-V120, RV300) | Trascurabile | ⭐⭐⭐⭐⭐ |
| Delta dal PTB (ampiezza) | Molto basso | ⭐⭐⭐⭐⭐ |
| Outcome con \|delta\| > $10 | Molto basso | ⭐⭐⭐⭐⭐ |
| Outcome con \|delta\| $5–$10 | Basso | ⭐⭐⭐⭐ |
| Outcome con \|delta\| < $5 | Medio | ⭐⭐⭐ |
| Distribuzione UP/DOWN assoluta | Basso-Medio | ⭐⭐⭐⭐ |
| Quote di mercato | N/A | Non ricostruibile |

---

## 5. Infrastruttura Esistente

Il progetto **usa già** i dati Lighter per costruire le fasce orarie di volatilità (H1–H6) salvate in `hour_bands.json`. Il modulo [lighter_ticks.py](../src/lighter_ticks.py) contiene già:

- `load_day_mid_by_sec()` — carica un CSV Lighter e produce un dizionario `{timestamp_sec: mid_price}`
- `iter_day_windows()` — itera finestre da 300 secondi allineate ai confini dei multipli di 5 minuti UTC
- `fast_window_metrics()` — calcola RV300 e mediane V30/V60/V120 su una griglia 1Hz
- `hour_band()` — assegna la fascia H a un timestamp

**Il 70% del lavoro è già fatto.** Manca solo:
1. Un iteratore su tutti i 77 CSV
2. Un formato di output per i round sintetici
3. Il calcolo dell'outcome e del flag di confidenza

---

## 6. Raccomandazione: FARE, con Precauzioni

### 6.1 Perché sì

- Il beneficio di passare da 583 a 22.000+ round è **enorme** per qualsiasi analisi statistica
- Il bias è concentrato nei round a basso delta ed è **quantificabile**
- L'infrastruttura esiste già in gran parte
- Possiamo **mitigare** il rischio con flag di confidenza e validazione futura

### 6.2 Precauzioni implementative

1. **Formato distinto** — Non mischiare round reali e sintetici. Usare un formato semplice (Parquet o CSV) con un campo `source: "lighter_synthetic"`.

2. **Flag `outcome_confidence`**:
   ```
   |delta_final| >= $10  → high
   |delta_final|  $5-$10 → medium
   |delta_final|  < $5   → low
   ```
   Permette di filtrare nelle analisi sensibili all'outcome.

3. **Allineamento temporale** — Polymarket fa round a multipli di 5 minuti UTC (HH:00, HH:05, HH:10...). `iter_day_windows()` già produce finestre allineate a questi confini. Usare lo stesso allineamento.

4. **Validazione incrociata appena possibile** — Quando ci saranno abbastanza round reali (es. 2-3 settimane), fare un confronto sistematico: per ogni round reale, ricostruire l'outcome sintetico dai tick Lighter dello stesso timestamp. Questo produrrà la **matrice di confusione** empirica tra outcome sintetico e reale.

5. **Naming esplicito** — In report e grafici, distinguere sempre la fonte dei dati. Mai aggregare round reali e sintetici senza evidenziarlo.

### 6.3 Stima effort

- **Script principale:** ~200-300 linee di Python, riutilizzando `lighter_ticks.py`
- **Formato output:** Parquet consigliato (~6.6M righe = 22K round × 300 tick)
- **Tempo di esecuzione:** ~30-60 minuti per processare 34 GB di CSV
- **Modifiche a codice esistente:** Nessuna necessaria, solo nuovo script in `scripts/`

---

## 7. Formato Proposto per Round Sintetico

### 7.1 Schema

```python
# Un round sintetico = una finestra da 300 secondi
{
    "start_ts": 1775433600,           # Unix timestamp UTC inizio round
    "start_dt": "2026-04-06T00:00:00Z",  # ISO 8601
    "dow": 0,                         # 0=Lunedì ... 6=Domenica
    "hour": 0,                        # 0-23 UTC
    "source": "lighter_synthetic",    # Fonte dati
    "ptb_mid": 68980.55,             # Mid price a t=0 ((ask+bid)/2)
    "final_mid": 68992.10,           # Mid price a t=300
    "delta_final": 11.55,            # final_mid - ptb_mid
    "outcome": "UP",                 # UP se delta >= 0, altrimenti DOWN
    "outcome_confidence": "high",    # high / medium / low
    "rv300": 18.5,                   # Realized volatility sui 300s
    "v30_med": 12.3,                 # Mediana V30 sui tick della finestra
    "v60_med": 14.1,                 # Mediana V60
    "v120_med": 16.8,                # Mediana V120
    "hour_band": 3,                  # Fascia H (1-6)
    "coverage": 0.997,               # % secondi con tick nella finestra
    "ticks": [                       # Array di 300 mid price (1/sec)
        68980.55, 68980.60, 68981.20, ...
    ]
}
```

### 7.2 Soglie `outcome_confidence`

| Confidenza | Condizione |
|---|---|
| `high` | \|delta_final\| >= $10 |
| `medium` | $5 <= \|delta_final\| < $10 |
| `low` | \|delta_final\| < $5 |

Le soglie sono indicative e andranno calibrate con la validazione incrociata.

### 7.3 Storage

**Opzione consigliata: Parquet** con due livelli:
- **Tabella `synthetic_rounds`**: una riga per round (22K righe), colonne di summary + array dei 300 mid
- **Tabella `synthetic_ticks`**: una riga per tick (6.6M righe), colonne: `start_ts, second, mid_price, delta`

Parquet è efficiente per query analitiche (Pandas, Polars, DuckDB) e compressione.

---

## 8. Validazione Futura

### 8.1 Matrice di Confusione

Appena disponibili N round reali (consigliato N >= 500 per significatività), per ogni round reale con timestamp `T`:
1. Cercare il tick Lighter corrispondente al secondo `T` e `T+300`
2. Calcolare l'outcome sintetico: `mid(T+300) >= mid(T)` → UP
3. Confrontare con l'outcome reale (da Gamma API o Chainlink)

Risultato atteso:

| | UP (reale) | DOWN (reale) |
|---|---|---|
| **UP (sintetico)** | Alta concordanza | Bassa discordanza |
| **DOWN (sintetico)** | Bassa discordanza | Alta concordanza |

### 8.2 Analisi per Fasce di Delta

L'analisi va stratificata per `|delta_final|`:

| Fascia delta | Atteso accordo |
|---|---|
| < $2 | 60-70% |
| $2 – $5 | 80-90% |
| $5 – $10 | 90-95% |
| > $10 | > 98% |

Questi numeri sono stime; la validazione empirica fornirà i valori reali.

---

## 9. Conclusione

L'idea di ricostruire round sintetici dai tick Lighter è **valida e consigliata**. Il rischio di distorsione esiste ma è:
- **Quantificabile** (concentrato nei round a basso delta)
- **Mitigabile** (flag di confidenza, formato distinto, naming esplicito)
- **Validabile** (matrice di confusione non appena disponibili round reali a sufficienza)

Il beneficio netto è fortemente positivo: passare da 583 a ~22.000 round permette analisi statistiche che altrimenti richiederebbero mesi di attesa.

**Next step:** Piano di implementazione dettagliato → script `scripts/build_synthetic_rounds.py`.
