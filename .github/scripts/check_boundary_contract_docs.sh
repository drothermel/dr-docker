#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Required boundary/contract docs for this repository.
REQUIRED_DOCS=(
  "README.md"
  "docs/loop_architecture_paradigm.md"
  "docs/runtime_primitives_contract.md"
)

# Required marker families that must appear across the required docs.
REQUIRED_MARKERS=(
  "runtime primitives"
  "nl_latents"
  "genprompt"
  "boundary"
  "contract"
  "version"
)

missing_docs=()
for doc in "${REQUIRED_DOCS[@]}"; do
  if [[ ! -f "$ROOT_DIR/$doc" ]]; then
    missing_docs+=("$doc")
  fi
done

if (( ${#missing_docs[@]} > 0 )); then
  echo "Boundary contract doc check FAILED: missing required docs"
  printf ' - %s\n' "${missing_docs[@]}"
  exit 1
fi

combined=""
for doc in "${REQUIRED_DOCS[@]}"; do
  # Lowercase to make marker checks case-insensitive.
  combined+="$(tr '[:upper:]' '[:lower:]' < "$ROOT_DIR/$doc")"
  combined+=$'\n'
done

missing_markers=()
for marker in "${REQUIRED_MARKERS[@]}"; do
  if ! grep -Fq "$marker" <<< "$combined"; then
    missing_markers+=("$marker")
  fi
done

if (( ${#missing_markers[@]} > 0 )); then
  echo "Boundary contract doc check FAILED: missing required marker coverage"
  printf ' - %s\n' "${missing_markers[@]}"
  exit 1
fi

echo "Boundary contract doc check PASSED"
echo "Validated docs: ${REQUIRED_DOCS[*]}"
echo "Validated markers: ${REQUIRED_MARKERS[*]}"
