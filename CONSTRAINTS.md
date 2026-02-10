# Runtime Primitives Contract

## Purpose

Define the contract surface owned by `nl-runtime-primitives` for runtime integration primitives only.

## Ownership

`nl-runtime-primitives` owns:
- Docker integration primitives (typed config, adapter interface, validation boundaries)
- Langfuse integration primitives (typed config, event/trace interface boundaries, validation)
- Stable contract artifacts consumed by downstream runtimes

`nl-runtime-primitives` does not own:
- Loop orchestration or runtime control execution
- Selector/policy/budget loop behavior
- Prompt primitive definitions or prompt composition contracts

## Contract surfaces

1. Docker primitive contract
- Defines how runtimes provide container/runtime configuration
- Defines validation constraints and error boundaries
- Exposes deterministic, typed interfaces only

2. Langfuse primitive contract
- Defines tracing/telemetry integration inputs and output envelope boundaries
- Defines validation constraints for instrumentation primitives
- Exposes deterministic, typed interfaces only

3. Adapter protocol layer
- `execute_in_runtime(request) -> DockerRuntimeResult`
- `fetch_prompt(request) -> PromptPayload`
- `emit_trace(event) -> TraceAck`
- Infra failures use typed `ErrorEnvelope` semantics (or `RuntimePrimitiveError`
  for `fetch_prompt` failures).

## Cross-repo interface model

- `nl_latents` consumes runtime primitives and implements orchestration/execution flows
- `genprompt` provides prompt-side contracts consumed by orchestrated systems
- `nl-runtime-primitives` remains orchestration-agnostic and prompt-agnostic

## Versioning and change policy

- Contract changes must be explicit and documented.
- Breaking changes require migration notes and coordinated version updates across dependent repos.
- New fields should be additive and backward-compatible where possible.

## Routing rule

If requested work requires loop runtime control or prompt primitive changes, route to:
- `nl_latents` for orchestration/runtime control
- `genprompt` for prompt primitives/composition
