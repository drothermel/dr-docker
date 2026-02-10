# Loop Architecture Paradigm

## Intent

Keep loop architecture explicit, modular, and repository-scoped.

## Repository responsibilities

- `nl_latents` owns loop orchestration:
  - Control flow, step progression, scheduling, selector/policy logic, budget loops
- `genprompt` owns prompt primitives:
  - Prompt blocks, composition, registries, arm-catalog semantics
- `nl-runtime-primitives` owns runtime integration primitives:
  - Docker and Langfuse primitive contracts and validations

## Paradigm constraints

1. Orchestration is isolated from integration primitives.
2. Prompt ownership is isolated from runtime integration ownership.
3. Runtime primitives are deterministic contract providers, not loop controllers.

## Practical routing

- Request involves loop behavior or runtime policy: implement in `nl_latents`.
- Request involves prompt primitives or catalog composition: implement in `genprompt`.
- Request involves Docker/Langfuse integration contracts/primitives: implement in `nl-runtime-primitives`.

## Change coordination

When loop features require new runtime primitive fields:
1. Propose interface change from `nl_latents`.
2. Align `nl_latents` + `genprompt` + `nl-runtime-primitives` owners.
3. Land only the agreed primitive contract updates in `nl-runtime-primitives`.
