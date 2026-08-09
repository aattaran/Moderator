"""Launch browser in headed mode for manual X.com login. Run this locally (not in Docker)."""

import asyncio
from playwright.async_api import async_playwright


async def main():
    print("Launching Firefox for X.com login...")
    print("Log in to your X account, then close the browser window.")
    print("Your session will be saved to ./browser-profile/\n")

    pw = await async_playwright().start()
    context = await pw.firefox.launch_persistent_context(
        user_data_dir="./browser-profile",
        headless=False,
        viewport={"width": 1280, "height": 900},
    )
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("https://x.com/login")

    print("Waiting for you to log in... (close browser when done)")
    try:
        await page.wait_for_url("**/home", timeout=300000)  # 5 min timeout
        print("\nLogin detected! Saving session...")
        await asyncio.sleep(3)
    except Exception:
        print("\nBrowser closed or timed out.")

    await context.close()
    await pw.stop()
    print("Session saved to ./browser-profile/")
    print("You can now run: docker compose up -d")


if __name__ == "__main__":
    asyncio.run(main())
