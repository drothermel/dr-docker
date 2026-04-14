# dr-docker

Reusable Docker execution contracts and adapters.

## Purpose

This repo provides Docker runtime contracts and a concrete subprocess adapter:
- Docker runtime request/result contracts with security and resource profiles
- Runtime adapter protocol
- Subprocess-based Docker adapter with stream capping and cidfile cleanup
- Worker helpers for mounted scripts/directories with reusable runtime policies
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
    MountedWorker,
    ResourceLimits,
    RuntimeAdapter,
    RuntimePrimitiveError,
    SecurityProfile,
    SubprocessDockerAdapter,
    TmpfsMount,
    WorkerRuntimePolicy,
    __version__,
    build_mounted_worker_request,
    execute_batch_in_container,
    mount_worker_directory,
    mount_worker_file,
    run_batch_with_failure_isolation,
)
```

## Worker Support

`dr-docker` now includes a small worker-support layer for the common pattern of:
- starting from a reusable isolated runtime policy
- mounting a local worker file or directory into the container
- building a `DockerRuntimeRequest` with stdin, env, mounts, tmpfs, and resource limits already wired together

```python
from pathlib import Path

from dr_docker import (
    WorkerRuntimePolicy,
    build_mounted_worker_request,
    mount_worker_file,
)

worker = mount_worker_file(Path("worker.py"), mount_target="/sandbox")
worker = worker.with_path_command(
    entrypoint="python3",
    args_before_path=["-I"],
    working_dir="/tmp",
)

policy = WorkerRuntimePolicy.small_isolated().model_copy(
    update={"memory": "1g", "tmpfs_exec": True}
)

request = build_mounted_worker_request(
    image="python:3.12-slim",
    worker=worker,
    timeout_seconds=30,
    policy=policy,
    stdin_payload='{"job": "ping"}',
    env={"WORKER_MODE": "json"},
)
```

For optional worker-side JSON-over-stdin helpers, use `dr_docker.workers.json_stdio`. That module intentionally stays separate from the core Docker contract layer and includes bounded stdin reading, bounded stdout capture, container guards, and basic RLIMIT helpers.

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
