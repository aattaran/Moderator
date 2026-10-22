#!/usr/bin/env python3
"""
Launch headed Chromium on DISPLAY=:99, navigate to Facebook login,
wait up to 10 minutes for the user to log in via VNC,
then save storage state.
"""
import asyncio
import json
import os

os.environ["DISPLAY"] = ":99"


async def main():
    from playwright.async_api import async_playwright

    output_path = "/opt/moderator/data/facebook_auth_state.json"

    async with async_playwright() as p:
        print("[*] Launching headed Chromium on DISPLAY=:99 ...")
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1260, "height": 860},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        print("[*] Navigating to https://www.facebook.com/login ...")
        await page.goto(
            "https://www.facebook.com/login",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        print("[*] Browser is open. Connect VNC to 137.184.137.154:5900 and log in.")
        print("[*] Waiting up to 600 seconds for URL to change away from /login ...")

        timeout_s = 600
        poll_interval = 2
        elapsed = 0

        while elapsed < timeout_s:
            url = page.url
            # Detect successful login: URL no longer contains /login
            if "/login" not in url and "facebook.com" in url:
                print("[+] Login detected! URL: " + url)
                # Wait a moment for cookies to settle
                await asyncio.sleep(3)
                break
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            if elapsed % 30 == 0:
                print(
                    "    ... still waiting ("
                    + str(elapsed)
                    + "s elapsed, current URL: "
                    + url
                    + ")"
                )
        else:
            print(
                "[-] Timeout after "
                + str(timeout_s)
                + "s. URL is still: "
                + page.url
            )
            print("[-] Saving whatever state we have anyway ...")

        # Save storage state
        state = await context.storage_state()
        with open(output_path, "w") as f:
            json.dump(state, f, indent=2)

        cookie_count = len(state.get("cookies", []))
        print("[+] Saved storage state to " + output_path)
        print("[+] Cookie count: " + str(cookie_count))

        for c in state.get("cookies", []):
            cname = c.get("name", "?")
            cdomain = c.get("domain", "?")
            print("    - " + cname + " (domain: " + cdomain + ")")

        await browser.close()
        print("[*] Done.")


if __name__ == "__main__":
    asyncio.run(main())
