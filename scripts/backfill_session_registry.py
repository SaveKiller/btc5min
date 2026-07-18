"""One-shot: ricostruisce history/sessions/ da session_id nel ledger account.

Uso (dalla root repo):
  python scripts/backfill_session_registry.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dashv2.config import load_config
from dashv2.execution_log import read_execution_session
from dashv2.history import accounts_dir
from dashv2.sessions import create_session, load_session, sessions_dir


def _strategies_from_exec(history_dir: Path, session_id: str) -> list[str]:
    rows = read_execution_session(history_dir, session_id, limit=500)
    for r in rows:
        if r.get("cmd") == "session.begin":
            return list(r.get("active_strategy_ids") or [])
    return []


def main() -> None:
    cfg = load_config()
    history_dir = Path(cfg["history_dir"])
    root = accounts_dir(history_dir)
    created = 0
    skipped = 0
    for path in sorted(root.glob("account_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        account_id = data["id"]
        by_sid: dict[str, dict] = {}
        for o in data.get("orders") or []:
            sid = o.get("session_id")
            if not sid:
                continue
            if sid not in by_sid:
                by_sid[sid] = o
        for sid, o in by_sid.items():
            reg_path = sessions_dir(history_dir) / f"session_{sid}.json"
            if reg_path.is_file():
                existing = load_session(history_dir, sid)
                if existing["account_id"] != account_id:
                    raise Exception(
                        f"session {sid} already owned by {existing['account_id']}, "
                        f"ledger claims {account_id}"
                    )
                skipped += 1
                continue
            mts = int(o["market_start_ts"])
            started = o.get("session_started_at_utc") or o.get("saved_at_utc")
            if not started:
                raise Exception(f"session {sid} on account {account_id}: missing started_at")
            strats = _strategies_from_exec(history_dir, sid)
            create_session(history_dir, sid, account_id, mts, started, strats)
            created += 1
            print(f"created session_{sid}.json account={account_id} mts={mts}")
    print(f"done: created={created} skipped_existing={skipped}")


if __name__ == "__main__":
    main()
