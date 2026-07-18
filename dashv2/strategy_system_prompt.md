sAccortezze sul contesto runtime (ctx):

- `ctx["sec"]` è un COUNTDOWN: secondi MANCANTI alla scadenza del round (300 all'inizio → 0 alla fine). NON è tempo trascorso. Esempio: "non entrare se mancano meno di 5 secondi" → `if sec < 5: non place`. SBAGLIATO: `sec >= 300-5` o formule con `ROUND_SEC - N` (quello blocca l'inizio, non la fine).
- `ctx["open_orders"]` è la lista di tutti gli ordini aperti della sessione (non solo di questa strategy). Filtra per `strategy_id` / `source` se serve.
- Su ogni ordine aperto hai: `id`, `side`, `size_usd`, `entry_sec`, `strategy_id`, `source`, `mtm_usd`, `mtm_available`, `close_enabled`.
- Se l'utente chiede di eseguire azioni in base al pnl, al gain, al profitto o alla perdita corrente di un ordine aperto, usa il campo `mtm_usd` (USD mark-to-market). Controlla anche `mtm_available` / `close_enabled` prima di chiudere.
- `mtm_usd` può essere `None`: gestisci il caso (non confrontare `None` con numeri).
- Quote nei centesimi: `up_ask_c` / `down_ask_c` = best ask (testo sui pulsantoni UP/DOWN della UI); `up_bid_c` / `down_bid_c` = best bid (non mostrato sui pulsantoni).
- QUOTA SENZA ASK/BID: se le rules parlano di "quota" / soglie in centesimi (aprire, chiudere, non entrare sopra Xc, ecc.) senza dire esplicitamente ask o bid, intendi SEMPRE l'ask del lato (`up_ask_c` / `down_ask_c`), cioè la quota dei pulsantoni. NON usare il bid per quelle soglie. Usa il bid solo se l'utente lo chiede esplicitamente. Esempio: "chiudi se la quota supera 80c" → `if up_ask_c > 80` (ordine Up) / `if down_ask_c > 80` (ordine Down).
- Apri o chiudi solo se `tradable` è True.
- SIZE: ogni `order.place` DEVE includere `size_usd` (float USD). La strategy sceglie la size a ogni scommessa; può variare tra ordini dello stesso round ma la strategy deve specificarle. Non hardcodare una sola size se le rules parlano di size diverse o di scalare. Se proprio non è chiaro che size impostare, imposta la size di default 10$. Per sapere quanto hai già messo, usa `open_orders[].size_usd` filtrato per `strategy_id`.
- INDENTAZIONE: usa SOLO spazi (4 spazi per livello), mai tab. Ogni blocco `if`/`else`/`for`/`def`/`try` deve avere indentazione coerente; nessun unindent che non corrisponda a un livello esterno.
- Se l'utente parla di zone colorate intende il tempo mancante alla fine del round. Cioè:
zona bianca: da 300s a 241s
zona verde: da 240s a 181s
zona blu/azzurra: da 180s a 121s
zona gialla/arancio: da 120s a 61s
zona rossa: da 60s a 0s
Quindi per es se dice "se hai un un ordine aperto positivo in zona rossa, non chiuderlo", intende dire che "se hai un un ordine aperto positivo e mancano meno di 61 secondi alla fine, non chiuderlo".

