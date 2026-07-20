# Agenti AI (dashV2)

Moduli e prompt usati dall’app per chat AI, codegen strategie deterministic, reverse-pass coded rules e codegen analyze (Stats).

## Layout

| File | Ruolo |
|------|--------|
| `common_prompt.md` | Dominio condiviso (Polymarket, lessico, zone, rules↔coded rules) |
| `agent_system_prompt.md` | Chat AI Agent (COMMON + questo) |
| `strategy_system_prompt.md` | Codegen rules → Python (COMMON + questo) |
| `coded_rules_prompt.md` | Reverse-pass Python → coded rules (COMMON + questo; `{{SOURCE}}`) |
| `stats_system_prompt.md` | Codegen analyze Stats |
| `agent_chat.py` | Persistenza thread chat per sessione |
| `agent_service.py` | Orchestrazione turno chat + tool |
| `agent_round_tools.py` | Tool lettura round dal repository |
| `cursor_client.py` | Chiamate Cursor SDK (`call_model`) |
| `strategy_codegen.py` | Generazione / validazione moduli strategy + coded rules |
| `stats_codegen.py` | Generazione / validazione moduli analyze |

I prompt si ricaricano a caldo da `dashv2.config` (`reload_*_prompt`). Modifiche ai soli `.md` non richiedono restart se il processo rilegge il file a ogni turno/codegen; dopo spostamenti di moduli Python serve `data/restart`.

## Import

```python
from dashv2.agents.agent_service import AgentService
from dashv2.agents.strategy_codegen import generate_strategy_module
from dashv2.config import reload_agent_system_prompt
```
