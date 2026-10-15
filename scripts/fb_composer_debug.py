import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])

        context = await browser.new_context(
            storage_state="/opt/moderator/data/facebook_auth_state.json",
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        print("Navigating to FB group...")
        await page.goto("https://www.facebook.com/groups/773954008871273", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(10000)

        await page.screenshot(path="/opt/moderator/data/fb_group_loaded.png", full_page=False)
        print("Screenshot 1 saved: fb_group_loaded.png")

        # Find composer trigger
        print("\n=== Looking for composer trigger elements ===")
        write_something = None

        triggers = await page.query_selector_all("[role=\"button\"]")
        print(f"Found {len(triggers)} role=button elements")

        for t in triggers:
            text = await t.inner_text()
            if text and ("write" in text.lower() or "what" in text.lower() or "create" in text.lower()):
                print(f"  Potential trigger: text='{text}'")
                tag_html = await t.evaluate("el => el.outerHTML.substring(0, 300)")
                print(f"    HTML: {tag_html}")
                if not write_something:
                    write_something = t

        spans = await page.query_selector_all("span")
        for s in spans:
            text = await s.inner_text()
            if text and ("write something" in text.lower() or "on your mind" in text.lower()):
                print(f"  Found span: '{text}'")
                if not write_something:
                    write_something = s

        if write_something:
            print(f"\nClicking composer trigger...")
            await write_something.click()
            await page.wait_for_timeout(5000)
            print("Clicked and waited 5s")
        else:
            print("WARNING: No composer trigger found, trying alternative selectors...")
            alt = await page.query_selector("[data-testid=\"composer_placeholder\"]")
            if alt:
                await alt.click()
                await page.wait_for_timeout(5000)

        await page.screenshot(path="/opt/moderator/data/fb_composer_opened.png", full_page=False)
        print("Screenshot 2 saved: fb_composer_opened.png")

        # Dump all contenteditable elements
        print("\n=== All contenteditable elements ===")
        editables = await page.query_selector_all("[contenteditable]")
        for i, el in enumerate(editables):
            ce_val = await el.get_attribute("contenteditable")
            role = await el.get_attribute("role")
            aria_label = await el.get_attribute("aria-label")
            tag = await el.evaluate("el => el.tagName")
            visible = await el.is_visible()
            data_attrs = await el.evaluate("el => Object.keys(el.dataset).map(k => 'data-' + k + '=' + el.dataset[k]).join(', ')")
            html = await el.evaluate("el => el.outerHTML.substring(0, 500)")
            print(f"\n  [{i}] contenteditable={ce_val} role={role} aria-label={aria_label} tag={tag} visible={visible}")
            print(f"      data-attrs={data_attrs}")
            print(f"      html={html}")

        # Dump all role=textbox elements
        print("\n=== All role=textbox elements ===")
        textboxes = await page.query_selector_all("[role=\"textbox\"]")
        for i, el in enumerate(textboxes):
            ce_val = await el.get_attribute("contenteditable")
            aria_label = await el.get_attribute("aria-label")
            tag = await el.evaluate("el => el.tagName")
            visible = await el.is_visible()
            html = await el.evaluate("el => el.outerHTML.substring(0, 500)")
            print(f"\n  [{i}] role=textbox contenteditable={ce_val} aria-label={aria_label} tag={tag} visible={visible}")
            print(f"      html={html}")

        # Dump all dialog/modal elements
        print("\n=== All dialog/modal elements ===")
        dialogs = await page.query_selector_all("[role=\"dialog\"]")
        for i, el in enumerate(dialogs):
            aria_label = await el.get_attribute("aria-label")
            visible = await el.is_visible()
            children_info = await el.evaluate("""el => {
                let results = [];
                let all = el.querySelectorAll('[role], [contenteditable], textarea, input[type="text"]');
                all.forEach(child => {
                    results.push({
                        tag: child.tagName,
                        role: child.getAttribute("role"),
                        contenteditable: child.getAttribute("contenteditable"),
                        ariaLabel: child.getAttribute("aria-label"),
                        placeholder: child.getAttribute("placeholder") || child.getAttribute("data-placeholder"),
                        visible: child.offsetParent !== null,
                        html: child.outerHTML.substring(0, 300)
                    });
                });
                return results;
            }""")
            print(f"\n  Dialog [{i}] aria-label={aria_label} visible={visible}")
            for ci, child in enumerate(children_info):
                print(f"    Child [{ci}]: tag={child['tag']} role={child['role']} ce={child['contenteditable']} label={child['ariaLabel']} placeholder={child['placeholder']} visible={child['visible']}")
                print(f"      html={child['html']}")

        # Check textareas and inputs
        print("\n=== textareas ===")
        textareas = await page.query_selector_all("textarea")
        for i, el in enumerate(textareas):
            visible = await el.is_visible()
            placeholder = await el.get_attribute("placeholder")
            print(f"  textarea[{i}] visible={visible} placeholder={placeholder}")

        print("\n=== input[type=text] ===")
        inputs = await page.query_selector_all("input[type=\"text\"]")
        for i, el in enumerate(inputs):
            visible = await el.is_visible()
            placeholder = await el.get_attribute("placeholder")
            aria_label = await el.get_attribute("aria-label")
            print(f"  input[{i}] visible={visible} placeholder={placeholder} aria-label={aria_label}")

        # Check iframes
        print("\n=== iframes ===")
        iframes = await page.query_selector_all("iframe")
        for i, el in enumerate(iframes):
            src = await el.get_attribute("src")
            title = await el.get_attribute("title")
            visible = await el.is_visible()
            print(f"  iframe[{i}] src={src} title={title} visible={visible}")

        await page.screenshot(path="/opt/moderator/data/fb_composer_debug.png", full_page=False)
        print("\nScreenshot 3 saved: fb_composer_debug.png")

        await browser.close()
        print("\nDone!")

asyncio.run(main())
