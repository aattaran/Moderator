"""One-time YouTube OAuth2 setup. Run on your local machine (not the server).

Usage: python scripts/youtube_auth.py

Opens a browser for Google consent, saves refresh token to data/youtube_credentials.json.
Upload this file to the droplet after.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS = "data/youtube_client_secrets.json"
CREDENTIALS_FILE = "data/youtube_credentials.json"


def main():
    if not os.path.exists(CLIENT_SECRETS):
        print(f"ERROR: {CLIENT_SECRETS} not found.")
        print("Download it from Google Cloud Console → Credentials → OAuth 2.0 Client ID")
        return

    print("Opening browser for YouTube authorization...")
    print("Log in with the Google account that owns the YouTube channel.\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    credentials = flow.run_local_server(port=8080, prompt="consent")

    with open(CREDENTIALS_FILE, "w") as f:
        f.write(credentials.to_json())

    print(f"\nCredentials saved to {CREDENTIALS_FILE}")
    print(f"Refresh token: {credentials.refresh_token[:20]}...")
    print("\nUpload to droplet:")
    print(f"  scp -i ~/.ssh/id_moderator {CREDENTIALS_FILE} root@137.184.137.154:/opt/moderator/{CREDENTIALS_FILE}")


if __name__ == "__main__":
    main()
