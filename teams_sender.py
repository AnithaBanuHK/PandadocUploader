"""
Microsoft Teams Webhook Utility for PandaDoc Follow-up System
Sends personalized follow-up notifications to a Teams channel via Incoming Webhook
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

TEAMS_WEBHOOK_URL = os.getenv("TEAMS_WEBHOOK_URL")


def send_teams_message(document_name: str, recipient_name: str, days_pending: int, document_id: str = None) -> bool:
    """
    Send a personalized follow-up reminder to a Teams channel

    Args:
        document_name: Name of the pending document
        recipient_name: Name of the unsigned recipient
        days_pending: Number of days since the document was sent
        document_id: PandaDoc document ID (used to generate the signing link)

    Returns:
        True if message sent successfully, False otherwise
    """
    if not TEAMS_WEBHOOK_URL:
        print("❌ Teams webhook URL not configured in .env file")
        print("   Please set TEAMS_WEBHOOK_URL")
        return False

    # Build the Adaptive Card body
    card_body = [
        {
            "type": "TextBlock",
            "text": f"Hi **{recipient_name}**,",
            "wrap": True,
            "size": "Medium",
            "weight": "Bolder"
        },
        {
            "type": "TextBlock",
            "text": f"Just a friendly reminder - the document **\"{document_name}\"** has been waiting for your signature for **{days_pending} day(s)**.",
            "wrap": True,
            "spacing": "Small"
        },
        {
            "type": "TextBlock",
            "text": "Could you please take a moment to review and sign it? Your approval helps keep things moving smoothly for everyone involved.",
            "wrap": True,
            "spacing": "Small"
        }
    ]

    # Add a direct link button if we have the document ID
    card_actions = []
    if document_id:
        doc_url = f"https://app.pandadoc.com/a/#/documents/{document_id}"
        card_actions.append({
            "type": "Action.OpenUrl",
            "title": "Review & Sign Document",
            "url": doc_url,
            "style": "positive"
        })

    card_content = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": card_body
    }
    if card_actions:
        card_content["actions"] = card_actions

    # Adaptive Card payload for Teams Incoming Webhook
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card_content
            }
        ]
    }

    try:
        response = requests.post(TEAMS_WEBHOOK_URL, json=payload, timeout=10)

        if response.status_code in [200, 202]:
            print(f"  Teams message sent for {recipient_name}")
            return True
        else:
            print(f"  Teams webhook failed: {response.status_code} - {response.text}")
            return False

    except Exception as e:
        print(f"  Teams error: {str(e)}")
        return False


if __name__ == "__main__":
    print("Teams Sender Test\n")

    if not TEAMS_WEBHOOK_URL:
        print("TEAMS_WEBHOOK_URL not found in .env")
        print("\nTo configure:")
        print("1. In your Teams channel, click '...' -> 'Connectors' -> 'Incoming Webhook'")
        print("2. Name it (e.g., 'PandaDoc Reminders') and copy the webhook URL")
        print("3. Add to your .env file:")
        print("   TEAMS_WEBHOOK_URL=https://your-org.webhook.office.com/...")
    else:
        print("Webhook URL configured")
        print("\nSending test message...")
        success = send_teams_message(
            document_name="Test Document",
            recipient_name="Test User",
            days_pending=1,
            document_id="test123"
        )
        if success:
            print("\nTest message sent! Check your Teams channel.")
        else:
            print("\nTest message failed. Check your webhook URL.")
