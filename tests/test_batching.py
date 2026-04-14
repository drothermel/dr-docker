from __future__ import annotations

from dr_docker import (
    ErrorCode,
    ErrorEnvelope,
    RuntimePrimitiveError,
    run_batch_with_failure_isolation,
)


def _runtime_infra_error(message: str) -> RuntimePrimitiveError:
    return RuntimePrimitiveError(
        ErrorEnvelope(
            code=ErrorCode.UNAVAILABLE,
            message=message,
            retriable=True,
        )
    )


def test_run_batch_with_failure_isolation_full_batch_success() -> None:
    calls: list[list[int]] = []

    def run_batch(items: list[int]) -> list[str]:
        calls.append(items)
        return [f"result-{item}" for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("a", 1), ("b", 2), ("c", 3)],
        run_batch,
    )

    assert results == {"a": "result-1", "b": "result-2", "c": "result-3"}
    assert infra_failures == {}
    assert calls == [[1, 2, 3]]


def test_run_batch_with_failure_isolation_isolates_one_infra_failure() -> None:
    failing_items = {3}

    def run_batch(items: list[int]) -> list[int]:
        if any(item in failing_items for item in items):
            raise _runtime_infra_error(f"batch failed for {items}")
        return [item * 10 for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("a", 1), ("b", 2), ("c", 3), ("d", 4)],
        run_batch,
    )

    assert results == {"a": 10, "b": 20, "d": 40}
    assert set(infra_failures) == {"c"}
    assert infra_failures["c"].error.code is ErrorCode.UNAVAILABLE
    assert infra_failures["c"].error.message == "batch failed for [3]"


def test_run_batch_with_failure_isolation_isolates_multiple_infra_failures() -> None:
    class _BatchInfraFailure(Exception):
        pass

    failing_items = {2, 5}

    def run_batch(items: list[int]) -> list[str]:
        if any(item in failing_items for item in items):
            raise _BatchInfraFailure(",".join(str(item) for item in items))
        return [f"ok-{item}" for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("one", 1), ("two", 2), ("three", 3), ("four", 4), ("five", 5)],
        run_batch,
        infra_failure_type=_BatchInfraFailure,
    )

    assert results == {
        "one": "ok-1",
        "three": "ok-3",
        "four": "ok-4",
    }
    assert set(infra_failures) == {"two", "five"}
    assert isinstance(infra_failures["two"], _BatchInfraFailure)
    assert str(infra_failures["two"]) == "2"
    assert str(infra_failures["five"]) == "5"


def test_run_batch_with_failure_isolation_handles_empty_input() -> None:
    calls = 0

    def run_batch(items: list[int]) -> list[int]:
        nonlocal calls
        calls += 1
        return items

    results, infra_failures = run_batch_with_failure_isolation([], run_batch)

    assert results == {}
    assert infra_failures == {}
    assert calls == 0


def test_run_batch_with_failure_isolation_preserves_result_id_alignment() -> None:
    def run_batch(items: list[int]) -> list[str]:
        return [f"value-{item}" for item in items]

    results, infra_failures = run_batch_with_failure_isolation(
        [("gamma", 3), ("alpha", 1), ("beta", 2)],
        run_batch,
    )

    assert results == {
        "gamma": "value-3",
        "alpha": "value-1",
        "beta": "value-2",
    }
    assert infra_failures == {}
