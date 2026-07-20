# Cursor SDK — guida operativa per riuso in altri progetti

Documento di riferimento per un agente/progetto esterno che deve usare lo **stesso account Cursor** (stessa API key, stesso pool di usage) per chiamare modelli come **Composer 2.5** o **Grok 4.5**, **non** necessariamente per riassumere video.

Fonte primaria di questo documento: implementazione reale in **aitube** (`composer.py` + `main.py`), pacchetto installato `cursor-sdk==0.1.8`, docs ufficiali [Python SDK](https://cursor.com/docs/sdk/python) / [TypeScript SDK](https://cursor.com/docs/sdk/typescript), e catalogo modelli restituito da `Cursor.models.list()` sull’account usato da aitube (luglio 2026).

---

## 0. Cosa è (e cosa non è)

### È

- Un SDK ufficiale Cursor (`cursor-sdk` in Python, `@cursor/sdk` in TypeScript) che avvia un **Agent** Cursor in modo programmatico.
- L’agent è lo stesso tipo di agente dell’IDE/CLI/web: può ragionare, usare tool, leggere/scrivere file, chiamare MCP, ecc.
- Autenticazione e billing passano dall’**account Cursor** (User API Key o service account).
- Runtime tipici: **local** (sulla macchina del caller, workspace = `cwd`) oppure **cloud** (VM Cursor).

### Non è

- Un’API “chat completions” stile OpenAI (`/v1/chat/completions`).
- Un wrapper che restituisce solo testo senza side-effect: **di default l’agent è un agent**, non un LLM puro.
- Una chiave separata “per Composer”: Composer/Grok si selezionano col parametro `model`; la chiave è sempre `CURSOR_API_KEY`.

### Implicazione critica per chi riusa questo pattern

Se il tuo scopo è ottenere **solo testo** (traduzione, classificazione, generazione JSON, sommario, ecc.), **devi forzarlo nel prompt** e idealmente validare l’output. Altrimenti l’agent può:

- creare/modificare file nel `cwd`
- usare tool
- rispondere con meta-commenti (“Ho salvato il file in…”) invece del contenuto richiesto

aitube affronta esattamente questo problema (vedi §7 e §9).

---

## 1. Prerequisiti

| Requisito | Dettaglio |
|-----------|-----------|
| Python | **≥ 3.10** (aitube usa 3.12 in venv dedicato) |
| Pacchetto | `pip install cursor-sdk` (aitube: `requirements.txt` → `cursor-sdk`) |
| Account Cursor | Piano con accesso ai modelli desiderati |
| API key | User API Key da [Cursor Dashboard → Integrations / API Keys](https://cursor.com/dashboard/integrations) |
| Env var | `CURSOR_API_KEY` (oppure passaggio esplicito `api_key=...`) |
| OS Windows | Serve un **patch al bridge** (WinError 10038). Obbligatorio su Windows — vedi §8 |

Dipendenze tipiche di supporto (come in aitube):

```text
cursor-sdk
python-dotenv
```

Caricamento `.env` all’avvio (come `main.py`):

```python
from dotenv import load_dotenv
load_dotenv()  # legge .env nella CWD / path standard
```

Esempio `.env` (mai versionare il valore reale):

```env
CURSOR_API_KEY=crsr_xxxxxxxx
```

Nota: le chiavi osservate in pratica possono avere prefisso `crsr_…`. Nei documenti interni aitube compare anche l’esempio `cursor_…`. Non fare assunzioni sul prefisso: usa la chiave generata dalla dashboard così com’è.

---

## 2. Autenticazione e billing

### Auth

1. Apri [cursor.com/dashboard/integrations](https://cursor.com/dashboard/integrations) (sezione API Keys).
2. Crea una **User API Key** (oppure service account key da Team settings).
3. Esporta o metti in `.env`: `CURSOR_API_KEY=...`
4. Nel codice: `api_key=os.environ["CURSOR_API_KEY"]` **oppure** lascia che l’SDK legga da solo `CURSOR_API_KEY` se non passi `api_key`.

Risoluzione `api_key` (ordine tipico SDK):

1. Valore passato esplicitamente a `Agent.create` / `Agent.prompt`
2. Fallback a env `CURSOR_API_KEY`
3. Se manca → `ConfigurationError` / errore di config (non silenzioso)

**Team Admin API keys**: non supportate (al momento della docs ufficiale).

### Billing / usage

- Ogni run SDK consuma il **piano Cursor** come IDE / Cloud Agents.
- Nel dashboard usage le run SDK sono tipicamente taggate come **SDK**.
- Privacy Mode e regole del piano valgono anche qui.
- Token usage per-run: disponibile su `run.usage` / `result.usage` quando il runtime lo espone (`TokenUsage` con `input_tokens`, `output_tokens`, cache, ecc.).

---

## 3. Concetti fondamentali

| Concetto | Significato |
|----------|-------------|
| **Agent** | Handle durevole: modello, workspace, stato conversazione. Può ricevere più `send()`. |
| **Run** | Una singola submission di prompt. Ha `status`, `result`, stream, `wait()`, eventuale `cancel()`. |
| **Local runtime** | Esegue sulla macchina del caller, file relativi a `cwd`. Default se non passi `cloud`. |
| **Cloud runtime** | VM Cursor, tipicamente con repo clonati. ID agent spesso `bc-…`. |
| **Bridge** | Processo locale avviato dall’SDK Python per orchestrare agent locali. Su Windows ha un bug noto (vedi §8). |

Pattern di invocazione (scegline uno):

1. **`Agent.prompt(...)`** — one-shot: create → send → wait → dispose. Ideale per script semplici.
2. **`Agent.create(...)` + `agent.send(...)` + `run.wait()`** — controllo esplicito, retry, logging. **È quello usato da aitube.**
3. **`Agent.resume(agent_id, ...)`** — riprende un agent esistente (multi-process / follow-up differiti).

---

## 4. Pattern minimo riusabile (Python sync, local)

Questo è il nucleo da copiare in un altro progetto (equivalente allo `_prompt()` di aitube, semplificato):

```python
import os
from cursor_sdk import (
    Agent, CursorAgentError, LocalAgentOptions,
    ModelParameterValue, ModelSelection,
)

MODEL = ModelSelection(
    id="composer-2.5",
    params=[ModelParameterValue(id="fast", value="false")],
)

def call_cursor(prompt: str, cwd: str) -> str:
    api_key = os.environ["CURSOR_API_KEY"]
    try:
        with Agent.create(
            api_key=api_key,
            model=MODEL,
            local=LocalAgentOptions(cwd=cwd, auto_review=False),
        ) as agent:
            run = agent.send(prompt)
            result = run.wait()
    except CursorAgentError as e:
        raise RuntimeError(f"Cursor startup failed: {e.message}") from e

    if result.status == "finished" and result.result and result.result.strip():
        return result.result.strip()
    raise RuntimeError(f"Cursor run failed: status={result.status} run_id={result.id}")
```

### Perché queste scelte (come in aitube)

| Scelta | Motivo |
|--------|--------|
| `with Agent.create(...)` | Dispose automatico; evita leak di bridge/processi |
| `local=LocalAgentOptions(cwd=...)` | Runtime locale esplicito (non lasciare il default implicito se ti serve chiarezza) |
| `auto_review=False` | Evita gate Auto-review su tool call in run non interattive |
| `ModelSelection(..., fast="false")` | **Obbligatorio** se vuoi Composer *standard*: senza params, `composer-2.5` risolve al default **fast** (più costoso / diverso billing) |
| `run.wait()` | Sempre: senza `wait()` non hai esito terminale affidabile |
| Distinguere `CursorAgentError` vs `result.status != "finished"` | Startup fallito ≠ run eseguita e fallita |

### Alternativa one-shot

```python
from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

result = Agent.prompt(
    "Il tuo prompt…",
    AgentOptions(
        api_key=os.environ["CURSOR_API_KEY"],
        model=MODEL,
        local=LocalAgentOptions(cwd=".", auto_review=False),
    ),
)
print(result.status, result.result)
```

---

## 5. Selezione modello (Composer, Grok, altri)

### Scoperta dinamica (consigliata)

```python
from cursor_sdk import Cursor

models = Cursor.models.list()  # usa CURSOR_API_KEY
for m in models:
    print(m.id, m.display_name, m.parameters)
```

Non hardcodare slug “a caso”: il catalogo evolve e dipende dall’account.

### Catalogo osservato sull’account aitube (luglio 2026)

Estratto rilevante (34 modelli totali). Parametri = valori ammessi da `Cursor.models.list()`:

| `id` | Display | Parametri tipici |
|------|---------|------------------|
| `composer-2.5` | Composer 2.5 | `fast`: `false` \| `true` |
| `grok-4.5` | Cursor Grok 4.5 | `effort`: `low`\|`medium`\|`high`; `fast`: `false`\|`true` |
| `default` | Auto | (server sceglie) |
| `composer-2` | Composer 2 | `fast` |
| `claude-opus-4-8`, `claude-sonnet-5`, … | Anthropic via Cursor | `thinking`, `context`, `effort`, a volte `fast` |
| `gpt-5.6-sol`, `gpt-5.5`, … | OpenAI via Cursor | `reasoning`, `context`, `fast` |
| `gemini-3.1-pro`, … | Gemini | spesso senza params |
| `kimi-k2.7-code`, `glm-5.2`, … | Altri | vari |

### Composer 2.5 — come lo usa aitube

```python
COMPOSER_MODEL = ModelSelection(
    id="composer-2.5",
    params=[ModelParameterValue(id="fast", value="false")],
)
```

**Attenzione billing:** se passi solo `model="composer-2.5"` senza `params`, Cursor risolve spesso la variante **fast** (dashboard: `composer-2.5-fast`). Per la variante standard (quella che aitube vuole): **`fast=false` esplicito**.

### Grok 4.5 — esempio per l’altro progetto

```python
GROK_MODEL = ModelSelection(
    id="grok-4.5",
    params=[
        ModelParameterValue(id="effort", value="high"),
        ModelParameterValue(id="fast", value="false"),
    ],
)
```

Regola: copia i `params` da `Cursor.models.list()` / preset `variants` del modello, non inventarli.

### Override per-run

```python
from cursor_sdk import SendOptions

run = agent.send(
    "…",
    SendOptions(model=ModelSelection(id="grok-4.5", params=[...])),
)
```

L’override è **sticky**: i `send` successivi senza override usano l’ultimo modello inviato con successo.

---

## 6. Opzioni locali importanti (`LocalAgentOptions`)

Campi rilevanti (SDK 0.1.8):

| Campo | Uso consigliato per batch/LLM-as-text |
|-------|----------------------------------------|
| `cwd` | Directory workspace dell’agent. In aitube: root progetto. Se l’agent può scrivere file, punta a una cartella dedicata/sandbox. |
| `auto_review` | aitube: `False`. Per automazioni headless evita review interattive. |
| `setting_sources` | Default `None` = **solo config inline**. Non mettere `"all"` a caso: caricherebbe MCP/settings IDE dell’utente. |
| `custom_tools` | Solo se vuoi esporre funzioni Python all’agent. |
| `sandbox_options` / `store` | Avanzati; non usati da aitube. |

`mode` su `AgentOptions` / `SendOptions`: `"agent"` (default) o `"plan"`. Per “dammi solo testo” resta tipicamente `"agent"` + prompt anti-tool (vedi §7).

---

## 7. Prompt engineering obbligatorio (agent ≠ completion API)

L’agent Cursor **ha tool**. Per task “solo testo”, aitube aggiunge sempre regole di output:

```text
CRITICO SULL'OUTPUT:
- Rispondi SOLO con il testo richiesto nel messaggio
- NON usare tool, NON creare o modificare file su disco
- NON descrivere cosa hai fatto: l'output deve ESSERE il contenuto richiesto, non un riepilogo
```

Inoltre, dopo la risposta, aitube **valida** che non ci siano meta-commenti tipici dell’agent:

```python
META_MARKERS = (
    "Documento unificato",
    "Struttura del risultato",
    "salvato in `",
    "ho salvato",
    "file salvato",
)

def validate_document_output(text: str, min_chars: int, label: str) -> None:
    if len(text) < min_chars:
        raise RuntimeError(f"{label}: output too short ({len(text)} chars, min {min_chars})")
    for marker in META_MARKERS:
        if marker in text:
            raise RuntimeError(f"{label}: meta-commentary instead of document (found '{marker}')")
```

### Raccomandazioni per l’altro progetto

1. Inserisci regole anti-tool / anti-file **in ogni prompt**.
2. Chiedi un formato output esplicito (es. “SOLO JSON valido”, “SOLO markdown senza preambolo”).
3. Valida lunghezza, schema, assenza di frasi tipo “Ho creato…”, “File salvato…”.
4. Se serve isolamento totale dai file del progetto: `cwd` su directory vuota/temporanea dedicata.
5. Non assumere che `result.result` sia sempre il contenuto utile: controlla `status == "finished"` e testo non vuoto.

---

## 8. Patch Windows obbligatoria (bridge / WinError 10038)

Su Windows, `cursor_sdk` usa `select()` su pipe stderr del bridge → **`OSError: [WinError 10038]`**.

aitube monkey-patcha `cursor_sdk._bridge._read_discovery` **prima** di ogni uso dell’SDK. Senza questa patch, su Windows falliscono anche operazioni semplici come `Cursor.models.list()`.

Implementazione di riferimento (da `composer.py`):

```python
def _patch_cursor_sdk_windows() -> None:
    """cursor-sdk usa select() su pipe stderr: su Windows fallisce con WinError 10038."""
    if sys.platform != "win32":
        return
    import cursor_sdk._bridge as bridge

    def _read_discovery(process, timeout: float) -> Mapping[str, Any]:
        if process.stderr is None:
            raise bridge.CursorSDKError("Bridge process stderr is unavailable")
        stderr_fd = process.stderr.fileno()
        was_blocking = os.get_blocking(stderr_fd)
        os.set_blocking(stderr_fd, False)
        try:
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            deadline = time.monotonic() + timeout
            stderr_lines: list[str] = []
            pending = ""

            def drain_available() -> Mapping[str, Any] | None:
                nonlocal pending
                while True:
                    try:
                        chunk = os.read(stderr_fd, 8192)
                    except BlockingIOError:
                        return None
                    if not chunk:
                        final_text = decoder.decode(b"", final=True)
                        if final_text:
                            pending += final_text
                        if pending:
                            line, pending = pending, ""
                            stderr_lines.append(line)
                            return bridge.parse_discovery_line(line)
                        return None
                    pending += decoder.decode(chunk)
                    while "\n" in pending:
                        line, pending = pending.split("\n", 1)
                        line += "\n"
                        stderr_lines.append(line)
                        discovery = bridge.parse_discovery_line(line)
                        if discovery is not None:
                            return discovery

            while time.monotonic() < deadline:
                discovery = drain_available()
                if discovery is not None:
                    return discovery
                if process.poll() is not None:
                    discovery = drain_available()
                    if discovery is not None:
                        return discovery
                    raise bridge.CursorSDKError(
                        f"Bridge exited before discovery with status {process.poll()}: "
                        + "".join(stderr_lines) + pending
                    )
                time.sleep(0.05)
            raise bridge.CursorSDKError("Timed out waiting for bridge discovery")
        finally:
            os.set_blocking(stderr_fd, was_blocking)

    bridge._read_discovery = _read_discovery


_patch_cursor_sdk_windows()
# SOLO DOPO il patch:
from cursor_sdk import Agent, ...
```

**Ordine obbligatorio:** applicare il patch **prima** di `Agent.create` / `Cursor.models.list` / `Agent.prompt`.

Su Linux/macOS la funzione ritorna subito: nessun effetto.

---

## 9. Come aitube usa Cursor SDK (riferimento end-to-end)

Questo paragrafo descrive *il caso d’uso di aitube*. L’altro progetto **non** deve copiare lo scopo (riassunto video), ma può copiare l’infrastruttura.

### Dove sta il codice

| File | Ruolo |
|------|-------|
| `composer.py` | Unico wrapper SDK: patch Windows, modello, `_prompt()`, `rewrite_chunk()`, `generate_summary()`, validazione |
| `main.py` | `load_dotenv()`; pipeline; chiama rewrite per chunk e summary sul documento finale |
| `.env` | `CURSOR_API_KEY` (gitignored) |
| `requirements.txt` | `cursor-sdk`, `faster-whisper`, `python-dotenv` |

### Flusso pipeline (solo parte LLM)

1. Trascrizione Whisper → chunk temporali (~`chunk_max_sec`, es. 600s).
2. Per ogni chunk **non in cache**: `rewrite_chunk(...)` → chiamata Composer → markdown riscritto + marker screenshot.
3. Assemblaggio **locale** dei chunk in `content.md` (**nessuna** chiamata LLM di merge).
4. `generate_summary(full_doc)` → altra chiamata Composer → `summary.md`.
5. Cache: `chunk_XX.md` su disco; se esiste, skip chiamata SDK.

### Funzione centrale `_prompt`

Comportamento reale:

- Legge `os.environ["CURSOR_API_KEY"]` (no default: se manca → `KeyError`).
- Fino a **3 tentativi** (`COMPOSER_RETRIES = 3`), delay **15s** tra tentativi.
- Ogni tentativo: nuovo `Agent.create` → un `send` → `wait`.
- Successo solo se `result.status == "finished"` e `result.result` non vuoto.
- `CursorAgentError` → fallimento immediato (startup), non retry di run.
- Run fallita → log warning + retry; dopo 3 → `RuntimeError` con dettagli (`status`, `run_id`, `duration_ms`, ultimi turni di `conversation()` se supportati).

### Due task LLM di aitube (solo come esempio di prompt)

**A) `rewrite_chunk`** — riscrittura completa (non riassunto) di un pezzo di trascrizione, con regole su paragrafi/timestamp/marker `[SCREENSHOT ts=MM:SS]`. Validazione: output ≥ 50% lunghezza input; niente meta-marker.

**B) `generate_summary`** — sommario tematico medio-lungo del documento completo. Validazione: minimo caratteri; non troppo lungo (≥ 90% del doc ⇒ sospetto di aver ritrascritto tutto).

### Cosa aitube *non* fa con l’SDK

- Non usa cloud agents.
- Non usa streaming (`messages()` / `iter_text()`): solo `wait()`.
- Non usa MCP / custom tools.
- Non usa `Agent.resume`.
- Non usa merge LLM: il merge è concatenazione Python.

---

## 10. Gestione errori (modello mentale)

Due famiglie distinte:

| Situazione | Segnale | Cosa fare |
|------------|---------|-----------|
| Auth/config/rete/bridge non parte | Eccezione `CursorAgentError` (e sottotipi: `AuthenticationError`, `RateLimitError`, …) | Controlla key, rete, patch Windows; guarda `err.is_retryable`, `err.retry_after`, `err.request_id` |
| Run partita ma fallita | `result.status` in `error` / `cancelled` / `expired` | Logga `result.id`, `agent.agent_id`, eventuale `run.conversation()`; retry se ha senso |
| Run ok ma testo inutile | `status==finished` ma meta-commenti / troppo corto | Validazione applicativa (come aitube) + retry con prompt più stretto |

Snippet stile produzione:

```python
try:
    run = agent.send(prompt)
    result = run.wait()
    if result.status == "error":
        # run eseguita e fallita
        ...
except CursorAgentError as err:
    # non è partita / errore infrastrutturale
    # err.is_retryable, err.retry_after, err.message, err.request_id
    ...
```

---

## 11. Retry e resilienza (pattern aitube)

```text
COMPOSER_RETRIES = 3
COMPOSER_RETRY_DELAY_SEC = 15
```

- Retry su run non `finished` / risultato vuoto.
- **Non** confondere con `err.is_retryable` dello SDK: aitube oggi rilancia subito su `CursorAgentError`.
- Per l’altro progetto: se vedi `RateLimitError` / `is_retryable=True`, onora `retry_after` prima di ritentare.
- Ogni tentativo: **nuovo** `Agent.create` (conversazione pulita). Utile per task one-shot “solo testo”.

---

## 12. Logging e debug utili

Subito dopo `send()` / dopo `wait()`:

- `agent.agent_id` — es. `agent-…` (local)
- `run.id` / `result.id`
- `result.status`, `result.duration_ms`
- `result.model` — selezione effettivamente usata
- `result.usage` / `run.usage` — se presente
- Se fallisce: `run.conversation()` (ultimi turni) se `run.supports("conversation")`

In dashboard Cursor: filtra Source → **SDK** per vedere le run cloud; le local restano sulla macchina ma con ID loggabili.

---

## 13. Async (se l’altro progetto è un server)

aitube è sync. Per concurrency:

```python
from cursor_sdk import AsyncClient, LocalAgentOptions

async with await AsyncClient.launch_bridge(workspace=".") as client:
    async with await client.agents.create(
        model=MODEL,
        api_key=os.environ["CURSOR_API_KEY"],
        local=LocalAgentOptions(cwd=".", auto_review=False),
    ) as agent:
        run = await agent.send("…")
        result = await run.wait()
```

Regole: non mescolare sync e async client nello stesso path; un `AsyncClient` per event loop.

---

## 14. TypeScript (stessi concetti)

```typescript
import { Agent } from "@cursor/sdk";

await using agent = await Agent.create({
  apiKey: process.env.CURSOR_API_KEY!,
  model: { id: "composer-2.5", params: [{ id: "fast", value: "false" }] },
  local: { cwd: process.cwd() },
});

const run = await agent.send("…");
const result = await run.wait();
```

Install: `npm install @cursor/sdk`. Docs: https://cursor.com/docs/sdk/typescript

---

## 15. Checklist per portare il pattern in un altro progetto

1. [ ] `pip install cursor-sdk` (+ `python-dotenv` se usi `.env`)
2. [ ] Creare API key Cursor e impostare `CURSOR_API_KEY`
3. [ ] Su Windows: copiare `_patch_cursor_sdk_windows()` e chiamarlo **prima** degli import/uso agent
4. [ ] Smoke test: `Cursor.models.list()` e stampare gli `id` disponibili sull’account
5. [ ] Scegliere modello con `ModelSelection` + params espliciti (`fast=false` per Composer standard; `effort`/`fast` per Grok)
6. [ ] Usare `Agent.create` + `send` + `wait` in `with`, oppure `Agent.prompt`
7. [ ] Impostare `local=LocalAgentOptions(cwd=..., auto_review=False)`
8. [ ] Scrivere prompt con regole “solo testo / no tool / no file”
9. [ ] Validare `status`, lunghezza, formato, assenza di meta-commenti
10. [ ] Gestire retry e distinguere `CursorAgentError` vs run fallita
11. [ ] Loggare `agent_id` e `run_id`
12. [ ] Verificare sul dashboard usage che il modello fatturato sia quello atteso (es. non `composer-2.5-fast` se volevi standard)

---

## 16. Anti-pattern da evitare

| Anti-pattern | Perché |
|--------------|--------|
| Usare `model="composer-2.5"` senza `fast=false` | Spesso fattura come **fast** |
| Non validare l’output | L’agent può rispondere con narrazione operativa invece del deliverable |
| `setting_sources="all"` in un servizio | Carica MCP/settings dell’utente host in modo imprevedibile |
| Dimenticare `wait()` | Run “appese”, niente esito |
| Non fare dispose / non usare `with` | Leak bridge/processi |
| Ignorare la patch Windows | Fallimenti sistematici su Win |
| Confondere agent ID (`agent-` / `bc-`) con run ID | Debug impossibile |
| Trattare l’SDK come OpenAI Chat API | Contratto diverso (agent + tool + workspace) |
| Hardcodare slug modello senza `models.list()` | Account senza accesso → errori a runtime |

---

## 17. Riferimenti rapidi codice aitube

### Modello e create (estratto concettuale da `composer.py`)

```python
COMPOSER_MODEL = ModelSelection(
    id="composer-2.5",
    params=[ModelParameterValue(id="fast", value="false")],
)

with Agent.create(
    api_key=api_key,
    model=COMPOSER_MODEL,
    local=LocalAgentOptions(cwd=str(PROJECT_ROOT), auto_review=False),
) as agent:
    run = agent.send(text)
    result = run.wait()
```

### Entry env (`main.py`)

```python
from dotenv import load_dotenv
load_dotenv()
```

### Chiamate pipeline

- `rewrite_chunk(raw, title, channel, i, total)` → testo chunk
- `generate_summary(full_doc)` → `summary.md`

File completo da leggere nel repo: `composer.py`.

---

## 18. Link ufficiali

- Python SDK: https://cursor.com/docs/sdk/python
- TypeScript SDK: https://cursor.com/docs/sdk/typescript
- Dashboard API Keys / Integrations: https://cursor.com/dashboard/integrations
- PyPI: https://pypi.org/project/cursor-sdk/
- Skill Cursor IDE: comando `/sdk` dentro Cursor per setup guidato

---

## 19. Template “drop-in” consigliato per l’altro progetto

Struttura minima suggerita:

```text
altro-progetto/
├── .env                 # CURSOR_API_KEY=...
├── agents/cursor_client.py     # patch Windows + call_model() + validate
├── requirements.txt     # cursor-sdk, python-dotenv
└── ...
```

`agents/cursor_client.py` dovrebbe esportare qualcosa come:

```python
def call_model(prompt: str, *, model_id: str, params: list[tuple[str, str]], cwd: str) -> str:
    ...
```

dove `params` è tipicamente `[("fast", "false")]` o `[("effort", "high"), ("fast", "false")]` per Grok.

Il resto del progetto costruisce i prompt per il **proprio** scopo; l’infrastruttura Cursor resta identica a quella documentata qui.

---

*Documento generato dal progetto aitube come guida di riuso dell’account Cursor via SDK. Versione SDK di riferimento: `cursor-sdk` 0.1.8. Aggiornare `Cursor.models.list()` se il catalogo modelli cambia.*
