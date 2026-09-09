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

- [x] 2.1 `GET /sessions/{id}/stream/{pad}` proxiet HTTP naar de KasmVNC-poort
      van die sessie op 127.0.0.1. De browser bereikt dit via
      `/exapps/ash_nazg/…` (zie §1); de `app_api/proxy`-URL kan geen upgrade
      dragen.
- [x] 2.2 Websocket-upgrade op hetzelfde pad, bidirectioneel, met een nette
      afsluiting als de sessie stopt.
- [x] 2.3 Autorisatie vóór de eerste byte: admin (zoals `/run`) én eigenaar van
      de sessie. Onbekende of andermans sessie → 404, niet 403 (geen orakel
      voor sessie-id's).
- [x] 2.4 Route in `appinfo/info.xml` (GET, ADMIN), inclusief het
      websocket-pad.

## 3. Sessie-eigen KasmVNC-inloggegevens

- [x] 3.1 Spawner genereert een geheim per sessie en schrijft het
      wachtwoordbestand in de sessiemap (0600).
- [x] 3.2 Het gebakken `demo`-wachtwoord verdwijnt uit het image.
- [x] 3.3 De relay geeft de client wat hij nodig heeft; het geheim staat nooit
      in een URL die in een browsergeschiedenis of proxy-log belandt.

## 4. Beeld in de browser

- [x] 4.1 `IframeHost.vue` laadt KasmVNC's eigen webclient via het relay-pad.
- [x] 4.2 `SessionStatus.vue` toont het beeld in plaats van de melding dat het
      er nog niet is; de sluitknop blijft.
- [x] 4.3 Een gesloten of verlopen sessie geeft een leesbare melding in het
      kader, geen kapot iframe.

## 5. Idle-timeout op echte activiteit

- [x] 5.1 De relay stempelt activiteit per sessie.
- [x] 5.2 Geen verkeer gedurende het venster (default 900 s) → dezelfde
      afsluitweg als `DELETE /sessions/{id}`, inclusief het vrijgeven van de
      claim.
- [x] 5.3 De voorwaardelijke eis in de `engines`-spec wordt onvoorwaardelijk.

## 6. Nameten

- [x] 6.1 Unittests: autorisatie (eigenaar/vreemde/onbekend), relay-fouten,
      idle-afsluiting.
- [x] 6.2 Level-3 bewijst de relay met curl (client 200, upgrade 101) — die
      stappen draaien overal. Het beeld zelf vraagt een browser en zit in
      `scripts/e2e-playwright/verify-stream.js`: die meet dat het canvas het
      sessiescherm draagt en laat een screenshot achter. Beide vandaag groen.
- [x] 6.3 Het security-model bijwerken: wat de relay wél en niet afschermt.

## 7. Wat het bouwen aan het licht bracht

Vier dingen die geen ontwerp had voorspeld, alle vier nagemeten en opgelost;
ze staan hier omdat ze het soort fout zijn dat je een middag kost:

- [x] 7.1 **KasmVNC antwoordt een upgrade zonder `Origin` met 404.** Niet 400,
      niet 403 — een kale "dit pad bestaat niet", waardoor je het verkeerde
      websocket-pad gaat zoeken. Ook de subprotocol-header `binary` is nodig.
- [x] 7.2 **De client verbindt niet zonder `path=`.** Hij bouwt zijn
      websocket-URL vanaf de origin (`/websockify`), niet vanaf de pagina, en
      blijft anders stil op zijn verbindingsscherm staan — zonder één poging.
- [x] 7.3 **De pagina moest van de proxy-URL af.** Nextcloud levert die met zijn
      eigen CSP, die onze bundel weigert (geen nonce). De sessiepagina draait nu
      op `/exapps/…`, waar ook de stream loopt.
- [x] 7.4 **Assets stonden absoluut** (`/static/…`) en resolveerden tegen
      Nextclouds root: pagina rendert, Vue mount nooit. Nu relatief aan het
      prefix dat de browser gebruikte. Gold ook voor de admin-pagina.
- [x] 7.5 **Sluiten liet KasmVNC leven.** `kasmvncserver` is een starter: hij
      zet Xvnc op en keert terug. Alleen het kind signaleren liet Xvnc én de
      emulator draaien, waarna de volgende sessie "zijn" poort al open vond,
      aan de vórige server hing en 401 gaf. Nu een eigen procesgroep, een
      nette `-kill :N` en opruimen van het display-slot.
