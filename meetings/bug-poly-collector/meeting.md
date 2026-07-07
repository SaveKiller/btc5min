# Diagnosi bug collector poly — round persi e feed Chainlink

- **id**: bug-poly-collector
- **created_utc**: 2026-07-07T09:20:00Z
- **participants**: m-sonnet, m-deepseek, m-gpt, m-gemini, m-composer, m-glm, m-kimi, m-grok, m-minimax

## Scopo

Analisi approfondita del bug del collector `btc5min` in produzione sul container **poly** (Proxmox CT 103, Debian 12): pochi round salvati rispetto al tempo di attività, errori `price_to_beat not captured` e `chainlink final not captured`, con sospetta causa H5 (WebSocket Chainlink apparentemente up ma stream BTC/oracle non utilizzabile).

Il meeting deve produrre ipotesi, test, prove e piano di debug da sottoporre a implementazione.

## Punto 01

Analizzate il report del bug (`context/report-bug-0707.md`) e tutto il materiale in `context/`. Fate ricerche approfondite su quale possa essere la causa e valutate **tutte** le possibilità, anche quelle meno frequenti.

Valutate anche un **cambio di sistema operativo** del container poly: è un CT creato appositamente per questo scopo, quindi se pensate che un'altra versione di Linux o Windows possa andare meglio di Debian 12 LXC unprivileged, proponetela pure (può essere installata facilmente su Proxmox).

Valutate anche la disattivazione del firewall del ct, è cmq all'interno di una lan sicura e non è veramente utile.

Valutate anche impostazione di rete del sistema operativo, eventuali conflitti con qualcos'altro.

Scrivete tutti i **test**, le **prove** e le **info di debug** proposte che possono servire alla soluzione del problema. Quello che proponete verrà analizzato da un agente e, se ritenuto valido, andrà messo in pratica.

**Deliverable atteso per turno 01:** elenco strutturato di ipotesi (con probabilità e evidenze), comandi/script di diagnostica, modifiche di logging suggerite, criteri di validazione fix, e raccomandazioni infra/OS se applicabili.