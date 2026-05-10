# files-integration — delta spec

## ADDED Requirements

### Requirement: Files action registered for supported file types

The frontend SHALL register a right-click "Run with Ash Nazg" action on
files in the Nextcloud Files app. The action SHALL be visible only to
admin users.

#### Scenario: Action shown for admin on .exe file

- **GIVEN** an admin viewing a folder containing `keen1.exe` in Files
- **WHEN** they right-click the file
- **THEN** the context menu SHALL include "Run with Ash Nazg".

#### Scenario: Action hidden for non-admin

- **GIVEN** a non-admin user viewing the same folder
- **WHEN** they right-click any file
- **THEN** the context menu SHALL NOT include the Ash Nazg action.

#### Scenario: Action shown but warns on unsupported type

- **GIVEN** an admin right-clicking a `.txt` file
- **WHEN** they trigger the action (the frontend may show it
  optimistically; the backend is authoritative)
- **THEN** the host SHALL return 415
- **AND** the frontend SHALL display a toast "Ash Nazg cannot run this
  file type".

### Requirement: WebDAV mount of user files inside engine

The engine container SHALL mount a slice of the requesting user's
Nextcloud Files at `/mnt/files`. The mount SHALL use WebDAV via davfs2
authenticated with the per-session token issued by AppAPI.

#### Scenario: Engine reads the binary via mount

- **GIVEN** the user clicks Run on `/Programs/keen1.exe` in their Files
- **WHEN** the engine container starts
- **THEN** the engine SHALL find the binary at `/mnt/files/Programs/keen1.exe`
  inside the container
- **AND** SHALL be able to read it.

#### Scenario: Engine writes output to the mount

- **GIVEN** during execution, the application writes a file (e.g., a
  saved game, a screenshot, an exported document)
- **WHEN** the application calls the underlying write syscall
- **THEN** the write SHALL traverse the davfs2 mount
- **AND** the resulting file SHALL appear in the user's Nextcloud Files
  within 30 seconds (allowing for davfs2 cache flush).

#### Scenario: Mount scope cannot escape user root

- **GIVEN** the user's Files root is at WebDAV path `/remote.php/dav/files/alice/`
- **WHEN** the engine container's mount is established
- **THEN** the mount root SHALL be exactly that path (or a subdirectory)
- **AND** path traversal attempts (`/mnt/files/../../etc/passwd`) SHALL
  not escape because davfs2 mounts at WebDAV root, not host filesystem
  root.

### Requirement: Outputs land in the same directory as the input

When an engine produces files (saves, exports, screenshots), they SHALL
appear in the same Nextcloud Files directory as the binary that was
launched, unless the application itself specifies a different path.

#### Scenario: DOSBox save next to .exe

- **GIVEN** `/Programs/keen1.exe` is launched
- **WHEN** Commander Keen saves its state to `SAVEGAM0.CK1`
- **THEN** the save file SHALL appear at `/Programs/SAVEGAM0.CK1` in
  Nextcloud Files.

#### Scenario: Application writes to a sub-path

- **GIVEN** an application writes to `./output/result.txt` from its
  working directory
- **WHEN** the working directory is `/Programs/`
- **THEN** the file SHALL appear at `/Programs/output/result.txt` in
  Nextcloud Files (the host SHALL NOT redirect this).

### Requirement: Concurrent access detection

The host SHALL refuse to start a new session for a binary that is
already executing in another session for the same user.

#### Scenario: Double-click while running

- **GIVEN** an admin has `keen1.exe` running in session A
- **WHEN** they click Run on the same file again
- **THEN** the host SHALL return 409 Conflict with message "this file
  is already running — close the existing session first"
- **AND** SHALL NOT spawn a second engine container.

#### Scenario: Different users running same file

- **GIVEN** admin Alice has `shared.exe` running, and admin Bob clicks
  Run on the same file (both are admins, the file is in a shared folder)
- **WHEN** Bob's request reaches the host
- **THEN** the host SHALL allow the parallel session
- **AND** each session SHALL get its own engine container with its own
  WebDAV mount under each respective user's token.

### Requirement: Working directory is the binary's directory

When an engine starts, its working directory SHALL be the directory
containing the launched binary. Relative paths in the application
behave as the user expects from their Files view.

#### Scenario: Relative path resolution

- **GIVEN** `/Programs/myapp.exe` reads `./data/config.ini`
- **WHEN** the engine launches it
- **THEN** the engine's working directory SHALL be `/mnt/files/Programs/`
- **AND** the application SHALL find `data/config.ini` inside
  `/Programs/data/config.ini` in Nextcloud Files.

### Requirement: File size limit on launchable binaries

The host SHALL refuse to launch binaries larger than a configurable
limit (default 100 MB).

#### Scenario: Oversized binary refused

- **GIVEN** the limit is 100 MB and a 250 MB `.exe` file
- **WHEN** an admin clicks Run on it
- **THEN** the host SHALL return 413 Payload Too Large with message
  "binary exceeds size limit (100 MB) — adjust in admin settings if
  intentional".
