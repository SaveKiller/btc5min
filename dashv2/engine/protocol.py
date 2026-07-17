"""Contratto plugin Engine (replay / live / …).

Il processo Engine è la shell stabile (pipe col server). Il plugin porta
sorgente round, clock, ordini, settlement, account e history.
Una sola plugin attiva per processo; scelta solo a startup via setup.json
(`engine_plugin`). Nessun hot-swap a runtime.
"""

from __future__ import annotations

from typing import Protocol


class EnginePlugin(Protocol):
    """Interfaccia comune di un plugin caricato nel processo Engine.

    Lo shell Engine non conosce regole replay vs Polymarket: inoltra i comandi
    IPC al plugin e il plugin emette eventi. Ogni plugin possiede il proprio
    backend account e le relative regole.
    """

    plugin_id: str  # replay | live | …
    account_backend: str  # local | polymarket | …

    def run(self) -> None:
        """Loop principale: drain comandi IPC + clock/eventi di dominio."""
        ...


# --- Responsabilità obbligatorie del plugin (via _handle_cmd / emit) ---
#
# Round / timeline
#   - Caricare o sottoscrivere la sorgente round (file .bin/.txt | feed live)
#   - Clock / seek / play / pause (replay) oppure sync feed (live)
#   - Emit: session, tick, chart, round_end, error
#
# Trading (stessa semantica verso bridge; implementazione diversa)
#   - order.size / order.preview / order.place / order.close / order.cancel
#   - Fee e walk book: replay su snapshot tick; live su CLOB Polymarket
#   - Tag source/actor: user | bot
#
# Account (regole e persistenza *del plugin*, non dello shell)
#   - account.list / select / create / rename / update
#   - replay: ledger JSON in history/accounts/ (balance iniziale, note, stats)
#   - live: account Polymarket dell'utente (API keys / wallet), regole diverse
#   - Switch account bloccato se ci sono open orders (o equivalente live)
#   - Emit: accounts (lista + active + stats)
#
# Settlement
#   - Chiusura posizioni a fine round / risoluzione mercato
#   - Mapping won/lost, fee exit, append o sync verso backend account
#   - Emit: orders, history, accounts, round_end
#
# History
#   - Snapshot verso UI (evento history): ledger + closed live della sessione
#   - Anti-spoiler outcome finché il round non è settled (regole plugin)
#   - Export: oggi CSV lato client dalla history; futuro eventuale comando
#     dedicato (es. history.export) implementato dal plugin
#
# Bot / strategy (stato di selezione nel plugin attivo)
#   - bot.list / bot.set_active — stato active strategies + master switch
#   - strategy.list / create / rename / delete / load / unload — catalogo JSON + active set
#   - Emit: bot.status (lo shell non gestisce strategy; solo il bot process)
