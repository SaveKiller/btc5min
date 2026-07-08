# Indici di timing entrata — BTC Up/Down 5m

- **id**: entry-indicators
- **created_utc**: 2026-07-08T12:43:00Z
- **participants**: m-composer, m-gpt, m-gemini, m-grok, m-sonnet, m-deepseek, m-glm, m-kimi, m-minimax

## Scopo

Definire indici e indicatori calcolabili a posteriori (e poi integrabili nel feed tick-by-tick) per scegliere **quando** entrare in una scommessa Polymarket "BTC Up or Down 5m", massimizzando il guadagno atteso e minimizzando il rischio. Standardizzare i concetti chiave del trade-off tempo/rischio/rendimento su base statistica (288 round/giorno, migliaia di file nel tempo).

## Punto 01

Leggere i file `.txt` in `context/` — ognuno è il campionamento a **1 Hz** dei valori rilevanti durante un round di "btc5min UP/DOWN" di Polymarket.

**Obiettivo:** trovare uno o più **indici** (calcolabili a posteriori e poi scrivibili nel feed) che permettano di scegliere il momento di piazzare la scommessa in modo da massimizzare il guadagno e minimizzare il rischio.

Esplorare tutte le possibilità utili, anche indicatori noti o indici usati nel trading di opzioni. Da questi indici deve emergere una **standardizzazione** dei concetti chiave, ad esempio:

- entrare troppo presto aumenta molto il rischio e la casualità è maggiore;
- entrare troppo tardi abbassa molto il rischio ma anche il guadagno finale;
- altri concetti analoghi utili per scegliere il momento o i momenti di entrata.

Cercare tecniche dal settore delle scommesse, dalla matematica/statistica e dal trading di opzioni.

**Per ogni proposta specificare:**

1. la **tecnica** o il framework teorico;
2. gli **indici/indicatori** coinvolti, con formula o definizione operativa;
3. come variano **riga per riga** (ogni secondo del round) e come si aggregano su molti round.

**Contesto dati:** le strategie non si basano solo sui 7 file di esempio, ma su **288 file al giorno** (e migliaia nel tempo) su cui fare statistiche, calibrazione e validazione.

**Esempio guida:** un indice di rischio/rendimento calcolato sui valori di ogni riga, specifico per quel secondo — più alto indica maggiore rischio e maggiore gain potenziale, e viceversa.

**Nota sui file binari:** esistono anche file `.bin` con il LOB completo; non sono nel contesto attuale. Se servono per una proposta, richiederli esplicitamente.

**Deliverable atteso:** catalogo strutturato di indici candidati, definizioni formali, ipotesi di soglie/zone temporali, e raccomandazioni su quali validare per prime sui dati storici.
