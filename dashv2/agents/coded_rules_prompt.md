# Reverse-pass: Python → coded rules (oltre al COMMON)

Leggi SOLO il modulo Python qui sotto. Riscrivi ciò che il codice FA davvero, per un utente della dashboard che NON programma.

CRITICO SULL'OUTPUT:
- Rispondi SOLO con testo nelle tre sezioni obbligatorie sotto
- Niente markdown fences, niente codice, niente introduzioni
- Linguaggio COLLOQUIALE (italiano), termini dashboard; **PnL** non MTM; stop loss / take profit ammessi se riflettono il codice
- VIETATO citare variabili/identificatori del codice o del contesto (es. ctx, mtm_usd, size_usd, majority_side, dwin_a, open_orders, sec, tradable, order.place, …)
- I numeri (soglie, secondi, percentuali, size in $) devono restare espliciti e non ambigui
- Non inventare regole assenti dal codice; non copiare docstring/commenti se contraddicono il flusso
- Non usare un template fisso di trading: elenca solo ciò che il codice implementa
- SOLO logica SPECIFICA di questa strategia. NON includere controlli generici di infrastruttura, ad esempio:
  - "mercato operabile" / tradable
  - bot attivo / bot_active
  - close_enabled / mtm_available / "MTM disponibile" / "mark-to-market"
  - presenza di campi None / "se i dati ci sono"

FORMULAZIONE FASCE ALTE (oltre al COMMON):
- VIETATO: "se sia Up sia Down fossero…", "se qualificano entrambi…", "privilegia Up perché controlla prima…", "in caso di pareggio sceglie Up".
- Se il codice fa if Up-in-fascia / elif Down-in-fascia, descrivi SOLO le condizioni separate, senza tie-break.
  CORRETTO: "Apre con size 100$ su Up quando la quota Up resta tra 80c e 94c per almeno 2 secondi; apre su Down quando la quota Down resta tra 80c e 94c per almeno 2 secondi."
  SBAGLIATO: "Se sia Up sia Down fossero contemporaneamente tra 80c e 94c, il codice privilegia Up…"
- Se usa il lato maggioritario: "Apre sul lato maggioritario quando la sua quota resta tra 80c e 94c…".

TEMPO: countdown e zone come nel COMMON. Confronti sul codice → zona o secondi mancanti, mai "primi N secondi del round".

Schema obbligatorio (heading esatti):

Apertura:
- ...

Chiusura:
- ...

Vincoli:
- ...

NO RIPETIZIONI TRA SEZIONI (obbligatorio):
- Ogni fatto/regola va in **una sola** sezione, dove è più naturale (apertura → Apertura; uscita/TP/SL → Chiusura; limiti trasversali non già detti → Vincoli).
- **Vincoli** non deve ripetere condizioni già scritte in Apertura o Chiusura. Se è già chiaro lì, non riscriverlo.
- Esempio sbagliato: in Apertura “apre solo in zona verde…” e in Vincoli di nuovo “non apre fuori zona verde”.
- In Vincoli metti solo ciò che **non** rientra già in apertura/chiusura (es. max ordini aperti, divieto di riaprire dopo close, size fissa globale) — altrimenti `- (nessuna)`.

Se una sezione non ha condizioni rilevanti nel codice (o tutto è già detto altrove), metti un solo bullet "- (nessuna)".

Esempio di tono (NON copiare i contenuti, solo lo stile):
- Apri con size 100$ quando la quota maggioritaria resta tra 80c e 94c per almeno 2 secondi e Model A o Model B è almeno al 78%.

Modulo Python:
---
{{SOURCE}}
---
