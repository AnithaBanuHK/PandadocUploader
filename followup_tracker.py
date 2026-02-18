"""
Document Tracking System for PandaDoc Follow-up Workflow
Tracks documents sent via the main workflow for automated follow-ups
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Default tracker file path
DEFAULT_TRACKER_PATH = os.path.expanduser("~/pandadoc_tracking.json")
TRACKER_PATH = os.path.expanduser(os.getenv("FOLLOWUP_TRACKER_PATH", DEFAULT_TRACKER_PATH))


def load_tracker() -> Dict:
    """Load tracker data from JSON file"""
    if not os.path.exists(TRACKER_PATH):
        return {"documents": {}}

    try:
        with open(TRACKER_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading tracker: {str(e)}")
        return {"documents": {}}


def save_tracker(data: Dict) -> bool:
    """Save tracker data to JSON file"""
    try:
        with open(TRACKER_PATH, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving tracker: {str(e)}")
        return False


def add_document(
    document_id: str,
    name: str,
    sent_date: str,
    recipients: List[Dict]
) -> bool:
    """
    Add a new document to tracking

    Args:
        document_id: PandaDoc document ID
        name: Document name
        sent_date: ISO format timestamp when document was sent
        recipients: List of recipient dicts with email, first_name, last_name, role

    Returns:
        True if successful, False otherwise
    """
    tracker = load_tracker()

    tracker["documents"][document_id] = {
        "document_id": document_id,
        "document_name": name,
        "sent_date": sent_date,
        "recipients": recipients,
        "last_followup_date": sent_date,  # Initialize with sent date
        "followup_count": 0,
        "status": "pending"
    }

    success = save_tracker(tracker)
    if success:
        print(f"📊 Added document '{name}' ({document_id}) to tracker")
    return success


def get_pending_documents() -> List[Dict]:
    """Get all documents with status='pending'"""
    tracker = load_tracker()
    pending = [
        doc for doc in tracker["documents"].values()
        if doc["status"] == "pending"
    ]
    return pending


def update_followup(document_id: str, followup_date: str) -> bool:
    """
    Update last follow-up date and increment count

    Args:
        document_id: PandaDoc document ID
        followup_date: ISO format timestamp of follow-up

    Returns:
        True if successful, False otherwise
    """
    tracker = load_tracker()

    if document_id not in tracker["documents"]:
        print(f"⚠️ Document {document_id} not found in tracker")
        return False

    doc = tracker["documents"][document_id]
    doc["last_followup_date"] = followup_date
    doc["followup_count"] = doc.get("followup_count", 0) + 1

    success = save_tracker(tracker)
    if success:
        print(f"💾 Updated follow-up for document {document_id} (count: {doc['followup_count']})")
    return success


def mark_completed(document_id: str) -> bool:
    """
    Mark a document as completed (all recipients have signed)

    Args:
        document_id: PandaDoc document ID

    Returns:
        True if successful, False otherwise
    """
    tracker = load_tracker()

    if document_id not in tracker["documents"]:
        print(f"⚠️ Document {document_id} not found in tracker")
        return False

    tracker["documents"][document_id]["status"] = "completed"
    tracker["documents"][document_id]["completed_date"] = datetime.now().isoformat()

    success = save_tracker(tracker)
    if success:
        doc_name = tracker["documents"][document_id]["document_name"]
        print(f"✅ Marked document '{doc_name}' ({document_id}) as completed")
    return success


def get_document_status(document_id: str) -> Optional[str]:
    """Get status of a specific document"""
    tracker = load_tracker()
    if document_id in tracker["documents"]:
        return tracker["documents"][document_id]["status"]
    return None


def get_tracker_stats() -> Dict:
    """Get summary statistics from tracker"""
    tracker = load_tracker()
    docs = tracker["documents"]

    return {
        "total_documents": len(docs),
        "pending": sum(1 for d in docs.values() if d["status"] == "pending"),
        "completed": sum(1 for d in docs.values() if d["status"] == "completed"),
        "total_followups_sent": sum(d.get("followup_count", 0) for d in docs.values())
    }


if __name__ == "__main__":
    # Test the tracker
    print("📋 Document Tracker Test\n")

    # Test adding a document
    test_doc_id = "test_doc_123"
    test_recipients = [
        {
            "email": "anithabanu2021@gmail.com",
            "first_name": "Test",
            "last_name": "User",
            "role": "Signer"
        }
    ]

    add_document(
        document_id=test_doc_id,
        name="Test Document",
        sent_date=datetime.now().isoformat(),
        recipients=test_recipients
    )

    # Test getting pending documents
    pending = get_pending_documents()
    print(f"\n📬 Pending documents: {len(pending)}")

    # Test stats
    stats = get_tracker_stats()
    print(f"\n📊 Tracker Stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print(f"\n✅ Tracker test complete. Data saved to: {TRACKER_PATH}")
