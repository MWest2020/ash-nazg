# Design — streaming-proxy

## The thing to measure first

```
browser ──https──▶ Nextcloud ──▶ AppAPI proxy ──▶ HaRP (haproxy)
                                                     │
                                              FRP tunnel (frpc)
                                                     ▼
                                            shim (unix socket)
                                                     │
                                        127.0.0.1:69NN  KasmVNC
```

Five hops, each of which can quietly drop an `Upgrade: websocket`
header. HaRP's haproxy proxies websockets in principle and FRP is a TCP
tunnel, so the odds are good — but "good odds" is not a measurement, and
everything in this change is worthless if the answer is no.

### Gemeten 2026-09-09 — het antwoord is ja, maar niet langs de weg die we aannamen

Een echo-websocket op de shim, een echte browser (Chromium via
Playwright) tegen de lab-stack (NC 32.0.14, AppAPI 5.x, HaRP v0.4.0), en
twee URL-vormen naast elkaar:

| pad | resultaat |
|-----|-----------|
| `/index.php/apps/app_api/proxy/ash_nazg/ws-spike` | **werkt niet** — handshake mislukt (`Unexpected response`), curl hangt en krijgt 0 bytes |
| `/exapps/ash_nazg/ws-spike` | **werkt** — `101 Switching Protocols`, begroeting, echo, nette sluiting 1000 |

Het interessante aan de mislukking: de ExApp *accepteert* de socket wel
(`WebSocket /ws-spike [accepted]`, `connection open` in zijn log). De
upgrade legt de hele weg af; wat niet terugkomt is de 101. Dat is de
PHP-proxycontroller van AppAPI: PHP kan geen protocol-upgrade
teruggeven. Die weg is dood voor streaming, hoe hard je ook probeert.

`/exapps/…` gaat niet door PHP. De webserver vóór Nextcloud routeert dat
pad rechtstreeks naar HaRP, dat het door de FRP-tunnel naar de shim
duwt. Dezelfde weg die AppAPI zelf voor de heartbeat gebruikt.

**En de toegangscontrole blijft staan op dat pad**, apart nagemeten:

| aanroep | antwoord |
|---------|----------|
| `POST /exapps/ash_nazg/selftest` zonder inloggegevens | 403 |
| idem mét | 200 |
| websocket vanuit een browser **zonder** sessie | geweigerd (1006) |
| websocket vanuit een browser **mét** NC-sessie | verbonden, echo, 1000 |

HaRP handhaaft dus het `access_level` uit `info.xml` op deze route, ook
bij een upgrade. De ADMIN-eis van de streamroute wordt daar afgedwongen;
de eigenaarscheck blijft werk voor de shim, want HaRP weet niets van
sessies.

**Gevolgen voor deze change:**

1. De iframe laadt `/exapps/ash_nazg/sessions/{id}/stream/…`, niet de
   `app_api/proxy`-URL. De rest van de app blijft de proxy-URL gebruiken;
   alleen de stream wijkt af, en dat verdient een regel commentaar op de
   plek waar de URL wordt gebouwd.
2. Een installatie-eis erbij: de webserver vóór Nextcloud MOET `/exapps/*`
   naar HaRP routeren. Dat is de standaard-HaRP-opstelling (onze stack
   doet het met Caddy), maar het is nu een harde eis in plaats van een
   detail — zonder die route is er geen beeld.
3. De spike is weg. Wat overblijft is deze meting.

## Why the shim relays instead of AppAPI routing to the session port

AppAPI knows one port per ExApp — the one it allocated (`APP_PORT`).
Sessions listen on their own ports inside the same container. There is
no way to declare "and also 6901" in `info.xml`, and no second FRP proxy
per session. The shim is the only thing that can see both sides.

## Authorisation happens before the first byte

The session id is not a capability. `/sessions/{id}/stream/…` checks the
caller the way `/run` does (admin, via AppAPI's proxy) *and* that the
session belongs to that caller, before any byte moves. A relay that
authorises on the first HTTP request and then trusts the socket is a
relay that leaks sessions to whoever guesses an id.

## Per-session credentials

Today every session inherits the image's baked-in KasmVNC password. Two
users, one password, and it survives a redeploy. Instead: the spawner
generates a secret per session, writes it to that session's own password
file in its private directory, and passes it to the client through the
relay. It dies with the directory.

## Idle timeout belongs to the relay

The relay is the only place that sees whether anyone is watching. It
stamps a clock on every frame in either direction; a session with no
traffic for the window is terminated by the same path that
`DELETE /sessions/{id}` uses, including the claim release. That keeps one
termination path rather than two that can disagree.

## Verworpen: de stream buiten Nextcloud om

Publishing the session port straight to the network (a host port, a
second ingress) would skip every hop above and work tomorrow. It also
puts an unauthenticated-by-Nextcloud surface next to a Nextcloud app,
undoes the single-door property the AppAPI proxy gives us, and would not
survive an App Store review. No.
