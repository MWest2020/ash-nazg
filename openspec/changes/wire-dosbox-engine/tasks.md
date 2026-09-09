# Tasks — wire-dosbox-engine

> **Reconciliatie-status (2026-09-09).** De change is voor het eerst
> tegen een **echte** stack gedraaid: NC 32.0.14 + AppAPI 5.x + HaRP
> v0.4.0 op een Docker-host (proxmox-VM `ash-nazg-lab`). Level-3
> (`scripts/verify-against-nextcloud.sh`) is **groen** vanaf een lege
> stack: HaRP pullt het image uit de registry, spawnt de container,
> deelt de poort uit (`oc_ex_apps.port` = `APP_PORT`, géén SQL-patch),
> de ExApp doorloopt de lifecycle (heartbeat → init → enabled) en is
> bereikbaar via de AppAPI-proxy.
>
> Wat dat aan het licht bracht — vier dingen die alleen op een echte
> host zichtbaar waren, alle vier opgelost:
> 1. **frpc ontbrak in het host-image.** HaRP bereikt een ExApp
>    uitsluitend door de FRP-tunnel die de ExApp zélf opzet; een
>    direct gebonden containerpoort wordt nooit gebruikt. Image ships
>    nu `frpc` + `start.sh` (vendored uit nextcloud/HaRP) en uvicorn
>    luistert op de unix-socket als `HP_SHARED_KEY` gezet is.
> 2. **`/heartbeat` gaf plain-text `ok`.** AppAPI leest de body:
>    alles wat geen `{"status": "ok"}` is telt als *failed heartbeat*
>    bij HTTP 200, en de registratie loopt oneindig door.
> 3. **`/init` en `/enabled` ontbraken.** Zonder init-rapport
>    (`PUT /ocs/v1.php/apps/app_api/ex-app/status`, progress 100)
>    keert `app:register --wait-finish` nooit terug.
> 4. **De daemon wees naar de NC-container.** AppAPI bouwt ExApp-URLs
>    als `<nextcloud_url>/exapps/<appid>/…` en verwacht dat die naar
>    HaRP gerouteerd worden; Apache antwoordt 404. De daemon wijst nu
>    naar de reverse proxy (`http://caddy`).
>
> Plus: de audit-logger schreef naar `apps/admin_audit/api/v1/event`
> (bestaat niet — 404) met basic auth (kan niet — 401). Nu AppAPI's
> log-endpoint met de `AUTHORIZATION-APP-API`-header; live groen.
>
> **Het spawn-besluit is genomen (Mark, 2026-09-09): de engine gaat in
> hetzelfde image.** Een sessie is nu een procesboom in de ExApp-
> container, geen zustercontainer. Daarmee zijn §7, §8, §9.3 en de
> `/run`-acceptatie af; wat het kost staat in `design.md` onder
> *Decision: the engine ships in the host image* en in de spec-deltas
> voor `sandbox` en `engines`. Live nagemeten: een door dit repo
> gegenereerde DOS-binary uit Files draait echt — `dosbox-x` schreef
> "ASH NAZG OK" via een gemounte C-schijf.
>
> §2 (GHCR) is bewust nog open: level-3 gebruikt de lokale registry
> in de stack als GHCR-stand-in, wat dezelfde pull-en-spawn-weg door
> HaRP aflegt. De echte GHCR-push is CI-werk op een tag.

## 1. HaRP-based level-3 verifier rewrite

The scaffold's `scripts/local-nextcloud-stack.yml` runs the host
container directly under compose with manual-install + a SQL port
patch. That model is retired in this change.

- [x] 1.1 Add an `appapi-harp` service to
        `scripts/local-nextcloud-stack.yml` — image
        `ghcr.io/nextcloud/nextcloud-appapi-harp` (verify exact
        repo path against AppAPI 5.x docs at implementation time),
        with the rootless podman socket mounted at
        `/var/run/docker.sock`. Wire it onto the same network as
        Nextcloud.
- [x] 1.2 **Remove** the `ash-nazg-host` service from the compose
        file. HaRP spawns it on demand at `app_api:app:register`
        time; it must NOT be co-started by compose.
- [x] 1.3 Rewrite `scripts/bootstrap-nextcloud.sh`:
    - Register the HaRP daemon with `docker-install` deploy id
      (replacing the manual-install daemon).
    - Register the ExApp via `app_api:app:register ash_nazg
      <harp-daemon> --info-xml=/tmp/info.xml --wait-finish`.
    - **Delete** the `UPDATE oc_ex_apps SET port = 8080` SQL
      block — HaRP allocates the port and spawns the container
      with `APP_PORT=<that>` directly, so no patching is needed.
    - Delete the docker-cp of `info.xml` if AppAPI 5.x can read
      it from a different path; otherwise keep that step but
      document why.
- [x] 1.4 Update `scripts/verify-against-nextcloud.sh` assertions:
    - Keep: `/health` returns canonical body, `/selftest` returns
      4-check skipped JSON, `/admin/settings` shell renders.
    - **New positive assertion**: `GET /index.php/apps/app_api/proxy/ash_nazg/health`
      through NC's basic-auth returns the canonical
      `{"status":"ok","app":"ash_nazg",…}` body. This replaces
      the "404-by-design" caveat from `docs/testing.md`.
    - **New positive assertion**: container spawned by HaRP shows
      up in `docker ps` with the expected name pattern.
- [x] 1.5 Update `docs/testing.md`:
    - Remove the "404 is by design" wording for the proxy URL.
    - Document the new HaRP dependency (rootless podman socket,
      or rootful docker socket; both supported).
    - Document the level-3 startup time impact (~3-5 min more
      due to HaRP + first GHCR pull).

## 2. GHCR image-pull validation

Validates the App Store distribution path *before* writing engine
wiring on top. If GHCR pulls fail in HaRP, no amount of dispatcher
code helps.

- [ ] 2.1 Push host + engine images to GHCR under a `wire-dosbox-engine`
        development tag (e.g. `0.1.0-wire-dev`) — this is the first
        time `build-host.yml` and `build-engine-dosbox.yml` actually
        push from a non-tag context. Use a temp branch + the
        existing workflows' `type=ref,event=branch` tag pattern.
- [ ] 2.2 Update `appinfo/info.xml` `<image-tag>` to the same
        `0.1.0-wire-dev` value (still no `latest`; the
        `verify-info-xml.sh` allowlist still passes).
- [x] 2.3 Re-run the level-3 verifier against the now-rewritten
        compose stack. HaRP pulls from `ghcr.io/...` and spawns a
        fresh container — no `localhost/ash-nazg-host` dependency.
- [ ] 2.4 If the pull fails on auth, document the credential
        requirement (HaRP needs a GHCR token for private repos;
        public repos need none). For our public repo, expect no
        auth needed.
- [ ] 2.5 The `verify-images-published.yml` workflow (already
        added in `init-mvp-runtime`) gates tag-push releases on
        `docker manifest inspect` of both images. Verify it still
        passes for the dev tag, then keep it as the App Store
        submission gate it was always meant to be.

## 3. Engine registry

- [x] 3.1 `host/src/ash_nazg/engines/registry.py` discovers engines
        via the `ash_nazg.engines` Python entrypoint group.
- [x] 3.2 Broken engines (missing attrs, raises on load) are logged
        and skipped without taking the host down.
- [x] 3.3 Admin-disabled engines are excluded from the dispatch
        list. New engines default to disabled.

## 4. dosbox-x engine plugin

- [x] 4.1 `host/src/ash_nazg/engines/dosbox_x.py` implements the
        `Engine` Protocol. `can_handle()` returns True for `pe32`,
        `pe32-plus`, `mz-dos`.
- [x] 4.2 `session_config()` returns the canonical SessionConfig
        from `engines/spec.md` (1 CPU, 1024 MB, 900 s idle, port
        6901, `/mnt/files`).
- [x] 4.3 Registered as a `[project.entry-points."ash_nazg.engines"]`
        in `host/pyproject.toml`.

## 5. Dispatcher

- [x] 5.1 `host/src/ash_nazg/dispatch.py` reads the file's first
        ≤512 bytes via WebDAV range request, classifies, and
        selects an engine.
- [x] 5.2 `/run` endpoint replaces the 501 stub; returns
        `{session_id, host, port}` on success, `415` for unhandled
        formats, `400` for unrecognised, `403` for non-admin.
- [x] 5.3 Per-dispatch audit-log entry per `detection` and
        `sandbox` specs.

## 6. AppAPI lifecycle handshake (HaRP-spawned env consumption)

In docker-install via HaRP, AppAPI sets `APP_HOST`, `APP_PORT`,
`APP_SECRET`, `APP_VERSION`, `APP_ID`, `NEXTCLOUD_URL`, `HP_SHARED_KEY`
and `HP_FRP_ADDRESS`/`HP_FRP_PORT` on the spawned container. The host
shim **accepts** these, it does not choose them.

Route registration turned out NOT to be a runtime POST: AppAPI 5.x
reads the proxy allowlist from `<external-app><routes>` in `info.xml`
at register time. What the shim owes AppAPI instead is the lifecycle
handshake — and *that* is what `--wait-finish` blocks on.

- [x] 6.1 Ship `frpc` + `start.sh` in the host image and bind uvicorn
        to the unix socket `/tmp/exapp.sock` (umask 0177) when
        `HP_SHARED_KEY` is set; TCP `APP_PORT` otherwise. Without the
        tunnel HaRP cannot reach the ExApp at all — its haproxy has no
        route to a directly-bound container port.
- [x] 6.2 `GET /heartbeat` returns `{"status": "ok"}` as JSON. AppAPI
        parses the body; a plain-text `ok` is recorded as a failed
        heartbeat *at HTTP 200*.
- [x] 6.3 `POST /init` answers `{}` and reports progress 100 in the
        background via `PUT /ocs/v1.php/apps/app_api/ex-app/status`.
        Until that report lands, `app:register --wait-finish` hangs.
- [x] 6.4 `PUT /enabled?enabled=1` answers `{"error": ""}` and
        registers the Files right-click entry from there — enabling is
        the first moment AppAPI accepts OCS calls from the ExApp
        (before that: 401 "AppAPI authentication failed"). A few short
        retries suffice; the old startup-time register needed minutes
        of them and still failed.
- [x] 6.5 The deploy daemon's `nextcloud_url` points at the reverse
        proxy that routes `/exapps/*` to HaRP, not at the Nextcloud
        container.

## 7. Engine container entrypoint

- [x] 7.1 **Vervallen met het spawn-besluit**: geen davfs2-mount meer.
        De shim downloadt de binary naar een privé-sessiemap (0700), dus
        de sessie ziet één bestand in plaats van de hele Files-boom en
        er is geen mount-privilege nodig. De davfs2-tak blijft in het
        entrypoint staan voor de losse engine-image.
- [x] 7.2 Start `kasmvncserver` op de sessiepoort (6900 + slot; de
        eerste sessie krijgt 6901). Poort en xstartup-pad zijn nu
        per sessie, zodat één container er meerdere kan dragen.
- [x] 7.3 `exec dosbox-x <FILE_PATH>` met het pad in de sessiemap, en
        met `-nopromptfolder` — zonder die vlag vraagt dosbox-x om een
        werkmap op stdin, krijgt EOF en herhaalt dat tot de schijf vol
        is (41 GB in twintig minuten, echt gebeurd).

## 8. Frontend wiring

- [x] 8.1 `frontend/src/files-action.ts` `exec` roept `POST /run` aan
        via de AppAPI-proxy en navigeert naar de sessiepagina; bij een
        fout toont het de boodschap die de host teruggaf (415, 409,
        404 met pad), nooit "something went wrong".
- [x] 8.2 `frontend/src/SessionStatus.vue` toont sessie-id, engine en
        status, met een knop die de sessie sluit (`DELETE
        /sessions/{id}`) — sluiten geeft de claim vrij, anders kan de
        gebruiker hetzelfde bestand nooit opnieuw draaien. Geen
        iframe-stream; die zit in `streaming-proxy`.

## 9. Self-test — replace stubs with real checks

- [x] 9.1 `host-health`: in-container `/health` probe.
- [x] 9.2 `engines-registered`: ≥1 enabled engine.
- [x] 9.3 `engine-runtime`: the spawner's preflight — `dosbox-x` and
        `kasmvncserver` present in the image, the engine entrypoint
        executable, a session slot free. The original "spawn a busybox
        sidecar via HaRP" version died with the sibling-container
        design.
- [x] 9.4 `audit-log-write`: write `ash_nazg.selftest` and assert
        2xx from the AppAPI audit-log API.

## 10. Tests

- [x] 10.1 Unit tests for `dispatch.detect()` covering every
        magic family from the `detection` spec.
- [x] 10.2 Unit tests for `registry` covering load failures,
        admin-disable, ordering.
- [x] 10.3 Host-only integration test that mocks AppAPI's
        spawn-time env injection and asserts the host shim binds
        to `APP_PORT` and registers its routes.

## 11. Docs touch-ups (small but non-trivial)

- [x] 11.1 `docs/installation.md` — bump documented minimum to
        NC 32 + AppAPI 5.x. NC 30 + AppAPI 4.0.6 stays in
        `CHANGELOG.md` as the historical first-verified target,
        not a support claim.
- [x] 11.2 `docs/testing.md` — remove the "404 is by design"
        wording for the proxy URL (handled in §1.5 above as part
        of the verifier rewrite, but worth the explicit checkbox).

## 12. Hand-off

- [ ] 12.1 Open `streaming-proxy` change: KasmVNC iframe +
        websocket proxy through AppAPI's HaRP network.
- [ ] 12.2 Archive `wire-dosbox-engine` once §2 (GHCR) is done. §1 en
        §3–§11 zijn groen en een echte run produceert DOSBox-X-uitvoer
        ("ASH NAZG OK", nagemeten in de ExApp-container).

## Open ontwerpbesluit — hoe spawnt een ExApp een engine-container?

Het live-blok. `design.md` tekent de host-shim die `POST /spawn` naar
de deploy daemon stuurt; die API bestaat niet. Wat er wél is:

- `DockerSubprocessSpawner` shelt `docker run` uit. In een ExApp-
  container is er geen docker-CLI en geen socket — de self-test zegt
  het zonder omhaal: `docker binary not found on PATH`.
- HaRP's docker-engine-backend is er voor AppAPI, niet voor ExApps.
  Met de gedeelde sleutel komt een ExApp langs de auth (401 wordt
  404), maar elk docker-pad antwoordt 404; er is geen sanctioned
  spawn-oppervlak voor ExApps.

Drie wegen, en dit is een productbeslissing, geen implementatiedetail:

**(a) Eén container, engine erin.** dosbox-x + KasmVNC in het host-
image; geen sibling-spawn. Simpelste installatie (werkt op elke
App-Store-install, geen extra rechten), maar sessie-isolatie tussen
gebruikers verdwijnt en het image wordt fors. De compose-stack heeft
hier al een aanzet voor: `engine-dosbox` draait als always-on service.

**(b) Docker-socket eisen.** De admin mount een socket in de ExApp
(`DOCKER_HOST`). Houdt per-sessie-isolatie, maar het is precies het
soort privilege waar de App Store review op let, en het maakt de app
onbruikbaar voor de meeste beheerde installs.

**(c) Elke engine een eigen ExApp.** AppAPI spawnt ze, wat de
gesanctioneerde weg is; de host-shim vraagt AppAPI om deploy/enable.
Zwaarste variant: elke engine wordt een eigen App-Store-item met een
eigen levenscyclus.

Aanbeveling: **(a) voor de MVP-demo**, met (c) als richting zodra er
meer dan één engine is. (b) alleen als bewuste "advanced setup", nooit
als default.

Tot dit besluit valt blijven open: §7, §8, §9.3, §12 en de
acceptatiebullet over `POST /run`.
