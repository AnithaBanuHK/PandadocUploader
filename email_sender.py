"""
Gmail SMTP Email Utility for PandaDoc Follow-up System
Sends HTML emails via Gmail with retry logic
"""

import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()

# Gmail SMTP Configuration
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def send_email(
    to_email: str,
    cc_emails: List[str],
    subject: str,
    body_html: str,
    from_name: str = "PandaDoc Automation"
) -> bool:
    """
    Send HTML email via Gmail SMTP

    Args:
        to_email: Primary recipient email
        cc_emails: List of CC recipient emails
        subject: Email subject line
        body_html: HTML email body
        from_name: Display name for sender

    Returns:
        True if email sent successfully, False otherwise
    """
    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        print("❌ Gmail credentials not configured in .env file")
        print("   Please set GMAIL_EMAIL and GMAIL_APP_PASSWORD")
        return False

    # Create message
    msg = MIMEMultipart('alternative')
    msg['From'] = f"{from_name} <{GMAIL_EMAIL}>"
    msg['To'] = to_email
    if cc_emails:
        msg['Cc'] = ', '.join(cc_emails)
    msg['Subject'] = subject

    # Attach HTML body
    html_part = MIMEText(body_html, 'html')
    msg.attach(html_part)

    # Combine TO and CC for actual sending
    all_recipients = [to_email] + cc_emails

    # Retry logic (3 attempts with exponential backoff)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Connect to Gmail SMTP server
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()  # Enable TLS encryption
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)

            # Send email
            server.sendmail(GMAIL_EMAIL, all_recipients, msg.as_string())
            server.quit()

            print(f"✅ Email sent to {to_email}")
            if cc_emails:
                print(f"   CC: {', '.join(cc_emails)}")
            return True

        except smtplib.SMTPAuthenticationError:
            print("❌ Gmail authentication failed")
            print("   Make sure you're using an App Password, not your regular password")
            print("   Generate one at: https://myaccount.google.com/apppasswords")
            return False

        except smtplib.SMTPException as e:
            print(f"⚠️ SMTP error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                print(f"   Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"❌ Failed to send email after {max_retries} attempts")
                return False

        except Exception as e:
            print(f"❌ Unexpected error sending email: {str(e)}")
            return False

    return False


def send_test_email(test_email: str) -> bool:
    """
    Send a test email to verify configuration

    Args:
        test_email: Email address to send test to

    Returns:
        True if successful, False otherwise
    """
    subject = "PandaDoc Follow-up System - Test Email"
    body_html = """
    <html>
    <body>
        <h2>Test Email from PandaDoc Follow-up System</h2>
        <p>This is a test email to verify your Gmail SMTP configuration.</p>
        <p>If you're seeing this, your email setup is working correctly! ✅</p>
        <hr>
        <p style="color: #666; font-size: 12px;">
            Sent by PandaDoc Automation System<br>
            Powered by Gmail SMTP
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
    # Test the email sender
    print("📧 Email Sender Test\n")

    if not GMAIL_EMAIL or not GMAIL_APP_PASSWORD:
        print("❌ Gmail credentials not found!")
        print("\nTo configure:")
        print("1. Add to your .env file:")
        print("   GMAIL_EMAIL=your-email@gmail.com")
        print("   GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx")
        print("\n2. Generate App Password:")
        print("   - Go to https://myaccount.google.com/apppasswords")
        print("   - Enable 2-Step Verification first (required)")
        print("   - Generate app password for 'Mail'")
        print("   - Copy the 16-character password to .env")
    else:
        print(f"✅ Gmail credentials found: {GMAIL_EMAIL}")
        print("\nTo send a test email, run:")
        print(f"  python -c \"from email_sender import send_test_email; send_test_email('{GMAIL_EMAIL}')\"")
