"""Contratto plugin strategy (shim attuale: BotPlugin in *_bot.py).

Le Strategy vere (DETERMINISTICA / INFERENZIALE / AGENTICA) arriveranno in un piano separato.
Il processo bot resta l'unica interfaccia verso il server; le strategy vivono solo dentro il bot.
"""

from __future__ import annotations

from typing import Protocol


class BotPlugin(Protocol):
    """Interfaccia minima di una strategy caricata nel processo bot (shim legacy)."""

    name: str
    kind: str  # code | config | ai  (legacy; tipi target: deterministic | inferential | agentic)

    def on_session(self, session: dict) -> list[dict]: ...
    def on_tick(self, tick: dict, session: dict | None, orders: dict | None) -> list[dict]: ...
    def on_orders(self, orders: dict) -> list[dict]: ...
    def on_action(self, action: dict) -> list[dict]: ...
    def on_consult(self, message: dict) -> list[dict]: ...
    def on_round_start(self, session: dict) -> list[dict]: ...
    def on_round_end(self, payload: dict) -> list[dict]: ...


def empty_actions() -> list[dict]:
    return []
