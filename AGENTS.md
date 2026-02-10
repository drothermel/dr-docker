# nl-runtime-primitives agent boundary

## Non-negotiable rule

Only implement Docker and Langfuse runtime integration primitives in this repository.

## Allowed scope

- Primitive-level Docker runtime integration contracts and helpers
- Primitive-level Langfuse integration contracts and helpers
- Validation, typing, and artifact surfaces required by downstream runtimes
- Documentation of runtime integration contracts

## Disallowed scope

- Loop orchestration, loop runtime control, or execution-policy loops
- Scheduler/controller state machines and per-step runtime decision logic
- Selector/exploration/exploitation implementations
- Prompt primitive ownership, prompt composition, block registries, arm-catalog generation

## Routing

- Route loop/runtime orchestration work to `nl_latents`
- Route prompt primitive and prompt-catalog work to `genprompt`
- Keep this repo focused on Docker/Langfuse integration primitives only

## Contract change escalation

If loop/runtime work in `nl_latents` needs integration-contract updates here:

1. Open a contract proposal in `nl_latents` with required interface changes.
2. Align owners of `nl_latents`, `genprompt`, and `nl-runtime-primitives` on versioning/migration.
3. Implement only the agreed integration-contract surface in this repo.
