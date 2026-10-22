"""Extract X.com cookies from your regular Chrome browser and save as Playwright auth state.
You must be logged into X.com in Chrome. Close Chrome before running this."""

import json
import browser_cookie3


def main():
    print("Extracting X.com cookies from Chrome...")
    print("(Make sure Chrome is CLOSED first)\n")

    try:
        cj = browser_cookie3.chrome(domain_name=".x.com")
    except Exception as e:
        print(f"Error reading Chrome cookies: {e}")
        print("Make sure Chrome is fully closed (check Task Manager).")
        return

    cookies = []
    for cookie in cj:
        if "x.com" in cookie.domain or "twitter.com" in cookie.domain:
            cookies.append({
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires or -1,
                "httpOnly": bool(cookie._rest.get("HttpOnly", False)),
                "secure": cookie.secure,
                "sameSite": "None" if cookie.secure else "Lax",
            })

    # Check for auth cookies
    auth_cookies = [c for c in cookies if c["name"] in ("auth_token", "ct0", "twid")]
    if not auth_cookies:
        print("WARNING: No auth cookies found. Are you logged into X.com in Chrome?")
        print(f"Found {len(cookies)} cookies but none are auth tokens.")
        return

    auth_state = {
        "cookies": cookies,
        "origins": [],
    }

    with open("data/auth_state.json", "w") as f:
        json.dump(auth_state, f, indent=2)

    print(f"Extracted {len(cookies)} cookies ({len(auth_cookies)} auth cookies)")
    print(f"Auth cookies: {[c['name'] for c in auth_cookies]}")
    print(f"Saved to data/auth_state.json")


if __name__ == "__main__":
    main()
