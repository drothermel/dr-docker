# Claude guidance for nl-runtime-primitives

## Repository mission

This repository is the runtime integration owner for Docker and Langfuse primitives.

## Hard boundaries

Do:
- Define and maintain primitive-level integration contracts
- Provide typed interfaces, validation, and minimal adapter utilities for Docker/Langfuse integration
- Preserve backward-compatible contract evolution where practical

Do not:
- Implement loop orchestration or runtime control flows
- Add selector, policy, or budget-loop logic
- Own prompt primitives, prompt block registries, or prompt composition

## 3-repo routing

- `nl-runtime-primitives`: Docker/Langfuse runtime integration primitives
- `nl_latents`: Loop orchestration/runtime execution logic
- `genprompt`: Prompt primitive and catalog contracts

## Working rule

When a request mixes scopes, implement only the `nl-runtime-primitives` contract surface and route orchestration/prompt ownership work to the correct repo.
