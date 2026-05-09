# detection — delta spec

## ADDED Requirements

### Requirement: Binary type detection by magic bytes

The host shim SHALL detect the type of a user-uploaded binary by inspecting
its leading bytes ("magic bytes") before dispatching to an engine. Detection
MUST NOT rely solely on file extension, as users may upload binaries with
incorrect or missing extensions.

#### Scenario: PE32 binary (Windows .exe) detected

- **GIVEN** a file in Nextcloud Files whose first two bytes are `0x4D 0x5A`
  ("MZ" — DOS/Windows executable header)
- **WHEN** the host shim is asked to dispatch the file
- **THEN** the host SHALL identify it as `pe32` or `pe32-plus` based on
  the offset-0x3c PE header
- **AND** offer dispatch to engines whose `can_handle()` returns True for
  PE32

#### Scenario: ELF binary detected

- **GIVEN** a file whose first four bytes are `0x7F 0x45 0x4C 0x46` (ELF magic)
- **WHEN** the host is asked to dispatch the file
- **THEN** the host SHALL identify it as `elf`
- **AND** since no ELF-handling engine is shipped in v1, the host SHALL
  return a 415 Unsupported Media Type response with a message naming the
  detected type

#### Scenario: WASM binary detected

- **GIVEN** a file whose first four bytes are `0x00 0x61 0x73 0x6D` (`\0asm`)
- **WHEN** the host is asked to dispatch the file
- **THEN** the host SHALL identify it as `wasm`
- **AND** return 415 (no WASM engine in v1).

#### Scenario: Unknown / textual file refused

- **GIVEN** a file whose magic bytes do not match any known binary format
- **WHEN** the host is asked to dispatch the file
- **THEN** the host SHALL return 400 Bad Request with message "not a
  recognized executable format"
- **AND** the host SHALL NOT attempt to execute the file under any engine.

### Requirement: Detection by extension as fallback hint

The host SHALL use the file extension as a tiebreaker when magic-byte
detection is ambiguous (e.g., a generic ZIP file that could be a `.jar`,
a Java executable, or a generic archive). Extension-based hints SHALL
only refine an already-matched magic-byte family; they SHALL NOT
override magic-byte detection.

#### Scenario: ZIP file with .jar extension

- **GIVEN** a file with magic bytes `0x50 0x4B 0x03 0x04` (ZIP) and
  extension `.jar`
- **WHEN** dispatch is requested
- **THEN** the host SHALL classify it as `jar`, not as `zip`.

#### Scenario: ZIP file without distinguishing extension

- **GIVEN** a file with ZIP magic bytes and extension `.zip`
- **WHEN** dispatch is requested
- **THEN** the host SHALL return 415 with message "ambiguous archive — no
  engine handles raw ZIP".

### Requirement: Detection precedes any engine selection

The detection result SHALL be computed once per dispatch request and
passed to all engine `can_handle()` calls. Engines SHALL NOT re-read the
binary header themselves.

#### Scenario: Single read of binary header

- **GIVEN** a 50 MB binary uploaded to Files
- **WHEN** dispatch is requested
- **THEN** the host SHALL read at most the first 512 bytes via WebDAV
  range request
- **AND** SHALL NOT download the full file before dispatch decision.

### Requirement: Detection results logged

Every dispatch attempt SHALL produce an audit log entry, regardless of
whether dispatch succeeds.

#### Scenario: Successful dispatch logged

- **GIVEN** a PE32 binary that successfully dispatches to dosbox-x
- **WHEN** the dispatch completes
- **THEN** an audit log entry SHALL exist with: detected_type=pe32,
  selected_engine=dosbox-x, file_sha256=..., outcome=dispatched.

#### Scenario: Refused dispatch logged

- **GIVEN** an ELF binary in v1 (no engine handles it)
- **WHEN** dispatch returns 415
- **THEN** an audit log entry SHALL exist with: detected_type=elf,
  selected_engine=null, outcome=refused, reason="no engine".
