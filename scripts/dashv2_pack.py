#!/usr/bin/env python3
"""Assembla zip portabile dashV2 (replay offline, senza collector né round)."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dashv2.config import parse_all_tabs, parse_hide_tabs

_RUNTIME_HISTORY_PREFIX = "dashv2/history/"
_HISTORY_SCAFFOLD = (
    "dashv2/history/accounts/.keep",
    "dashv2/history/sessions/.keep",
    "dashv2/history/executions/.keep",
    "dashv2/history/agent/.keep",
    "dashv2/history/stats/.keep",
    "dashv2/history/simulations/.keep",
    "dashv2/history/strategies/.keep",
)

_INSTALL_MD = """# Installazione dashV2 (replay offline)

Pacchetto **btc5min** — dashboard replay Polymarket BTC 5m.  
Non include il collector live né i file round: vanno copiati separatamente in `data/`.

---

## Requisiti

- **Windows 10/11** o Linux
- **Python 3.11 o superiore** ([python.org](https://www.python.org/downloads/))
  - Su Windows: spuntare **"Add python.exe to PATH"** durante l'installazione
- ~300 MB di spazio disco (applicativo + ambiente virtuale; i round sono a parte)
- Browser moderno (Chrome, Firefox, Edge)
- Archivio zip separato con i round Polymarket in `data/YYYY-MM-DD/bin|txt/`

---

## 1. Estrazione e installazione (Windows — consigliato)

1. Crea una cartella, es. `C:\\btc5min` (evita spazi nel path).
2. Estrai **tutto** il contenuto dello zip in quella cartella.
3. **Doppio click su `install.bat`** e attendi il messaggio "INSTALLAZIONE COMPLETATA" (solo la prima volta, o dopo un aggiornamento del programma).
4. Se hai ricevuto i file dei round, copiali nella cartella `data\\` (vedi sotto).

---

## 2. Avvio dashboard (Windows)

1. **Doppio click su `dashv2.bat`**
2. Lascia aperta la finestra nera che compare
3. Apri il browser su: **http://127.0.0.1:8780/**
4. Per fermare: chiudi la finestra nera o `Ctrl+C`

---

## Installazione manuale (Linux / utenti tecnici)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dashv2-offline.txt
python -m dashv2
```

Browser: **http://127.0.0.1:8780/**

---

## Cartella `data/` (round)

I round **non** sono in questo zip. Copia le cartelle con le date ricevute separatamente:

```
data/
  YYYY-MM-DD/
    bin/
    txt/
```

---

## 4. Uso rapido

1. In alto: scegli **giorno** e **round** dal picker.
2. **Play** / pausa / velocità x2 x5 sulla timeline.
3. Pulsanti **BUY Up / Down** per ordini simulati sul book del tick corrente.
4. Tab **STRATEGY** per caricare bot (opzionale).
5. Tab **Backtest** / **Analyze** per batch su più round (richiede più CPU).

Lo **storico ordini** simulati è in `dashv2/history/accounts/` (creato automaticamente).

---

## 5. Funzioni AI (Cursor)

Il file `.env` è **già incluso** nel pacchetto (chiave `CURSOR_API_KEY` per tab AGENT, codegen strategy e analyze).

Se le funzioni AI non partono, verifica che `.env` sia nella root `btc5min/` accanto a `dashv2.bat`.

Il **replay e le simulazioni manuali** funzionano anche senza chiave valida.

---

## 6. Aggiornare i dati (nuovi round)

I round **non** sono in questo zip. Quando ricevi nuovi giorni:

1. Chiudi la dashboard (`Ctrl+C`) se è in esecuzione.
2. Copia o estrai i file sotto `data/YYYY-MM-DD/bin` e `data/YYYY-MM-DD/txt`.
3. Riavvia `dashv2.bat`.

Non serve reinstallare pip se non cambia il codice applicativo.

---

## 7. Risoluzione problemi

| Problema | Soluzione |
|----------|-----------|
| `python` non riconosciuto | Reinstalla Python con PATH, o usa `py -3.12` |
| `data_dir not found` | Verifica `dashv2/setup.json` → `"data_dir": "../data"` e che esista `data/` |
| Porta 8780 occupata | Cambia `"port"` in `dashv2/setup.json` e riavvia |
| Picker vuoto | Copia i round in `data/YYYY-MM-DD/bin/btc5m_*.bin` e `.txt` accoppiati |
| Modifiche codice non visibili | Crea file vuoto `data/restart` con dashboard avviata, oppure riavvia |

---

## 8. Contatti / documentazione

Documentazione tecnica completa: cartella `docs/` nel repo sorgente, file `dashv2-offline-bundle.md`.

Pacchetto generato: {generated_utc}
"""


class PackWriter(Protocol):
    def write_path(self, path: Path, arcname: str) -> None: ...
    def write_text(self, arcname: str, text: str) -> None: ...
    def list_names(self) -> list[str]: ...
    def close(self) -> None: ...


def _is_local_runtime_history(rel: Path) -> bool:
    """Esclude dashv2/history/* runtime (account, sessioni, closed orders, …)."""
    parts = rel.parts
    if not parts or parts[0] != "history":
        return False
    return len(parts) > 1


class ZipPackWriter:
    def __init__(self, path: Path) -> None:
        self._zf = zipfile.ZipFile(path, "w", compression=zipfile.ZIP_LZMA, compresslevel=9)

    def write_path(self, path: Path, arcname: str) -> None:
        self._zf.write(path, arcname, compress_type=zipfile.ZIP_LZMA, compresslevel=9)

    def write_text(self, arcname: str, text: str) -> None:
        self._zf.writestr(arcname, text, compress_type=zipfile.ZIP_LZMA, compresslevel=9)

    def list_names(self) -> list[str]:
        return self._zf.namelist()

    def close(self) -> None:
        self._zf.close()


def _add_tree(
    writer: PackWriter, src: Path, arc_prefix: str, *, skip_names: set[str], skip_files: set[str] | None = None,
) -> int:
    skip_files = skip_files or set()
    n = 0
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if rel.as_posix() in skip_files:
            continue
        if any(part in skip_names for part in rel.parts):
            continue
        if arc_prefix == "dashv2" and _is_local_runtime_history(rel):
            continue
        if "__pycache__" in rel.parts:
            continue
        if rel.suffix in (".pyc", ".pyo"):
            continue
        writer.write_path(path, f"{arc_prefix}/{rel.as_posix()}")
        n += 1
    return n


def _write_empty_history_scaffold(writer: PackWriter) -> None:
    for path in _HISTORY_SCAFFOLD:
        writer.write_text(path, "")


def _is_packed_runtime_history(arcname: str) -> bool:
    if not arcname.startswith(_RUNTIME_HISTORY_PREFIX):
        return False
    return not arcname.endswith("/.keep")


def _assert_pack_has_no_runtime_history(writer: PackWriter) -> None:
    leaks = [n for n in writer.list_names() if _is_packed_runtime_history(n)]
    if leaks:
        sample = ", ".join(leaks[:5])
        raise Exception(f"pack leaked runtime history ({len(leaks)}): {sample}")


def _patch_setup_json(raw: dict) -> dict:
    patched = dict(raw)
    patched["ticks_root"] = "data/_ticks_stub"
    return patched


def _patch_dashv2_setup(raw: dict, hide_tabs: list[str] | None) -> dict:
    patched = dict(raw)
    if hide_tabs is not None:
        patched["hide_tabs"] = hide_tabs
    parse_all_tabs(patched["all_tabs"])
    parse_hide_tabs(patched["hide_tabs"])
    return patched


def _format_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024**2:.0f} MB"
    return f"{n / 1024:.0f} KB"


def main() -> None:
    p = argparse.ArgumentParser(description="Crea zip portabile dashV2 offline (solo applicativo)")
    p.add_argument("--output", type=Path, required=True, help="path file .zip in uscita")
    p.add_argument("--repo-root", type=Path, default=_ROOT, help="root repo btc5min")
    p.add_argument(
        "--hide-tabs", nargs="*", metavar="TAB",
        help="tab da nascondere in dashv2/setup.json del pacchetto (chiavi in all_tabs); "
        "se omesso usa hide_tabs del repo; se passato senza valori → nessuna tab nascosta",
    )
    args = p.parse_args()

    root = args.repo_root.resolve()
    out_path = args.output.resolve()
    if out_path.suffix.lower() != ".zip":
        raise Exception(f"output must be a .zip path, got: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    install_md = _INSTALL_MD.format(generated_utc=generated_utc)

    skip_dirs = {"tests", "history", "__pycache__"}
    code_files = 0
    packaged_hide_tabs: list[str] | None = None

    writer = ZipPackWriter(out_path)
    try:
        writer.write_text("INSTALL.md", install_md)
        writer.write_path(root / "install.bat", "install.bat")
        writer.write_path(root / "dashv2.bat", "dashv2.bat")
        writer.write_path(root / "requirements-dashv2-offline.txt", "requirements-dashv2-offline.txt")
        writer.write_path(root / "hour_bands.json", "hour_bands.json")
        writer.write_text("data/_ticks_stub/.keep", "")
        writer.write_text(
            "setup.json",
            json.dumps(_patch_setup_json(json.loads((root / "setup.json").read_text(encoding="utf-8"))), indent=4) + "\n",
        )
        env_path = root / ".env"
        if not env_path.is_file():
            raise FileNotFoundError(f"missing .env: {env_path}")
        writer.write_path(env_path, ".env")
        model = root / "models" / "delta_win_v2.json"
        if not model.is_file():
            raise FileNotFoundError(f"missing model: {model}")
        writer.write_path(model, "models/delta_win_v2.json")
        dashv2_setup_raw = json.loads((root / "dashv2" / "setup.json").read_text(encoding="utf-8"))
        hide_arg = args.hide_tabs if args.hide_tabs is not None else None
        dashv2_setup = _patch_dashv2_setup(dashv2_setup_raw, hide_arg)
        packaged_hide_tabs = list(dashv2_setup["hide_tabs"])
        code_files += _add_tree(
            writer, root / "dashv2", "dashv2", skip_names=skip_dirs, skip_files={"setup.json"},
        )
        writer.write_text("dashv2/setup.json", json.dumps(dashv2_setup, indent=4) + "\n")
        code_files += 1
        code_files += _add_tree(writer, root / "src", "src", skip_names=set())
        _write_empty_history_scaffold(writer)
        writer.write_text("docs/README-offline.txt", "Vedi INSTALL.md nella root del pacchetto.\n")

        _assert_pack_has_no_runtime_history(writer)
    finally:
        writer.close()

    print(f"written: {out_path}")
    if packaged_hide_tabs is not None:
        print(f"  hide_tabs:  {packaged_hide_tabs or '(nessuna)'}")
    print(f"  code files: {code_files}")
    print(f"  archive:    {_format_bytes(out_path.stat().st_size)}")


if __name__ == "__main__":
    main()
