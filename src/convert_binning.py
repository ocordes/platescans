"""Convert the plate scans in ``files/`` with configurable N x N sum-binning.

For every input graphics file:

* the output is written with the **same directory layout and file name**,
  rooted at ``results/bin<N>/`` (e.g. ``files/SIEGEN_TEST/A1927/x.tif`` ->
  ``results/bin2/SIEGEN_TEST/A1927/x.tif``),
* every N x N block of pixels (N selectable from **2 to 8**) is replaced by
  a single pixel whose value is the **sum** of all original pixels in the
  block,
* the output format stays **TIFF** (as input); the pixel format is chosen
  automatically: **float32 (single precision) whenever the sum is exact in
  single precision**, otherwise float64.

Precision analysis for these inputs (uint16 pixels, max value 65535):

  max sum = N * N * 65535   ->   N=2: 262,140 | N=4: 1,048,560
                                  N=6: 2,359,260 | N=8: 4,194,240

float32 has a 24-bit mantissa, so every integer up to 2^24 = 16,777,216 is
represented exactly.  All sums for N = 2..8 are <= 4,194,240 < 16,777,216,
so **single precision is sufficient** (and results are bit-exact).  The
script therefore writes float32 for N = 2..8; ``--dtype float64`` forces
double precision if ever needed.

Input files are opened strictly read-only.  Files are processed in
row-blocks via memory mapping, so the 1.4 GiB inputs never need to fit
into RAM at once.

Usage (from the project root, inside the virtual environment):

    python -m src.convert_binning --bin 2 [--dtype float32|float64] [--rows N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterator, Tuple

import numpy as np
import tifffile

INPUT_DIR = Path("files")
RESULTS_DIR = Path("results")
GRAPHICS_SUFFIXES = {".tif", ".tiff"}

MIN_BIN = 2
MAX_BIN = 8
DEFAULT_BLOCK_ROWS = 256  # bin blocks handled per chunk (in output rows)

# uint16 input: the largest possible sum over an N x N block.
MAX_INPUT_VALUE = 65535


def required_precision(n: int) -> str:
    """Smallest float dtype that stores every possible N x N sum exactly."""
    max_sum = n * n * MAX_INPUT_VALUE
    if max_sum < 2 ** 24:  # float32 mantissa: exact integers up to 2^24
        return "float32"
    return "float64"


def bin_block(block: np.ndarray, n: int) -> np.ndarray:
    """Sum an (rows, cols) block in N x N steps -> float32/float64.

    Odd-sized dimensions are handled by summing only the pixels that
    exist (partial blocks along the right/bottom edge).
    """
    rows, cols = block.shape
    out_h = rows // n + (1 if rows % n else 0)
    out_w = cols // n + (1 if cols % n else 0)
    out = np.zeros((out_h, out_w), dtype=np.float64)
    full_h = (rows // n) * n
    full_w = (cols // n) * n
    if full_h and full_w:
        core = block[:full_h, :full_w].astype(np.float64)
        out[: full_h // n, : full_w // n] = core.reshape(
            full_h // n, n, full_w // n, n
        ).sum(axis=(1, 3))
    if full_h and cols % n:  # trailing partial column of blocks
        tail = block[:full_h, full_w:].astype(np.float64)
        out[: full_h // n, -1] = tail.reshape(full_h // n, n, -1).sum(axis=(1, 2))
    if rows % n and full_w:  # trailing partial row of blocks
        tail = block[full_h:, :full_w].astype(np.float64)
        out[-1, : full_w // n] = tail.reshape(-1, full_w // n, n).sum(
            axis=(0, 2)
        )
    if rows % n and cols % n:  # bottom-right corner
        out[-1, -1] = block[full_h:, full_w:].astype(np.float64).sum()
    return out


def iter_row_blocks(
    out_rows: int, n: int, block_out_rows: int, total_rows: int
) -> Iterator[Tuple[int, int]]:
    """Yield (start, end) input row ranges; `start` is always a multiple of `n`.

    `end` is clipped to `total_rows`, so the final block may contain fewer
    than `block_out_rows * n` rows (and its size may be < n when the input
    height is not a multiple of n).  `out_rows` is ceil(total_rows / n).
    """
    start = 0
    while start < total_rows:
        size = min(block_out_rows * n, total_rows - start)
        if start + size < total_rows and size % n:
            size -= size % n  # keep interior blocks aligned to n
        yield start, start + size
        start += size


def convert_file(src: Path, dst: Path, n: int, dtype: np.dtype,
                 block_out_rows: int) -> None:
    """Read `src` read-only, N x N sum-bin, write `dtype` TIFF to `dst`."""
    src_arr = tifffile.memmap(src, mode="r")  # read-only view of the input
    height, width = src_arr.shape[:2]
    out_h = height // n + (1 if height % n else 0)
    out_w = width // n + (1 if width % n else 0)

    dst.parent.mkdir(parents=True, exist_ok=True)
    # memmap-backed output: bound RAM use, then stream to the TIFF writer
    out_arr = np.memmap(str(dst) + ".tmp.mmap", mode="w+", dtype=dtype,
                        shape=(out_h, out_w))

    for start, end in iter_row_blocks(out_h, n, block_out_rows, height):
        # ceil(end / n): the final block may hold fewer than n rows
        out_arr[start // n : -(-end // n)] = bin_block(
            np.asarray(src_arr[start:end]), n
        ).astype(dtype)
    out_arr.flush()

    tifffile.imwrite(dst, out_arr, photometric="minisblack",
                     compression=None, dtype=dtype)

    del out_arr
    Path(str(dst) + ".tmp.mmap").unlink(missing_ok=True)
    del src_arr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--bin", type=int, default=2, choices=range(MIN_BIN, MAX_BIN + 1),
        metavar=f"{MIN_BIN}..{MAX_BIN}",
        help=f"binning factor N (square N x N blocks, {MIN_BIN}-{MAX_BIN})",
    )
    parser.add_argument(
        "--dtype", choices=("auto", "float32", "float64"), default="auto",
        help="output pixel format (default: auto -> float32 when the max "
             "sum is exact in single precision)",
    )
    parser.add_argument("--rows", type=int, default=DEFAULT_BLOCK_ROWS,
                        help="bin blocks processed per chunk (in output rows)")
    args = parser.parse_args()

    n = args.bin
    if args.dtype == "auto":
        dtype = np.dtype(required_precision(n))
    else:
        dtype = np.dtype(args.dtype)
    if n * n * MAX_INPUT_VALUE >= 2 ** 24 and dtype == np.float32:
        print("warning: float32 cannot store the maximum N x N sum exactly",
              file=sys.stderr)

    if not INPUT_DIR.is_dir():
        print(f"input folder not found: {INPUT_DIR}", file=sys.stderr)
        return 1

    graphics = sorted(
        p for p in INPUT_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in GRAPHICS_SUFFIXES
    )
    if not graphics:
        print(f"no graphics files found under {INPUT_DIR}", file=sys.stderr)
        return 1

    print(f"binning {n}x{n}, output pixel format {dtype.name}, "
          f"outputs under {RESULTS_DIR}/bin{n}/")

    failures = 0
    for src in graphics:
        rel = src.relative_to(INPUT_DIR)
        dst = RESULTS_DIR / f"bin{n}" / rel  # same layout, per-bin root
        print(f"binning {src} -> {dst} ...", flush=True)
        try:
            convert_file(src, dst, n, dtype, args.rows)
        except Exception as exc:  # keep going with the remaining files
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        with tifffile.TiffFile(dst) as tf:
            page = tf.pages[0]
            print(f"  done: {page.shape[0]} x {page.shape[1]} px, "
                  f"dtype {np.dtype(page.dtype).name}, "
                  f"compressed={page.compression.name}", flush=True)

    print(f"converted {len(graphics) - failures}/{len(graphics)} file(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
