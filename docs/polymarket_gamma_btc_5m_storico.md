# Analisi: recupero storico dei round BTC 5m su Polymarket Gamma

## Risposta breve

Sì. Per recuperare molti round storici non devi interrogare lo slug di ogni singolo mercato: usa l'endpoint Gamma keyset-paginated filtrato sui mercati/eventi chiusi, con intervallo temporale e pagine fino a 100 market per richiesta (o 500 eventi).

## Endpoint consigliato

Per questo caso è preferibile `/markets/keyset`: ogni round BTC 5m è normalmente un singolo market, mentre `/events/keyset` restituisce anche i market annidati e può essere utile se vuoi conservare i metadati dell'evento.

L'endpoint market supporta `closed`, `start_date_min/max`, `end_date_min/max`, ordinamento e `after_cursor`; il massimo è 100 risultati per chiamata.

```http
GET https://gamma-api.polymarket.com/markets/keyset
  ?closed=true
  &start_date_min=2026-07-01T00:00:00Z
  &start_date_max=2026-07-02T00:00:00Z
  &order=endDate
  &ascending=false
  &limit=100
```

La risposta ha questa forma:

```json
{
  "markets": [
    {
      "id": "...",
      "question": "Bitcoin Up or Down - ...",
      "slug": "...",
      "closed": true,
      "outcomes": "[\"Up\", \"Down\"]",
      "outcomePrices": "[\"1\", \"0\"]",
      "clobTokenIds": "[\"...\", \"...\"]",
      "startDate": "...",
      "endDate": "...",
      "closedTime": "..."
    }
  ],
  "next_cursor": "..."
}
```

Per la pagina successiva invia lo stesso filtro aggiungendo `after_cursor=<next_cursor>`. Il cursore è opaco: non va interpretato né ricostruito.

## Filtro BTC 5m

Nella specifica di `/markets/keyset` non risulta un filtro `title_search`; quindi, per una query bulk affidabile, filtra lato client `question` o `slug` dopo aver ristretto il periodo temporale.

Una query giornaliera è pratica: con round esatti ogni 5 minuti si hanno al massimo 288 record/giorno, quindi circa 3 pagine da 100.

In alternativa puoi partire da `/events/keyset`, che espone `title_search` e restituisce i `markets` dentro ogni evento; il limite è 500 eventi per risposta.

```http
GET https://gamma-api.polymarket.com/events/keyset
  ?closed=true
  &title_search=Bitcoin
  &start_date_min=2026-07-01T00:00:00Z
  &start_date_max=2026-07-02T00:00:00Z
  &order=endDate
  &ascending=false
  &limit=500
```

Applica poi un filtro stretto locale su `event["title"]` e/o `market["question"]` per distinguere i 5 minuti dai 15 minuti e dagli altri prodotti BTC.

## Implementazione Python

```python
from __future__ import annotations

import requests
from datetime import datetime, timezone

GAMMA = "https://gamma-api.polymarket.com"


def fetch_btc_5m_history(
    start: datetime,
    end: datetime,
    page_size: int = 100,
) -> list[dict]:
    params = {
        "closed": "true",
        "start_date_min": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "start_date_max": end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "order": "endDate",
        "ascending": "false",
        "limit": page_size,
    }

    rows = []

    while True:
        r = requests.get(
            f"{GAMMA}/markets/keyset",
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        payload = r.json()

        for m in payload["markets"]:
            text = f'{m.get("question", "")} {m.get("slug", "")}'.lower()

            # Adatta il predicato al pattern effettivo di slug/question.
            if "bitcoin" in text and ("5 min" in text or "5m" in text):
                rows.append({
                    "market_id": m["id"],
                    "condition_id": m["conditionId"],
                    "slug": m["slug"],
                    "question": m["question"],
                    "start": m.get("startDate") or m.get("startDateIso"),
                    "end": m.get("endDate") or m.get("endDateIso"),
                    "closed_at": m.get("closedTime"),
                    "outcomes": m.get("outcomes"),
                    "outcome_prices": m.get("outcomePrices"),
                    "clob_token_ids": m.get("clobTokenIds"),
                    "volume": m.get("volumeNum"),
                })

        cursor = payload.get("next_cursor")
        if not cursor:
            break
        params["after_cursor"] = cursor

    return rows
```

Dopo la risoluzione, `outcomePrices` in genere contiene `"1"` per il lato vincente e `"0"` per quello perdente. Conviene fare `json.loads()` di `outcomes`, `outcomePrices` e `clobTokenIds`, perché Gamma può esporli come stringhe JSON.

## Strategia operativa

- **Backfill:** scarica per finestre giornaliere o settimanali; deduplica con `conditionId` o `id` come chiave univoca.
- **Incrementale:** salva l'ultimo `endDate` elaborato, sovrapponi una finestra di 15–30 minuti per tollerare ritardi di chiusura/risoluzione, quindi esegui un upsert.
- **Discovery iniziale:** analizza alcuni market recenti per verificare il formato effettivo di `slug`, `question`, `events[].series` e degli eventuali tag; se disponibile stabilmente, sostituisci il filtro testuale con `series_id` o `tag_id`.
- **Paginazione:** non usare `offset` nei nuovi endpoint keyset; usa `next_cursor` nella risposta e `after_cursor` nella richiesta successiva.

## Sintesi

Una singola richiesta a `/markets/keyset` può ottenere fino a 100 round chiusi. Con date range e keyset pagination, poche richieste coprono un'intera giornata di BTC 5m; persisti i risultati localmente e usa un filtro di famiglia/serie stabile quando lo avrai identificato.

## Fonti

- https://docs.polymarket.com/api-reference/markets/list-markets-keyset-pagination
- https://docs.polymarket.com/api-reference/events/list-events-keyset-pagination
