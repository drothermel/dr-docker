# Loop Architecture Paradigm (Mirror)

This document mirrors the canonical architecture contract in:
- `genprompt/docs/loop_architecture_paradigm.md`

If there is any conflict, the `genprompt` canonical document is authoritative.

## Local Summary

1. `nl-runtime-primitives` owns Docker/Langfuse runtime primitives only.
2. Loop orchestration belongs to `nl_latents`, not this repository.
3. Prompt primitive/catalog ownership belongs to `genprompt`.
4. Runtime surfaces should remain narrow, versioned contracts.
