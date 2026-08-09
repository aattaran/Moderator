import asyncio, os
os.environ["DISPLAY"] = ":99"

async def run():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False, args=["--no-sandbox"])
    ctx = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        storage_state="/opt/moderator/data/facebook_auth_state.json",
    )
    page = await ctx.new_page()
    await page.goto("https://www.facebook.com/groups/773954008871273/settings", timeout=60000)
    print("Group settings page open — connect VNC to 137.184.137.154:5900")
    await asyncio.sleep(600)
    await browser.close()
    await pw.stop()

asyncio.run(run())
