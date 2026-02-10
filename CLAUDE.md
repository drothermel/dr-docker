# Claude guidance for nl-runtime-primitives

## Repository mission

This repository is the runtime integration owner for Docker and Langfuse primitives.

## Canonical contract

Canonical scope, ownership, and routing rules live in `CONSTRAINTS.md`.

In short, this repo owns runtime integration primitives and does not own orchestration or prompt composition.

## 3-repo routing

- `nl-runtime-primitives`: Docker/Langfuse runtime integration primitives
- `nl_latents`: Loop orchestration/runtime execution logic
- `genprompt`: Prompt primitive and catalog contracts

## Working rule

When a request mixes scopes, implement only the `nl-runtime-primitives` contract surface and route orchestration/prompt ownership work to the correct repo.
