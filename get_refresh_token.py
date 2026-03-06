"""
One-time setup script to obtain and save a Teams refresh token.
Uses the OAuth2 Device Code Flow — no web server or Postman needed.

Run this script whenever the refresh token expires (~90 days):
    python get_refresh_token.py

What it does:
  1. Requests a device code from Microsoft
  2. Prints a short URL + code for you to open in any browser
  3. Polls silently until you complete login
  4. Automatically writes the refresh token into your .env file
"""

import os
import time
import requests
from dotenv import load_dotenv, set_key
from pathlib import Path

load_dotenv()

TEAMS_TENANT_ID = os.getenv("TEAMS_TENANT_ID")
TEAMS_CLIENT_ID = os.getenv("TEAMS_CLIENT_ID")

ENV_FILE = Path(__file__).parent / ".env"

# Scopes needed for Teams DM sending
SCOPES = "Chat.ReadWrite User.Read offline_access"

TOKEN_URL    = f"https://login.microsoftonline.com/{TEAMS_TENANT_ID}/oauth2/v2.0/token"
DEVICE_URL   = f"https://login.microsoftonline.com/{TEAMS_TENANT_ID}/oauth2/v2.0/devicecode"


def request_device_code() -> dict | None:
    """Step 1: Request a device code from Microsoft."""
    response = requests.post(
        DEVICE_URL,
        data={
            "client_id": TEAMS_CLIENT_ID,
            "scope":     SCOPES
        },
        timeout=10
    )
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Failed to get device code: {response.status_code} — {response.text}")
        return None


def poll_for_token(device_code: str, interval: int, expires_in: int) -> dict | None:
    """Step 2: Poll until the user completes login."""
    deadline = time.time() + expires_in

    while time.time() < deadline:
        time.sleep(interval)

        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type":  "urn:ietf:params:oauth:grant-type:device_code",
                "client_id":   TEAMS_CLIENT_ID,
                "device_code": device_code
            },
            timeout=10
        )

        data = response.json()

        if response.status_code == 200:
            return data  # Contains access_token + refresh_token

        error = data.get("error")

        if error == "authorization_pending":
            print("  ⏳ Waiting for login...", end="\r")
            continue
        elif error == "slow_down":
            interval += 5
            continue
        elif error == "expired_token":
            print("\n❌ Code expired. Please run the script again.")
            return None
        elif error == "access_denied":
            print("\n❌ Login was cancelled or denied.")
            return None
        else:
            print(f"\n❌ Unexpected error: {data}")
            return None

    print("\n❌ Timed out waiting for login.")
    return None


def save_refresh_token(refresh_token: str):
    """Write the refresh token into the .env file automatically."""
    set_key(str(ENV_FILE), "TEAMS_REFRESH_TOKEN", refresh_token)
    print(f"\n✅ Refresh token saved to {ENV_FILE}")


def main():
    print("=" * 55)
    print("  Teams Refresh Token Setup (Device Code Flow)")
    print("=" * 55)

    if not TEAMS_TENANT_ID or not TEAMS_CLIENT_ID:
        print("❌ TEAMS_TENANT_ID and TEAMS_CLIENT_ID must be set in .env first.")
        return

    print("\nStep 1: Requesting device code...")
    device_data = request_device_code()
    if not device_data:
        return

    # Show the user what to do
    print("\n" + "=" * 55)
    print(f"  Open this URL in your browser:")
    print(f"\n    {device_data['verification_uri']}")
    print(f"\n  Enter this code when prompted:")
    print(f"\n    {device_data['user_code']}")
    print("=" * 55)
    print(f"\nWaiting for you to complete login (expires in {device_data['expires_in'] // 60} minutes)...\n")

    # Poll for token
    token_data = poll_for_token(
        device_code=device_data["device_code"],
        interval=device_data.get("interval", 5),
        expires_in=device_data["expires_in"]
    )

    if not token_data:
        return

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print("❌ No refresh token in response. Make sure 'offline_access' is in the scope.")
        return

    # Save to .env
    save_refresh_token(refresh_token)

    print("\nDone! You can now run:")
    print("  python teams_sender.py recipient@yourcompany.com")
    print("\nNote: Re-run this script when the token expires (~90 days).")


if __name__ == "__main__":
    main()
