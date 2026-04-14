"""Utilities for batch execution with recursive infra-failure isolation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, overload

from .adapters import RuntimePrimitiveError

TItem = TypeVar("TItem")
TResult = TypeVar("TResult")
TInfraFailure = TypeVar("TInfraFailure", bound=Exception)


@overload
def run_batch_with_failure_isolation(
    items_by_id: list[tuple[str, TItem]],
    run_batch: Callable[[list[TItem]], list[TResult]],
) -> tuple[dict[str, TResult], dict[str, RuntimePrimitiveError]]: ...


@overload
def run_batch_with_failure_isolation(
    items_by_id: list[tuple[str, TItem]],
    run_batch: Callable[[list[TItem]], list[TResult]],
    *,
    infra_failure_type: type[TInfraFailure],
) -> tuple[dict[str, TResult], dict[str, TInfraFailure]]: ...


def run_batch_with_failure_isolation(
    items_by_id: list[tuple[str, TItem]],
    run_batch: Callable[[list[TItem]], list[TResult]],
    *,
    infra_failure_type: type[Exception] = RuntimePrimitiveError,
) -> tuple[dict[str, TResult], dict[str, Exception]]:
    """Run batched work, recursively splitting on batch-level infra failures."""

    seen_item_ids: set[str] = set()
    duplicate_item_ids: list[str] = []
    for item_id, _item in items_by_id:
        if item_id in seen_item_ids and item_id not in duplicate_item_ids:
            duplicate_item_ids.append(item_id)
        seen_item_ids.add(item_id)
    if duplicate_item_ids:
        duplicate_ids = ", ".join(repr(item_id) for item_id in duplicate_item_ids)
        raise ValueError(f"Duplicate item IDs are not allowed: {duplicate_ids}")

    results: dict[str, TResult] = {}
    infra_failures: dict[str, Exception] = {}

    def process_chunk(chunk: list[tuple[str, TItem]]) -> None:
        if not chunk:
            return

        try:
            chunk_results = run_batch([item for _, item in chunk])
        except infra_failure_type as exc:
            if len(chunk) == 1:
                infra_failures[chunk[0][0]] = exc
                return

            midpoint = len(chunk) // 2
            process_chunk(chunk[:midpoint])
            process_chunk(chunk[midpoint:])
            return

        for (item_id, _item), result in zip(chunk, chunk_results, strict=True):
            results[item_id] = result

    process_chunk(items_by_id)
    return results, infra_failures
