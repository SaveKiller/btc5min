# Report bug: collector su poly — round persi e feed Chainlink

**Data:** 2026-07-07  
**Stato:** analisi sospesa; riprendere da sezione 7 (strumentazione)  
**Log analizzati:** `/opt/btc5min/data/collector.log` (copia locale: `data/collector-poly.log`)  
**Dati scaricati:** 11 file `.txt` in `data/bin/` (tutti quelli presenti sul server al momento del download)

---

## 0. Ambiente e infrastruttura

Il bug si manifesta sul **collector di produzione** in LAN, non sul PC dev Windows.

### Nodo hypervisor Proxmox (host fisico)

| Campo | Valore |
|-------|--------|
| Hostname | `proxmox` |
| IP LAN | `10.1.1.70/24` (bridge `vmbr0` su `enp87s0`) |
| Accesso SSH | alias `proxmox-root` → `root@10.1.1.70` (chiave `proxmox`) |
| OS host | **Debian GNU/Linux 12 (bookworm)** |
| Proxmox VE | **8.4.0** (`pve-manager 8.4.1`) |
| Kernel host | `6.8.12-10-pve` (build 2025-04-18) |
| CPU host | Intel **i9-13900HK**, 20 thread (1 socket), max 5.4 GHz |
| RAM host | **31 GB** totali (~6.3 GB usati, ~24 GB disponibili; swap assente) |
| Storage host | ZFS pool `rpool` (~151 GB liberi su root); CT su `local-zfs` |
| Gateway LAN | `10.1.1.1` (Fritz.box) |
| Uptime host al check | **~6 giorni** (nodo stabile) |
| Altri CT sul nodo | CT 102 `dualbot` (stopped), CT **104** `lobsaver` `10.1.1.77` (running), CT 120 `mem0` (stopped) |
| VM sul nodo | VM 100 `Win11`, VM 101 `Play1` (entrambe stopped) |

### Container CT 103 — `poly` (guest LXC)

| Campo | Valore |
|-------|--------|
| VMID | **103** |
| Hostname | `poly` (`poly.fritz.box`) |
| Tipo | **LXC unprivileged** (`unprivileged: 1`, `container=lxc`) |
| Stato al check | **running** (uptime guest ~1.7 giorni) |
| OS guest | **Debian GNU/Linux 12 (bookworm)** |
| Kernel guest | `6.8.12-10-pve` (kernel condiviso con host PVE) |
| Architettura | `amd64` |
| IP LAN | `10.1.1.73/24` |
| Gateway / DNS | `10.1.1.1` (router Fritz.box, `search fritz.box`) |
| Rete CT | `eth0` veth su bridge `vmbr0`, MAC `BC:24:11:F1:F7:75`, **firewall PVE abilitato** (`firewall=1`), **MTU 1500** |
| vCPU allocate | **6** core (`cores: 6`, `nesting=1`) |
| RAM allocate | **2048 MB** |
| Swap configurata | **1024 MB** (config PVE; non montata/visibile nel guest al check) |
| Rootfs | `local-zfs:subvol-103-disk-0`, **101 GB** (`rpool/data/subvol-103-disk-0`, ~1.9 GB usati) |
| Accesso SSH | alias `ticksaver` → `root@10.1.1.73` (chiave dedicata) |
| Scopo | macchina 24/7 dedicata al salvataggio tick (vedi `AGENTS.md`) |

### Sistema operativo (dentro il CT)

| Campo | Valore |
|-------|--------|
| Distribuzione | **Debian GNU/Linux 12 (bookworm)** — non Ubuntu |
| Kernel guest | `Linux poly 6.8.12-10-pve #1 SMP PREEMPT_DYNAMIC PMX` x86_64 |
| Timezone | **UTC** (`Etc/UTC`), clock sincronizzato |
| Uptime al check | ~1 giorno 18 ore (container stabile, non reboot frequente) |

### Risorse allocate al CT

| Risorsa | Valore |
|---------|--------|
| RAM | **2 GB** (config PVE; uso tipico ~36 MB app + ~187 MB cache) |
| vCPU | **6** core su host i9-13900HK (20 thread totali) |
| Disco | ZFS `subvol-103-disk-0`, **101 GB** totali, **~2%** usato |
| Dati app | `/opt/btc5min/data/` → **2.6 MB** (11 round al momento del download) |

### Stack applicativo su poly

| Campo | Valore |
|-------|--------|
| Path deploy | `/opt/btc5min/` |
| Python sistema | 3.11.2 (Debian apt, non usato dal servizio) |
| Python runtime | **3.12.10** (compilato `make altinstall` in `/usr/local/bin/python3.12`) |
| Virtualenv | `/opt/btc5min/venv/` |
| Entrypoint | `venv/bin/python3 -m src.main` |
| Dipendenze | `httpx 0.28.1`, `websocket-client 1.9.0`, `numpy 2.5.1` |
| Servizio | `btc5min.service` (systemd, `Restart=always`, `RestartSec=5`) |
| Log stdout | append su `/opt/btc5min/data/collector.log` |
| Log stderr (SAMPLE) | journal systemd |
| User servizio | `root` |
| Deploy codice | rsync/scp da PC dev `F:\btc5min` (no git clone su poly) |

### Stato servizio al momento del report

| Campo | Valore |
|-------|--------|
| Ultimo avvio | 2026-07-06 **22:38:38 UTC** |
| Ultimo stop | 2026-07-07 **02:40:16 UTC** (stop manuale / analisi) |
| Durata run analizzato | **~4 h 2 min** |
| Stato attuale | **inactive (dead)** — servizio abilitato al boot ma fermo per debug |
| CPU run | ~13 min su 4 h |

### Rete e connettività verso Polymarket

| Metrica | Valore poly | Note |
|---------|-------------|------|
| Ping `gamma-api.polymarket.com` | ~16 ms avg, 0% loss | check 2026-07-07 |
| Latenza TCP (probe precedente) | ~24 ms | verso endpoint Polymarket |
| `tcp_keepalive_time` | **7200 s** | kernel default; collector usa ping WS ogni 5 s |
| `ip_forward` | 0 | CT non fa routing |
| `nf_conntrack_count` | 0 | nessuna pressione NAT interna al CT |
| Probe 10 min vs Windows | identico (579 tick, gap max ~8.3 s) | vedi sezione 4, H1/H2 |

### Confronto con ambiente dev (probe)

| Campo | PC dev (`RyzenHome`) | poly (CT 103 su Proxmox) |
|-------|----------------------|--------------------------|
| OS | **Windows 11 Pro** (build 26200) | Debian 12 bookworm LXC unprivileged |
| Host | PC fisico LAN | Nodo `proxmox` `10.1.1.70`, CT 103 |
| Python progetto | **3.12.10** (venv locale `.venv`) | **3.12.10** (venv `/opt/btc5min`) |
| Avvio collector | `collect.bat` | `systemd btc5min.service` |
| Rete | stessa LAN `10.1.1.0/24` via Fritz.box | idem (`10.1.1.73` → gateway `10.1.1.1`) |
| Bug riprodotto | no (probe OK) | **sì** (round persi in produzione) |

### File di debug già presenti su poly

| Path | Note |
|------|------|
| `/opt/btc5min/debug-9c51e0.log` | ~138 KB, sessione debug precedente |
| `/opt/btc5min/data/collector.log` | log principale analizzato |

### Configurazione PVE CT 103 (dump `pct config 103`, check 2026-07-07)

```
arch: amd64
cores: 6
features: nesting=1
hostname: poly
memory: 2048
net0: name=eth0,bridge=vmbr0,firewall=1,gw=10.1.1.1,hwaddr=BC:24:11:F1:F7:75,ip=10.1.1.73/24,type=veth
ostype: debian
rootfs: local-zfs:subvol-103-disk-0,size=101G
swap: 1024
unprivileged: 1
```

### Alias SSH utili

| Alias | Target | Uso |
|-------|--------|-----|
| `proxmox-root` | `root@10.1.1.70` | gestione nodo PVE, `pct config/status` |
| `ticksaver` | `root@10.1.1.73` | deploy, log, restart `btc5min` su poly |
| `lobsaver` | `root@10.1.1.77` | CT 104 analogo (collector LOB, riferimento deploy) |

---

## 1. Sintomo

Il collector su poly produce **pochi round** rispetto al tempo di attività. In ~3 ore di run (avvio 2026-07-06 22:38 UTC) sono stati salvati **11 file** (10 round completi a 300 sec + 1 parziale a 260 sec), mentre ci si aspetterebbe ~36 round da 5 minuti.

Il download locale non era incompleto: sul server c'erano effettivamente solo 11 coppie `.bin`/`.txt`.

---

## 2. Round salvati vs persi

### Round salvati con successo

| Round | Ora UTC (fine) | Note |
|-------|----------------|------|
| 1783377600 → 1783379100 | 22:45 – 23:10 | 6 round OK |
| 1783384500 | 00:40 | **parziale: 260 sec** (manca ptb per 222 sec) |
| 1783384800 → 1783385700 | 00:45 – 01:00 | 4 round OK |

### Errori principali nel log

| Tipo errore | Occorrenze (circa) |
|-------------|-------------------|
| `chainlink price_to_beat not captured` | molte (maggioranza dei fallimenti) |
| `chainlink final not captured` | 2 round (1783379400, 1783386000) |
| `chainlink ws error` (disconnect WS) | **1** (`Going away`, 00:38:39 UTC) |
| `clob ws drop` | 5 |
| `chainlink stall` (reconnect client) | **0** |
| Round `done` | 11 |

**Osservazione chiave:** i round falliscono **molto più spesso** di quanto il feed Chainlink si disconnetta. Il problema percepito come “disconnessioni frequenti” non è supportato dal log: c'è **1 sola** chiusura WS Chainlink esplicita in ore di run.

---

## 3. Timeline del log (estratti significativi)

```
22:38  avvio servizio, round 1783377300 skipped (già iniziato)
22:45–23:10  6 round OK
23:10  round 1783379100 done
23:15  round 1783379400 failed: chainlink final not captured
23:15–00:30  ~17 round consecutivi: price_to_beat not captured (NESSUN log di disconnect Chainlink)
00:38:39  WARNING chainlink ws error: fin=1 opcode=8 data=b'\x03\xe9Going away'
00:38:43  round 1783384500 price_to_beat catturato con lag=222s → file parziale (260 sec)
00:45–01:00  4 round OK
01:05+  nuovi fallimenti ptb / final
```

Al momento dell'analisi (01:45 UTC), i log systemd mostravano ancora `btc=63985.15 ptb=-`: prezzo Chainlink presente in memoria ma **price_to_beat mai catturato** per il round corrente.

---

## 4. Ipotesi valutate

### H1 — Container Proxmox / rete LXC causa disconnect WS

**Esito: REJECTED**

Probe identico al collector (subscribe RTDS + ping testuale ogni 5s) eseguito per **10 minuti** su poly e su Windows:

| Metrica | Windows | Poly (Debian 12 CT) |
|---------|---------|---------------------|
| Tick `btc/usd` | 579 | 579 |
| Gap max tra tick BTC | 8.35 s | 8.29 s |
| Gap p95 | 1.59 s | 1.54 s |
| Disconnect server-side | 0 | 0 |

Ambiente poly verificato: MTU 1500, gateway `10.1.1.1`, `nf_conntrack_count=0`, RAM 119/2048 MB, latenza TCP verso Polymarket ~24 ms.

Script probe: `scripts/probe_btc_gaps.py` (e variante completa `scripts/probe_chainlink_ws.py`).

### H2 — Debian 12 / TCP stack

**Esito: REJECTED**

Stesso comportamento del probe su Windows. `tcp_keepalive_time=7200` sul kernel non influisce: il collector usa ping applicativo (`"ping"` testuale ogni 5s in `feed_chainlink.py`), non keepalive TCP di `run_forever`.

### H3 — Disconnect frequenti lato server Polymarket RTDS

**Esito: REJECTED** (per “frequenti”)

Un solo evento `Going away` (WebSocket close **1001**, chiusura volontaria lato server) in tutto il log. È un comportamento del server RTDS, non specifico di Debian/container.

### H4 — NAT/router LAN (10.1.1.1) droppa connessioni long-lived

**Esito: INCONCLUSIVE**

Possibile contributo per CLOB (`ws drop` ×5), meno plausibile per RTDS con traffico ogni ~1s. Il probe 10 min non ha mostrato drop.

### H5 — WS “connessa” ma stream BTC inutilizzabile (ipotesi attiva)

**Esito: CONFIRMED (direzione principale)**

Evidenze:

1. Lunghi periodi di fallimento **senza** log `chainlink ws error` né `chainlink stall`.
2. Sampler logga `btc=...` ma `ptb=-` → `chainlink_price` valorizzato (anche da `prime_chainlink`) ma `price_to_beat` mai impostato.
3. Dopo il reconnect `Going away`, ptb catturato con **lag oracle 222s** (round parziale).
4. Lo **stall detector** in `feed_chainlink.py` aggiorna `_last_msg_ts` **solo** su messaggi `btc/usd`. Se la WS resta viva con altri simboli ma BTC si ferma, non scatta reconnect e non compare nulla nel log.

---

## 5. Meccanismo sospetto (codice)

### Cattura `price_to_beat` (`round_state.py`)

```python
def apply_chainlink(self, value, ts_ms, recv_ms):
    self.chainlink_price = value
    self.chainlink_ts_ms = ts_ms
    if ts_ms < self._ptb_start_ms: return   # ← esce senza impostare ptb
    if self._ptb_ts_ms is None or ts_ms < self._ptb_ts_ms:
        self.price_to_beat = value
```

Se i tick oracle hanno `timestamp < market_start_ts` (ritardo oracle, batch storico dopo reconnect, o dati “priming” obsoleti), il prezzo BTC compare nei log ma **ptb resta `None`** per tutto il round → eccezione a fine round.

### Priming alla registrazione (`feed_chainlink.py`)

All'`register()` di un nuovo round, viene chiamato `prime_chainlink(last_value, last_ts_ms)`. Se `last_ts_ms` è anteriore a `market_start_ts`, il sampler può partire con un prezzo visibile ma ptb ancora assente fino al primo tick oracle con timestamp valido.

### Stall detector (`feed_chainlink.py`)

```python
STALL_RECONNECT_SEC = 45.0
# _last_msg_ts aggiornato solo dopo filtro symbol == "btc/usd"
```

Blind spot: connessione apparentemente sana, altri simboli in arrivo, BTC fermo → nessun stall, nessun log, round perso.

---

## 6. File e script utili

| Path | Descrizione |
|------|-------------|
| `data/collector-poly.log` | Copia del log poly al momento dell'analisi |
| `data/bin/*.txt` | 11 round scaricati da poly |
| `scripts/probe_chainlink_ws.py` | Probe generico RTDS 2 min (tutti i simboli) |
| `scripts/probe_btc_gaps.py` | Probe 10 min focalizzato su gap tick `btc/usd` |
| `docs/ssh-commands.txt` | Comandi SSH rapidi (`ticksaver` → poly) |

### Comandi rapidi per riprendere

```bash
# Stato servizio
ssh ticksaver systemctl status btc5min

# Coda log
ssh ticksaver tail -f /opt/btc5min/data/collector.log

# Conteggio errori
ssh ticksaver "grep -cE 'chainlink ws error|ws drop|price_to_beat not captured| done ' /opt/btc5min/data/collector.log"

# Probe 10 min su poly
scp scripts/probe_btc_gaps.py ticksaver:/tmp/
ssh ticksaver "/opt/btc5min/venv/bin/python3 /tmp/probe_btc_gaps.py 600"
```

---

## 7. Prossimo passo: strumentazione di debug

**Obiettivo:** capire perché il feed BTC/oracle smette di produrre tick **utilizzabili** (ptb/final) pur con WS spesso ancora up — non aggiungere pezze di reconnect.

**Log di debug:** `debug-7f092d.log` (NDJSON, root repo)  
**Session ID:** `7f092d`

### Punti da instrumentare in `src/feed_chainlink.py`

| # | Punto | Cosa loggare | Ipotesi |
|---|-------|--------------|---------|
| 1 | `_on_open` | `conn_open_ts`, subscribe inviato | baseline connessione |
| 2 | `_on_close` | `close_status_code`, `close_msg`, `intentional_close`, `connected_sec`, `last_btc_msg_age_sec` | H3: close server |
| 3 | `_on_error` | `error`, `intentional_close`, età ultimo msg BTC | H3/H5 |
| 4 | `_close_ws` | `intentional`, motivo (`stall` vs `stop`) | distinguere client vs server |
| 5 | `_run` (branch stall) | prima di `_close_ws` per stall: `stall_sec`, `last_btc_msg_age` | H5: stall non scattato |
| 6 | `_on_message` (btc/usd) | ogni tick: `oracle_ts_ms`, `recv_ms`, `gap_sec` dall'ultimo; se `gap_sec > 15` log warning | H5: buchi stream BTC |
| 7 | `_dispatch` | per ogni round attivo: `round_start_ts`, `oracle_ts_ms`, `market_start_ms`, `ptb_set`, `skipped_reason` se `ts_ms < market_start` | H5: timestamp oracle |
| 8 | `_ping_loop` (except) | fallimento invio ping | connessione zombie |

### Payload NDJSON (formato)

```json
{
  "sessionId": "7f092d",
  "hypothesisId": "H5",
  "location": "feed_chainlink._dispatch",
  "message": "ptb skip",
  "data": {
    "round": 1783388700,
    "oracle_ts_ms": 1783388699000,
    "market_start_ms": 1783388700000,
    "value": 63985.15
  },
  "timestamp": 1783388700123,
  "runId": "poly-overnight"
}
```

Helper compatto (da aggiungere in `feed_chainlink.py`):

```python
_DBG_LOG = Path(__file__).resolve().parent.parent / "debug-7f092d.log"

def _dbg(location, message, data, hypothesis_id="H5", run_id="poly"):
    # #region agent log
    with open(_DBG_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "sessionId": "7f092d", "hypothesisId": hypothesis_id,
            "location": location, "message": message, "data": data,
            "timestamp": int(time.time() * 1000), "runId": run_id,
        }, default=str) + "\n")
    # #endregion
```

### Instrumentazione opzionale in `src/round_runner.py`

Già presente debug residuo sessione `9c51e0` (`debug-9c51e0.log`) — da **unificare o sostituire** con `7f092d` al riprendere:

- `sampler start`: lag dopo `market_start_ts`
- `first sample`: `ptb_ready`
- `ptb captured`: `lag_ptb_sec`, tick count
- **da aggiungere:** a fine round fallito, dump `chainlink_ts_ms`, `price_to_beat`, `_ptb_start_ms`, `_final_end_ms`

### Deploy su poly e raccolta

1. Aggiungere instrumentazione in `feed_chainlink.py` (e aggiornare `round_runner.py`).
2. `scp`/`rsync` codice su `/opt/btc5min/`.
3. `ssh ticksaver systemctl restart btc5min`
4. Lasciare girare **≥ 30–60 min** (coprire almeno 6–12 round).
5. Scaricare: `scp ticksaver:/opt/btc5min/debug-7f092d.log data/`
6. Analizzare: correlare gap BTC, skip ptb per timestamp, eventuali close 1001.

### Criteri di conferma nel log debug

| Pattern nel debug log | Interpretazione |
|----------------------|-----------------|
| `gap_sec > 45` senza `_on_close` | BTC fermo, WS up → bug stall detector (H5 confermata) |
| `skipped_reason: ts_ms < market_start` ripetuto per un round intero | oracle timestamp in ritardo vs wall clock |
| `_on_close` con code 1001 | evento server RTDS (sporadico, non causa principale) |
| `ptb_set: true` ma round failed | spostare analisi su `final_chainlink` / altro |

---

## 8. Cosa NON fare (per ora)

- **Non** aggiungere reconnect più aggressivi come prima risposta: maschera il sintomo senza spiegare perché i tick BTC non sono utilizzabili.
- **Non** attribuire il problema a Debian 12 o Proxmox: probe runtime li esclude come causa primaria.
- **Non** rimuovere la instrumentazione finché un run post-fix non conferma round stabili con log.

---

## 9. Checklist ripresa lavoro (domani)

- [ ] Aggiungere `_dbg()` in `feed_chainlink.py` (punti 1–8 sopra)
- [ ] Pulire/unificare debug `9c51e0` in `round_runner.py`
- [ ] Deploy su poly + restart `btc5min`
- [ ] Run 30–60 min, scaricare `debug-7f092d.log`
- [ ] Analizzare: gap BTC, skip timestamp, close frame
- [ ] Solo dopo evidenza log: fix mirato (es. stall su assenza BTC, gestione timestamp oracle, ecc.)

---

## 10. Riferimenti codice

| File | Ruolo |
|------|-------|
| `src/feed_chainlink.py` | WS RTDS singleton, ping, stall, dispatch Chainlink |
| `src/feed_clob.py` | WS CLOB per round (disconnect separati, meno critici) |
| `src/round_state.py` | Logica ptb/final da timestamp oracle |
| `src/round_runner.py` | Orchestrazione round, eccezioni ptb/final |
| `src/main.py` | Avvio `ChainlinkFeed` + spawn round ogni 5 min |
