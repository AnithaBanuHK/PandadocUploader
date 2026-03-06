"""
Microsoft Teams Graph API Utility for PandaDoc Follow-up System
Sends personalized direct messages to individual users via Microsoft Graph API.
Uses DELEGATED permissions with a stored refresh token (same auth as Postman test).

Flow per recipient:
  Step 1 — Exchange refresh token → access token  (delegated, on behalf of the sender user)
  Step 2 — Resolve chat ID                        (POST /v1.0/chats, oneOnOne — idempotent)
  Step 3 — Send direct message                    (POST /v1.0/chats/{chatId}/messages)

How to get TEAMS_REFRESH_TOKEN (one-time setup via Postman):
  1. In Postman → Authorization → OAuth 2.0 → Get New Access Token
  2. Scope: Chat.ReadWrite User.Read.All offline_access
  3. After token is generated, open Postman console or the token details —
     copy the 'refresh_token' value and paste it into .env as TEAMS_REFRESH_TOKEN
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

TEAMS_TENANT_ID     = os.getenv("TEAMS_TENANT_ID")
TEAMS_CLIENT_ID     = os.getenv("TEAMS_CLIENT_ID")
TEAMS_CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET")
TEAMS_REFRESH_TOKEN = os.getenv("TEAMS_REFRESH_TOKEN")

# Use .default so the scope always matches whatever was consented for this app —
# avoids AADSTS65001 scope mismatch errors with stored refresh tokens
DELEGATED_SCOPE = "https://graph.microsoft.com/.default offline_access"


def get_access_token() -> str | None:
    """
    Step 1: Exchange stored refresh token for a delegated access token.
    Endpoint: POST https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
    grant_type: refresh_token
    """
    if not all([TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET]):
        print("❌ Missing Teams credentials (TEAMS_TENANT_ID / CLIENT_ID / CLIENT_SECRET)")
        return None

    if not TEAMS_REFRESH_TOKEN:
        print("❌ TEAMS_REFRESH_TOKEN not set in .env")
        print("   In Postman: Get New Access Token → include 'offline_access' in scope")
        print("   Copy the refresh_token from the response and add it to .env")
        return None

    url = f"https://login.microsoftonline.com/{TEAMS_TENANT_ID}/oauth2/v2.0/token"
    payload = {
        "grant_type":    "refresh_token",
        "refresh_token": TEAMS_REFRESH_TOKEN,
        "client_id":     TEAMS_CLIENT_ID,
        "client_secret": TEAMS_CLIENT_SECRET,
        "scope":         DELEGATED_SCOPE
    }

    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"  ❌ Token refresh failed: {response.status_code} — {response.text}")
            return None
    except Exception as e:
        print(f"  ❌ Token error: {str(e)}")
        return None


def get_sender_id(token: str) -> str | None:
    """
    Get the authenticated sender's user ID via /me.
    Requires only User.Read (delegated) — no admin consent needed.
    """
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=headers,
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("id")
        else:
            print(f"  ❌ Could not get /me: {response.status_code} — {response.text}")
            return None
    except Exception as e:
        print(f"  ❌ /me error: {str(e)}")
        return None


def get_chat_id(token: str, recipient_email: str) -> str | None:
    """
    Step 2: Get or create a 1:1 chat between the sender and recipient.
    POST /v1.0/chats is idempotent — returns existing chat if it already exists.

    Uses recipient email directly as UPN in user@odata.bind — no User.Read.All needed.
    Endpoint: https://graph.microsoft.com/v1.0/chats
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }

    # Get sender ID via /me (requires only User.Read — no admin consent)
    sender_id = get_sender_id(token)
    if not sender_id:
        return None

    # Use recipient email directly as UPN — skips User.Read.All lookup entirely
    chat_payload = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type":     "#microsoft.graph.aadUserConversationMember",
                "roles":           ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{sender_id}')"
            },
            {
                "@odata.type":     "#microsoft.graph.aadUserConversationMember",
                "roles":           ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{recipient_email}')"
            }
        ]
    }

    chat_resp = requests.post(
        "https://graph.microsoft.com/v1.0/chats",
        headers=headers,
        json=chat_payload,
        timeout=10
    )

    if chat_resp.status_code in [200, 201]:
        chat_id = chat_resp.json().get("id")
        print(f"  Chat ID resolved: {chat_id}")
        return chat_id
    else:
        print(f"  ❌ Failed to get/create chat: {chat_resp.status_code} — {chat_resp.text}")
        return None


def send_teams_message(
    document_name: str,
    recipient_name: str,
    days_pending: int,
    document_id: str = None,
    recipient_email: str = None
) -> bool:
    """
    Send a personalized direct message to a Teams user via Microsoft Graph API.

    Args:
        document_name:   Name of the pending document
        recipient_name:  Display name of the recipient
        days_pending:    Days since the document was sent
        document_id:     PandaDoc document ID (used to build the signing link)
        recipient_email: Recipient's email address (resolves to their Teams account)

    Returns:
        True if message delivered, False otherwise
    """
    if not all([TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_REFRESH_TOKEN]):
        print("❌ Teams Graph API credentials not fully configured in .env")
        print("   Required: TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_REFRESH_TOKEN")
        return False

    if not recipient_email:
        print(f"  ❌ No email provided for {recipient_name} — cannot send Teams DM")
        return False

    # Step 1: Get delegated access token via refresh token
    token = get_access_token()
    if not token:
        return False

    # Step 2: Resolve / create 1:1 chat
    chat_id = get_chat_id(token, recipient_email)
    if not chat_id:
        return False

    # Step 3: Build and post the message
    doc_link_html = ""
    if document_id:
        doc_url = f"https://app.pandadoc.com/a/#/documents/{document_id}"
        doc_link_html = f'<br><br><a href="{doc_url}">Review &amp; Sign Document</a>'

    message_html = (
        f"Hi <b>{recipient_name}</b>,<br><br>"
        f"Just a friendly reminder — the document <b>&quot;{document_name}&quot;</b> has been "
        f"waiting for your signature for <b>{days_pending} day(s)</b>.<br><br>"
        f"Could you please take a moment to review and sign it? Your approval helps keep "
        f"things moving smoothly for everyone involved."
        f"{doc_link_html}"
    )

    payload = {
        "body": {
            "contentType": "html",
            "content":     message_html
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }

    try:
        # Endpoint: https://graph.microsoft.com/v1.0/chats/{chatId}/messages
        response = requests.post(
            f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code in [200, 201]:
            print(f"  ✅ Teams DM sent to {recipient_name} ({recipient_email})")
            return True
        else:
            print(f"  ❌ Teams message failed: {response.status_code} — {response.text}")
            return False

    except Exception as e:
        print(f"  ❌ Teams error: {str(e)}")
        return False


if __name__ == "__main__":
    import sys

    print("Teams Graph API Sender — Test (Delegated Auth)\n")

    missing = [v for v in [
        "TEAMS_TENANT_ID", "TEAMS_CLIENT_ID",
        "TEAMS_CLIENT_SECRET", "TEAMS_REFRESH_TOKEN"
    ] if not os.getenv(v)]

    if missing:
        print(f"❌ Missing .env variables: {', '.join(missing)}")
        print("\nRequired .env entries:")
        print("  TEAMS_TENANT_ID=<azure-tenant-id>")
        print("  TEAMS_CLIENT_ID=<app-client-id>")
        print("  TEAMS_CLIENT_SECRET=<app-client-secret>")
        print("  TEAMS_REFRESH_TOKEN=<refresh-token-from-postman>")
        print("\nRequired Azure AD app permissions (Delegated):")
        print("  Chat.ReadWrite    — to create/read chats and send messages")
        print("  User.Read.All     — to resolve email → user ID")
        print("  offline_access    — to obtain refresh tokens")
    else:
        # Accept email as CLI arg: python teams_sender.py someone@company.com
        if len(sys.argv) > 1:
            test_email = sys.argv[1]
            print(f"Recipient: {test_email}\n")
        else:
            test_email = input("Enter a test recipient email: ").strip()

        success = send_teams_message(
            document_name="Test Document",
            recipient_name="Test User",
            days_pending=3,
            document_id="test123",
            recipient_email=test_email
        )
        print("\nTest message sent! Check the recipient's Teams DMs." if success
              else "\nTest message failed. Check credentials and permissions.")
