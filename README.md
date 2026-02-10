# nl-runtime-primitives

Runtime integration primitives for the NL stack.

## Purpose

This repository owns foundational runtime integration contracts and helpers for:
- Docker runtime primitives
- Langfuse integration primitives
- Adapter protocols used by loop/orchestration clients

Ownership is limited to integration primitives and their contracts. This repo is not the home for loop logic or prompt primitives.

## Scope

Allowed in this repository:
- Typed interfaces and schemas for Docker/Langfuse runtime integration
- Runtime integration adapters and validation utilities (primitive level)
- Contract docs and strict guarantees for downstream runtimes

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

## Quickstart

1. Install development dependencies:
   ```bash
   uv sync --group dev
   ```
2. Run tests:
   ```bash
   uv run pytest -q
   ```
3. Construct contract models in Python:
   ```python
   from nl_runtime_primitives import DockerRuntimeRequest, TraceEventRequest

   docker_req = DockerRuntimeRequest.model_validate({
       "image": "python:3.12-slim",
       "command": ["python", "-c", "print('ok')"],
       "timeout_seconds": 10,
   })

   langfuse_trace = TraceEventRequest.model_validate({
       "event_name": "runtime-primitive-test",
       "session_id": "session-123",
   })

   print(docker_req.model_dump())
   print(langfuse_trace.model_dump())
   ```
4. Consume exported contracts from downstream runtimes.

## Current status

- Contract models are available for prompt providers, trace emission, and
  runtime execution request/response envelopes.
- A strict protocol adapter layer is available for downstream wiring.
- `nl_latents` consumes these contracts through its bridge layer; loop logic
  still lives entirely in `nl_latents`.

Orchestration remains out of scope in this repository by design.
