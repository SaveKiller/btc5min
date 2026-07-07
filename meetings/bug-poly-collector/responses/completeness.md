# Completeness critic — bug-poly-collector

- **generated_utc**: 2026-07-07T10:35:00Z
- **turni_analizzati**: 01

## Gap di copertura

- **Distinzione H5.1 vs H5.2 non risolta.** Il meeting ha identificato due meccanismi concatenati (stall detector inattivo durante `run_forever()` vs timestamp oracle obsoleti), ma l'analisi locale di `docs/debug-9c51e0.log` contiene solo eventi `round_runner` (P1/P2): 73 `sampler start`, 39 `ptb captured`, 34 falliti. Mancano completamente eventi `feed_chainlink` (`ptb_skip`, `btc_gap_warn`, `stall_reconnect`, `ws_close`). Il logging Chainlink NDJSON proposto al §6 del report turno 01 **non era ancora deployato** al momento del run analizzato.

- **Soak test insufficienti.** I probe `probe_btc_gaps.py` e `probe_chainlink_ws.py` sono stati eseguiti solo per **10 minuti** (579 tick, gap max ~8.3 s). Nessun soak ≥30–60 min in parallelo al collector, né probe da 2–4 h. Il report raccomanda soak 4 h ma non è stato eseguito durante il meeting.

- **Soak Windows 4 h non eseguito.** L'assenza del bug su dev Windows è basata su campioni brevi (~5 min/round). Non c'è evidenza che il difetto long-run sia specifico di poly o cross-platform.

- **Test A/B firewall PVE non eseguito.** `firewall=1` sul CT 103 resta inconcluso (H9/H11). Il dissenso m-gemini (sconsiglia disabilitazione) vs maggioranza (test opzionale) non è stato risolto con dati.

- **Fix applicativi non implementati.** Nessuna modifica a `feed_chainlink.py` (stall in `_ping_loop`, logging NDJSON, `_on_close` con età ultimo tick BTC) è stata applicata nel repo principale durante il meeting. Il deliverable era diagnostica e piano, non implementazione.

- **Script diagnostici proposti ma non creati.** Mancano nel repo: `probe_oracle_ts.py` (m-sonnet), `probe_btc_staleness.py` / `analyze_debug_log.py` (m-composer), `diag_stream_btc.py` (m-kimi), `diag_h5_btc_stream.py` (m-grok). Solo `probe_btc_gaps.py`, `probe_chainlink_ws.py`, `diag_ptb.py` esistono in context.

- **Problema secondario CLOB / books not ready.** Il debug log mostra **485** eventi `books not ready` (hypothesisId P2) vs 73 round. Questo aspetto (feed CLOB, qualità order book) è stato menzionato marginalmente ma non analizzato come possibile contributo alla qualità dati o ai round parziali.

- **Cattura pacchetti / tcpdump non eseguita.** Proposto da m-deepseek e m-grok; nessuna evidenza Wireshark su flusso WS durante blocco FAIL.

- **Cross-check Gamma `priceToBeat`.** Proposto da m-gpt come controllo incrociato; non implementato né testato.

- **Codice analizzato da snapshot context.** I partecipanti hanno letto `meetings/bug-poly-collector/context/src/`; non è verificata la parità byte-per-byte con `f:\btc5min\src\` al momento della chiusura (probabile identica, ma non attestata formalmente).

- **Un solo turno di discussione.** L'utente ha chiuso il meeting senza turno 02; i dubbi aperti §11 del report turno 01 restano senza approfondimento multi-agente.

## Claim o decisioni senza evidenza sufficiente

- **H5.1 (stall detector dead code) al 85–95%.** Il consenso è forte e il codice supporta la tesi (`_run()` L75–77 vs `run_forever()` L94), ma **stall=0 in 4 h** potrebbe anche significare che i tick `btc/usd` arrivano ogni <45 s ma con timestamp inutilizzabili (H5.2). Senza logging `btc_gap_warn` / `ptb_skip` la probabilità relativa resta inferenza, non misura.

- **Meccanismo oracle heartbeat 3600 s + deviation 0.5% (m-sonnet).** Spiega elegantemente blocchi FAIL di ~80–90 min che terminano con `Going away`, ma **non è verificato** con probe timestamp oracle dedicato (`probe_oracle_ts.py` non eseguito).

- **REJECTED definitivo H1/H2/H3.** Valido per probe 10 min; il meeting stesso nota che failure intermittenti multi-ora non sono esclusi al 100%. La chiusura tratta H1–H3 come deprioritizzate, non come impossibili.

- **Recv-fallback ptb (F3, m-sonnet).** Proposto come safety net ma **nessun consenso** sulla correttezza semantica: potrebbe mascherare il problema oracle invece di risolverlo.

- **"9/9 unanime" su causa H5.** Vero sul quadro generale; le **probabilità numeriche** tra i partecipanti divergono sensibilmente (es. m-gemini: H5.2 solo 10%; m-composer: H5b 60%; m-gpt: H1 watchdog 35% come voce separata).

- **Analisi debug-9c51e0.log conferma H5.** Conferma il **rapporto 34/73 fallimenti ptb** coerente con `collector-poly.log`, ma **non distingue** H5.1 da H5.2 per assenza di log Chainlink.

## Angoli non esplorati

- **Comportamento `websocket-client` su send ping fallito.** `_ping_loop` fa `return` silenzioso su eccezione send (L119–120) senza `_close_ws()` — ipotesi H5 ping zombie (m-gpt, m-minimax H11) non testata.

- **Reconnect proattivo ogni 20–30 min** (m-gpt, m-kimi) come workaround temporaneo vs fix strutturale.

- **Fail-fast dopo N round consecutivi falliti** (m-minimax H9) per evitare ore di dati inutili.

- **Race singleton / overlap round** (m-kimi H5d, m-minimax H22): review lock non fatta con strace/thread dump.

- **Impatto `Restart=always` systemd** sul mascheramento di stati degradati tra restart.

- **Confronto con CT 104 `lobsaver`** (deploy analogo) come riferimento operativo long-run su stessa LAN/PVE.

- **Periodi di bassa volatilità BTC** come condizione trigger: validazione richiede run in orari diversi (notato da m-sonnet, m-composer) — non pianificata.

- **VM Debian non-LXC** come ultima risorsa infra (m-gpt Test F) — solo menzionata, non schedulata.
