# Nota round persi — 22-07-26 (deploy price_decimals)

## Macchina / path

- Host: CT **poly** (`10.1.1.73`), `/opt/btc5min/data/`
- Causa: `systemctl restart` di **tutti** i 14 collector per caricare `price_decimals` (TXT + header)

## Quando

Restart alle **~15:17:30 UTC** (offset_in_slot 5m ≈ 150), dopo `done` di `1784733000`.

## Effetto atteso

| Timeframe | Slot tipico skippato | Motivo |
|-----------|----------------------|--------|
| 5m | `1784733300` (15:15–15:20 UTC) | in sampling al restart → `skipped (already started)` su ogni asset 5m |
| 15m | round 15m iniziato alle 15:15 | stesso skip su ogni asset 15m |

Verificare buchi nella sequenza `.bin` del giorno per ciascun prefisso (`btc5m_*`, `eth5m_*`, …).

## Conferma post-deploy

- Codice + `setup.json` con `price_decimals` su `/opt/btc5min`
- 14 unit `active` dopo restart ~15:17:30 UTC
- Skip confermato nei log: es. `btc15m` → `round 1784733300 skipped (already started)`; stesso pattern sugli altri asset (slot 5m `1784733300` / 15m partito alle 15:15)
- Bin `*_1784733300_*` **assenti** (buco atteso tra `…3000` e il round successivo `…3600` / `…4200`)
- Rigenerati **492** `.txt` del giorno `2026-07-22` (`poly_regen_day_txt.py`): header con `asset` + `price_decimals`; `px`/delta per asset (btc 0, eth/bnb/sol/hype 2, xrp/doge 4). I prezzi in header dei bin già scritti restano quelli salvati al write originale (spesso 2 decimali) finché non arriva un round nuovo post-deploy
