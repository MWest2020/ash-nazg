"""Binary type detection by magic bytes.

Per `detection/spec.md`:
- The host shim reads at most the first 512 bytes via WebDAV range
  request, then classifies the file into a magic-byte family
  before any engine selection.
- Recognised families: pe32, pe32-plus, mz-dos, elf, wasm, jar,
  mach-o, unknown.
- Extension is a fallback hint only — it refines an already-matched
  magic-byte family (e.g. ZIP + `.jar` → jar) but never overrides
  the magic check.

This module is pure: no I/O, no async. The dispatcher does the
WebDAV range read and passes raw bytes here.
"""

from __future__ import annotations

import struct
from typing import Final

# Magic-byte families. Strings are normative — appear in audit logs
# and SessionConfig.SUPPORTED_MAGIC sets on engines, so keep stable.
PE32: Final[str] = "pe32"
PE32_PLUS: Final[str] = "pe32-plus"
MZ_DOS: Final[str] = "mz-dos"
ELF: Final[str] = "elf"
WASM: Final[str] = "wasm"
JAR: Final[str] = "jar"
MACH_O: Final[str] = "mach-o"
UNKNOWN: Final[str] = "unknown"

# Read at most this many bytes for detection. The detection spec
# limits this to 512; we expose it as a constant so callers can do
# range-request math.
DETECTION_READ_BYTES: Final[int] = 512

# The PE header offset lives at file offset 0x3c (u32 little-endian).
_PE_OFFSET_FIELD: Final[int] = 0x3C

# PE signature (4) + COFF File Header (20) = 24. The Optional Header
# starts immediately after, and its first u16 is the Magic field that
# tells PE32 (0x010B) from PE32+ (0x020B).
_OPTHDR_MAGIC_FROM_PE_SIG: Final[int] = 4 + 20  # = 24
_PE32_OPTHDR_MAGIC: Final[int] = 0x010B
_PE32_PLUS_OPTHDR_MAGIC: Final[int] = 0x020B

# Mach-O magic words (covers thin 32/64 and FAT). All start at offset 0.
_MACH_O_MAGICS: Final[frozenset[bytes]] = frozenset(
    {
        b"\xfe\xed\xfa\xce",  # MH_MAGIC (32-bit, big-endian host)
        b"\xce\xfa\xed\xfe",  # MH_CIGAM (32-bit, swapped)
        b"\xfe\xed\xfa\xcf",  # MH_MAGIC_64
        b"\xcf\xfa\xed\xfe",  # MH_CIGAM_64
        b"\xca\xfe\xba\xbe",  # FAT_MAGIC
        b"\xbe\xba\xfe\xca",  # FAT_CIGAM
    }
)


def _classify_mz(head: bytes) -> str:
    """Refine an MZ-prefixed binary to pe32 / pe32-plus / mz-dos."""
    if len(head) < _PE_OFFSET_FIELD + 4:
        return MZ_DOS
    (pe_offset,) = struct.unpack_from("<I", head, _PE_OFFSET_FIELD)
    if pe_offset == 0 or pe_offset + 4 > len(head):
        return MZ_DOS
    if head[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        return MZ_DOS

    opthdr_at = pe_offset + _OPTHDR_MAGIC_FROM_PE_SIG
    if opthdr_at + 2 > len(head):
        # PE signature without enough room for opt-header magic.
        # Treat as plain PE32; the engine still handles it.
        return PE32
    (opt_magic,) = struct.unpack_from("<H", head, opthdr_at)
    if opt_magic == _PE32_PLUS_OPTHDR_MAGIC:
        return PE32_PLUS
    return PE32


def classify(head: bytes, extension: str = "") -> str:
    """Classify the binary based on its leading bytes + extension hint.

    `head` must contain the first up to DETECTION_READ_BYTES of the file.
    `extension` is the lowercased file extension without the leading dot
    (e.g. "exe", "jar"); pass "" if unknown.

    Returns one of the family constants defined in this module.
    """
    if len(head) < 2:
        return UNKNOWN

    # ELF — `\x7fELF`
    if head.startswith(b"\x7fELF"):
        return ELF

    # WASM — `\x00asm`
    if head.startswith(b"\x00asm"):
        return WASM

    # MZ (PE / DOS)
    if head[:2] == b"MZ":
        return _classify_mz(head)

    # Mach-O / FAT
    if len(head) >= 4 and head[:4] in _MACH_O_MAGICS:
        return MACH_O

    # ZIP-family: refine to jar only on extension hint, else unknown.
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        if extension.lower() == "jar":
            return JAR
        # Plain .zip / unknown archive — caller returns 415 per spec.
        return UNKNOWN

    return UNKNOWN
