---
name: subagents
description: Decides when to launch Task subagents vs doing the work in the parent agent. Use when considering parallel agents, worktrees, explore, generalPurpose, verifier, docs-keeper, issue-steward, /parallel-plan, /flow, or spawning more than one agent.
---

# Subagenti (irswitch)

Parent dělá práci sám u 1–3 konkrétních souborů nebo pár kroků.
Subagent jen když se vyplatí izolace, paralelismus, nebo specializovaný typ.

Projektoví agenti jsou v `.cursor/agents/` (`issue-steward`, `docs-keeper`, `verifier`).
Paralelní **upravující** agenti jen po `/parallel-plan` **a** schválení uživatele.

## Použij

| Typ | Kdy |
|-----|-----|
| `explore` | Neznámé místo v kódu, víc cest/jmen, „jak to funguje“ |
| `generalPurpose` | Složitý výzkum / multi-step bez vlastního typu |
| `docs-keeper` | Po změně kódu/config/CI — docs contract včetně `docs/dokumentace/` (`/flow`, `/docs-impact`, skill `dokumentace`) |
| `issue-steward` | Issue + dev diary přes GitHub MCP (`/flow`, `/ensure-issue`) |
| `verifier` | Po úpravách kódu/doků/CI — lint/test report (`/qa`) |
| `ci-investigator` | Jeden padající PR check |
| `bugbot` / `security-review` | **Jen** když to uživatel výslovně chce |
| `best-of-n-runner` | Izolovaný experiment ve vlastním worktree |
| `shell` | Dlouhé izolované git/shell operace (ne místo 1–2 příkazů) |

## Nepoužívej

- Needle: známý soubor/třída/endpoint → Grep/Read v parentovi
- Překryv souborů, zvlášť `logic/` + `iracing/` + API v jednom burstu
- Společný state machine / API kontrakt
- Změna kódu bez schválení
- Commit / push / PR z subagenta bez výslovného „commit/push/PR“
- `bugbot` / `security-review` „pro jistotu“

## Paralelní worktrees

Každý nezávislý úkol: vlastní větev + vlastní issue + jeden worktree. Nikdy commit na `master`.
Po dokončení vrať diff + evidence. Push/PR jen po schválení.

Překryv → sekvenčně. Stopnuté agenty a stash ping-pong = mělo to jít za sebou.

Než spustíš víc upravujících agentů: `/parallel-plan`, počkej na OK.

## Jak spouštět

- Jeden Task call na agenta; víc nezávislých = víc Task v **jedné** zprávě
- Prompt musí obsahovat celý kontext (subagent nevidí historii parenta)
- `run_in_background: true` v Multitask Mode
- Po kódu z subagenta: parent zkontroluje diff, nespouští overlapping agenty

## Výstup (vyžaduj od subagenta)

- co změnil / našel (soubory)
- evidence (test / příkaz)
- co nespouštět dál (překryv)
