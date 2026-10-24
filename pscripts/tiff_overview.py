"""Overview of the graphics files in the ``files/`` input folder.

The plate scans are huge (> 1 GB each), so this script never reads pixel
data.  It only parses the TIFF header / IFD chain (pure standard library,
no external packages required) and reports for every file and every frame:

* file type (byte order, TIFF flavour, number of frames)
* frame size (width x height in pixels, uncompressed size in bytes)
* colour coding (photometric interpretation, samples per pixel,
  planar configuration)
* bit depth (bits per sample)
* compression state (compression scheme, strip layout, on-disk size)

Usage (from the project root, inside the virtual environment):

    python -m pscripts.tiff_overview

The report is printed and written to ``results/tiff_overview.txt``.
Input files under ``files/`` are only opened read-only.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

INPUT_DIR = Path("files")
RESULTS_DIR = Path("results")
OUTPUT_FILE = RESULTS_DIR / "tiff_overview.txt"

# TIFF tag ids we care about
TAG_IMAGE_WIDTH = 256
TAG_IMAGE_LENGTH = 257
TAG_BITS_PER_SAMPLE = 258
TAG_COMPRESSION = 259
TAG_PHOTOMETRIC = 262
TAG_STRIP_OFFSETS = 273
TAG_SAMPLES_PER_PIXEL = 277
TAG_ROWS_PER_STRIP = 278
TAG_STRIP_BYTE_COUNTS = 279
TAG_PLANAR_CONFIG = 284
TAG_TILE_WIDTH = 322
TAG_TILE_LENGTH = 323
TAG_SAMPLE_FORMAT = 339

TIFF_TYPES = {
    1: ("B", 1),   # BYTE
    2: ("s", 1),   # ASCII
    3: ("H", 2),   # SHORT
    4: ("I", 4),   # LONG
    5: ("II", 8),  # RATIONAL
    6: ("b", 1),   # SBYTE
    7: ("B", 1),   # UNDEFINED
    8: ("h", 2),   # SSHORT
    9: ("i", 4),   # SLONG
    10: ("ii", 8),  # SRATIONAL
    11: ("f", 4),  # FLOAT
    12: ("d", 8),  # DOUBLE
}

PHOTOMETRIC = {
    0: "WhiteIsZero (min-is-white greyscale)",
    1: "BlackIsZero (min-is-black greyscale)",
    2: "RGB",
    3: "Palette/colour-map",
    4: "Transparency mask",
    5: "CMYK",
    6: "YCbCr",
    8: "CIE L*a*b*",
}

COMPRESSION = {
    1: "none (uncompressed)",
    2: "CCITT modified Huffman RLE",
    3: "CCITT Group 3 fax",
    4: "CCITT Group 4 fax",
    5: "LZW",
    6: "JPEG (old style)",
    7: "JPEG (new style)",
    8: "Adobe Deflate",
    32773: "PackBits",
    34712: "JPEG2000",
    34892: "Lossy JPEG2000",
    34925: "LZMA",
    34926: "Zstd",
    34927: "WebP",
    34933: "Zstd (lossless)",
    34934: "LZ4",
}

SAMPLE_FORMAT = {1: "unsigned integer", 2: "signed integer", 3: "IEEE float",
                 4: "undefined", 5: "complex integer", 6: "complex float"}

PLANAR = {1: "chunky (interleaved)", 2: "planar (separate planes)"}


@dataclass
class FrameInfo:
    index: int
    width: int = 0
    height: int = 0
    bits_per_sample: List[int] = field(default_factory=list)
    samples_per_pixel: int = 1
    photometric: int = -1
    compression: int = -1
    planar_config: int = -1
    sample_format: int = -1
    rows_per_strip: int = -1
    strip_offsets: List[int] = field(default_factory=list)
    strip_byte_counts: List[int] = field(default_factory=list)
    strip_count: int = 0
    tiled: bool = False


def _read_tiff_value(fh, file_size: int, byteorder: str, typ: int, count: int,
                     raw: bytes) -> list:
    """Decode `count` values of TIFF type `typ`; `raw` is the 4-byte value field.

    Values that do not fit into the 4-byte field are read from their
    out-of-line offset in the (seekable) file.  Only a small window is
    read, so this is safe for multi-GB files.
    """
    if typ not in TIFF_TYPES:
        return []
    fmt, size = TIFF_TYPES[typ]
    if count * size <= len(raw):
        payload = raw[:count * size]
    else:
        offset_fmt = "Q" if len(raw) == 8 else "I"
        (offset,) = struct.unpack(byteorder + offset_fmt, raw[:struct.calcsize(offset_fmt)])
        length = count * size
        # strip offset/count arrays are capped: only first 100k entries
        max_len = min(length, 100_000 * size)
        if offset + max_len > file_size:
            max_len = max(0, file_size - offset)
        fh.seek(offset)
        payload = fh.read(max_len)
    if typ == 2:  # ASCII
        return [payload.split(b"\x00")[0].decode("ascii", "replace")]
    if fmt in ("II", "ii"):
        return [struct.unpack(byteorder + fmt, payload[i * 8:(i + 1) * 8])[0]
                for i in range(count)]
    return list(struct.unpack(byteorder + fmt * count, payload))


def parse_tiff_frames(path: Path) -> tuple[str, List[FrameInfo]]:
    """Return (byte-order/flavour description, list of FrameInfo)."""
    file_size = path.stat().st_size
    with path.open("rb") as fh:
        data_head = fh.read(16)
        if data_head[:4] in (b"II*\x00", b"MM\x00*"):
            byteorder = "<" if data_head[:2] == b"II" else ">"
            flavour = "Classic TIFF (little-endian)" if byteorder == "<" else "Classic TIFF (big-endian)"
            (ifd_offset,) = struct.unpack(byteorder + "I", data_head[4:8])
            entry_size, count_fmt, val_off = 12, "HHI", 8
        elif data_head[:4] in (b"II+\x00", b"MM\x00+"):
            byteorder = "<" if data_head[:2] == b"II" else ">"
            flavour = "BigTIFF (little-endian)" if byteorder == "<" else "BigTIFF (big-endian)"
            _, _, ifd_offset = struct.unpack(byteorder + "HHQ", data_head[2:16])
            entry_size, count_fmt, val_off = 20, "HHQ", 12
        else:
            raise ValueError("not a TIFF file")

        frames: List[FrameInfo] = []
        index = 0
        while ifd_offset and ifd_offset < file_size:
            fh.seek(ifd_offset)
            if flavour.startswith("Classic"):
                (num_tags,) = struct.unpack(byteorder + "H", fh.read(2))
            else:
                (num_tags,) = struct.unpack(byteorder + "Q", fh.read(8))
            if num_tags == 0 or num_tags > 1000:
                raise ValueError(
                    f"corrupt or truncated TIFF: implausible tag count {num_tags} "
                    f"at IFD offset {ifd_offset} (file size {file_size:,})"
                )
            entries = fh.read(num_tags * entry_size)
            if len(entries) != num_tags * entry_size:
                raise ValueError(
                    f"corrupt or truncated TIFF: IFD #{index} runs past end of file"
                )
            if flavour.startswith("Classic"):
                (next_ifd,) = struct.unpack(byteorder + "I", fh.read(4))
            else:
                (next_ifd,) = struct.unpack(byteorder + "Q", fh.read(8))

            frame = FrameInfo(index=index)
            for i in range(num_tags):
                entry = entries[i * entry_size:(i + 1) * entry_size]
                tag, typ, count = struct.unpack(byteorder + count_fmt, entry[:struct.calcsize(count_fmt)])
                values = _read_tiff_value(fh, file_size, byteorder, typ, count,
                                          entry[val_off:entry_size])
                if tag == TAG_IMAGE_WIDTH and values:
                    frame.width = values[0]
                elif tag == TAG_IMAGE_LENGTH and values:
                    frame.height = values[0]
                elif tag == TAG_BITS_PER_SAMPLE and values:
                    frame.bits_per_sample = values
                elif tag == TAG_COMPRESSION and values:
                    frame.compression = values[0]
                elif tag == TAG_PHOTOMETRIC and values:
                    frame.photometric = values[0]
                elif tag == TAG_SAMPLES_PER_PIXEL and values:
                    frame.samples_per_pixel = values[0]
                elif tag == TAG_PLANAR_CONFIG and values:
                    frame.planar_config = values[0]
                elif tag == TAG_SAMPLE_FORMAT and values:
                    frame.sample_format = values[0]
                elif tag == TAG_ROWS_PER_STRIP and values:
                    frame.rows_per_strip = values[0]
                elif tag == TAG_TILE_WIDTH and values:
                    frame.tiled = True
                elif tag == TAG_STRIP_OFFSETS and values:
                    frame.strip_offsets = values
                elif tag == TAG_STRIP_BYTE_COUNTS and values:
                    frame.strip_byte_counts = values
                    frame.strip_count = count
            frames.append(frame)
            index += 1
            ifd_offset = next_ifd
            if index > 10000:  # safety guard
                break
        return flavour, frames
    return "", []


def describe_frame(frame: FrameInfo, file_size: int) -> str:
    bits = "/".join(str(b) for b in frame.bits_per_sample) or "?"
    total_bits = sum(frame.bits_per_sample) if frame.bits_per_sample else 0
    photometric = PHOTOMETRIC.get(frame.photometric, f"unknown ({frame.photometric})")
    compression = COMPRESSION.get(frame.compression, f"unknown ({frame.compression})")
    planar = PLANAR.get(frame.planar_config, f"unknown ({frame.planar_config})")
    sample_fmt = SAMPLE_FORMAT.get(frame.sample_format, "not specified")

    px_count = frame.width * frame.height
    raw_bytes = px_count * total_bits // 8 if total_bits else 0
    stored_bytes = sum(frame.strip_byte_counts)

    lines = [
        f"  Frame {frame.index}:",
        f"    size              : {frame.width} x {frame.height} px"
        f"  ({px_count:,} pixels)",
        f"    raw (uncompressed): {human_bytes(raw_bytes)}",
        f"    on disk           : {human_bytes(stored_bytes)}"
        + ("  (whole file)" if frame.index == 0 and stored_bytes >= file_size * 0.9 else ""),
        f"    bit depth         : {bits} bits/sample, {frame.samples_per_pixel} sample(s)/pixel"
        f"  -> {total_bits} bit/pixel",
        f"    colour coding     : {photometric}",
        f"                      : planar config {planar}, sample format {sample_fmt}",
        f"    compression       : {compression}",
    ]
    if frame.tiled:
        lines.append("    layout            : tiled")
    elif frame.strip_count:
        lines.append(f"    layout            : {frame.strip_count:,} strip(s), "
                     f"rows/strip {frame.rows_per_strip}")
    return "\n".join(lines)


def human_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n:,} B"
        n /= 1024.0
    return f"{n} B"


def sniff_format(path: Path) -> str:
    with path.open("rb") as fh:
        head = fh.read(12)
    if head[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return "TIFF"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if head[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if head[:4] == b"BM":
        return "BMP"
    if head[:4] == b"II*\x00":
        return "TIFF"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    return "unknown"


def main() -> None:
    if not INPUT_DIR.is_dir():
        raise SystemExit(f"input folder not found: {INPUT_DIR}")

    graphics = sorted(
        p for p in INPUT_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp", ".gif"}
    )

    report: List[str] = []
    report.append("Graphics file overview")
    report.append("=" * 60)
    report.append(f"input folder : {INPUT_DIR}  (read-only)")
    report.append(f"files found  : {len(graphics)}")

    for path in graphics:
        size = path.stat().st_size
        fmt = sniff_format(path)
        report.append("")
        report.append("-" * 60)
        report.append(f"file         : {path}")
        report.append(f"format       : {fmt}")
        report.append(f"file size    : {human_bytes(size)} ({size:,} bytes)")
        if fmt == "TIFF":
            try:
                flavour, frames = parse_tiff_frames(path)
            except (ValueError, struct.error) as exc:
                report.append(f"variant      : UNREADABLE - {exc}")
                report.append("  -> file appears damaged/truncated; header could not be parsed")
            else:
                report.append(f"variant      : {flavour}")
                report.append(f"frames       : {len(frames)}")
                for frame in frames:
                    report.append(describe_frame(frame, size))
        else:
            report.append("  (no header parser for this format implemented)")

    text = "\n".join(report) + "\n"
    print(text)
    RESULTS_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(text)
    print(f"report written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
