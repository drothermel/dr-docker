# nl-runtime-primitives

Runtime integration primitives for the NL stack.

## Purpose

This repository owns foundational runtime integration contracts and helpers for:
- Docker runtime primitives
- Langfuse integration primitives

Ownership is limited to integration primitives and their contracts. This repo is not the home for loop logic or prompt primitives.

## Scope

Allowed in this repository:
- Typed interfaces and schemas for Docker/Langfuse runtime integration
- Runtime integration adapters and validation utilities (primitive level)
- Contract docs and compatibility guarantees for downstream runtimes

Disallowed in this repository:
- Loop orchestration, controller state machines, scheduling, or runtime policy loops
- Exploration/exploitation selectors or budget execution loops
- Prompt primitive ownership, prompt block registries, or prompt composition logic

## Repo Routing (3-Repo Boundary)

- `nl-runtime-primitives` (this repo): Docker/Langfuse runtime integration primitives and contracts
- `nl_latents`: Loop orchestration, runtime control, selectors, policies, and execution flows
- `genprompt`: Prompt primitives, block registries, arm catalogs, and prompt composition contracts

## Docs

- `docs/runtime_primitives_contract.md`
- `docs/loop_architecture_paradigm.md`
- `AGENTS.md`
- `CLAUDE.md`

## Quickstart (Placeholders)

1. Clone repo and install dependencies (TBD).
2. Configure Docker and Langfuse runtime integration settings (TBD).
3. Run primitive-level validation/tests (TBD).
4. Consume exported contracts from downstream runtimes (TBD).

Until implementation details are finalized, treat this repo primarily as contract and boundary guidance.
