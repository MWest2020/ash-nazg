# Tasks — streaming-proxy

## 1. Meet eerst of een websocket de keten overleeft

Alles hieronder staat of valt hiermee. Niet bouwen voor het antwoord er is.

- [x] 1.1 Tijdelijke echo-websocket op de shim (`/ws-spike`), route in
      `info.xml`, uitgerold op de lab-VM.
- [x] 1.2 Vanuit een echte browser (Chromium/Playwright) door de hele keten:
      via `/exapps/ash_nazg/ws-spike` verbonden, begroeting én echo ontvangen,
      nette sluiting (1000). Via `/index.php/apps/app_api/proxy/…` mislukt de
      handshake — de ExApp accepteert de socket wél, maar de 101 komt niet
      terug door de PHP-controller.
- [x] 1.3 Uitkomst staat in `design.md` (§ *Gemeten 2026-09-09*), inclusief de
      meting dat HaRP het `access_level` óók bij een upgrade handhaaft: zonder
      sessie geweigerd, mét sessie verbonden. Spike verwijderd.

## 2. De relay

- [ ] 2.1 `GET /sessions/{id}/stream/{pad}` proxiet HTTP naar de KasmVNC-poort
      van die sessie op 127.0.0.1. De browser bereikt dit via
      `/exapps/ash_nazg/…` (zie §1); de `app_api/proxy`-URL kan geen upgrade
      dragen.
- [ ] 2.2 Websocket-upgrade op hetzelfde pad, bidirectioneel, met een nette
      afsluiting als de sessie stopt.
- [ ] 2.3 Autorisatie vóór de eerste byte: admin (zoals `/run`) én eigenaar van
      de sessie. Onbekende of andermans sessie → 404, niet 403 (geen orakel
      voor sessie-id's).
- [ ] 2.4 Route in `appinfo/info.xml` (GET, ADMIN), inclusief het
      websocket-pad.

## 3. Sessie-eigen KasmVNC-inloggegevens

- [ ] 3.1 Spawner genereert een geheim per sessie en schrijft het
      wachtwoordbestand in de sessiemap (0600).
- [ ] 3.2 Het gebakken `demo`-wachtwoord verdwijnt uit het image.
- [ ] 3.3 De relay geeft de client wat hij nodig heeft; het geheim staat nooit
      in een URL die in een browsergeschiedenis of proxy-log belandt.

## 4. Beeld in de browser

- [ ] 4.1 `IframeHost.vue` laadt KasmVNC's eigen webclient via het relay-pad.
- [ ] 4.2 `SessionStatus.vue` toont het beeld in plaats van de melding dat het
      er nog niet is; de sluitknop blijft.
- [ ] 4.3 Een gesloten of verlopen sessie geeft een leesbare melding in het
      kader, geen kapot iframe.

## 5. Idle-timeout op echte activiteit

- [ ] 5.1 De relay stempelt activiteit per sessie.
- [ ] 5.2 Geen verkeer gedurende het venster (default 900 s) → dezelfde
      afsluitweg als `DELETE /sessions/{id}`, inclusief het vrijgeven van de
      claim.
- [ ] 5.3 De voorwaardelijke eis in de `engines`-spec wordt onvoorwaardelijk.

## 6. Nameten

- [ ] 6.1 Unittests: autorisatie (eigenaar/vreemde/onbekend), relay-fouten,
      idle-afsluiting.
- [ ] 6.2 Level-3 krijgt een browserstap: run starten, beeld zien, sluiten.
      De bestaande curl-stappen blijven.
- [ ] 6.3 Het security-model bijwerken: wat de relay wél en niet afschermt.
