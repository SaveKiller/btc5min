"""Plugin Engine replay: round da file, clock 1 Hz, account ledger locale."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from multiprocessing.connection import Connection
from pathlib import Path

from dashv2 import ipc
from dashv2.execution_log import append_execution
from dashv2.history import (
    account_summary, accounts_dir, append_settled_orders, compute_stats, create_account,
    list_accounts, load_account, load_active_account_id, order_rows_for_run, order_rows_from_ledger,
    rename_account, save_active_account_id, update_account,
)
from dashv2.sessions import create_session
from dashv2.orders import OrderEngine
from dashv2.rounds import LoadedRound, RoundRepository
from dashv2.strategies import (
    clone_strategy, create_strategy, delete_strategy, list_strategies, load_active_ids,
    load_strategy, save_active_ids, strategies_dir, strategy_summary, update_strategy,
)


def _actor_from_payload(payload: dict) -> str:
    actor = payload.get("actor", "user")
    if actor not in ("user", "bot"):
        raise Exception(f"invalid actor: {actor!r}")
    return actor


def _dwin_public(tick: dict) -> dict:
    """DWinA/B dal txt: P(vittoria) per il lato del segno delta (come nel feed)."""
    delta = tick.get("delta_usd")
    dwin_a = tick.get("dwin_a")
    dwin_b = tick.get("dwin_b_pct")
    ref = "Up" if delta is not None and delta >= 0 else ("Down" if delta is not None else None)
    a_pct = int(round(dwin_a["p_win"] * 100)) if dwin_a and dwin_a.get("p_win") is not None else None
    return {
        "dwin_ref_side": ref,
        "dwin_a": {"p_win_pct": a_pct, "n": dwin_a["n"] if dwin_a else None},
        "dwin_b": {"p_win_pct": dwin_b},
    }


def _ask_liq_usd(asks: list, depth: int) -> float:
    """Notional ask USD sui primi `depth` livelli (price × size, senza fee)."""
    return sum(p * size for p, size in asks[:depth])


def _public_tick(tick: dict | None, sec: int, seq: int, gap: bool, book=None) -> dict:
    if tick is None or gap:
        return {
            "seq": seq, "sec": sec, "gap": True, "chainlink_btc": None, "delta_usd": None,
            "up_mid_c": None, "down_mid_c": None, "up_ask_c": None, "down_ask_c": None,
            "up_bid_c": None, "down_bid_c": None,
            "vol": {}, "risk": _empty_side_risk(), "dwin_ref_side": None,
            "dwin_a": None, "dwin_b": None, "tradable": False, "liq2_ask_usd": None,
        }
    dwin = _dwin_public(tick)
    liq2 = None
    if book is not None:
        side = tick.get("majority_side")
        if side == "Up":
            liq2 = _ask_liq_usd(book.up_asks, 2)
        elif side == "Down":
            liq2 = _ask_liq_usd(book.down_asks, 2)
    return {
        "seq": seq, "sec": sec, "gap": False, "chainlink_btc": tick["chainlink_btc"],
        "chainlink_stale": tick["chainlink_stale"], "delta_usd": tick["delta_usd"],
        "up_mid_c": tick["up_mid_c"], "down_mid_c": tick["down_mid_c"],
        "up_ask_c": int(round(tick["up_ask"] * 100)) if tick["up_ask"] is not None else None,
        "down_ask_c": int(round(tick["down_ask"] * 100)) if tick["down_ask"] is not None else None,
        "up_bid_c": int(round(tick["up_bid"] * 100)) if tick["up_bid"] is not None else None,
        "down_bid_c": int(round(tick["down_bid"] * 100)) if tick["down_bid"] is not None else None,
        "majority_side": tick["majority_side"], "vol": tick["vol"], "risk": tick["side_risk"],
        "dwin_ref_side": dwin["dwin_ref_side"], "dwin_a": dwin["dwin_a"], "dwin_b": dwin["dwin_b"],
        "tradable": not tick["partial"] and not tick["gap"] and tick["chainlink_btc"] is not None,
        "liq2_ask_usd": liq2,
    }


def _empty_side_risk() -> dict:
    blank = {"rq": None, "rs": None}
    return {"Up": dict(blank), "Down": dict(blank)}


class ReplayEngine:
    """Plugin replay: file .bin/.txt, ordini simulati, account JSON locale."""

    plugin_id = "replay"

    def __init__(self, cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
        self.cfg = cfg
        self.cmd_conn = cmd_conn
        self.evt_conn = evt_conn
        self.repo = RoundRepository(cfg["data_dir"], cfg["stall_reconnect_sec"])
        self.orders = OrderEngine(cfg["default_order_size_usd"], cfg["default_order_size_usd"])
        self.accounts_root = accounts_dir(Path(cfg["history_dir"]))
        self.active_account_id: str | None = load_active_account_id(self.accounts_root)
        self.strategies_root = strategies_dir(Path(cfg["history_dir"]))
        self.active_strategy_ids: list[str] = load_active_ids(self.strategies_root)
        self.loaded: LoadedRound | None = None
        self.sec = 300
        self.playing = False
        self.round_ended = False
        self.seq = 0
        self.session_id: str | None = None
        self.session_started_at_utc: str | None = None
        self.replay_speed = 1
        self._next_tick_at = 0.0
        self._last_tick: dict | None = None
        self._prev_candles: list[dict] = []
        self._round_advanced = False
        self.bot_active = False
        self.engine_plugin = "replay"
        self.round_source = "replay"
        self.account_backend = "local"

    def run(self) -> None:
        self._emit_event("bootstrap", self._bootstrap_payload())
        self._emit_accounts()
        next_tick_at = 0.0
        while True:
            while self.cmd_conn.poll(0):
                self._handle_cmd(self.cmd_conn.recv())
            if self.playing and self.loaded and not self.round_ended:
                now = time.monotonic()
                if now >= self._next_tick_at:
                    self._advance_sec()
                    self._next_tick_at = now + (1.0 / self.replay_speed)
            time.sleep(0.02)

    def _bootstrap_payload(self) -> dict:
        return {
            "round_days": self.repo.list_days(),
            "round_nav": self.repo.list_nav_ts(),
            "default_order_size_usd": self.cfg["default_order_size_usd"],
            "host": self.cfg["host"], "port": self.cfg["port"],
            "accounts": list_accounts(self.accounts_root),
            "active_account_id": self.active_account_id,
            "engine_plugin": self.engine_plugin, "account_backend": self.account_backend,
            "strategies": list_strategies(self.strategies_root),
            "active_strategy_ids": list(self.active_strategy_ids),
            "bot_attach_allowed": self._bot_attach_allowed(), "bot_active": self.bot_active,
        }

    def _handle_cmd(self, msg: dict) -> None:
        if msg.get("kind") != "request":
            raise Exception(f"unexpected ipc message: {msg}")
        rid, cmd, payload = msg["request_id"], msg["cmd"], msg.get("payload") or {}
        try:
            if cmd == "round.load":
                result, after = self._cmd_round_load(payload)
                self.evt_conn.send(ipc.make_response(rid, result))
                after()
                return
            if cmd == "round.unload": result = self._cmd_round_unload()
            elif cmd == "rounds.list": result = self._cmd_rounds_list(payload)
            elif cmd == "replay.play": result = self._cmd_replay_play()
            elif cmd == "replay.pause": result = self._cmd_replay_pause()
            elif cmd == "replay.speed": result = self._cmd_replay_speed(payload)
            elif cmd == "replay.seek": result = self._cmd_replay_seek(payload)
            elif cmd == "replay.preview": result = self._cmd_replay_preview(payload)
            elif cmd == "order.size": result = self._cmd_order_size(payload)
            elif cmd == "order.preview": result = self._cmd_order_preview(payload)
            elif cmd == "order.place": result = self._cmd_order_place(payload)
            elif cmd == "order.close": result = self._cmd_order_close(payload)
            elif cmd == "order.cancel": result = self._cmd_order_cancel(payload)
            elif cmd == "account.list": result = self._cmd_account_list()
            elif cmd == "account.select": result = self._cmd_account_select(payload)
            elif cmd == "account.create": result = self._cmd_account_create(payload)
            elif cmd == "account.rename": result = self._cmd_account_rename(payload)
            elif cmd == "account.update": result = self._cmd_account_update(payload)
            elif cmd == "bot.list": result = self._cmd_bot_list()
            elif cmd == "bot.set_active": result = self._cmd_bot_set_active(payload)
            elif cmd == "strategy.list": result = self._cmd_strategy_list(payload)
            elif cmd == "strategy.create": result = self._cmd_strategy_create(payload)
            elif cmd == "strategy.update": result = self._cmd_strategy_update(payload)
            elif cmd == "strategy.clone": result = self._cmd_strategy_clone(payload)
            elif cmd == "strategy.delete": result = self._cmd_strategy_delete(payload)
            elif cmd == "strategy.load": result = self._cmd_strategy_load(payload)
            elif cmd == "strategy.unload": result = self._cmd_strategy_unload(payload)
            elif cmd == "session.sync": result = self._cmd_session_sync()
            elif cmd == "controller.claim": result = {"ok": True}
            elif cmd == "controller.release": result = {"ok": True}
            else: raise Exception(f"unknown cmd: {cmd}")
            self.evt_conn.send(ipc.make_response(rid, result))
        except Exception as e:
            self.evt_conn.send(ipc.make_error(rid, str(e)))

    def _cmd_round_load(self, payload: dict) -> tuple[dict, callable]:
        if self.active_account_id is None:
            raise Exception("no active account")
        mts = int(payload["market_start_ts"])
        self.loaded = self.repo.load(mts)
        self.sec = 300
        self.playing = True
        self.round_ended = False
        self.session_id = uuid.uuid4().hex[:12]
        self.session_started_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.seq = 0
        self.orders.reset(self.cfg["default_order_size_usd"], self.cfg["default_order_size_usd"])
        self._prev_candles = self.repo.previous_candles(mts, self.cfg["chart_previous_candles"])
        self._round_advanced = False
        result = {"ok": True, "market_start_ts": mts}
        def after():
            self._write_session_begin()
            self._emit_session()
            self._emit_chart_full()
            self._emit_tick_at(self.sec)
            self._emit_orders()
            self._emit_history()
            self._emit_accounts()
            self._emit_bot_status()
        return result, after

    def _cmd_round_unload(self) -> dict:
        if not self.loaded:
            raise Exception("no round loaded")
        if self.orders.open_orders:
            raise Exception("cannot unload session with open orders")
        self.playing = False
        self.loaded = None
        self.session_id = None
        self.session_started_at_utc = None
        self.round_ended = False
        self.sec = 300
        self.seq = 0
        self._last_tick = None
        self._prev_candles = []
        self._round_advanced = False
        self.orders.reset(self.cfg["default_order_size_usd"], self.cfg["default_order_size_usd"])
        self._emit_session()
        self._emit_event("chart", {"previous": [], "current": None, "full_reset": True})
        self._emit_event("tick", _public_tick(None, self.sec, self.seq, True))
        self._emit_orders()
        self._emit_history()
        self._emit_accounts()
        self._emit_bot_status()
        return {"ok": True}

    def _cmd_rounds_list(self, payload: dict) -> dict:
        day_utc = payload["day_utc"]
        return {"ok": True, "rounds": self.repo.list_picker_day(day_utc)}

    def _restart_round(self, *, playing: bool, sec: int) -> dict:
        if not self.loaded:
            raise Exception("no round loaded")
        if self.active_account_id is None:
            raise Exception("no active account")
        self.sec = sec
        self.playing = playing
        self.round_ended = False
        # Nuova sessione: il round precedente è concluso (sec=0); le scommesse future non si mischiano.
        self.session_id = uuid.uuid4().hex[:12]
        self.session_started_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.seq = 0
        self._round_advanced = sec != 300
        self.orders.clear_positions()
        self._write_session_begin()
        self._emit_session()
        self._emit_chart_full()
        self._emit_tick_at(self.sec)
        self._emit_orders()
        self._emit_history()
        self._emit_bot_status()
        return {"ok": True, "sec": self.sec, "playing": playing, "restarted": True}

    def _cmd_replay_play(self) -> dict:
        if not self.loaded: raise Exception("no round loaded")
        if self.round_ended:
            return self._restart_round(playing=True, sec=300)
        self.playing = True
        self._next_tick_at = time.monotonic()
        self._emit_session()
        self._emit_bot_status()
        return {"ok": True, "playing": True}

    def _cmd_replay_pause(self) -> dict:
        self.playing = False
        self._emit_session()
        self._emit_bot_status()
        return {"ok": True, "playing": False}

    def _cmd_replay_speed(self, payload: dict) -> dict:
        speed = int(payload["speed"])
        if speed not in (1, 2, 5):
            raise Exception(f"invalid replay speed: {speed}")
        self.replay_speed = speed
        self._next_tick_at = time.monotonic() + (1.0 / self.replay_speed)
        self._emit_session()
        return {"ok": True, "replay_speed": speed}

    def _scrub_sec(self, target_sec: int) -> int:
        if target_sec < 0 or target_sec > 300:
            raise Exception(f"sec out of range 0..300: {target_sec}")
        if self.round_ended:
            return 0 if target_sec == 0 else max(1, min(300, target_sec))
        if target_sec < 1:
            return 1
        return target_sec

    def _cmd_replay_preview(self, payload: dict) -> dict:
        if not self.loaded:
            raise Exception("no round loaded")
        sec = self._scrub_sec(int(payload["sec"]))
        self._emit_scrub_preview(sec)
        return {"ok": True, "sec": sec}

    def _emit_scrub_preview(self, sec: int) -> None:
        dt = datetime.fromtimestamp(self.loaded.market_start_ts, tz=timezone.utc)
        mm, ss = divmod(max(sec, 0), 60)
        self._emit_event("session", {
            "loaded": True, "market_start_ts": self.loaded.market_start_ts,
            "session_id": self.session_id,
            "replay_timestamp": dt.strftime("%d/%m/%Y | %H:%M:%S"),
            "sec": sec, "countdown": f"{sec} | {mm}:{ss:02d}",
            "progress": 300 - sec, "playing": False, "round_ended": self.round_ended,
            "ptb_chainlink": self.loaded.ptb_chainlink,
            "tradable": not self.round_ended and sec >= 1,
            "preview": True,
            "active_account_id": self.active_account_id,
            "account_switch_locked": bool(self.loaded),
        })
        self.seq += 1
        tick = self.loaded.ticks_by_sec.get(sec)
        gap = tick is None or tick.get("gap", False)
        book = None if gap else self.loaded.books_by_sec.get(sec)
        public = _public_tick(tick, sec, self.seq, gap, book)
        previews = self._previews_at(sec) if not gap and public.get("tradable") else {}
        self._emit_event("tick", {**public, "previews": previews, "preview": True})
        current = self.repo.current_candle(self.loaded, sec)
        self._emit_event("chart", {"current": current, "full_reset": False, "preview": True})
        if not gap and tick:
            book = self.loaded.books_by_sec[sec]
            snap = self.orders.preview_snapshot(sec, tick, book, self.loaded.fee_rate)
            self._emit_event("orders", {**snap, "preview": True})

    def _cmd_replay_seek(self, payload: dict) -> dict:
        if not self.loaded: raise Exception("no round loaded")
        target_sec = int(payload["sec"])
        if target_sec < 0 or target_sec > 300: raise Exception(f"sec out of range 0..300: {target_sec}")
        if self.round_ended:
            if target_sec == 0:
                target_sec = 300
            was_playing = bool(payload.get("resume"))
            result = self._restart_round(playing=was_playing, sec=target_sec)
            return result
        resume = bool(payload.get("resume"))
        self.playing = False
        if target_sec == 0:
            self._finish_round()
            return {"ok": True, "sec": 0}
        if target_sec < 1: target_sec = 1
        self.orders.prune_seek(target_sec)
        self.sec = target_sec
        if target_sec != 300:
            self._round_advanced = True
        self._emit_session()
        self._emit_chart_current()
        self._emit_tick_at(self.sec)
        self._emit_orders()
        self._emit_history()
        self._emit_bot_status()
        if resume:
            self.playing = True
            self._emit_session()
        return {"ok": True, "sec": self.sec, "playing": self.playing}

    def _cmd_order_size(self, payload: dict) -> dict:
        size = float(payload["size_usd"])
        if size > 0:
            self.orders.set_size(payload["side"], size)
        self._emit_orders()
        return {"ok": True}

    def _cmd_order_preview(self, payload: dict) -> dict:
        if not self.loaded or self.round_ended:
            return {"ok": True, "previews": {"Up": None, "Down": None}}
        try:
            tick, book = self._require_tick_book()
        except Exception:
            return {"ok": True, "previews": {"Up": None, "Down": None}}
        out: dict = {}
        for side, key in (("Up", "size_up_usd"), ("Down", "size_down_usd")):
            size = float(payload[key])
            if size <= 0:
                ask_key = "up_ask" if side == "Up" else "down_ask"
                ask = tick.get(ask_key)
                out[side] = {
                    "best_ask_c": int(round(ask * 100)) if ask is not None else None,
                    "profit_if_win_usd": 0, "roi_if_win": 0,
                }
            else:
                try:
                    out[side] = self.orders.preview(side, size, self.sec, tick, book, self.loaded.fee_rate)
                except Exception:
                    out[side] = None
        return {"ok": True, "previews": out}

    def _require_active_account(self) -> str:
        if self.active_account_id is None:
            raise Exception("no account selected")
        return self.active_account_id

    def _require_bot_trading(self, actor: str) -> None:
        if actor == "bot" and not self.bot_active:
            raise Exception("bot inactive")

    def _cmd_order_place(self, payload: dict) -> dict:
        if not self.loaded or self.round_ended: raise Exception("trading blocked")
        actor = _actor_from_payload(payload)
        self._require_bot_trading(actor)
        account_id = self._require_active_account()
        tick, book = self._require_tick_book()
        side, size = payload["side"], float(payload["size_usd"])
        strategy_id = payload.get("strategy_id") if actor == "bot" else None
        reason = payload.get("reason")
        order = self.orders.place(
            side, size, self.sec, tick, book, self.loaded.fee_rate, account_id, actor,
            strategy_id=strategy_id, reason=reason)
        self.orders.revalue_mtm(self.sec, tick, book, self.loaded.fee_rate)
        self._emit_orders(actor=actor)
        detail = {
            "order_id": order["id"], "side": side, "size_usd": size, "strategy_id": strategy_id,
            "reason": reason, "best_ask_c": order.get("best_ask_c"),
        }
        self._emit_action(actor, "order.place", detail)
        self._append_exec_log(actor, "order.place", detail, order)
        self._emit_session()
        return {"ok": True, "order": order}

    def _cmd_order_close(self, payload: dict) -> dict:
        if not self.loaded or self.round_ended: raise Exception("trading blocked")
        actor = _actor_from_payload(payload)
        self._require_bot_trading(actor)
        tick, book = self._require_tick_book()
        reason = payload.get("reason")
        if reason is None and actor == "user":
            reason = "manual"
        closed = self.orders.close(
            payload["order_id"], self.sec, tick, book, self.loaded.fee_rate, reason=reason)
        self._emit_orders(actor=actor)
        self._emit_history()
        detail = {
            "order_id": closed["id"], "strategy_id": closed.get("strategy_id"),
            "reason": closed.get("close_reason"), "pnl_usd": closed.get("pnl_usd"),
            "side": closed.get("side"), "size_usd": closed.get("size_usd"),
        }
        self._emit_action(actor, "order.close", detail)
        self._append_exec_log(actor, "order.close", detail, closed)
        self._emit_session()
        return {"ok": True, "order": closed}

    def _append_exec_log(self, actor: str, cmd: str, detail: dict, order: dict) -> None:
        if not self.session_id or not self.loaded:
            return
        append_execution(Path(self.cfg["history_dir"]), {
            "session_id": self.session_id,
            "market_start_ts": self.loaded.market_start_ts,
            "sec": self.sec,
            "strategy_id": detail.get("strategy_id") or order.get("strategy_id"),
            "cmd": cmd,
            "order_id": detail.get("order_id") or order.get("id"),
            "side": detail.get("side") or order.get("side"),
            "size_usd": detail.get("size_usd") or order.get("size_usd"),
            "best_ask_c": order.get("best_ask_c"),
            "mtm_usd": order.get("mtm_usd"),
            "pnl_usd": detail.get("pnl_usd") or order.get("pnl_usd"),
            "reason": detail.get("reason"),
            "source": actor,
        })

    def _write_session_begin(self) -> None:
        """Snapshot strategie + registro sessione all'avvio."""
        if not self.session_id or not self.loaded:
            return
        if self.active_account_id is None:
            raise Exception("no active account")
        create_session(
            Path(self.cfg["history_dir"]),
            self.session_id,
            self.active_account_id,
            self.loaded.market_start_ts,
            self.session_started_at_utc,
            list(self.active_strategy_ids),
        )
        append_execution(Path(self.cfg["history_dir"]), {
            "session_id": self.session_id,
            "account_id": self.active_account_id,
            "market_start_ts": self.loaded.market_start_ts,
            "sec": self.sec,
            "cmd": "session.begin",
            "active_strategy_ids": list(self.active_strategy_ids),
            "source": "engine",
        })

    def _cmd_order_cancel(self, payload: dict) -> dict:
        if not self.loaded or self.round_ended: raise Exception("trading blocked")
        actor = _actor_from_payload(payload)
        self._require_bot_trading(actor)
        removed = self.orders.cancel(payload["order_id"])
        self._emit_orders(actor=actor)
        self._emit_action(actor, "order.cancel", {"order_id": removed["id"]})
        self._emit_session()
        return {"ok": True, "order": removed}

    def _cmd_account_list(self) -> dict:
        return {"ok": True, "accounts": list_accounts(self.accounts_root), "active_account_id": self.active_account_id}

    def _cmd_account_select(self, payload: dict) -> dict:
        if self.loaded:
            raise Exception("cannot switch account while a session is loaded")
        if self.orders.open_orders:
            raise Exception("cannot switch account with open orders")
        account_id = payload["account_id"]
        if account_id is not None:
            load_account(self.accounts_root, account_id)
        self.active_account_id = account_id
        save_active_account_id(self.accounts_root, account_id)
        self._emit_accounts()
        self._emit_history()
        self._emit_session()
        return {"ok": True, "active_account_id": account_id}

    def _cmd_account_create(self, payload: dict) -> dict:
        if self.loaded:
            raise Exception("cannot create account while a session is loaded")
        data = create_account(
            self.accounts_root, payload["name"], float(payload["initial_balance_usd"]), payload.get("note", ""))
        self.active_account_id = data["id"]
        save_active_account_id(self.accounts_root, data["id"])
        self._emit_accounts()
        self._emit_history()
        self._emit_session()
        return {"ok": True, "account": account_summary(data)}

    def _cmd_account_rename(self, payload: dict) -> dict:
        data = rename_account(self.accounts_root, payload["account_id"], payload["name"])
        self._emit_accounts()
        return {"ok": True, "account": account_summary(data)}

    def _cmd_account_update(self, payload: dict) -> dict:
        data = update_account(
            self.accounts_root, payload["account_id"], payload["name"],
            float(payload["initial_balance_usd"]), payload.get("note", ""))
        self._emit_accounts()
        self._emit_history()
        return {"ok": True, "account": account_summary(data)}

    def _bot_attach_allowed(self) -> bool:
        return not self.playing

    def _persist_active_ids(self) -> None:
        save_active_ids(self.strategies_root, self.active_strategy_ids)

    def _strategies_snapshot(self) -> list[dict]:
        out: list[dict] = []
        for sid in self.active_strategy_ids:
            data = load_strategy(self.strategies_root, sid)
            out.append({**strategy_summary(data), "active": True})
        return out

    def _emit_strategies(self) -> None:
        self._emit_event("strategies", {
            "strategies": list_strategies(self.strategies_root),
            "active_strategy_ids": list(self.active_strategy_ids),
        })

    def _cmd_bot_list(self) -> dict:
        return {
            "ok": True, "bot_attach_allowed": self._bot_attach_allowed(), "bot_active": self.bot_active,
            "strategies": self._strategies_snapshot(), "active_strategy_ids": list(self.active_strategy_ids),
            "catalog": list_strategies(self.strategies_root),
        }

    def _cmd_bot_set_active(self, payload: dict) -> dict:
        self.bot_active = bool(payload["active"])
        self._emit_bot_status()
        self._emit_session()
        return {"ok": True, "bot_active": self.bot_active}

    def _cmd_strategy_list(self, payload: dict) -> dict:
        stype = payload.get("type")
        return {
            "ok": True, "strategies": list_strategies(self.strategies_root, stype),
            "active_strategy_ids": list(self.active_strategy_ids),
        }

    def _cmd_strategy_create(self, payload: dict) -> dict:
        data = create_strategy(
            self.strategies_root, payload["name"], payload["type"], payload["description"],
            rules=payload.get("rules") or "",
            module_file=payload.get("module_file"),
            strategy_id=payload.get("strategy_id"),
        )
        self._emit_strategies()
        return {"ok": True, "strategy": strategy_summary(data)}

    def _cmd_strategy_update(self, payload: dict) -> dict:
        data = update_strategy(
            self.strategies_root, payload["strategy_id"], payload["name"], payload["description"],
            rules=payload.get("rules"),
            module_file=payload.get("module_file"),
        )
        self._emit_strategies()
        self._emit_bot_status()
        return {"ok": True, "strategy": strategy_summary(data)}

    def _cmd_strategy_clone(self, payload: dict) -> dict:
        data = clone_strategy(self.strategies_root, payload["strategy_id"])
        self._emit_strategies()
        return {"ok": True, "strategy": strategy_summary(data)}

    def _cmd_strategy_delete(self, payload: dict) -> dict:
        sid = payload["strategy_id"]
        if sid in self.active_strategy_ids:
            self.active_strategy_ids = [x for x in self.active_strategy_ids if x != sid]
            self._persist_active_ids()
        delete_strategy(self.strategies_root, sid)
        self._emit_strategies()
        self._emit_bot_status()
        return {"ok": True, "active_strategy_ids": list(self.active_strategy_ids)}

    def _cmd_strategy_load(self, payload: dict) -> dict:
        sid = payload["strategy_id"]
        load_strategy(self.strategies_root, sid)
        if sid in self.active_strategy_ids:
            raise Exception(f"strategy already active: {sid}")
        self.active_strategy_ids.append(sid)
        self._persist_active_ids()
        self._emit_strategies()
        self._emit_bot_status()
        return {
            "ok": True, "active_strategy_ids": list(self.active_strategy_ids),
            "strategies": self._strategies_snapshot(),
        }

    def _cmd_strategy_unload(self, payload: dict) -> dict:
        sid = payload["strategy_id"]
        if sid not in self.active_strategy_ids:
            raise Exception(f"strategy not active: {sid}")
        self.active_strategy_ids = [x for x in self.active_strategy_ids if x != sid]
        self._persist_active_ids()
        self._emit_strategies()
        self._emit_bot_status()
        return {
            "ok": True, "active_strategy_ids": list(self.active_strategy_ids),
            "strategies": self._strategies_snapshot(),
        }

    def _cmd_session_sync(self) -> dict:
        self._emit_event("bootstrap", self._bootstrap_payload())
        self._emit_session()
        if self.loaded:
            self._emit_chart_full()
            self._emit_tick_at(self.sec)
            self._emit_orders()
        self._emit_history()
        self._emit_accounts()
        self._emit_strategies()
        self._emit_bot_status()
        return {"ok": True}

    def _advance_sec(self) -> None:
        if self.sec <= 0: return
        self._round_advanced = True
        if self.sec == 1:
            self._finish_round()
            return
        self.sec -= 1
        self._emit_tick_at(self.sec)
        self._emit_chart_current()
        self._emit_session()

    def _finish_round(self) -> None:
        if not self.loaded: raise Exception("no round loaded")
        self.playing = False
        self.round_ended = True
        self.sec = 0
        outcome = self.loaded.outcome_name
        final_btc = self.loaded.final_chainlink
        settled = self.orders.settle_open(outcome, 0, final_btc)
        by_account: dict[str, list[dict]] = {}
        for o in self.orders.closed_orders:
            aid = o.get("account_id")
            if aid is None:
                raise Exception(f"closed order missing account_id: {o.get('id')}")
            by_account.setdefault(aid, []).append(o)
        for aid, orders in by_account.items():
            append_settled_orders(
                self.accounts_root, aid, self.loaded.market_start_ts, self.session_id or "",
                self.session_started_at_utc or "", outcome, orders, self.round_source)
        self._emit_orders()
        self._emit_history()
        self._emit_accounts()
        self._emit_event("round_end", {
            "outcome": outcome, "outcome_label": outcome.upper(),
            "final_chainlink": final_btc, "settled_orders": settled,
        })
        self._emit_session()
        self._emit_bot_status()

    def _require_tick_book(self):
        if not self.loaded: raise Exception("no round loaded")
        tick = self.loaded.ticks_by_sec.get(self.sec)
        book = self.loaded.books_by_sec.get(self.sec)
        if tick is None or book is None: raise Exception(f"no tick/book for sec={self.sec}")
        if tick.get("gap") or tick.get("partial"): raise Exception(f"tick not tradable sec={self.sec}")
        return tick, book

    def _emit_tick_at(self, sec: int) -> None:
        if not self.loaded: return
        self.seq += 1
        tick = self.loaded.ticks_by_sec.get(sec)
        gap = tick is None or tick.get("gap", False)
        book = None if gap else self.loaded.books_by_sec.get(sec)
        public = _public_tick(tick, sec, self.seq, gap, book)
        self._last_tick = public
        if self.loaded and not gap and tick:
            book = self.loaded.books_by_sec[sec]
            self.orders.revalue_mtm(sec, tick, book, self.loaded.fee_rate)
            self._emit_orders()
        previews = self._previews() if not gap and public.get("tradable") else {}
        self._emit_event("tick", {**public, "previews": previews})

    def _previews(self) -> dict:
        return self._previews_at(self.sec)

    def _previews_at(self, sec: int) -> dict:
        tick = self.loaded.ticks_by_sec.get(sec)
        book = self.loaded.books_by_sec.get(sec)
        if tick is None or book is None or tick.get("gap") or tick.get("partial"):
            raise Exception(f"tick not tradable sec={sec}")
        out = {}
        for side, size in (("Up", self.orders.size_up_usd), ("Down", self.orders.size_down_usd)):
            try:
                out[side] = self.orders.preview(side, size, sec, tick, book, self.loaded.fee_rate)
            except Exception:
                out[side] = None
        return out

    def _emit_session(self) -> None:
        if not self.loaded:
            self._emit_event("session", {
                "loaded": False, "session_id": None, "active_account_id": self.active_account_id,
                "account_switch_locked": bool(self.loaded),
                "replay_speed": self.replay_speed, "engine_plugin": self.engine_plugin,
                "account_backend": self.account_backend,
                "bot_attach_allowed": self._bot_attach_allowed(), "bot_active": self.bot_active,
                "active_strategy_ids": list(self.active_strategy_ids),
            })
            return
        dt = datetime.fromtimestamp(self.loaded.market_start_ts, tz=timezone.utc)
        mm, ss = divmod(max(self.sec, 0), 60)
        tradable = (
            not self.round_ended and self.sec >= 1 and self.active_account_id is not None
        )
        self._emit_event("session", {
            "loaded": True, "market_start_ts": self.loaded.market_start_ts,
            "session_id": self.session_id,
            "replay_timestamp": dt.strftime("%d/%m/%Y | %H:%M:%S"),
            "sec": self.sec, "countdown": f"{self.sec} | {mm}:{ss:02d}",
            "progress": 300 - self.sec, "playing": self.playing, "round_ended": self.round_ended,
            "ptb_chainlink": self.loaded.ptb_chainlink, "tradable": tradable,
            "active_account_id": self.active_account_id,
            "account_switch_locked": bool(self.loaded),
            "replay_speed": self.replay_speed, "engine_plugin": self.engine_plugin,
            "account_backend": self.account_backend,
            "bot_attach_allowed": self._bot_attach_allowed(), "bot_active": self.bot_active,
            "active_strategy_ids": list(self.active_strategy_ids),
        })

    def _emit_chart_full(self) -> None:
        if not self.loaded: return
        current = self.repo.current_candle(self.loaded, self.sec)
        self._emit_event("chart", {"previous": self._prev_candles, "current": current, "full_reset": True})

    def _emit_chart_current(self) -> None:
        if not self.loaded: return
        current = self.repo.current_candle(self.loaded, self.sec)
        self._emit_event("chart", {"current": current, "full_reset": False})

    def _emit_orders(self, actor: str | None = None) -> None:
        snap = self.orders.snapshot()
        if actor is not None:
            snap = {**snap, "actor": actor}
        self._emit_event("orders", snap)

    def _emit_action(self, actor: str, cmd: str, detail: dict) -> None:
        self._emit_event("action", {"actor": actor, "cmd": cmd, "detail": detail, "sec": self.sec})

    def _emit_bot_status(self) -> None:
        self._emit_event("bot.status", {
            "bot_attach_allowed": self._bot_attach_allowed(), "bot_active": self.bot_active,
            "strategies": self._strategies_snapshot(),
            "active_strategy_ids": list(self.active_strategy_ids),
            "loaded": bool(self.active_strategy_ids),
        })

    def _account_payload(self) -> dict | None:
        if self.active_account_id is None:
            return None
        data = load_account(self.accounts_root, self.active_account_id)
        stats = compute_stats(data)
        return {
            "id": data["id"], "name": data["name"], "note": data.get("note", ""),
            "initial_balance_usd": data["initial_balance_usd"], "created_at_utc": data["created_at_utc"],
            "updated_at_utc": data.get("updated_at_utc"), **stats,
        }

    def _emit_accounts(self) -> None:
        self._emit_event("accounts", {
            "accounts": list_accounts(self.accounts_root),
            "active_account_id": self.active_account_id,
            "active": self._account_payload(),
            "account_backend": self.account_backend,
        })

    def _emit_history(self) -> None:
        rows: list[dict] = []
        if self.active_account_id is not None:
            data = load_account(self.accounts_root, self.active_account_id)
            rows = order_rows_from_ledger(data.get("orders", []))
        if self.loaded and not self.round_ended and self.orders.closed_orders:
            live = order_rows_for_run(
                self.loaded.market_start_ts, self.orders.closed_orders,
                self.session_id or "", self.session_started_at_utc or "")
            rows = live + rows
        rows.sort(key=lambda r: (r["session_sort_ts"], r["market_start_ts"], r.get("entry_sec", 0)), reverse=True)
        self._emit_event("history", {
            "rows": rows,
            "active_account_id": self.active_account_id,
            "session_id": self.session_id if self.loaded else None,
        })

    def _emit_event(self, name: str, payload: dict) -> None:
        self.evt_conn.send(ipc.make_event(name, payload))
