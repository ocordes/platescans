# Input data overview — `files/SIEGEN_TEST/A1927`

Analysis produced by [`pscripts/tiff_overview.py`](../pscripts/tiff_overview.py);
full machine-generated report: [`results/tiff_overview.txt`](../results/tiff_overview.txt).

## Summary

| File | Format | Size | Frames | Dimensions | Colour coding | Bit depth | Compression |
|---|---|---|---|---|---|---|---|
| `A1927_Ass_Cep_19660919_ND.tif` | Classic TIFF, little-endian | 1.4 GiB | 1 | 27552 × 28011 px | greyscale, BlackIsZero (min-is-black) | 16 bit/sample, 1 sample/px → 16 bpp | none (uncompressed) |
| `A1927_Ass_Cep_19660919_NE.tif` | Classic TIFF, little-endian | 1.4 GiB | 1 | 27552 × 28011 px | greyscale, BlackIsZero | 16 bit/sample → 16 bpp | none |
| `A1927_Ass_Cep_19660919_NU.tif` | Classic TIFF, little-endian | 1.4 GiB | 1 | 27552 × 28011 px | greyscale, BlackIsZero | 16 bit/sample → 16 bpp | none |
| `A1927_Ass_Cep_19660919_NW.tif` | Classic TIFF, little-endian | 1.4 GiB | — | — | — | — | — **corrupt/truncated** |

## Details

* All four files are astronomical **plate scans** (plate A1927, Ass. Cep, 1966-09-19),
  named by quadrant: ND, NE, NU, NW.
* Each readable frame is stored as **28,011 strips of 1 row** each
  (`RowsPerStrip = 1`), chunky planar configuration, sample format not
  specified (default unsigned integer).
* Since the data is uncompressed 16-bit greyscale, on-disk size equals the
  raw size (width × height × 2 bytes ≈ 1.4 GiB).
* **Damaged file:** `A1927_Ass_Cep_19660919_NW.tif` has a valid TIFF header,
  but its Image File Directory (IFD) — stored at the *end* of the file
  (offset 1,543,518,152) — and the last ~25 % of the pixel data are filled
  with `0xFF` padding. The copy appears to have been interrupted; the file
  needs to be re-transferred/re-copied before it can be processed.

## How to regenerate

```bash
python -m pscripts.tiff_overview   # writes results/tiff_overview.txt
```
