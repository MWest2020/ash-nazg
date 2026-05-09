# Third-Party Notices

Ash Nazg is distributed under AGPL-3.0-or-later. It depends on, ships
with, or interfaces with the following upstream projects. Each retains
its own license; the table below is informational and not a substitute
for reading those licenses.

## Runtime components shipped in container images

| Component   | Role                                          | License    | Upstream                                               |
|-------------|-----------------------------------------------|------------|--------------------------------------------------------|
| DOSBox-X    | DOS / Windows 3.x execution engine            | GPL-2.0    | https://dosbox-x.com/                                  |
| KasmVNC     | Browser-side streaming protocol               | GPL-3.0    | https://github.com/kasmtech/KasmVNC                    |
| davfs2      | WebDAV mount inside the engine container      | GPL-2.0    | https://savannah.nongnu.org/projects/davfs2            |
| tini        | PID 1 init in the engine container            | MIT        | https://github.com/krallin/tini                        |
| Debian base | Engine container base image (`debian:12-slim`)| various    | https://www.debian.org/legal/licenses/                 |

## Host-side dependencies (Python)

| Component   | Role                                          | License    | Upstream                                               |
|-------------|-----------------------------------------------|------------|--------------------------------------------------------|
| FastAPI     | HTTP framework for the host shim              | MIT        | https://github.com/tiangolo/fastapi                    |
| uvicorn     | ASGI server                                   | BSD-3      | https://github.com/encode/uvicorn                      |
| httpx       | WebDAV / Nextcloud HTTP client                | BSD-3      | https://github.com/encode/httpx                        |
| pydantic    | Schema validation                             | MIT        | https://github.com/pydantic/pydantic                   |

## Frontend dependencies

| Component       | Role                              | License    | Upstream                                               |
|-----------------|-----------------------------------|------------|--------------------------------------------------------|
| Vue 3           | UI framework                      | MIT        | https://github.com/vuejs/core                          |
| Vite            | Build tool                        | MIT        | https://github.com/vitejs/vite                         |
| TypeScript      | Language tooling                  | Apache-2.0 | https://github.com/microsoft/TypeScript                |
| @nextcloud/vue  | Nextcloud UI components           | AGPL-3.0   | https://github.com/nextcloud-libraries/nextcloud-vue   |
| @nextcloud/files| Files-app integration helpers     | AGPL-3.0   | https://github.com/nextcloud-libraries/nextcloud-files |
| @nextcloud/l10n | Translation helpers (`t`, `n`)    | AGPL-3.0   | https://github.com/nextcloud-libraries/nextcloud-l10n  |

## Content NOT shipped

Ash Nazg ships **no** proprietary OS images, BIOS files, ROMs, fonts, or
binaries. Per `docs/bring-your-own-content.md`, users supply their own
legally-obtained software when running an engine. See also the sandbox
spec requirement "No bundled non-open-source content".

## Trademarks

"Ash Nazg" is used as a fan-homage reference to J.R.R. Tolkien's
legendarium. This project is not affiliated with or endorsed by the
Tolkien Estate, Microsoft, id Software, Apogee Software, or any other
trademark holder. All trademarks remain the property of their respective
owners.
