import json
import os
import time


def dbg_ndjson(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    if os.environ.get("BTC5MIN_DEBUG_NDJSON") != "1":
        return
    with open(os.environ["BTC5MIN_DEBUG_FILE"], "a", encoding="utf-8") as f:
        payload = {
            "hypothesisId": hypothesis_id, "location": location, "message": message,
            "data": data, "timestamp": int(time.time() * 1000),
        }
        if sid := os.environ.get("BTC5MIN_DEBUG_SESSION"):
            payload["sessionId"] = sid
        f.write(json.dumps(payload, default=str) + "\n")
    # #endregion
