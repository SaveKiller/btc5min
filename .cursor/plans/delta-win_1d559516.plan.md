---
name: delta-win
overview: Costruire e validare `delta_win` come probabilità calibrata che il lato indicato dal segno del delta al checkpoint coincida con l’outcome ufficiale Gamma. Il modello verrà scelto sui round sintetici con validazione temporale, poi congelato e testato sui round reali Chainlink successivi prima del backfill dei feed Lighter.
todos:
  - id: extract-audit
    content: Estrarre e auditare il dataset checkpoint con sole label Gamma ufficiali e feature live-safe
    status: completed
  - id: compare-models
    content: Confrontare baseline fisica, lookup monotona, GAM e random forest con validazione temporale e calibrazione OOF
    status: completed
  - id: freeze-model
    content: Selezionare, rifittare e versionare il modello delta_win con manifest e hash H
    status: completed
  - id: real-holdout
    content: Valutare il modello congelato sui round reali Chainlink con label Gamma affidabili
    status: completed
  - id: integrate-feed
    content: Integrare la percentuale checkpoint-only nel renderer Lighter e configurazione
    status: completed
  - id: backfill-verify
    content: Backfill idempotente dei feed storici, test, report e documentazione
    status: completed
isProject: false
---

# Piano delta_win

## Contratto statistico
- Per ogni checkpoint `180, 150, 120, 90, 60, 30`, definire il lato da `quote` del feed sintetico (`UP`/`DOWN`, già derivato dal delta float); questo evita l’ambiguità delle righe visualizzate come `0$`. La label è `1` quando quel lato coincide con l’`outcome` ufficiale Gamma del round.
- Usare come feature operative gli stessi valori visibili nel feed: `sec`, `abs(delta)` arrotondato, `V30/V60/V90/V120` arrotondate e H categorica. Escludere solo outcome proxy (`outcome_agreement: nan`): i 925 round `FALSE` hanno comunque label Gamma ufficiale e sono esempi essenziali del mismatch Lighter→settlement. Escludere inoltre checkpoint mancanti, valori `---` e checkpoint con stale dentro l’intera finestra causale V120; non usare finale, `move_error` o altre informazioni future.
- La percentuale descrive il **lato favorito dal delta**, non la maggioranza CLOB. L’assenza del segno tra le feature impone simmetria UP/DOWN: il report dovrà verificare separatamente eventuali residui direzionali.

## Dataset e confronto dei metodi
- L’inventario verificato contiene 22.030 round Lighter su 11 settimane, tutti con 300 tick e tutti e sei i checkpoint presenti; 22.019 round hanno outcome Gamma (`TRUE` o `FALSE`) e 11 soltanto hanno label proxy. I feed contengono già `intraday: Hk` nell’header; manca ancora `delta_win`.
- Estendere [src/listats.py](src/listats.py) con parser delle righe e un estrattore checkpoint che produca audit per settimana/H: round validi, label Gamma, duplicati, stale, valori mancanti e start esclusi. Leggere H dall’header `intraday`.
- Implementare [scripts/study_delta_win.py](scripts/study_delta_win.py) con confronto preregistrato fra:
  - prevalenza e formula fisica `Pwin = Φ(z)` come baseline, usando le quattro stime `z_w = |delta| / ((Vw / sqrt(w-1)) * sqrt(sec))`;
  - lookup empirica monotona e smussata su uno score che combina le quattro `z_w`, con effetto H regolarizzato;
  - regressione logistica spline/GAM regolarizzata;
  - random forest poco profonda e calibrata, solo challenger perché le probabilità raw non sono affidabili e può violare la monotonia.
- Fare ablation `delta+sec`, `+quartetto V`, `+H` per dimostrare il contributo reale dei parametri. Usare split rolling per settimane sui primi 9 blocchi, tenere le ultime 2 settimane come holdout sintetico bloccato e mantenere sempre insieme i sei checkpoint dello stesso round. Calibrazione solo su predizioni cronologiche out-of-fold.
- Selezionare il modello più semplice entro un errore standard dal miglior Brier settimanale appaiato; log-loss, reliability/Brier decomposition, calibration slope/intercept, stabilità per checkpoint/settimana/H e bootstrap a blocchi sono guardrail. Dopo il holdout, rifare fit sull’intero archivio Apr–Giu e calibrare da predizioni rolling OOF, senza usare i round reali.

## Modello e integrazione feed
- Aggiungere [src/delta_win.py](src/delta_win.py) con quantizzazione condivisa, caricamento cached dell’artifact, controllo versione/hash H e API `delta_win(sec, abs_delta, vols, intraday_h)`. Nessun fallback: artifact o schema incompatibile devono fallire esplicitamente.
- Salvare artifact e manifest versionati in `models/delta_win_v1.*`, includendo feature order, checkpoint, periodo/count training, famiglia e iperparametri, metriche OOS, versione libreria e hash di `hour_bands.json`. Aggiungere solo configurazione operativa (`checkpoints`, path/versione artifact) a [setup.json](setup.json) e [src/setup.py](src/setup.py); aggiungere le dipendenze ML necessarie a [requirements.txt](requirements.txt).
- Aggiornare [src/lighter_txt_format.py](src/lighter_txt_format.py) per una colonna `delta_win`: percentuale a una cifra decimale solo ai sei checkpoint, `---` altrove o se non eleggibile. Aggiungere nell’header versione/hash modello, target, label source, checkpoint, periodo training e stato `synthetic_calibrated`. Il modello va caricato una sola volta per worker dalla pipeline [scripts/build_lighter_rounds.py](scripts/build_lighter_rounds.py).
- Creare [scripts/backfill_lighter_delta_win.py](scripts/backfill_lighter_delta_win.py) per aggiornare atomicamente e in modo idempotente i circa 22k `.txt`, preservando warnings e aggiungendo la colonna `delta_win` ai checkpoint. Il backfill usa i valori già presenti nei feed, senza rileggere i 34 GB raw; le percentuali storiche restano enrichment in-sample e non saranno usate per misurare la bontà del modello.

## Test esterno sui round reali
- Creare [scripts/eval_delta_win_real.py](scripts/eval_delta_win_real.py): aggiornare prima il dataset con `sync.bat` (sono già presenti 675 round locali del 9–11 luglio), quindi estrarre ai medesimi checkpoint delta Chainlink, quattro V e H; il lato resta quello del segno del delta, indipendentemente dalla maggioranza CLOB e dai tick partial.
- Non fidarsi ciecamente di `header.outcome` dei `.bin`: il worker tardivo patcha prezzi Gamma ma non l’outcome. Derivare la label da `ptb_gamma/final_gamma` quando presenti oppure recuperarla da Gamma; escludere settlement provvisori e Chainlink stale. I reali restano un test esterno puro: nessun tuning o ricalibrazione dopo averli osservati.
- Riportare Brier/log-loss/reliability per checkpoint, H e giorno, intervalli clusterizzati e shift delle feature Lighter→Chainlink. Se il transfer è insufficiente, mantenere `delta_win` solo come indice sintetico sperimentale; non modificare in questa fase [src/txt_format.py](src/txt_format.py), [src/convert.py](src/convert.py) o il `.bin` v6 reale.

## Verifica e documentazione
- Aggiungere [tests/test_delta_win.py](tests/test_delta_win.py) per label `FALSE` inclusa/`nan` esclusa, delta visualizzato `0$`, rounding ±0,5, checkpoint esatti, stale nella V120, split/calibrazione senza leakage, serializzazione, range probabilità, parità renderer/backfill, idempotenza e mutazione dei tick futuri.
- Produrre `data/reports/delta_win_study_<timestamp>.json` e `delta_win_real_eval_<timestamp>.json`; documentare definizione, limiti e comandi in [docs/indicator_delta_win.md](docs/indicator_delta_win.md) e aggiornare la sezione Lighter di [AGENTS.md](AGENTS.md), preservando le modifiche locali già presenti.
- Validazione finale: test unitari, studio riproducibile con seed fisso, audit copertura dei sei checkpoint, confronto artifact round-trip, backfill dry-run/campione/completo e nuova esecuzione di `python -m src.listats summary`.