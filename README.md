# dr-docker

Reusable Docker execution contracts and adapters.

## Purpose

This repo provides Docker runtime contracts and a concrete subprocess adapter:
- Docker runtime request/result contracts with security and resource profiles
- Runtime adapter protocol
- Subprocess-based Docker adapter with stream capping and cidfile cleanup
- Typed error envelopes

## Public Surface

```python
from dr_docker import (
    CONTRACT_VERSION,
    DockerMount,
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ErrorCode,
    ErrorEnvelope,
    ResourceLimits,
    RuntimeAdapter,
    RuntimePrimitiveError,
    SecurityProfile,
    SubprocessDockerAdapter,
    TmpfsMount,
    __version__,
)
```

## Contract Guarantees

- `DockerRuntimeResult(ok=False)` requires `error`
- Successful result envelopes must not include `error`
- Error envelopes are typed (`ErrorCode`) with non-empty message and JSON-safe details
- Supported `ErrorCode` values are `timeout`, `unavailable`, and `internal_error`

## Development

```bash
uv sync --group dev
uv run pytest -q
uv run ruff format --check
uv run ruff check
uv run ty check
```

## Publishing

```bash
cp .env.example .env
# set PYPI_API_TOKEN in .env
set -a; source .env; set +a
uv build
uvx twine check dist/*
uvx twine upload -u __token__ -p "$PYPI_API_TOKEN" dist/*
```
