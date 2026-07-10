# Indice H — fascia oraria di volatilità micro

Indice intero **H1…Hk** che classifica il **regime di volatilità BTC atteso** al momento di inizio di un round Polymarket **BTC Up or Down 5m**, in base al calendario UTC (`market_start_ts`). Non misura la volatilità osservata *dentro* il round (quella resta negli indici `V30` / `V60` / `V120` nel `.txt`).

---

## Quante fascie e quali valori

Studio su **77 giorni** Lighter (2026-04-06 → 2026-06-21, **21 819** finestre da 300 s), metodo **`intraday_profile_v1`**:

| Fascia | RV300 mediano cluster (Lighter) | Celle | Regime |
|--------|----------------------------------|-------|--------|
| **H1** | ~39 $ | 42 | Weekend calmo (sabato intero, domenica 00–17 UTC) |
| **H2** | ~54 $ | 44 | Notte / mattino feriale basso (Lun–Gio 03–10, 20–21; Ven 06–11, 18–23; Dom 18–23) |
| **H3** | ~60 $ | 18 | Transizione mezzogiorno / tarda sera feriale |
| **H4** | ~72 $ | 16 | Notte profonda feriale (Lun–Gio 00–02, 18–19) |
| **H5** | ~88 $ | 20 | Tardo pomeriggio feriale (Lun–Gio 16–17, Ven 12–17) |
| **H6** | ~109 $ | 28 | **Picco** overlap US/EU (Lun–Gio **13–15 UTC**) |

**k = 6** scelto come minimo entro 1σ dal miglior errore holdout (MSE ≈ 2156 su ultime 3 settimane Lighter), con separazione **notte (H2) ≠ picco (H6)** verificata su train e holdout.

Report completo: [`data/reports/vol_h_study_20260710_131329.json`](../data/reports/vol_h_study_20260710_131329.json).  
Mappa runtime: [`hour_bands.json`](../hour_bands.json).

---

## Come assegnare H a un round

### Input

`market_start_ts` dell’header (Unix UTC, confine 5 min).

### Lookup

```python
from src.lighter_ticks import hour_band
h = hour_band(market_start_ts)   # → 1 … 6
```

La funzione legge **solo** `hour_bands.json` (nessun fallback). File assente, cella mancante o H non valida → eccezione.

### Esempi (coerenti con weekday UTC)

| Data/ora UTC | Giorno | H |
|--------------|--------|---|
| 2026-07-09 09:40 | mercoledì | **H2** (notte/mattino basso) |
| 2026-07-09 14:00 | mercoledì | **H6** (picco 13–15) |
| 2026-07-10 01:00 | giovedì | **H4** (notte profonda 00–02) |
| 2026-07-12 10:00 | sabato | **H1** (weekend) |
| 2026-07-13 15:00 | domenica | **H1** (dom 00–17) |

---

## Mappa visiva 7×24 (ora UTC → H)

Legenda: cifra = H1…H6. Righe = giorno UTC, colonne = ora 0–23.

```text
        h: 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23
Mon       4  4  4  2  2  2  2  2  2  2  2  3  3  6  6  6  5  5  4  4  2  2  3  3
Tue       4  4  4  2  2  2  2  2  2  2  2  3  3  6  6  6  5  5  4  4  2  2  3  3
Wed       4  4  4  2  2  2  2  2  2  2  2  3  3  6  6  6  5  5  4  4  2  2  3  3
Thu       4  4  4  2  2  2  2  2  2  2  2  3  3  6  6  6  5  5  4  4  2  2  3  3
Fri       3  3  3  3  3  3  2  2  2  2  2  2  5  5  5  5  5  5  2  2  2  2  2  2
Sat       1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1
Sun       1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  2  2  2  2  2  2
```

---

## Metodo (sintesi)

1. **Finestre** 300 s su mid Lighter 1 Hz; metrica primaria **RV300** (stessa formula `VW` del progetto).
2. **Split temporale**: prime 8 settimane → costruzione; ultime 3 → holdout (nessun leakage).
3. **Profili calendario**: Lun–Gio, Ven, Sab, Dom — segmentazione oraria **contigua** (min 2 h su Lun–Gio, min 6 h su profili a singolo giorno).
4. **Sessioni** raggruppate in **k = 5…10** per mediana RV300; scelta del più piccolo k entro 1σ dal miglior MSE holdout, con vincoli: 168/168 celle, ≥6 celle per H, separazione notte 03–08 vs picco 13–16 UTC su Lun–Gio.
5. **Bootstrap** (40 run, seed fisso): accordo esatto 66,7 %, entro ±1 H 97,2 %; k più frequente = 5 (26/40), k scelto = 6.

Silhouette sulle sessioni (k=6): **0,69** — solo diagnostica, non criterio unico di scelta.

---

## Validazione Chainlink (round locali)

Date disponibili: **2026-07-09**, **2026-07-10** (395 round). Nessun weekend → **H1 assente** (`status: ok`, 5 H distinti).

| H | Round | Mediana RV300 | Mediana V60 |
|---|-------|---------------|-------------|
| H2 | 165 | 34,9 $ | 13,1 $ |
| H3 | 120 | 37,0 $ | 14,9 $ |
| H4 | 51 | 50,4 $ | 18,8 $ |
| H5 | 23 | 48,0 $ | 19,4 $ |
| H6 | 36 | 66,4 $ | 28,6 $ |

Monotonia globale sul campione luglio **non** perfetta (H5 < H4 su Chainlink): atteso per feed/periodo diverso; luglio **non** è usato per scegliere k.

---

## Relazione con V30 / V60 / V120

| | **H** | **V30 / V60 / V120** |
|---|--------|----------------------|
| **Quando** | Fissato a `market_start_ts` | Ogni secondo nel round |
| **Fonte** | `hour_bands.json` (Lighter apr–giu) | `chainlink_btc` |
| **Uso** | Stratificare calibrazione / soglie per regime atteso | Rumore e shock intra-round |

---

## Limitazioni

1. Training Lighter mid; round operativi Chainlink.
2. Validazione su soli 2 giorni feriali — serve weekend in `data/` per testare H1.
3. H descrive il regime *tipico* dello slot, non la vol realizzata del singolo round.

---

## Riprodurre

```bash
python -u scripts/study_vol_h.py
```

Rigenera `data/reports/vol_h_study_<timestamp>.json` e `hour_bands.json`.

Test: `python -m unittest tests.test_vol_h tests.test_risk`

---

## Prossimo passo (fuori scope attuale)

Aggiungere `hour_band: Hk` nell’header `.txt` in `convert_round`.
