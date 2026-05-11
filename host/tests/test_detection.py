"""Tests for `ash_nazg.detection`.

Covers the `detection` spec scenarios:
- PE32 binary detected (MZ + PE header, optional-header magic 0x010B)
- PE32+ detected (optional-header magic 0x020B)
- mz-dos detected (MZ without PE signature)
- ELF detected
- WASM detected
- Mach-O detected (all four flavours plus FAT)
- Unknown / textual file → unknown
- ZIP + .jar extension → jar
- Plain ZIP → unknown (caller returns 415 per spec)
"""

from __future__ import annotations

import struct

import pytest

from ash_nazg.detection import (
    ELF,
    JAR,
    MACH_O,
    MZ_DOS,
    PE32,
    PE32_PLUS,
    UNKNOWN,
    WASM,
    classify,
)


def _make_pe(opt_magic_word: int) -> bytes:
    """Build a minimal MZ+PE header with the given optional-header magic."""
    pe_offset = 0x80
    head = bytearray(512)
    head[0:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, pe_offset)
    head[pe_offset : pe_offset + 4] = b"PE\x00\x00"
    # File Header is 20 bytes (PE\0\0 + 20 = 24 from PE signature start)
    # Optional Header magic is at PE_offset + 24
    struct.pack_into("<H", head, pe_offset + 24, opt_magic_word)
    return bytes(head)


# --- MZ / PE family -------------------------------------------------------


def test_pe32_detected() -> None:
    assert classify(_make_pe(0x010B)) == PE32


def test_pe32_plus_detected() -> None:
    assert classify(_make_pe(0x020B)) == PE32_PLUS


def test_mz_dos_no_pe_signature() -> None:
    """MZ header but bytes at PE-offset are not 'PE\\0\\0' → mz-dos."""
    head = bytearray(512)
    head[0:2] = b"MZ"
    # leave 0x3c onward zero; PE-offset 0 → not a PE
    assert classify(bytes(head)) == MZ_DOS


def test_mz_dos_short_file() -> None:
    """MZ header in a tiny file (< 0x40 bytes) → mz-dos by default."""
    assert classify(b"MZ" + b"\x00" * 10) == MZ_DOS


def test_mz_keen_lzexe_compressed() -> None:
    """Real-world Keen1.exe (LZEXE-compressed, no PE signature) → mz-dos."""
    head = bytes(
        [0x4D, 0x5A, 0xF6, 0x01, 0x64, 0x00, 0x00, 0x00, 0x02, 0x00, 0x9F, 0x11,
         0xFF, 0xFF, 0x92, 0x18, 0x80, 0x00, 0x00, 0x00, 0x0E, 0x00, 0x66, 0x0C,
         0x1C, 0x00, 0x00, 0x00, 0x4C, 0x5A, 0x39, 0x31]
    ) + b"\x00" * 480
    assert classify(head) == MZ_DOS


# --- ELF, WASM ------------------------------------------------------------


def test_elf_detected() -> None:
    assert classify(b"\x7fELF" + b"\x00" * 60) == ELF


def test_wasm_detected() -> None:
    assert classify(b"\x00asm\x01\x00\x00\x00") == WASM


# --- Mach-O ---------------------------------------------------------------


@pytest.mark.parametrize(
    "magic",
    [
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
    ],
)
def test_mach_o_variants(magic: bytes) -> None:
    assert classify(magic + b"\x00" * 60) == MACH_O


# --- ZIP / JAR ------------------------------------------------------------


def test_zip_with_jar_extension_classifies_as_jar() -> None:
    head = b"PK\x03\x04" + b"\x00" * 60
    assert classify(head, extension="jar") == JAR


def test_zip_with_jar_extension_case_insensitive() -> None:
    head = b"PK\x03\x04" + b"\x00" * 60
    assert classify(head, extension="JAR") == JAR


def test_plain_zip_without_jar_extension_is_unknown() -> None:
    head = b"PK\x03\x04" + b"\x00" * 60
    assert classify(head, extension="zip") == UNKNOWN


def test_empty_zip_marker() -> None:
    head = b"PK\x05\x06" + b"\x00" * 60
    assert classify(head, extension="zip") == UNKNOWN


# --- Unknown / fallback ---------------------------------------------------


def test_text_file_unknown() -> None:
    assert classify(b"#!/usr/bin/env python\n\nprint('hi')\n") == UNKNOWN


def test_empty_unknown() -> None:
    assert classify(b"") == UNKNOWN


def test_one_byte_unknown() -> None:
    assert classify(b"M") == UNKNOWN
