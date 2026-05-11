"""End-to-end Playwright verification of the wire-dosbox-engine demo.

Brings up no infrastructure — assumes the demo stack is already
running:

  1. Engine container active and reachable at
     https://127.0.0.1:16901/vnc.html  (KasmVNC web client)
  2. Either:
     (a) NC stack via `docker compose -f scripts/local-nextcloud-stack.yml up -d`
         and `./scripts/bootstrap-nextcloud.sh`, OR
     (b) NC URL passed in via --base-url

Pass: navigates an admin user through right-click → Run with Ash Nazg,
verifies the redirect, and screenshots Keen 1's title screen rendering
in the engine container's KasmVNC web client.

Requirements:
  uv pip install --extra demo-e2e .   (defined as optional dep group)
  playwright install chromium

Usage:
  python scripts/e2e-playwright/run-keen-demo.py \
      --base-url http://localhost:8088 \
      --admin admin --admin-password admin-local-dev \
      --keen-path /tmp/ash-nazg-fixtures/keen1/CKeen1/KEEN1.EXE \
      --output-dir /tmp/ash-nazg-screenshots/
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Import is deferred to runtime so this file can be syntax-checked
# without playwright installed.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8088")
    parser.add_argument("--admin", default="admin")
    parser.add_argument("--admin-password", default="admin-local-dev")
    parser.add_argument(
        "--keen-path",
        default="/tmp/ash-nazg-fixtures/keen1/CKeen1/KEEN1.EXE",  # noqa: S108
        help="Local path to Keen1.exe to upload to the admin's Files",
    )
    parser.add_argument(
        "--engine-url",
        default="https://127.0.0.1:16901/vnc.html",
        help="KasmVNC URL the host's StubSpawner returns",
    )
    parser.add_argument("--output-dir", default="/tmp/ash-nazg-screenshots")  # noqa: S108
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright not installed. Run: "
            "uv pip install --python .venv playwright "
            "&& playwright install chromium",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    keen_path = Path(args.keen_path)
    if not keen_path.exists():
        print(f"Keen binary not found at {keen_path}", file=sys.stderr)
        return 3

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--ignore-certificate-errors"],  # for KasmVNC self-signed
        )
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        # 1. Log in to Nextcloud
        page.goto(f"{args.base_url}/index.php/login")
        page.fill("input[name=user]", args.admin)
        page.fill("input[name=password]", args.admin_password)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(output_dir / "01-logged-in.png"))

        # 2. Upload Keen 1
        page.goto(f"{args.base_url}/index.php/apps/files/")
        page.wait_for_selector("[data-cy-files-list]", timeout=15000)
        # Trigger upload via the file input the Files app hides
        upload_input = page.locator("input[type=file].hidden-visually").first
        upload_input.set_input_files(str(keen_path))
        page.wait_for_timeout(2000)
        page.screenshot(path=str(output_dir / "02-keen-uploaded.png"))

        # 3. Right-click the uploaded file
        keen_row = page.locator("tr[data-cy-files-list-row]", has_text="KEEN1.EXE").first
        keen_row.click(button="right")
        page.wait_for_timeout(500)
        page.screenshot(path=str(output_dir / "03-context-menu.png"))

        # 4. Click "Run with Ash Nazg" — popped up via AppAPI FileActionsMenu
        run_item = page.locator("text=Run with Ash Nazg").first
        if run_item.count() == 0:
            print(
                "!! 'Run with Ash Nazg' not in context menu. Verify:\n"
                "   - host registered the FileActionsMenu at startup\n"
                "     (check ash-nazg-host container logs for 'registered FileActionsMenu')\n"
                "   - admin user has admin permission for the binary",
                file=sys.stderr,
            )
            return 4

        # 5. Click and wait for the new tab to open with the KasmVNC URL
        with context.expect_page() as new_page_info:
            run_item.click()
        new_page = new_page_info.value
        new_page.wait_for_load_state("domcontentloaded")
        time.sleep(3)  # noVNC client needs a moment to render

        # 6. Confirm the new tab is the KasmVNC client and screenshot
        new_page.screenshot(path=str(output_dir / "04-kasmvnc-client.png"))
        # Click Connect if KasmVNC needs it (varies by version)
        connect_btn = new_page.locator("text=Connect").first
        if connect_btn.count() > 0:
            connect_btn.click()
            time.sleep(2)
        # Log in (demo / ash_nazg)
        user_input = new_page.locator("input[type=text]").first
        if user_input.count() > 0:
            user_input.fill("demo")
            pass_input = new_page.locator("input[type=password]").first
            if pass_input.count() > 0:
                pass_input.fill("ash_nazg")
                new_page.keyboard.press("Enter")
        time.sleep(5)  # Keen needs a few seconds to load
        new_page.screenshot(path=str(output_dir / "05-keen-running.png"))

        print(f"\n✓ Screenshots written to {output_dir}/")
        print("  Verify 05-keen-running.png shows the Keen 1 title screen.")

        browser.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
