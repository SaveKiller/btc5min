# Risposta m-grok — Turno 01

**meeting-id**: bug-poly-collector  
**turno**: 01  
**data**: 2026-07-07  
**file**: `responses/response-m-grok-turn01.md`

## Punto 01

### Analisi del report e del contesto

Ho letto integralmente:
- `meeting.md` (scopo e Punto 01)
- `context/baseline.md` (fatti oggettivi, conteggi log, ipotesi pre-valutate)
- `context/00-manifest.md` (indice completo)
- `context/report-bug-0707.md` (report principale ~395 righe con timeline, H1-H5, meccanismi sospetti)
- `context/README.md`, `context/AGENTS.md`, `context/deploy-ct-lan-poly.md`
- `context/src/feed_chainlink.py` (critico: stall detector, _last_msg_ts solo su btc/usd, prime_chainlink)
- Esempi round poly (11 file .txt) e dev
- Script diagnostici (`probe_btc_gaps.py`, `probe_chainlink_ws.py`, `diag_ptb.py`)
- Log `collector-poly.log` (394 righe, ~4h run)

**Fatti chiave confermati**:
- ~4h run → 11 round salvati vs ~48 attesi
- Errori dominanti: `price_to_beat not captured` (~68 occorrenze, ~34 eventi), `chainlink final not captured` (4)
- Solo 1 `chainlink ws error` ("Going away" code 1001) e 0 `chainlink stall`
- Probe 10 min identici Windows/poly (579 tick, gap max ~8.3s, 0 disconnect)
- H5 confermata come causa principale sospetta nel report

### Ipotesi cause (con probabilità ed evidenze)

1. **H5 — WS connessa ma stream BTC/oracle inutilizzabile (probabilità alta: 85%)**
   - Evidenze: lunghi periodi di fallimento ptb senza log disconnect/stall; sampler logga `btc=... ptb=-`; dopo reconnect ptb con lag 222s (round parziale 1783384500); stall detector aggiorna `_last_msg_ts` **solo** su messaggi `btc/usd` (`feed_chainlink.py:75,282`).
   - Meccanismo: se WS resta viva con altri simboli ma tick btc/usd si fermano (ritardo oracle, batch storico post-reconnect, o priming obsoleto), non scatta reconnect e round fallisce silenziosamente.
   - Correlazione con `round_state.py:267`: `if ts_ms < self._ptb_start_ms: return` → ptb mai impostato se timestamp oracle < market_start.

2. **Timestamp oracle obsoleti al priming/register (probabilità media: 60%)**
   - Evidenze: `prime_chainlink` in `register()` usa `_last_value/_last_ts_ms` senza validare `ts_ms >= market_start_ts`; `apply_chainlink` skippa ptb se ts obsoleto.
   - Causa probabile dei ~17 round consecutivi falliti tra 23:15-00:30 senza disconnect.

3. **Stall detector insufficiente (probabilità media-alta: 70%)**
   - Evidenze: `STALL_RECONNECT_SEC=45.0` ma `_last_msg_ts` filtrato solo btc/usd; nessun log `chainlink stall` nonostante fallimenti ptb massicci.
   - Blind spot: connessione "sana" (altri simboli arrivano) ma BTC fermo → reconnect mai triggerato.

4. **H4 — NAT/router droppa connessioni long-lived (probabilità bassa: 20%)**
   - Evidenze: 5 `clob ws drop` ma solo 1 `chainlink ws error`; probe 10 min senza drop. Meno plausibile per RTDS con ping ogni 5s.

5. **H1/H2/H3 — Container/rete LXC, Debian 12 TCP, disconnect server (probabilità bassa: <10%)**
   - Evidenze: probe identici Windows/poly; 1 solo "Going away" (comportamento server RTDS noto, non causa principale).

### Valutazione cambio OS container poly

- **Debian 12 LXC unprivileged attuale**: stabile, probe OK, nessun problema kernel/TCP stack emerso.
- **Raccomandazione**: **non cambiare OS**. Il bug è applicativo (H5), non infra-specifico. Cambiare (es. Ubuntu 24.04 LTS o Alpine) aggiungerebbe overhead di rebuild Python 3.12 e testing senza beneficio misurabile.
- Se si volesse sperimentare: Ubuntu 22.04/24.04 LXC con stesso setup Python 3.12.10 via altinstall. Evitare Windows (non supportato nativo su Proxmox CT; richiederebbe VM).
- **Firewall PVE**: sì, disattivabile. CT in LAN sicura (10.1.1.0/24, dietro Fritz.box). `firewall=1` su veth aggiunge overhead iptables inutile. Comando: `pct set 103 -net0 name=eth0,bridge=vmbr0,firewall=0,...` + restart CT. Rischio basso.
- **Impostazioni rete**: `tcp_keepalive_time=7200` default kernel non impatta (app usa ping WS ogni 5s). MTU 1500 standard OK. Verificare `sysctl net.ipv4.tcp_tw_reuse=1` per connessioni long-lived, ma non critico. Nessun conflitto evidente con altri CT (104 lobsaver running).

### Test, prove, script diagnostici proposti

1. **Estensione logging strutturato in `feed_chainlink.py`** (modifica chiave):
   - Logga in `_on_message` (dopo filtro btc/usd): `oracle_ts_ms`, `recv_ms`, `gap_sec` dall'ultimo tick BTC, warning se `gap_sec > 15`.
   - In `_dispatch`: `round_start_ts`, `oracle_ts_ms`, `market_start_ms`, `ptb_set`, `skipped_reason` se `ts_ms < market_start`.
   - In `register/prime_chainlink`: logga se `last_ts_ms < market_start_ts` (tick obsoleto).
   - In `_run` stall branch: log `last_btc_msg_age_sec` prima di reconnect.
   - Formato: NDJSON su `debug-*.log` (già presente pattern).

2. **Script diagnostico nuovo: `scripts/diag_h5_btc_stream.py`**
   - Avvia feed Chainlink standalone per 30-60 min.
   - Conta tick btc/usd validi vs totali WS; logga gap >15s senza close; verifica se ptb mai settato nonostante price visibile.
   - Output: conteggio eventi H5, età ultimo msg BTC.

3. **Run soak test validazione fix**:
   - Su poly: `systemctl restart btc5min`; monitora 60+ min.
   - Criteri: `done` count ≥ 10 in 60 min; `price_to_beat not captured` < 5% dei round; nessun `chainlink stall` falso negativo.
   - Confronto pre/post fix su stesso CT.

4. **Probe esteso `probe_chainlink_ws.py`** (già presente, potenziare):
   - Aggiungi filtro symbol=="btc/usd" e alert gap >30s senza disconnect.
   - Esegui 30 min su poly e confronta con Windows.

5. **Disattivazione firewall + validazione**:
   - `pct set 103 -net0 ... firewall=0`; riavvia CT; run 30 min collector; verifica latenza TCP/ping identica e nessun aumento drop.

### Modifiche logging suggerite (priorità)

- `feed_chainlink.py`: 8 punti critici elencati nel report (sezioni 7) — implementare tutti.
- `round_runner.py`: a fine round fallito, dump `chainlink_ts_ms`, `price_to_beat`, `_ptb_start_ms`, `_final_end_ms`.
- `round_state.py`: log quando ptb skippa per ts obsoleto.

### Criteri di validazione fix

- Run ≥30-60 min su poly con ≥80% round completati (`done` count).
- Log NDJSON mostra `ptb_set: true` per round attivi e `gap_sec` monitorati senza buchi silenziosi.
- Nessun round con `btc=... ptb=-` persistente >1 sample.
- Probe 10-30 min post-fix: gap max <10s su btc/usd, 0 reconnect stall inutili.

### Raccomandazioni infra/OS

- Mantieni Debian 12 LXC (stabilità provata).
- Disattiva firewall PVE sul CT 103 (sicurezza LAN interna).
- Aggiungi logging H5-specifico prima di qualsiasi reconnect più aggressivo (rischio mascherare sintomo).
- Per futuro: considera VM Ubuntu 24.04 se si vuole kernel più recente, ma non necessario ora.

**Sintesi**: il bug è quasi certamente H5 (stall detector e timestamp filtering). Le modifiche di logging proposte permetteranno conferma e fix mirato senza cambiare OS o rete. Tutti i deliverable (ipotesi, script, criteri) sono pronti per implementazione e test su poly.

---

**Conferma**: file scritto `f:\btc5min\meetings\bug-poly-collector\responses\response-m-grok-turn01.md`. Sintesi: analisi completa Punto 01 con focus H5, test diagnostici e raccomandazioni infra conservative.