## Regole globali

All'inizio di ogni task, **leggi e applica** `C:\Users\savea\.cursor\AGENTS.global.md` (regole di comportamento, comunicazione e sviluppo comuni a tutti i progetti). In caso di conflitto tra regole globali e quelle qui sotto, **vincono le regole di questo file**.


## BTC5MIN

In questo progetto l'agente e l'utente devono studiare il meccanismo di variazione di ask e bid della scommessa del "BTC Up or Down 5m" 
esistente in polymarket:

"https://polymarket.com/event/btc-updown-5m-1783238400"

Lo studio può essere fatto in molti modi ma per iniziare 
deve comprendere un log di tutte le scommesse di questa
pagina che si susseguono ogni 5 minuti. Durante i 5 minuti deve tenere 
in memoria i dati numerici di ask e bid associati al timestamp e in 
particolare al tempo (in sec) mancante alla scadenza della scommessa.
Allo scadere questi dati vanno scritti in un file binario rileggibile 
in seguito. 

In base a tutti questi file di log poi si dovranno elaborare
strategie per capire se e quando puntare per poter avere un gain che va
al di là della semplice applicazione statistica della vincita. 
Cioè l'obbiettivo del progetto è proprio trovare un  meccanismo di entrata
nela scommessa che permetta di avere un bilancio positivo oltre
le normali vincite/perdite che si annullano a vicenda.

Valutare se può essere utile associare le scommesse ogni 5 minuti con
equivalenti da 15 min o 1 ora in modo collegato per compensare eventuali
perdite o in modo da avere un sistema più solido.


