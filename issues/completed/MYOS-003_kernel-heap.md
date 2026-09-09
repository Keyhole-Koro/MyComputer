# Kernel Heap Improvements

> **[古い / STALE 2026-09-09] tickets/ から completed/ へ移動。本文は最新の実装状況を反映していません。**
> - 実装済み: High Priority（隣接ブロック統合）と Efficiency（アドレス順 free
>   list）は commit `891a42d "feat(heap): coalescing free list, exhaustion
>   panic, unit tests"` で実装済み。Robustness の Heap Exhaustion Handling
>   （`debug.panic`）も実装済み。
> - 未実装（残作業）: best/next-fit の評価、Header Integrity Checks、Heap
>   Statistics は未実装。再着手する前に本文を書き直すこと。

The current kernel heap implementation (`system/MyKernel/src/libs/heap.mln`) is a basic first-fit free-list allocator. Several improvements are needed for long-term stability and efficiency.

## High Priority

- **Implement adjacent block coalescing (merging)**: 
  When a block is freed, check if the physical neighbors are also free and merge them into a single larger block. This prevents fragmentation where the sum of free memory is enough but no single block is large enough for an allocation.

## Efficiency

- **Ordered Free List**: 
  Maintain the free list sorted by memory address to make coalescing easier (linear time or better).
- **Best-fit or Next-fit strategy**: 
  Evaluate if other allocation strategies reduce fragmentation for common kernel workloads.

## Robustness

- **Heap Exhaustion Handling**: 
  Define clear behavior (e.g., panic or return error codes) when the kernel runs out of memory.
- **Header Integrity Checks**: 
  Add magic numbers or checksums to block headers to detect heap corruption caused by buffer overflows.

## Diagnostics

- **Heap Statistics**: 
  Add functions to report total used/free memory and the number of free blocks for debugging and monitoring.
