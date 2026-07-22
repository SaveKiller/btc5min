# Nota round persi — 22-07-26

## Macchina / path

- Host: CT **poly** (Proxmox 103, `10.1.1.73`)
- Dati: `/opt/btc5min/data/`
- Servizio: `btc5min` (restart durante deploy multi-market / cutover codice parametrico)

## Quanti round

**1** round 5m perso (nessun `.bin`).

| market_start_ts | Ora UTC | File atteso |
|-----------------|---------|-------------|
| `1784716200` | 2026-07-22 **10:30–10:35** UTC | `btc5m_1784716200_1030.bin` |

Due round successivi (`1784716500`, `1784716800`) hanno il `.bin` ma il `.txt` iniziale è fallito per `models/delta_win_v2.json` / `hour_bands.json` assenti su poly; txt backfill dopo sync. Non contano come round persi.

## Causa

Restart di `btc5min` alle **10:32:53 UTC** (offset_in_slot ≈ 166) per caricare il codice generalizzato (`--asset`/`--interval`, `ChainlinkFeed.configure`) e allineare la unit systemd a `python -m src.main --asset btc --interval 5m`.

Il round `1784716200` era già in sampling; al riavvio: `skipped (already started)`.

Il `done` più recente nel log prima del restart era del round precedente (`1784715900` alle 10:30:50), non del round in corso — quindi la finestra [150,210] da sola non protegge il round *corrente* in sampling.

## Timeline utile

1. ~10:30:00 — sampling `1784716200` avviato (codice vecchio ancora in RAM).
2. ~10:30:50 — `done` di `1784715900` (write ok).
3. ~10:31 — deploy `src/` + avvio `btc15min` (processo nuovo; non tocca i file 5m).
4. **10:32:53** — `systemctl restart btc5min` → skip `1784716200`.
5. Atteso spawn successivo: `1784716500` (10:35 UTC).

## Note

- Nessun round 15m perso in questo cutover: `btc15min` era appena partito e aveva già skippato lo slot 15m corrente (`1784716200`); primo campionamento 15m atteso su `1784717100` (10:45 UTC).
- Procedura futura: preferire restart 5m solo dopo `done` del round *corrente* (fine slot), non solo del precedente; oppure graceful drain.
