"""Open a visible browser on the server for manual login.
Run on the droplet, connect via VNC to log in, cookies are saved automatically.

Usage:
  python scripts/server_login.py facebook
  python scripts/server_login.py instagram
  python scripts/server_login.py tiktok
"""

import asyncio
import sys
import os

PLATFORM_URLS = {
    "facebook": "https://www.facebook.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
    "tiktok": "https://www.tiktok.com/login",
}

AUTH_FILES = {
    "facebook": "data/facebook_auth_state.json",
    "instagram": "data/instagram_auth_state.json",
    "tiktok": "data/tiktok_auth_state.json",
}


async def login(platform: str):
    from playwright.async_api import async_playwright

    url = PLATFORM_URLS[platform]
    auth_file = AUTH_FILES[platform]

    print(f"Opening {platform} login page...")
    print(f"Connect via VNC to localhost:5900 to log in.")
    print(f"Once logged in, press Ctrl+C to save session.\n")

    pw = await async_playwright().start()

    # Use headed mode with Xvfb display
    browser = await pw.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )

    # Mobile context for Instagram
    if platform == "instagram":
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
            is_mobile=True,
            has_touch=True,
        )
    else:
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    print(f"Browser open at {url}")
    print("Log in manually via VNC, then press Ctrl+C here to save...")

    try:
        while True:
            await asyncio.sleep(5)
            current_url = page.url
            # Auto-detect successful login
            if platform == "facebook" and "/home" in current_url:
                print("Facebook login detected!")
                break
            elif platform == "instagram" and "accounts/login" not in current_url and "challenge" not in current_url:
                print("Instagram login detected!")
                break
            elif platform == "tiktok" and "login" not in current_url:
                print("TikTok login detected!")
                break
    except KeyboardInterrupt:
        pass

    # Save session
    await context.storage_state(path=auth_file)
    print(f"\nSession saved to {auth_file}")

    # Verify
    import json
    with open(auth_file) as f:
        state = json.load(f)
    print(f"Cookies: {len(state['cookies'])}")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in PLATFORM_URLS:
        print(f"Usage: python {sys.argv[0]} [facebook|instagram|tiktok]")
        sys.exit(1)

    os.environ["DISPLAY"] = ":99"
    asyncio.run(login(sys.argv[1]))
