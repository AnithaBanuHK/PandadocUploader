"""
Follow-up Workflow for PandaDoc Document Approvals
Multi-agent system using LangGraph to automate daily follow-ups
"""

import os
import json
import requests
from datetime import datetime
from typing import TypedDict
from dotenv import load_dotenv
import vertexai
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, END

from followup_tracker import (
    get_pending_documents,
    update_followup,
    mark_completed
)
from email_sender import send_email
from teams_sender import send_teams_message

load_dotenv()

# Initialize Vertex AI
vertexai.init(
    project=os.getenv("VERTEX_PROJECT", "aac-dw-dev"),
    location=os.getenv("VERTEX_LOCATION", "europe-west1")
)


# State definition for follow-up workflow
class FollowupState(TypedDict):
    pending_documents: list[dict]      # Documents needing follow-up
    pandadoc_statuses: dict            # Current status from PandaDoc API
    filtered_documents: list[dict]     # Documents that need follow-up TODAY
    drafted_emails: list[dict]         # AI-drafted email content
    sent_teams: list[dict]             # Results of Teams notifications
    sent_emails: list[dict]            # Results of email sending
    error: str | None


# Agent 1: Load pending documents from tracker
def load_tracker_node(state: FollowupState) -> FollowupState:
    """Load all pending documents from tracking JSON"""
    print("📋 Agent 1: Loading pending documents from tracker...")

    try:
        pending = get_pending_documents()
        state["pending_documents"] = pending
        print(f"✅ Loaded {len(pending)} pending document(s)")

        if pending:
            for doc in pending:
                print(f"  - {doc['document_name']} ({doc['document_id']}) - Sent: {doc['sent_date'][:10]}")

    except Exception as e:
        state["error"] = f"Failed to load tracker: {str(e)}"
        state["pending_documents"] = []
        print(f"❌ Error loading tracker: {str(e)}")

    return state


# Agent 2: Check current status of each document in PandaDoc
def status_check_node(state: FollowupState) -> FollowupState:
    """Query PandaDoc API for each document's current status"""
    print("\n🔍 Agent 2: Checking document statuses in PandaDoc...")

    api_key = os.getenv("PANDADOC_API_KEY")
    api_url = os.getenv("PANDADOC_API_URL", "https://api.pandadoc.com/public/v1/documents")
    headers = {"Authorization": f"API-Key {api_key}"}

    statuses = {}

    for doc in state.get("pending_documents", []):
        doc_id = doc["document_id"]

        try:
            # GET /documents/{id}/details to get full info including recipients
            response = requests.get(f"{api_url}/{doc_id}/details", headers=headers)

            if response.status_code == 200:
                data = response.json()
                statuses[doc_id] = {
                    "status": data.get("status"),
                    "recipients": data.get("recipients", [])
                }
                print(f"  ✅ {doc['document_name']}: {data.get('status')}")
            else:
                print(f"  ⚠️ Failed to get status for {doc_id}: {response.status_code}")

        except Exception as e:
            print(f"  ❌ Error checking {doc_id}: {str(e)}")

    state["pandadoc_statuses"] = statuses
    print(f"✅ Checked status for {len(statuses)} document(s)")

    return state


# Agent 3: Filter documents that still need signatures
def filter_documents_node(state: FollowupState) -> FollowupState:
    """Filter documents that still have unsigned recipients"""
    print("\n🔎 Agent 3: Filtering documents that need follow-up...")

    filtered = []
    now = datetime.now()

    for doc in state.get("pending_documents", []):
        doc_id = doc["document_id"]

        # Check if we have PandaDoc status for this document
        if doc_id not in state.get("pandadoc_statuses", {}):
            print(f"  ⏭️ Skipping {doc['document_name']}: No status available")
            continue

        pd_status = state["pandadoc_statuses"][doc_id]

        # Skip if document is completed
        if pd_status["status"] == "document.completed":
            print(f"  ✅ {doc['document_name']}: Completed - marking in tracker")
            mark_completed(doc_id)
            continue

        # Check if all recipients have signed
        recipients = pd_status.get("recipients", [])
        if not recipients:
            print(f"  ⚠️ {doc['document_name']}: No recipients found")
            continue

        unsigned_recipients = [
            r for r in recipients
            if not r.get("has_completed", False)
        ]

        if not unsigned_recipients:
            print(f"  ✅ {doc['document_name']}: All recipients signed - marking completed")
            mark_completed(doc_id)
            continue

        # Include all documents with unsigned recipients
        doc["unsigned_recipients"] = unsigned_recipients
        sent_date = datetime.fromisoformat(doc["sent_date"])
        days_pending = (now - sent_date).days
        filtered.append(doc)
        print(f"  📬 {doc['document_name']}: {len(unsigned_recipients)} unsigned, {days_pending} day(s) since sent")

    state["filtered_documents"] = filtered
    print(f"\n✅ {len(filtered)} document(s) need follow-up today")

    return state


# Agent 4: Draft personalized follow-up emails using AI
def draft_emails_node(state: FollowupState) -> FollowupState:
    """Use Gemini AI to draft personalized follow-up emails"""
    print("\n✍️ Agent 4: Drafting follow-up emails with AI...")

    if not state.get("filtered_documents"):
        print("  ℹ️ No documents need follow-up - skipping email drafting")
        state["drafted_emails"] = []
        return state

    llm = ChatVertexAI(
        model=os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-lite"),
        temperature=0.3,  # Slightly creative but still professional
    )

    drafted_emails = []

    for doc in state["filtered_documents"]:
        sent_date = datetime.fromisoformat(doc["sent_date"])
        days_pending = (datetime.now() - sent_date).days

        for unsigned_recipient in doc["unsigned_recipients"]:
            # Get all other signers for CC
            all_recipients = doc["recipients"]
            other_signers = [
                r for r in all_recipients
                if r["email"] != unsigned_recipient["email"]
            ]

            recipient_name = f"{unsigned_recipient.get('first_name', '')} {unsigned_recipient.get('last_name', '')}".strip()
            if not recipient_name:
                recipient_name = unsigned_recipient.get("email", "there").split("@")[0]

            prompt = f"""You are a professional follow-up email writer. Draft a polite, concise follow-up email for a pending document approval.

**Document Details:**
- Document Name: {doc["document_name"]}
- Sent Date: {sent_date.strftime("%B %d, %Y")}
- Days Pending: {days_pending}
- Recipient Name: {recipient_name}
- Recipient Role: {unsigned_recipient.get("role", "Signer")}

**Instructions:**
1. Keep it SHORT (3-4 sentences max)
2. Be POLITE and PROFESSIONAL (not pushy)
3. Mention how long it's been pending ({days_pending} days)
4. Briefly explain why this approval is important (business continuity, project timeline, etc.)
5. Include a clear call-to-action (sign the document)
6. Use a friendly but professional tone

**Format:**
- Subject line (under 60 characters)
- Email body (HTML format, simple styling)
- Sign off with "Best regards,<br>PandaDoc Automation Team"

Return ONLY a JSON object with this structure:
{{
    "subject": "subject line here",
    "body_html": "HTML email body here with <p> tags"
}}

Example good email:
Subject: Reminder: NDA For Signoff - Pending Your Signature
Body:
<p>Hi John,</p>
<p>I hope this email finds you well. This is a gentle reminder that your signature is still needed on the <strong>NDA For Signoff</strong> document, which has been pending for 3 days.</p>
<p>Your approval is critical to keeping our project on track and ensuring smooth collaboration. Could you please take a moment to review and sign at your earliest convenience?</p>
<p>Best regards,<br>PandaDoc Automation Team</p>
"""

            try:
                response = llm.invoke(prompt)
                response_text = response.content.strip()

                # Parse JSON from response
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0].strip()
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0].strip()

                email_content = json.loads(response_text)

                drafted_emails.append({
                    "document_id": doc["document_id"],
                    "document_name": doc["document_name"],
                    "to_email": unsigned_recipient["email"],
                    "to_name": recipient_name,
                    "cc_emails": [r["email"] for r in other_signers],
                    "subject": email_content["subject"],
                    "body_html": email_content["body_html"]
                })

                print(f"  ✅ Drafted email for {unsigned_recipient['email']}")

            except Exception as e:
                print(f"  ❌ Error drafting email for {unsigned_recipient['email']}: {str(e)}")

    state["drafted_emails"] = drafted_emails
    print(f"\n✅ Drafted {len(drafted_emails)} email(s)")

    return state


# Agent 5: Send brief Teams channel notifications
def send_teams_node(state: FollowupState) -> FollowupState:
    """Send brief follow-up reminders to Teams channel"""
    print("\n📢 Agent 5: Sending Teams channel notifications...")

    if not state.get("filtered_documents"):
        print("  ℹ️ No documents need follow-up - skipping Teams notifications")
        state["sent_teams"] = []
        return state

    sent_results = []

    for doc in state["filtered_documents"]:
        sent_date = datetime.fromisoformat(doc["sent_date"])
        days_pending = (datetime.now() - sent_date).days

        for unsigned_recipient in doc.get("unsigned_recipients", []):
            recipient_name = f"{unsigned_recipient.get('first_name', '')} {unsigned_recipient.get('last_name', '')}".strip()
            if not recipient_name:
                recipient_name = unsigned_recipient.get("email", "Unknown").split("@")[0]

            success = send_teams_message(
                document_name=doc["document_name"],
                recipient_name=recipient_name,
                days_pending=days_pending,
                document_id=doc["document_id"]
            )

            sent_results.append({
                "document_id": doc["document_id"],
                "recipient": recipient_name,
                "success": success
            })

    state["sent_teams"] = sent_results

    successful = sum(1 for r in sent_results if r["success"])
    print(f"\n✅ Sent {successful}/{len(sent_results)} Teams notification(s)")

    return state


# Agent 6: Send drafted emails via Gmail SMTP
def send_emails_node(state: FollowupState) -> FollowupState:
    """Send drafted emails via Gmail SMTP"""
    print("\n📧 Agent 6: Sending follow-up emails...")

    if not state.get("drafted_emails"):
        print("  ℹ️ No emails to send")
        state["sent_emails"] = []
        return state

    sent_results = []

    for email in state["drafted_emails"]:
        try:
            success = send_email(
                to_email=email["to_email"],
                cc_emails=email["cc_emails"],
                subject=email["subject"],
                body_html=email["body_html"]
            )

            sent_results.append({
                "document_id": email["document_id"],
                "to_email": email["to_email"],
                "success": success
            })

        except Exception as e:
            print(f"  ❌ Error sending to {email['to_email']}: {str(e)}")
            sent_results.append({
                "document_id": email["document_id"],
                "to_email": email["to_email"],
                "success": False,
                "error": str(e)
            })

    state["sent_emails"] = sent_results

    # Summary
    successful = sum(1 for r in sent_results if r["success"])
    print(f"\n✅ Sent {successful}/{len(sent_results)} email(s) successfully")

    return state


# Agent 7: Update tracker with follow-up results
def update_tracker_node(state: FollowupState) -> FollowupState:
    """Update tracking JSON with follow-up results"""
    print("\n💾 Agent 7: Updating follow-up tracker...")

    updated_count = 0

    for result in state.get("sent_emails", []):
        if result.get("success"):
            success = update_followup(
                document_id=result["document_id"],
                followup_date=datetime.now().isoformat()
            )
            if success:
                updated_count += 1

    print(f"✅ Updated tracker for {updated_count} document(s)")

    return state


# Create the follow-up workflow graph
def create_followup_workflow() -> StateGraph:
    """Create and configure the follow-up workflow graph"""

    # Create workflow
    workflow = StateGraph(FollowupState)

    # Add nodes (agents)
    workflow.add_node("load_tracker", load_tracker_node)
    workflow.add_node("status_check", status_check_node)
    workflow.add_node("filter", filter_documents_node)
    workflow.add_node("draft_emails", draft_emails_node)
    workflow.add_node("send_teams", send_teams_node)
    workflow.add_node("send_emails", send_emails_node)
    workflow.add_node("update_tracker", update_tracker_node)

    # Add edges (workflow flow)
    workflow.set_entry_point("load_tracker")
    workflow.add_edge("load_tracker", "status_check")
    workflow.add_edge("status_check", "filter")
    workflow.add_edge("filter", "draft_emails")
    workflow.add_edge("draft_emails", "send_teams")
    workflow.add_edge("send_teams", "send_emails")
    workflow.add_edge("send_emails", "update_tracker")
    workflow.add_edge("update_tracker", END)

    return workflow.compile()


def run_followup_workflow():
    """Main entry point to run the follow-up workflow"""
    print("=" * 60)
    print("🚀 PandaDoc Follow-up Workflow Starting")
    print("=" * 60)
    print(f"⏰ Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Create workflow
    app = create_followup_workflow()

    # Initialize state
    initial_state = {
        "pending_documents": [],
        "pandadoc_statuses": {},
        "filtered_documents": [],
        "drafted_emails": [],
        "sent_teams": [],
        "sent_emails": [],
        "error": None
    }

    # Run workflow
    try:
        final_state = app.invoke(initial_state)

        print("\n" + "=" * 60)
        print("✅ Follow-up Workflow Complete")
        print("=" * 60)

        # Summary
        teams_count = len([r for r in final_state.get("sent_teams", []) if r.get("success")])
        email_count = len([r for r in final_state.get("sent_emails", []) if r.get("success")])
        print(f"\n📊 Summary:")
        print(f"  - Pending documents checked: {len(final_state.get('pending_documents', []))}")
        print(f"  - Documents needing follow-up: {len(final_state.get('filtered_documents', []))}")
        print(f"  - Emails drafted: {len(final_state.get('drafted_emails', []))}")
        print(f"  - Teams notifications sent: {teams_count}")
        print(f"  - Emails sent successfully: {email_count}")

        if final_state.get("error"):
            print(f"\n⚠️ Error: {final_state['error']}")

    except Exception as e:
        print(f"\n❌ Workflow error: {str(e)}")


if __name__ == "__main__":
    run_followup_workflow()
