# Nota: deploy ticksaver (collector su poly)

Host: CT **poly** (Proxmox 103, `10.1.1.73`), app `/opt/btc5min`, servizio `btc5min`, SSH `ticksaver`.

## Cutover depth-8 (18 luglio 2026)

Deploy del truncate orderbook a `book_depth: 8` (campionamento 1 Hz invariato).

Procedura adottata (da piano Gate B):

1. Sync codice su `/opt/btc5min` a collector ancora in esecuzione (full depth).
2. Attesa finestra “metà round” con `offset_in_slot = time % 300` ∈ **[90, 210]**.
3. `systemctl restart btc5min`.
4. Atteso: perdere **1** round (quello in sampling, poi skippato al riavvio).

### Esito reale

Si sono persi **2 round**, non 1. Dettaglio e timeline: [`nota-round-persi-18-07-26.md`](nota-round-persi-18-07-26.md).

Causa della seconda perdita: la finestra [90, 210] ignora che il **round precedente** può essere ancora vivo in fase **outcome / write** fino a ~`outcome_wait_sec` (120 s) dopo il boundary. Un restart a ~offset 100 del round corrente può uccidere quel write prima di `write_round`.

## Procedura consigliata la prossima volta (obiettivo: 1 solo round perso)

1. Sync codice **senza** restart.
2. Nel log (`collector.log` / journal): attendere la riga **`done … seconds`** del round che sta chiudendo (write completato).
3. Solo dopo quel `done`, e con il round *successivo* già in sampling da abbastanza tempo, scegliere un `offset_in_slot` più stretto, es. **[150, 210]** (o verificare a occhio che non ci siano due `round-*` rilevanti ancora in outcome).
4. Evitare comunque gli ultimi ~60–10 s del slot (prep del round dopo / overlap).
5. Dopo restart: confermare uno `skipped (already started)` e **un solo** buco di 5 minuti nella sequenza `.bin` del giorno.
6. Verificare il primo `.bin` nuovo (size / depth / `verify`) come da checklist del piano depth-8.

Alternative future (non usate in quel cutover): graceful drain in `main.py` (niente nuovi spawn, `join` dei runner fino a write, poi exit) → 0 round persi, a costo di un restart più lungo.

## Servizi collector (multi-token)

Su poly girano **14** unit systemd (7 asset × 5m+15m), stessi `data/`, prefissi file `{asset}{interval}_*`.

| Asset | 5m | 15m | Log |
|-------|----|-----|-----|
| btc | `btc5min` | `btc15min` | `collector.log` / `collector-btc15m.log` |
| eth | `eth5m` | `eth15m` | `collector-eth5m.log` / `collector-eth15m.log` |
| sol | `sol5m` | `sol15m` | idem pattern |
| xrp | `xrp5m` | `xrp15m` | |
| doge | `doge5m` | `doge15m` | |
| bnb | `bnb5m` | `bnb15m` | |
| hype | `hype5m` | `hype15m` | |

Template in [`deploy/`](../deploy/). Generatore: `python scripts/gen_collector_units.py --write deploy`.

Il 5m BTC resta il servizio “storico” primario; gli altri sono affiancati. Restart di un token non tocca gli altri processi.

## Riferimenti

- Piano: `.cursor/plans/orderbook_depth_8_543aca92.plan.md`
- Deploy base poly: `meetings/bug-poly-collector/context/deploy-ct-lan-poly.md`
- Inventario/capacità: [`inventory-capacity-updown-22-07-26.md`](inventory-capacity-updown-22-07-26.md)
- Risorse BTC 15m: [`nota-risorse-btc15m-22-07-26.md`](nota-risorse-btc15m-22-07-26.md)
- **Report sintetico multi-token:** [`report-collector-multitoken-poly-22-07-26.md`](report-collector-multitoken-poly-22-07-26.md)
