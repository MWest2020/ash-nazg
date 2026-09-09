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

So task §1 is a spike: a trivial websocket echo route on the shim, a
browser through the real proxy chain, and a verdict. If it fails, the
fallback is not "try harder": it is a documented decision between
(a) KasmVNC's HTTP-only transport if it has one that is good enough, and
(b) telling the admin to expose the session port directly on a trusted
network, which is a different product and probably a no.

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
