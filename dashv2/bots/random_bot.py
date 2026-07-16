"""Bot di test: piazza/chiude ordini a caso."""

from __future__ import annotations

import random

from dashv2.bots.protocol import empty_actions

BOT_ID = "random"
BOT_NAME = "Random bot"
BOT_KIND = "code"
CONFIG_FILE = "random_bot.json"


class RandomBot:
    """Piazza o chiude con probabilità da config; ignora consulto."""

    def __init__(self, config: dict) -> None:
        self.name = BOT_NAME
        self.kind = BOT_KIND
        self.size_usd = float(config["size_usd"])
        self.p_place = float(config["p_place_per_tick"])
        self.p_close = float(config["p_close_per_tick"])
        self.sides = list(config["sides"])
        self._rng = random.Random(config.get("seed"))

    def on_session(self, session: dict) -> list[dict]:
        return empty_actions()

    def on_tick(self, tick: dict, session: dict | None, orders: dict | None) -> list[dict]:
        if not tick.get("tradable"):
            return empty_actions()
        if session and (session.get("round_ended") or not session.get("tradable")):
            return empty_actions()
        actions: list[dict] = []
        open_orders = (orders or {}).get("open") or []
        if open_orders and self._rng.random() < self.p_close:
            o = self._rng.choice(open_orders)
            if o.get("close_enabled"):
                actions.append({"cmd": "order.close", "payload": {"order_id": o["id"]}})
                return actions
        if self._rng.random() < self.p_place:
            side = self._rng.choice(self.sides)
            actions.append({"cmd": "order.place", "payload": {"side": side, "size_usd": self.size_usd}})
        return actions

    def on_orders(self, orders: dict) -> list[dict]:
        return empty_actions()

    def on_action(self, action: dict) -> list[dict]:
        return empty_actions()

    def on_consult(self, message: dict) -> list[dict]:
        return empty_actions()

    def on_round_start(self, session: dict) -> list[dict]:
        return empty_actions()

    def on_round_end(self, payload: dict) -> list[dict]:
        return empty_actions()


def create_bot(config: dict) -> RandomBot:
    return RandomBot(config)
