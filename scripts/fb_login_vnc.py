import asyncio, os, json
os.environ["DISPLAY"] = ":99"

async def run():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=False, args=["--no-sandbox"])
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await ctx.new_page()
    await page.goto("https://www.facebook.com/login", timeout=30000)
    print("FB login open - log in via VNC (137.184.137.154:5900)")

    for i in range(120):
        await asyncio.sleep(5)
        url = page.url
        if "login" not in url and "checkpoint" not in url:
            print("Login detected: " + url)
            break
        if i % 12 == 0:
            print("Waiting... " + url[:50])

    await asyncio.sleep(5)
    path = "/opt/moderator/data/facebook_auth_state.json"
    await ctx.storage_state(path=path)
    data = json.load(open(path))
    print("Saved " + str(len(data.get("cookies", []))) + " cookies")
    await browser.close()
    await pw.stop()

asyncio.run(run())
