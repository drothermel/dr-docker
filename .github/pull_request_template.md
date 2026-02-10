## Summary

<!-- What changed and why? -->

## Context / Issue

<!-- Link the relevant issue or background context -->

## User-visible impact

<!-- Describe user-visible changes (or explicitly note "none") -->

## Manual test steps

<!-- List manual steps taken (if any), with outcomes -->

## Screenshots / GIFs (if UI changes)

<!-- Provide before/after evidence for UI changes -->

## Boundary + Contract Checklist

- [ ] I confirmed this PR stays within `nl-runtime-primitives` scope (runtime primitives only; no orchestration loops/policies).
- [ ] If runtime orchestration/loop logic was needed, I routed it to `nl_latents`.
- [ ] I reviewed boundary docs and kept `genprompt` vs `nl_latents` ownership clear.
- [ ] I documented runtime contract impact (if any).
- [ ] I documented contract versioning/migration impact (if any).
- [ ] I validated boundary/contract docs checks locally (`.github/scripts/check_boundary_contract_docs.sh`).

## Testing

- [ ] Tests pass locally (include commands and results).
- [ ] Added/updated tests where behavior changed.
