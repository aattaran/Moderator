"""Export X.com session by connecting to Chrome's existing profile via CDP."""

import asyncio
import json
import subprocess
import os
import sys
import time


async def main():
    chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    user_data = os.path.join(os.environ["LOCALAPPDATA"], "Google", "Chrome", "User Data")

    print("Launching Chrome with your real profile...")
    print("Make sure you're logged into X.com, then this script auto-extracts cookies.\n")

    # Launch Chrome with remote debugging
    proc = subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data}",
        "--profile-directory=Default",
        "https://x.com",
    ])

    # Wait for Chrome to start
    print("Waiting 15 seconds for Chrome to load...")
    await asyncio.sleep(15)

    # Connect via CDP and extract cookies
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        # Save storage state
        await context.storage_state(path="./data/auth_state.json")
        print("Session saved to ./data/auth_state.json")

        # Verify
        with open("./data/auth_state.json") as f:
            state = json.load(f)
        auth_cookies = [c for c in state["cookies"] if c["name"] in ("auth_token", "ct0", "twid")]
        all_x = [c for c in state["cookies"] if "x.com" in c.get("domain", "") or "twitter.com" in c.get("domain", "")]
        print(f"Total X cookies: {len(all_x)}")
        print(f"Auth cookies: {[c['name'] for c in auth_cookies]}")

        if auth_cookies:
            print("\nSUCCESS — session ready for Docker")
        else:
            print("\nWARNING — no auth cookies. Are you logged into X.com?")

        await pw.stop()
    except Exception as e:
        print(f"Error: {e}")

    proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
