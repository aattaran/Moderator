"""Log into X.com inside Docker using env vars X_USERNAME and X_PASSWORD."""

import asyncio
import json
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def login():
    username = os.environ.get("X_USERNAME", "")
    password = os.environ.get("X_PASSWORD", "")

    if not username or not password:
        logger.error("X_USERNAME and X_PASSWORD must be set in environment")
        return False

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir="/app/browser-profile",
        headless=True,
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    try:
        logger.info("Navigating to X.com login...")
        await page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(3)

        # Enter username
        logger.info("Entering username...")
        username_input = await page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
        await username_input.fill(username)
        await asyncio.sleep(1)

        # Click Next
        await page.click('button:has-text("Next")', timeout=5000)
        await asyncio.sleep(3)

        # Check for unusual activity / phone/email verification prompt
        phone_input = await page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
        if phone_input:
            logger.info("Verification required — entering username as verification...")
            await phone_input.fill(username)
            await page.click('button[data-testid="ocfEnterTextNextButton"]', timeout=5000)
            await asyncio.sleep(3)

        # Enter password
        logger.info("Entering password...")
        password_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
        await password_input.fill(password)
        await asyncio.sleep(1)

        # Click Log in
        await page.click('button[data-testid="LoginForm_Login_Button"]', timeout=5000)
        await asyncio.sleep(5)

        current_url = page.url
        logger.info("URL: %s", current_url)

        if "/home" in current_url:
            logger.info("LOGIN SUCCESSFUL!")
            await ctx.storage_state(path="/app/data/auth_state.json")
            logger.info("Session saved")
            return True
        else:
            await page.screenshot(path="/app/data/login_debug.png")
            logger.error("Login failed — URL: %s", current_url)
            return False

    except Exception as e:
        logger.error("Login error: %s", e)
        try:
            await page.screenshot(path="/app/data/login_debug.png")
        except Exception:
            pass
        return False
    finally:
        await ctx.close()
        await pw.stop()


if __name__ == "__main__":
    result = asyncio.run(login())
    exit(0 if result else 1)
