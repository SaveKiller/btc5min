# Nota round persi — 22-07-26 (reboot resize RAM)

## Macchina / path

- Host: CT **poly** (Proxmox 103, `10.1.1.73`)
- Dati: `/opt/btc5min/data/`
- Causa: riavvio CT dopo upgrade RAM **2 GB → 6 GB** (core già 6)

## Round persi / skippati al boot

Servizi ripartiti alle **12:03:01 UTC** (`collector start`).

| Servizio | market_start_ts | Ora UTC | Effetto |
|----------|-----------------|---------|---------|
| `btc5min` | `1784721600` | 12:00–12:05 | `skipped (already started)` — nessun `.bin` completo di questo slot post-boot |
| `btc15min` | `1784721600` | 12:00–12:15 | stesso skip; ripresa sul round successivo `1784722500` (12:15) |

Possibile buco anche su slot 5m immediatamente precedenti se il write era in corso al poweroff; verificare sequenza `btc5m_*` intorno a 11:55–12:05.

## Post-boot (ok)

- `free`: **6144 MB** total, MemAvailable ≈ 6060 MB
- `nproc`: **6**
- `btc5min` / `btc15min`: active + enabled
- Sampling 5m ripreso: `1784721900` (12:05) ok
