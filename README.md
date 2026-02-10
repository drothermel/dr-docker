# nl-runtime-primitives

Frozen runtime integration contracts for the NL stack.

## Purpose

This repo provides the minimum stable contract surface needed by `nl_latents`:
- Docker runtime request/result contracts
- Langfuse prompt/trace contracts
- Adapter protocols
- Typed error envelopes

If work does not directly strengthen these contracts, it does not belong here.

## Freeze Policy

This repository is in maintenance/freeze mode.
- No feature expansion
- No compatibility shims
- No orchestration or policy behavior
- Changes are contract-hardening, bug fixes, or security fixes only

Breaking changes require:
1. Explicit contract proposal from downstream (`nl_latents`)
2. Coordinated migration plan
3. `CONTRACT_VERSION` bump

## Out Of Scope

- Loop orchestration/runtime control/policy logic -> `nl_latents`
- Prompt primitive ownership/composition/catalog logic -> `genprompt`

## Contract Guarantees

- `DockerRuntimeResult(ok=False)` requires `error`
- `TraceAck(accepted=False)` requires `error`
- Successful envelopes must not include `error`
- `PromptPayload.system_content` is always a string (default `""`)
- Prompt extraction expects chat messages with exactly one `user` message
- `PromptFetchRequest.variables` must be JSON-safe
- `TraceEventRequest.metadata` must be JSON-safe
- Error envelopes are typed (`ErrorCode`) with non-empty message and JSON-safe details

## Public Surface

```python
from nl_runtime_primitives import (
    DockerMount,
    DockerRuntimeRequest,
    DockerRuntimeResult,
    PromptFetchRequest,
    PromptPayload,
    TraceEventRequest,
    TraceAck,
    RuntimeAdapter,
    PromptProvider,
    TraceEmitter,
    ErrorCode,
    ErrorEnvelope,
    RuntimePrimitiveError,
    LangfuseConfig,
    LangfusePromptProvider,
    LangfuseTraceEmitter,
    CONTRACT_VERSION,
)
```

## Versioning

- `CONTRACT_VERSION` is the compatibility gate for downstream consumers.
- Contract-breaking changes must bump `CONTRACT_VERSION`.

## Development

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check
uv run ty check
uv run pre-commit install
```
