"""
Microsoft Graph API Email Utility for PandaDoc Follow-up System
Sends HTML emails via Microsoft Graph API using delegated auth.
Reuses the same refresh token flow as teams_sender.py.

Required Azure AD app permission (Delegated): Mail.Send
Scope used when generating refresh token must include: Mail.Send
"""

import requests
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

OUTLOOK_EMAIL = os.getenv("OUTLOOK_EMAIL")


def get_access_token() -> str | None:
    """Reuse token exchange from teams_sender (same delegated auth flow)."""
    from teams_sender import get_access_token as _get_token
    return _get_token()


def send_email(
    to_email: str,
    cc_emails: List[str],
    subject: str,
    body_html: str,
) -> bool:
    """
    Send an HTML email via Microsoft Graph API (POST /me/sendMail).

    Args:
        to_email:   Primary recipient email address
        cc_emails:  List of CC recipient email addresses
        subject:    Email subject line
        body_html:  HTML email body
        from_name:  Display name (informational only — sender is the authenticated user)

    Returns:
        True if sent successfully (HTTP 202), False otherwise
    """
    token = get_access_token()
    if not token:
        return False

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html
            },
            "toRecipients": [
                {"emailAddress": {"address": to_email}}
            ],
            "ccRecipients": [
                {"emailAddress": {"address": cc}} for cc in cc_emails
            ]
        },
        "saveToSentItems": True
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json"
    }

    try:
        response = requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            headers=headers,
            json=payload,
            timeout=10
        )

        if response.status_code == 202:
            print(f"  ✅ Email sent to {to_email}")
            if cc_emails:
                print(f"     CC: {', '.join(cc_emails)}")
            return True
        else:
            print(f"  ❌ Email failed: {response.status_code} — {response.text}")
            return False

    except Exception as e:
        print(f"  ❌ Email error: {str(e)}")
        return False


def send_test_email(test_email: str) -> bool:
    """Send a test email to verify Graph API mail configuration."""
    subject = "PandaDoc Follow-up System - Test Email"
    body_html = """
    <html>
    <body>
        <h2>Test Email from PandaDoc Follow-up System</h2>
        <p>This is a test email to verify your Microsoft Graph API mail configuration.</p>
        <p>If you're seeing this, your Outlook email setup is working correctly! ✅</p>
        <hr>
        <p style="color: #666; font-size: 12px;">
            Sent by PandaDoc Automation System<br>
            Powered by Microsoft Graph API
        </p>
    </body>
    </html>
    """
    print(f"📧 Sending test email to {test_email}...")
    return send_email(
        to_email=test_email,
        cc_emails=[],
        subject=subject,
        body_html=body_html
    )


if __name__ == "__main__":
    import sys

    print("📧 Graph API Email Sender — Test\n")

    if len(sys.argv) > 1:
        test_addr = sys.argv[1]
    else:
        test_addr = input("Enter a test recipient email: ").strip()

    success = send_test_email(test_addr)
    print("\nTest email sent!" if success else "\nTest email failed. Check credentials and Mail.Send permission.")
