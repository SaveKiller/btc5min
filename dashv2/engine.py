"""Processo dati: round, replay, ordini, history — unica fonte di verità."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from multiprocessing.connection import Connection

from dashv2 import ipc
from dashv2.history import history_rows, list_runs, order_rows_for_run, visible_history, write_run
from dashv2.orders import OrderEngine
from dashv2.rounds import LoadedRound, RoundRepository


def _orient_dwin(tick: dict) -> dict:
    """DWinA/B orientati dal segno del delta: lato opposto mostra complemento."""
    delta = tick.get("delta_usd")
    dwin_a = tick.get("dwin_a")
    dwin_b = tick.get("dwin_b_pct")
    delta_side = "Up" if delta is not None and delta >= 0 else "Down"
    out_a = out_b = None
    if dwin_a and dwin_a.get("p_win") is not None:
        p = dwin_a["p_win"]
        if delta_side == "Down": p = 1.0 - p
        out_a = {"p_win_pct": int(round(p * 100)), "n": dwin_a["n"], "side": delta_side}
    if dwin_b is not None:
        p = dwin_b
        if delta_side == "Down": p = 100 - p
        out_b = {"p_win_pct": p, "side": delta_side}
    return {"dwin_a": out_a, "dwin_b": out_b, "delta_side": delta_side if delta is not None else None}


def _public_tick(tick: dict | None, sec: int, seq: int, gap: bool) -> dict:
    if tick is None or gap:
        return {
            "seq": seq, "sec": sec, "gap": True, "chainlink_btc": None, "delta_usd": None,
            "up_mid_c": None, "down_mid_c": None, "up_ask_c": None, "down_ask_c": None,
            "vol": {}, "rq": None, "rs": None, "dwin_a": None, "dwin_b": None, "tradable": False,
        }
    dwin = _orient_dwin(tick)
    return {
        "seq": seq, "sec": sec, "gap": False, "chainlink_btc": tick["chainlink_btc"],
        "chainlink_stale": tick["chainlink_stale"], "delta_usd": tick["delta_usd"],
        "up_mid_c": tick["up_mid_c"], "down_mid_c": tick["down_mid_c"],
        "up_ask_c": int(round(tick["up_ask"] * 100)) if tick["up_ask"] is not None else None,
        "down_ask_c": int(round(tick["down_ask"] * 100)) if tick["down_ask"] is not None else None,
        "majority_side": tick["majority_side"], "vol": tick["vol"], "rq": tick["rq"], "rs": tick["rs"],
        "dwin_a": dwin["dwin_a"], "dwin_b": dwin["dwin_b"], "delta_side": dwin["delta_side"],
        "tradable": not tick["partial"] and not tick["gap"] and tick["chainlink_btc"] is not None,
    }


class ReplayEngine:
    def __init__(self, cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
        self.cfg = cfg
        self.cmd_conn = cmd_conn
        self.evt_conn = evt_conn
        self.repo = RoundRepository(cfg["data_dir"], cfg["stall_reconnect_sec"])
        self.orders = OrderEngine(cfg["default_order_size_usd"], cfg["default_order_size_usd"])
        self.loaded: LoadedRound | None = None
        self.sec = 300
        self.playing = False
        self.round_ended = False
        self.seq = 0
        self.run_id: str | None = None
        self._resume_after_scrub = False
        self._last_tick: dict | None = None
        self._prev_candles: list[dict] = []

    def run(self) -> None:
        self._emit_event("bootstrap", self._bootstrap_payload())
        next_tick_at = 0.0
        while True:
            while self.cmd_conn.poll(0):
                self._handle_cmd(self.cmd_conn.recv())
            if self.playing and self.loaded and not self.round_ended:
                now = time.monotonic()
                if now >= next_tick_at:
                    self._advance_sec()
                    next_tick_at = now + 1.0
            time.sleep(0.02)

    def _bootstrap_payload(self) -> dict:
        return {
            "round_days": self.repo.list_days(),
            "default_order_size_usd": self.cfg["default_order_size_usd"],
            "host": self.cfg["host"], "port": self.cfg["port"],
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
            if cmd == "rounds.list": result = self._cmd_rounds_list(payload)
            elif cmd == "replay.play": result = self._cmd_replay_play()
            elif cmd == "replay.pause": result = self._cmd_replay_pause()
            elif cmd == "replay.seek": result = self._cmd_replay_seek(payload)
            elif cmd == "order.size": result = self._cmd_order_size(payload)
            elif cmd == "order.preview": result = self._cmd_order_preview(payload)
            elif cmd == "order.place": result = self._cmd_order_place(payload)
            elif cmd == "order.close": result = self._cmd_order_close(payload)
            elif cmd == "session.sync": result = self._cmd_session_sync()
            elif cmd == "controller.claim": result = {"ok": True}
            elif cmd == "controller.release": result = {"ok": True}
            else: raise Exception(f"unknown cmd: {cmd}")
            self.evt_conn.send(ipc.make_response(rid, result))
        except Exception as e:
            self.evt_conn.send(ipc.make_error(rid, str(e)))

    def _cmd_round_load(self, payload: dict) -> tuple[dict, callable]:
        mts = int(payload["market_start_ts"])
        self.loaded = self.repo.load(mts)
        self.sec = 300
        self.playing = True
        self.round_ended = False
        self.run_id = uuid.uuid4().hex[:12]
        self.seq = 0
        self.orders.reset(self.cfg["default_order_size_usd"], self.cfg["default_order_size_usd"])
        self._prev_candles = self.repo.previous_candles(mts, self.cfg["chart_previous_candles"])
        result = {"ok": True, "market_start_ts": mts}
        def after():
            self._emit_session()
            self._emit_chart_full()
            self._emit_tick_at(self.sec)
            self._emit_orders()
            self._emit_history()
        return result, after

    def _cmd_rounds_list(self, payload: dict) -> dict:
        day_utc = payload["day_utc"]
        return {"ok": True, "rounds": self.repo.list_picker_day(day_utc)}

    def _restart_round(self, *, playing: bool, sec: int) -> dict:
        if not self.loaded:
            raise Exception("no round loaded")
        self.sec = sec
        self.playing = playing
        self.round_ended = False
        self.run_id = uuid.uuid4().hex[:12]
        self.seq = 0
        self.orders.clear_positions()
        self._emit_session()
        self._emit_chart_full()
        self._emit_tick_at(self.sec)
        self._emit_orders()
        self._emit_history()
        return {"ok": True, "sec": self.sec, "playing": playing, "restarted": True}

    def _cmd_replay_play(self) -> dict:
        if not self.loaded: raise Exception("no round loaded")
        if self.round_ended:
            return self._restart_round(playing=True, sec=300)
        self.playing = True
        self._emit_session()
        return {"ok": True, "playing": True}

    def _cmd_replay_pause(self) -> dict:
        self.playing = False
        self._emit_session()
        return {"ok": True, "playing": False}

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
        was_playing = self.playing
        self.playing = False
        if target_sec == 0:
            self._finish_round()
            return {"ok": True, "sec": 0}
        if target_sec < 1: target_sec = 1
        self.orders.prune_seek(target_sec)
        self.sec = target_sec
        self._emit_session()
        self._emit_chart_current()
        self._emit_tick_at(self.sec)
        self._emit_orders()
        self._emit_history()
        if was_playing and payload.get("resume"):
            self.playing = True
        return {"ok": True, "sec": self.sec}

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

    def _cmd_order_place(self, payload: dict) -> dict:
        if not self.loaded or self.round_ended: raise Exception("trading blocked")
        tick, book = self._require_tick_book()
        side, size = payload["side"], float(payload["size_usd"])
        order = self.orders.place(side, size, self.sec, tick, book, self.loaded.fee_rate)
        self.orders.revalue_mtm(self.sec, tick, book, self.loaded.fee_rate)
        self._emit_orders()
        return {"ok": True, "order": order}

    def _cmd_order_close(self, payload: dict) -> dict:
        if not self.loaded or self.round_ended: raise Exception("trading blocked")
        tick, book = self._require_tick_book()
        closed = self.orders.close(payload["order_id"], self.sec, tick, book, self.loaded.fee_rate)
        self._emit_orders()
        self._emit_history()
        return {"ok": True, "order": closed}

    def _cmd_session_sync(self) -> dict:
        self._emit_event("bootstrap", self._bootstrap_payload())
        self._emit_session()
        if self.loaded:
            self._emit_chart_full()
            self._emit_tick_at(self.sec)
            self._emit_orders()
        self._emit_history()
        return {"ok": True}

    def _advance_sec(self) -> None:
        if self.sec <= 0: return
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
        run = {
            "market_start_ts": self.loaded.market_start_ts, "run_id": self.run_id,
            "outcome": outcome, "final_chainlink": final_btc, "ptb_chainlink": self.loaded.ptb_chainlink,
            "orders": self.orders.closed_orders, "total_pnl_usd": sum(o.get("pnl_usd", 0) for o in self.orders.closed_orders),
        }
        write_run(self.cfg["history_dir"], self.loaded.market_start_ts, run)
        self._emit_orders()
        self._emit_history()
        self._emit_event("round_end", {
            "outcome": outcome, "outcome_label": outcome.upper(),
            "final_chainlink": final_btc, "settled_orders": settled,
        })
        self._emit_session()

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
        public = _public_tick(tick, sec, self.seq, gap)
        self._last_tick = public
        if self.loaded and not gap and tick:
            book = self.loaded.books_by_sec[sec]
            self.orders.revalue_mtm(sec, tick, book, self.loaded.fee_rate)
            self._emit_orders()
        previews = self._previews() if not gap and public.get("tradable") else {}
        self._emit_event("tick", {**public, "previews": previews})

    def _previews(self) -> dict:
        tick, book = self._require_tick_book()
        out = {}
        for side, size in (("Up", self.orders.size_up_usd), ("Down", self.orders.size_down_usd)):
            try:
                out[side] = self.orders.preview(side, size, self.sec, tick, book, self.loaded.fee_rate)
            except Exception:
                out[side] = None
        return out

    def _emit_session(self) -> None:
        if not self.loaded:
            self._emit_event("session", {"loaded": False})
            return
        dt = datetime.fromtimestamp(self.loaded.market_start_ts, tz=timezone.utc)
        mm, ss = divmod(max(self.sec, 0), 60)
        self._emit_event("session", {
            "loaded": True, "market_start_ts": self.loaded.market_start_ts,
            "replay_timestamp": dt.strftime("%d/%m/%Y | %H:%M:%S"),
            "sec": self.sec, "countdown": f"{self.sec} | {mm}:{ss:02d}",
            "progress": 300 - self.sec, "playing": self.playing, "round_ended": self.round_ended,
            "ptb_chainlink": self.loaded.ptb_chainlink, "tradable": not self.round_ended and self.sec >= 1,
        })

    def _emit_chart_full(self) -> None:
        if not self.loaded: return
        current = self.repo.current_candle(self.loaded, self.sec)
        self._emit_event("chart", {"previous": self._prev_candles, "current": current, "full_reset": True})

    def _emit_chart_current(self) -> None:
        if not self.loaded: return
        current = self.repo.current_candle(self.loaded, self.sec)
        self._emit_event("chart", {"current": current, "full_reset": False})

    def _emit_orders(self) -> None:
        snap = self.orders.snapshot()
        self._emit_event("orders", snap)

    def _emit_history(self) -> None:
        runs = list_runs(self.cfg["history_dir"])
        active = self.loaded.market_start_ts if self.loaded else None
        visible = visible_history(runs, active, self.round_ended)
        rows = history_rows(visible)
        if self.loaded and not self.round_ended and self.orders.closed_orders:
            live = order_rows_for_run(self.loaded.market_start_ts, self.orders.closed_orders)
            rows = live + rows
        self._emit_event("history", {"runs": visible, "rows": rows})

    def _emit_event(self, name: str, payload: dict) -> None:
        self.evt_conn.send(ipc.make_event(name, payload))


def run_data_process(cfg: dict, cmd_conn: Connection, evt_conn: Connection) -> None:
    ReplayEngine(cfg, cmd_conn, evt_conn).run()
