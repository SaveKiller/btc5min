"""Parser righe data: dei round reali (.txt) per dashv2."""

from __future__ import annotations

import re
from pathlib import Path

from src.binary_format import txt_path_for_bin
from src.delta_win import parse_vol_txt
from src.setup import DELTA_WIN_TXT_COLUMNS, VOLATILITY_WINDOWS_SEC


def _is_btc_cell(token: str) -> bool:
    return token.endswith("$") and token[:-1].isdigit()


def _parse_dwin_a_parts(parts: list[str], start: int, end: int) -> dict | None:
    chunk = parts[start:end]
    if not chunk or chunk[0] == "---":
        return None
    p_win: float | None = None
    n: int | None = None
    if len(chunk) == 1 and chunk[0].startswith("[n="):
        m = re.match(r"\[n=(\d+)\*\]", chunk[0])
        if not m:
            raise Exception(f"invalid sparse dwin_a: {chunk[0]!r}")
        n = int(m.group(1))
    elif len(chunk) >= 2 and chunk[1].startswith("[n="):
        if chunk[0].endswith("%"):
            p_win = int(chunk[0][:-1]) / 100.0
        m = re.match(r"\[n=(\d+)\*?\]", chunk[1])
        if not m:
            raise Exception(f"invalid dwin_a band: {chunk[1]!r}")
        n = int(m.group(1))
    else:
        raise Exception(f"unparsable dwin_a tokens: {chunk}")
    if n is None:
        raise Exception(f"dwin_a missing n: {chunk}")
    return {"p_win": p_win, "n": n}


def _parse_dwin_b_token(token: str) -> int | None:
    if token == "---":
        return None
    if token.endswith("%"):
        return int(token[:-1])
    raise Exception(f"invalid dwin_b cell: {token!r}")


def _parse_dwin_cells(parts: list[str], start: int, btc_i: int) -> tuple[dict | None, int | None, int]:
    i = start
    dwin_a: dict | None = None
    dwin_b: int | None = None
    if i >= btc_i or _is_btc_cell(parts[i]):
        return None, None, i
    if "a" in DELTA_WIN_TXT_COLUMNS:
        if i >= btc_i:
            raise Exception(f"missing dwin_a before btc in row: {parts}")
        if parts[i] == "---":
            i += 1
        elif i + 1 < btc_i and parts[i + 1].startswith("["):
            dwin_a = _parse_dwin_a_parts(parts, i, i + 2)
            i += 2
        elif parts[i].startswith("[n="):
            dwin_a = _parse_dwin_a_parts(parts, i, i + 1)
            i += 1
        else:
            raise Exception(f"unparsable dwin_a in row: {parts}")
    if "b" in DELTA_WIN_TXT_COLUMNS:
        if i >= btc_i:
            raise Exception(f"missing dwin_b before btc in row: {parts}")
        dwin_b = _parse_dwin_b_token(parts[i])
        i += 1
    return dwin_a, dwin_b, i


def _parse_risk(parts: list[str]) -> tuple[int | None, int | None]:
    rq_i = parts.index("Rq")
    rs_i = parts.index("Rs")
    rq = None if parts[rq_i + 1] == "-" else int(parts[rq_i + 1])
    rs = None if parts[rs_i + 1] == "-" else int(parts[rs_i + 1])
    return rq, rs


def _normalize_parts(parts: list[str]) -> list[str]:
    out: list[str] = []
    for p in parts:
        if "%[n=" in p:
            pct, band = p.split("[", 1)
            out.append(pct)
            out.append("[" + band)
        else:
            out.append(p)
    return out


def parse_txt_data_rows(txt_path: Path) -> dict[int, dict]:
    if not txt_path.is_file():
        raise Exception(f"txt round file not found: {txt_path}")
    rows: dict[int, dict] = {}
    in_data = False
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "data:":
            in_data = True
            continue
        if not in_data or not line.strip() or line.startswith("-"):
            continue
        parts = line.split()
        if not parts[0].isdigit():
            continue
        row = _parse_data_row_line(line)
        rows[row["sec"]] = {k: v for k, v in row.items() if k != "sec"}
    if not rows:
        raise Exception(f"no data rows in {txt_path}")
    return rows


def _parse_data_row_line(line: str) -> dict:
    parts = _normalize_parts(line.split())
    if len(parts) < 10:
        raise Exception(f"unparsable data row: {line}")
    rs_i = parts.index("Rs")
    sec = int(parts[0])
    btc_i = next((i for i in range(6, rs_i) if _is_btc_cell(parts[i])), None)
    if btc_i is None:
        raise Exception(f"no btc cell in row sec={sec}: {line}")
    dwin_a, dwin_b_pct, _ = _parse_dwin_cells(parts, 6, btc_i)
    vol: dict[int, int | None] = {}
    i = btc_i + 1
    while i < rs_i:
        if not parts[i].startswith("V"):
            break
        w = int(parts[i][1:])
        vol[w] = parse_vol_txt(f"{parts[i]} {parts[i + 1]}")
        i += 2
    for w in VOLATILITY_WINDOWS_SEC:
        if w not in vol:
            raise Exception(f"missing vol V{w} in row sec={sec}: {line}")
    rq, rs = _parse_risk(parts)
    return {"sec": sec, "vol": vol, "rq": rq, "rs": rs, "dwin_a": dwin_a, "dwin_b_pct": dwin_b_pct}


def txt_path_for_bin_path(bin_path: Path) -> Path:
    return txt_path_for_bin(str(bin_path))
