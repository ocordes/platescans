# Configurable N x N sum-binning conversion

Script: [`src/convert_binning.py`](../src/convert_binning.py)
Check: [`pscripts/check_binning.py`](../pscripts/check_binning.py)

## What it does

For every graphics file under `files/`:

* writes an output file with the **same directory layout and name**, rooted
  at `results/bin<N>/`
  (`files/SIEGEN_TEST/A1927/x.tif` → `results/bin<N>/SIEGEN_TEST/A1927/x.tif`)
* bins pixels in **N x N blocks** (N a **parameter, 2–8**), each output
  pixel = **sum** of all original pixels in the block
* output format stays **TIFF** (as input); pixel format is **chosen
  automatically**: single precision (float32) whenever it stores every sum
  exactly, else float64

## Output pixel format decision

Inputs are uint16 (max value 65535). Max possible sum = N² × 65535:

| N | max sum | float32 exact? (24-bit mantissa, exact ≤ 2²⁴ = 16,777,216) |
|---|---|---|
| 2 | 262,140 | yes |
| 4 | 1,048,560 | yes |
| 6 | 2,359,260 | yes |
| 8 | 4,194,240 | yes |

All sums for N = 2..8 are ≤ 4,194,240 < 16,777,216, so **single precision
is sufficient** and results are bit-exact. The script therefore writes
float32 for every supported N (verified in `test_precision`). Override
with `--dtype float64` if ever needed.

## Run

```bash
pip install -r requirements.txt   # numpy, tifffile
python -m pscripts.check_binning          # verify binning logic (N = 2..8)
python -m src.convert_binning --bin 2     # 2x2 binning (default)
python -m src.convert_binning --bin 8     # 8x8 binning
# options: --dtype auto|float32|float64, --rows N (chunk size)
```

Processing is chunked over memory-mapped row blocks, so the 1.4 GiB inputs
never fully fit into RAM; inputs are opened strictly read-only.

## Results (2026-10-24)

| Output | Shape | Dtype |
|---|---|---|
| `results/bin2/SIEGEN_TEST/A1927/..._{ND,NE,NU}.tif` | 14006 × 13776 px | float32 |
| `results/bin8/SIEGEN_TEST/A1927/..._{ND,NE,NU}.tif` | 3502 × 3444 px | float32 |
| `..._NW.tif` | **not converted** — input corrupt/truncated (see [input_data.md](input_data.md)) | |

Verification: `python -m pscripts.check_binning` passes for N = 2..8
(brute-force reference for all shapes incl. odd/partial blocks, exactness
of the float32 decision, worst-case sums of solid max-pixel blocks,
row-block alignment/coverage, slice mapping). Converted outputs were
cross-checked against independent brute-force sums at interior patches and
along the odd trailing row/column — exact matches at bin 2 and bin 8.
`files/` is untouched.
