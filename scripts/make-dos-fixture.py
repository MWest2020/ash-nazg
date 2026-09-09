#!/usr/bin/env python3
"""Write a tiny, self-authored MZ-DOS .exe for testing the Run flow.

The demo needs *some* DOS binary, and shipping a game (or any
third-party binary) would drag licensing into the test path — the
`sandbox` spec's "No bundled non-open-source content" requirement is
explicit about that. So this generates one: 60 bytes that print a line
and exit through int 21h. It is a real MZ executable, so `detection`
classifies it as `mz-dos` exactly like a real DOS program.

    python3 scripts/make-dos-fixture.py /tmp/hello.exe
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

MESSAGE = b"ASH NAZG OK\r\n$"

# push cs / pop ds       — DS:=CS, so the message offset is code-relative
# mov ah,09 / mov dx,msg — DOS "print $-terminated string"
# int 21h
# mov ax,4C00h / int 21h — exit(0)
CODE = bytes(
    [0x0E, 0x1F, 0xB4, 0x09, 0xBA, 0x0E, 0x00, 0xCD, 0x21, 0xB8, 0x00, 0x4C, 0xCD, 0x21]
)
assert len(CODE) == 0x0E, "the mov dx,0x000E above is the offset of MESSAGE"

HEADER_PARAGRAPHS = 2  # 32-byte header


def build() -> bytes:
    body = CODE + MESSAGE
    total = HEADER_PARAGRAPHS * 16 + len(body)
    header = struct.pack(
        "<2s13H",
        b"MZ",
        total % 512,          # bytes used on the last page
        (total + 511) // 512,  # pages
        0,                     # relocations
        HEADER_PARAGRAPHS,     # header size in paragraphs
        0x20,                  # minalloc: 512 bytes, room for the stack
        0xFFFF,                # maxalloc
        0x0000,                # initial SS (relative to load segment)
        0x0200,                # initial SP
        0,                     # checksum (unused)
        0x0000,                # initial IP
        0x0000,                # initial CS (relative to load segment)
        0x001C,                # offset of the relocation table
        0,                     # overlay number
    )
    return header.ljust(HEADER_PARAGRAPHS * 16, b"\x00") + body


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    destination = Path(sys.argv[1])
    destination.write_bytes(build())
    print(f"wrote {destination} ({destination.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
