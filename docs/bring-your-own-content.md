# Bring your own content

Ash Nazg is the **runtime**. Your software is **yours**. The
project deliberately ships zero proprietary binaries, ROMs, BIOS
files, fonts, or operating system images. That keeps the licensing
story uncomplicated for the project; it puts the licensing story
for what you run on you.

This page is the friendly version of that boundary. The normative
version is `specs/sandbox/spec.md` → *Requirement: No bundled
non-open-source content*.

## What does **not** ship with Ash Nazg

- **Microsoft Windows** (any version, including 3.x install media,
  registry hives, or system fonts).
- **DOS** itself — MS-DOS, PC-DOS, IBM-DOS, etc.
- **Console BIOS files** for any platform that a future engine
  might emulate.
- **Game ROMs** — commercial or otherwise.
- **Commercial business applications** — old or new.
- **Proprietary fonts** that ride along with retro install media.

If you need any of the above to run a binary, you supply it from a
source you have a legal right to use. Ash Nazg's job is to give it
a place to run; sourcing it is yours.

## What you can legitimately bring

Three categories cover most demo-worthy use cases:

1. **Software you bought a licence for.** A legacy invoicing app
   you still have the floppies and key for. A DOS-era utility your
   employer paid for once and which is now business-critical for a
   handful of records-retention reasons. A copy of Windows 3.11
   from the era when you bought it new.
2. **Open source software.** FreeDOS, FreeBASIC, OpenWatcom — all
   legitimate, all permissive enough to redistribute. Plenty of
   useful old utilities have been re-released under MIT / BSD /
   GPL by their authors. Use those.
3. **Homebrew / fan-made software.** Indie developers continue to
   target DOS and Windows 3.x today, often releasing freely. Same
   for emulator scenes.

The boundary that matters is *do you have the right to run this
binary*. Ash Nazg can't tell. You can.

## What's in the grey zone

"Abandonware" is a real cultural concept and a thin legal one. A
publisher who hasn't sold a thirty-year-old game in two decades
still owns the copyright. Sites that distribute that software
without permission are infringing — that's true of the *site*, not
necessarily of *you* if you can show ownership of the original. But
"I'll just download it from there" is not the same thing.

The project does not endorse, link to, or ship from grey-zone
archives. If you're running grey-zone software in your own
Nextcloud, that's your call and your risk. We don't help and we
don't gatekeep; we just don't redistribute.

## How to convert your own install media

The detail here is intentionally high-level — step-by-step
walkthroughs belong in `docs/user-guide.md` once the demo flow is
working end-to-end. The shape is:

- **Floppy or CD images.** Most retro install media is preserved
  as `.img`, `.iso`, or `.imd` files. DOSBox-X mounts these
  directly; you upload one to Files, run the binary that requires
  it, and DOSBox-X picks it up via your engine session config.
- **Original installation discs you still have physical copies
  of.** Make a clean disk image with a tool like `dd` or
  `ddrescue` on Linux, or any reputable imager on Windows. Verify
  the image checksum against a public hash database if one
  exists. Upload the resulting image to Files.
- **Windows 3.x.** Same deal — image your install floppies, drop
  them into Files, point DOSBox-X at the install entry point on
  the first disk. Once installed in a DOSBox-X disk, you save the
  hard-disk image back to Files and Ash Nazg runs that on next
  invocation.
- **Save games and config.** Persistence is the WebDAV mount at
  `/mnt/files`. Anything written to that path lives in your
  Nextcloud Files; anything written to `/tmp` is gone when the
  session ends. Plan accordingly.

## Why we draw the line this way

Two reasons:

1. **It matches reality.** Ash Nazg has no business shipping a
   thirty-year-old corporation's installer. We're a runtime, not a
   distributor.
2. **It keeps the project's compliance story trivial.** AGPL-3.0
   plus only OSI-approved upstreams = no licence audit headaches,
   no re-distribution disputes, no need to stop accepting
   contributions because someone added a `roms/` folder.

The trade-off is friction — you have to bring your own software.
That's deliberate. Anyone for whom that's a blocker is not the
target audience for v1.

## TL;DR

> **Ash Nazg is the runtime; your software is yours.** Bring it,
> run it, keep it inside your own Nextcloud. We don't ship it,
> mirror it, link to it, or check it.
