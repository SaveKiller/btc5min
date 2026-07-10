---
name: Fasce H intraday
overview: Sostituire la segmentazione Jenks errata con un modello ibrido calendario-volatilità che distingua esplicitamente i regimi intraday e scelga in modo riproducibile da 5 a 10 fasce H. Lo studio rigenererà report, mappa canonica, documentazione e helper runtime, senza modificare il formato dei round né `convert`.
todos:
  - id: replace-clustering
    content: Rifattorizzare lo studio con split temporale, profili calendario e segmentazione oraria contigua
    status: pending
  - id: select-validate-k
    content: Valutare k=5…10 con holdout, bootstrap e criterio esplicito notte–picco
    status: pending
  - id: publish-runtime-map
    content: Generare hour_bands.json e collegare hour_band() alla lookup canonica
    status: pending
  - id: document-test
    content: Rigenerare indicatorH.md, aggiungere test e verificare studio e suite esistente
    status: pending
isProject: false
---

# Piano fasce H intraday

## Diagnosi da correggere
- Il piano originario prevedeva clustering per similarità di volatilità, ma [`scripts/study_vol_h.py`](scripts/study_vol_h.py) ordina le 168 celle per `(dow, hour)` e passa quel vettore a `_jenks_breaks`, che presuppone valori ordinati per RV300. Il risultato è una segmentazione della settimana lineare: il taglio dominante cade a venerdì 21:00 e produce solo weekend/quasi-weekend contro feriale.
- La scelta tramite sola silhouette, il vincolo globale `SEP_RATIO_MIN = 1.15` e almeno 5 celle per cluster favoriscono ulteriormente `k=2`. In questo modo la differenza già visibile nei dati tra notte feriale e picco 13–16 UTC rimane assorbita in H2.
- La validazione attuale non dimostra la separazione: i 395 round Chainlink del 9–10 luglio appartengono tutti a H2 e il test Kruskal-Wallis non è calcolabile.

## Semantica e vincoli della nuova H
- H resta una previsione calendario live-safe: dipende esclusivamente da giorno e ora UTC di `market_start_ts`; non usa tick, V60 o outcome del round corrente.
- Costruire profili distinti per Mon–Gio, venerdì, sabato e domenica. Dentro ogni profilo, creare intervalli orari contigui; la stessa H può ricomparire in più intervalli o profili quando il livello di volatilità è simile.
- Ordinare globalmente le etichette per RV300 mediano: `H1` più calma, `Hk` più volatile, con `5 ≤ k ≤ 10`.
- Garantire una distinzione intraday verificabile: notte/bassa attività 03–08 UTC, ore intermedie e picco feriale 13–16 UTC non possono essere tutti collassati nella stessa fascia.
- Restano fuori scope [`src/convert.py`](src/convert.py), header `.txt` e formato `.bin`.

## Nuovo metodo di studio
1. Rifattorizzare [`scripts/study_vol_h.py`](scripts/study_vol_h.py) affinché lo scan Lighter conservi le circa 21.800 osservazioni per finestra (`start_ts`, giorno, ora, RV300, V60), così split e bootstrap lavorano sulle finestre già calcolate senza rileggere i CSV.
2. Separare cronologicamente gli 11 blocchi settimanali disponibili: prime 8 settimane per costruzione, ultime 3 per holdout. Fare bootstrap a blocchi di settimana con seed fisso, preservando dipendenza intraday e riproducibilità.
3. Per ciascuno dei quattro profili calendario, applicare una segmentazione dinamica sulle 24 ore, con intervalli minimi di 2 ore e un numero candidato di sessioni limitato. La funzione obiettivo userà `log(median_RV300)` come segnale primario e V60/IQR come diagnostica; non userà la posizione lineare Mon→Dom come distanza statistica.
4. Raggruppare le sessioni contigue risultanti in livelli globali ordinati di volatilità, pesati per numero di celle/finestre. Valutare ogni `k` da 5 a 10; rimuovere il rapporto rigido 1,15 e riportare invece separazione, overlap ed effect size tra fasce adiacenti.
5. Scegliere il più piccolo `k` entro una deviazione standard dal miglior errore holdout, purché assegni tutte le 168 celle, non produca fasce vuote o con meno di 6 celle, mantenga mediane H non decrescenti sul holdout e superi il controllo notte–picco. Silhouette resta solo una metrica diagnostica, non il selettore unico.
6. Misurare stabilità con bootstrap settimanale: accordo esatto e accordo entro ±1 H per ogni cella, variazione dei breakpoint, distribuzione del `k` scelto. Se nessun candidato 5–10 supera i criteri, lo studio deve fallire esplicitamente e mostrare i candidati, non ripiegare su 2 fasce.

## Output e integrazione
- Estendere il report timestampato `data/reports/vol_h_study_<timestamp>.json` con split temporale, profili orari, breakpoint, risultati completi per `k=5…10`, stabilità bootstrap, lookup 7×24 e motivazione della scelta finale.
- Pubblicare una mappa canonica versionata e non ignorata in [`hour_bands.json`](hour_bands.json), contenente versione del metodo, `k`, intervalli leggibili e lookup completo. Il report analitico resta l’audit dettagliato.
- Aggiornare [`src/lighter_ticks.py`](src/lighter_ticks.py) affinché `hour_band(market_start_ts)` legga la mappa canonica e restituisca `1…k`; file assente, mappa incompleta o H non valida devono produrre errore esplicito, senza regola H1/H2 di fallback.
- Rigenerare [`docs/indicatorH.md`](docs/indicatorH.md) dai risultati effettivi: numero finale di fasce, range RV300/V60, regole UTC, matrice 7×24, esempi, stabilità e limiti. Correggere anche gli esempi con giorno della settimana oggi incoerente con la data mostrata.

## Validazione e test
- Aggiungere [`tests/test_vol_h.py`](tests/test_vol_h.py) con fixture sintetiche che dimostrino la separazione notte/picco e testino: determinismo, `5 ≤ k ≤ 10`, copertura 168/168, durata minima degli intervalli, minimo 6 celle per H, ordinamento delle mediane e assenza di leakage.
- Verificare che [`hour_bands.json`](hour_bands.json), lookup prodotto dallo studio e `hour_band()` assegnino la stessa H a tutte le 168 celle.
- Rendere la validazione Chainlink data-driven su tutte le date locali disponibili. Se sono presenti meno di due H, registrare `not_testable` invece di una monotonia vera per costruzione; non usare luglio per scegliere `k`.
- Eseguire lo studio completo, `python -m unittest tests.test_vol_h tests.test_risk` e controllare nel report finale: separazione notte/picco su train e holdout, stabilità bootstrap, distribuzione dei round per H e motivazione numerica del `k` selezionato.