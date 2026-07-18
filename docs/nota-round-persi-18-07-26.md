# Round persi — 18 luglio 2026 (UTC)

Macchina: **poly** (`/opt/btc5min/data`). Giorno file: `2026-07-18`.

## Contesto

Cutover collector: ordine book salvato da full depth a **`book_depth: 8`**.  
Restart servizio: **`systemctl restart btc5min`** alle **09:16:45 UTC** circa.  
Procedura e lezione: [`nota-ticksaver-deploy.md`](nota-ticksaver-deploy.md).

## Quanti e quali

**2 round** assenti su disco (gap 15 minuti tra l’ultimo full e il primo depth-8).

| market_start_ts | Ora UTC inizio | Esito | Motivo |
|-----------------|----------------|-------|--------|
| `1784365500` | 09:05 | presente (`btc5m_1784365500_0905.bin`, ~914 KB, full) | — |
| **`1784365800`** | **09:10** | **perso** | Kill durante **outcome/write** post-sampling |
| **`1784366100`** | **09:15** | **perso** | Kill a metà sampling + skip al riavvio |
| `1784366400` | 09:20 | presente (`btc5m_1784366400_0920.bin`, ~165 KB, depth 8) | primo round col nuovo codice |

Nessun file `.bin` / `.txt` per `1784365800` e `1784366100`.

## Timeline (da `collector.log`)

| UTC | Evento |
|-----|--------|
| 09:10:00 | Sampling start round `1784365800` (09:10) |
| 09:15:00 | Fine sampling attesa 09:10; start sampling `1784366100` (09:15) |
| 09:16:45 | Restart `btc5min` (offset slot ~100) |
| 09:16:45 | Log: `1784366100 skipped (already started), next round 1784366400` |
| 09:20:00 | Sampling start `1784366400` (primo depth 8) |
| 09:26:10 | `done` `1784366400` → file scritto |

Il round 09:10, per analogia con i write tipici (~1–2 min dopo fine sampling), avrebbe dovuto scrivere intorno a **09:16–09:17**. Il restart a **09:16:45** lo ha interrotto prima di `write_round`.

## Impatto analisi

- Buchi nella serie 5m: **09:10** e **09:15** UTC del 2026-07-18.
- Non sono corruzioni di file: round **mai scritti**.
- I round da 09:20 in poi su poly sono depth ≤ 8; quelli precedenti del giorno restano full depth.
- Per backfill/statistiche: trattare i due ts come missing (non usare placeholder sintetici come se fossero Polymarket reali).
