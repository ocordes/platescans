"""Checks for the configurable N x N sum-binning in ``src.convert_binning``.

Verifies on synthetic arrays (for every supported N = 2..8, including odd
row/column counts and trailing partial blocks) that:

* the output equals the brute-force sum of each N x N block,
* the dtype matches ``required_precision`` (single precision is exact for
  the maximum uint16 sum at every supported N),
* row-block iteration covers every row exactly once with aligned starts.

Run from the project root:

    python -m pscripts.check_binning
"""

from __future__ import annotations

import sys

import numpy as np

from src.convert_binning import (
    MAX_BIN,
    MIN_BIN,
    bin_block,
    iter_row_blocks,
    required_precision,
)


def brute_force(block: np.ndarray, n: int) -> np.ndarray:
    """Reference: sum every existing pixel of each N x N cell."""
    rows, cols = block.shape
    out = np.zeros(
        (rows // n + (1 if rows % n else 0), cols // n + (1 if cols % n else 0)),
        dtype=np.float64,
    )
    for r in range(rows):
        for c in range(cols):
            out[r // n, c // n] += float(block[r, c])
    return out


def test_precision() -> int:
    """Single precision must be exact for every supported N."""
    failures = 0
    for n in range(MIN_BIN, MAX_BIN + 1):
        max_sum = n * n * 65535
        want = "float32" if max_sum < 2 ** 24 else "float64"
        got = required_precision(n)
        if got != want:
            print(f"FAIL precision N={n}: {got} != {want}")
            failures += 1
        # the chosen dtype must round-trip the extreme sum exactly
        if np.float32(max_sum) != np.float64(max_sum):
            print(f"FAIL float32 not exact for N={n} max sum {max_sum}")
            failures += 1
        # worst case: a solid block of maximal pixels sums to n*n*65535
        block = np.full((n, n), 65535, dtype=np.uint16)
        if bin_block(block, n)[0, 0] != np.float64(max_sum):
            print(f"FAIL worst-case sum N={n}")
            failures += 1
    return failures


def test_shapes() -> int:
    failures = 0
    rng = np.random.default_rng(42)
    for n in range(MIN_BIN, MAX_BIN + 1):
        for rows in range(1, 2 * n + 4):  # 1..2N+3 covers odd/partial cases
            for cols in range(1, 2 * n + 4):
                block = rng.integers(0, 65536, size=(rows, cols), dtype=np.uint16)
                got = bin_block(block, n)
                want = brute_force(block, n)
                if got.shape != want.shape:
                    print(f"FAIL shape N={n} {rows}x{cols}: {got.shape} != {want.shape}")
                    failures += 1
                elif not np.array_equal(got, want):
                    print(f"FAIL values N={n} {rows}x{cols}")
                    failures += 1
    return failures


def test_large_random() -> int:
    """Bigger random images, N = 2 and N = 8."""
    failures = 0
    rng = np.random.default_rng(7)
    for n in (2, 8):
        block = rng.integers(0, 65536, size=(37, 53), dtype=np.uint16)
        if not np.array_equal(bin_block(block, n), brute_force(block, n)):
            print(f"FAIL large random N={n}")
            failures += 1
    return failures


def test_row_blocks() -> int:
    """Blocks must align to N, cover every row once, and stay in range."""
    failures = 0
    for n in range(MIN_BIN, MAX_BIN + 1):
        for height in range(1, 700):
            out_rows = height // n + (1 if height % n else 0)
            blocks = list(iter_row_blocks(out_rows, n, 16, height))
            covered = []
            for start, end in blocks:
                if start % n and end != height:
                    print(f"FAIL unaligned block N={n} h={height}: {start}:{end}")
                    failures += 1
                if end > height:
                    print(f"FAIL out-of-range block N={n} h={height}: {start}:{end}")
                    failures += 1
                covered.extend(range(start, end))
            if covered != list(range(height)):
                print(f"FAIL coverage N={n} h={height}")
                failures += 1
            # slice mapping used by convert_file must match bin_block output
            img = rng_for(n).integers(0, 65536, size=(height, 8), dtype=np.uint16)
            out = np.zeros((out_rows, -(-8 // n)), dtype=np.float64)
            for start, end in blocks:
                out[start // n : -(-end // n)] = bin_block(img[start:end], n)
            if not np.array_equal(out, brute_force(img, n)):
                print(f"FAIL slice mapping N={n} h={height}")
                failures += 1
    return failures


_rng_cache: dict = {}


def rng_for(key: int) -> np.random.Generator:
    if key not in _rng_cache:
        _rng_cache[key] = np.random.default_rng(11)
    return _rng_cache[key]


def main() -> int:
    failures = test_precision() + test_shapes() + test_large_random() + test_row_blocks()
    if failures:
        print(f"{failures} check(s) FAILED")
        return 1
    print(f"all binning checks passed (N = {MIN_BIN}..{MAX_BIN})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
