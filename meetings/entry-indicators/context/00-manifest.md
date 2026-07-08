# Manifest contesto meeting `entry-indicators`

Indice del materiale disponibile in `context/` (solo lettura durante il meeting).

## File round di esempio (`.txt`)

Campionamento **1 Hz** per 300 secondi (5 minuti). Ogni file contiene:

| Sezione | Campi |
|---------|-------|
| `header` | `market_start_ts`, `market_end_ts`, `ptb_price`, `ptb_chainlink`, `ptb_gamma`, `final_price`, `final_chainlink`, `final_gamma`, `outcome` (Up/Down), `tick_count`, `fee_rate`, eventuali `warnings` |
| `data` | per ogni secondo: `sec` (secondi alla scadenza), `time`, `quote` (UP/DOWN/----), prezzo quote in centesimi, `delta` ($ vs ptb), `gain%` (rendimento potenziale netto fee), `btc` (prezzo BTC) |

| File | Outcome | PTB → Final BTC | Note |
|------|---------|-----------------|------|
| `btc5m_1783476600.txt` | Up | 62781.66 → 62861.82 | warning ptb_gamma |
| `btc5m_1783476900.txt` | Down | 62854.37 → 62835.38 | |
| `btc5m_1783477200.txt` | Up | 62829.64 → 62872.56 | |
| `btc5m_1783479600.txt` | Up | 62933.20 → 62993.62 | |
| `btc5m_1783479900.txt` | Down | 62993.29 → 62967.66 | |
| `btc5m_1783480200.txt` | Up | 62967.69 → 63022.65 | |
| `btc5m_1783481100.txt` | Up | 62962.45 → 63005.19 | quote parte da ---- a sec 300 |

## File binari (non inclusi)

I file `.bin` corrispondenti in `data/bin/` contengono in aggiunta il **LOB completo** (order book). Non sono nel contesto: vanno richiesti esplicitamente se servono per una proposta.

## Scala produzione

- **288 round/giorno** (uno ogni 5 minuti)
- Migliaia di file nel tempo per backtest, calibrazione soglie e validazione statistica degli indici proposti

## Colonne chiave per gli indici

Valori disponibili **ogni secondo** senza LOB:

- tempo residuo (`sec`, 300 → 1)
- direzione/prezzo quote (`quote`, centesimi)
- distanza da price-to-beat (`delta`, `btc` vs `ptb_price` nell'header)
- rendimento potenziale (`gain%`, già netto di `fee_rate`)
- esito noto a posteriori (`outcome` nell'header) — utile per validazione, non per decisione live
