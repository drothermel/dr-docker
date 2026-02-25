# CLAUDE.md

Operational guidance for working in `dr-docker`.

## What To Optimize For

- Preserve a small, stable public contract.
- Prefer strict, explicit behavior over permissive fallbacks.
- Keep changes minimal and easy to reason about.

## Scope Rules

Allowed:
- Docker runtime primitive contracts
- Runtime adapter and validation behavior
- Typed error-envelope behavior
- Tests for contract guarantees

Not allowed:
- Orchestration/control-loop logic
- Scheduler/policy/selector behavior
- Prompt-catalog or prompt-composition ownership

## Change Rules

- Do not add broad compatibility shims.
- Do not expand the public surface without clear necessity.
- Treat validator behavior and exported symbols as contract-critical.
- If a change breaks downstream expectations, bump `CONTRACT_VERSION` and package version together.

## Testing Standard

Before finishing work, run:

```bash
uv run pytest -q
uv run ruff check
uv run ty check
```

If behavior changed, tests should clearly pin the new behavior.

## Practical Style

- Keep errors typed and deterministic (`ErrorCode` + `ErrorEnvelope`).
- Prefer explicit failure over silent fallback.
- Keep contracts small and explicit at package boundaries.
- Keep docs concise; avoid duplicating large architectural narratives.
