# BTC5MIN

Collector per mercati Polymarket **BTC Up or Down 5m**: logga ask/bid in file binari per round.

Architettura **sync + thread**: un set di thread per round (Chainlink, CLOB, sampler), con overlap tra round consecutivi.

## Setup

```bash
pip install -r requirements.txt
```

## Avvio collector

```bash
# Orchestratore continuo (overlap round ogni 5m)
python -m src.main

# oppure
collect.bat

# Singolo round
python -m src.main --once --start-ts 1783238400
```

Log orchestratore su stdout → `data/collector.log` (via `collect.bat`).  
Righe campionamento `SAMPLE` su **stderr** (solo console).

## Strumenti

```bash
python -m src.verify data/
python -m src.reader data/btc5m_1783238400.bin
python -m src.convert data/btc5m_1783238400.bin
python -m src.convert data/btc5m_1783238400.bin -o data/btc5m_1783238400.txt
```

I file `.bin` vengono scritti in `data/`.
