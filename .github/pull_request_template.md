## Summary

<!-- What changed and why? -->

## Boundary + Contract Checklist

- [ ] I confirmed this PR stays within `nl-runtime-primitives` scope (runtime primitives only; no orchestration loops/policies).
- [ ] If runtime orchestration/loop logic was needed, I routed it to `nl_latents`.
- [ ] I reviewed boundary docs and kept `genprompt` vs `nl_latents` ownership clear.
- [ ] I documented runtime contract impact (if any).
- [ ] I documented contract versioning/migration impact (if any).
- [ ] I validated boundary/contract docs checks locally (`.github/scripts/check_boundary_contract_docs.sh`).

## Testing

- [ ] Tests pass locally.
- [ ] Added/updated tests where behavior changed.
