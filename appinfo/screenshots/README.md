# Screenshots

The three PNGs in this directory are **1×1 transparent placeholders**.
They satisfy the literal requirement that `appinfo/info.xml` reference
three valid PNG files, but they are NOT App Store-ready.

| Filename                  | Eventual subject                                                |
|---------------------------|-----------------------------------------------------------------|
| `01-files-action.png`     | The right-click "Run with Ash Nazg" action in the Files app.    |
| `02-admin-settings.png`   | The admin settings panel (engine toggle + limits + Test).       |
| `03-iframe-host.png`      | A running DOSBox-X session rendered inside the Nextcloud UI.    |

## Replace before App Store submission

Real screenshots come **after** the demo flow works end-to-end (i.e.
after `wire-dosbox-engine` and `streaming-proxy` land). The
`appstore-v1-submission` change owns final asset preparation.

App Store dimension expectations (verify against the current
nextcloud/appstore docs at submission time):

- Recommended canvas: **1280 × 800** PNG.
- Maximum canvas: 1920 × 1080.
- Total per screenshot ≤ 1 MB.
- Avoid sensitive data, real user names, or any content under
  proprietary licence (no Microsoft Windows screenshots without
  rights, etc.).

## Why placeholders ship at all

The scaffold change deliberately exercises the `<screenshot>` element
of `info.xml` so the App Store validator (and any local schema check)
sees the references resolve. Shipping no images would let a real bug
hide until submission.
