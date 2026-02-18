# PandaDoc Multi-Agent Document Management System

A Streamlit-based document management system that uses a multi-agent AI workflow (LangGraph) to extract signer information from PDFs, add signature fields, upload documents to PandaDoc, and send them for signing. Includes an automated follow-up system for unsigned documents.

## Architecture

### Main Workflow (6-Agent Pipeline)

```
PDF Upload → Extract → Validate → Add Form Fields → Upload → Assign Fields → Send
```

| Agent | Description |
|-------|-------------|
| **Extraction** | Extracts recipient/signer info from PDF tables using Gemini AI |
| **Validation** | Validates email format and required fields (Python-based) |
| **Form Fields** | Uses AI to detect signature positions and adds PDF form widgets (PyMuPDF) |
| **Upload** | Uploads the modified PDF to PandaDoc via API |
| **Field Assignment** | Assigns signature fields to recipients via PandaDoc API |
| **Send** | Sends the document to all recipients for signature |

### Follow-up Workflow (7-Agent Pipeline)

```
Load Tracker → Check Status → Filter → Draft Emails → Send Teams → Send Emails → Update Tracker
```

| Agent | Description |
|-------|-------------|
| **Load Tracker** | Reads pending documents from the tracking JSON |
| **Status Check** | Queries PandaDoc API for current document status |
| **Filter** | Identifies all documents with unsigned recipients |
| **Draft Emails** | Uses Gemini AI to draft personalized follow-up emails |
| **Send Teams** | Sends brief chat-style reminders to a Teams channel via webhook |
| **Send Emails** | Sends emails via Gmail SMTP with retry logic |
| **Update Tracker** | Updates the tracking JSON with follow-up results |

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Authenticate with Google Cloud** (for Vertex AI)
   ```bash
   gcloud auth application-default login
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set the required values:

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `PANDADOC_API_KEY` | Yes | Your PandaDoc API key |
   | `PANDADOC_API_URL` | Yes | PandaDoc API endpoint (default: `https://api.pandadoc.com/public/v1/documents`) |
   | `VERTEX_PROJECT` | No | Google Cloud project ID (default: `aac-dw-dev`) |
   | `VERTEX_LOCATION` | No | Vertex AI region (default: `europe-west1`) |
   | `VERTEX_MODEL_NAME` | No | Gemini model (default: `gemini-2.0-flash-lite`) |
   | `GMAIL_EMAIL` | For follow-ups | Gmail address for sending follow-up emails |
   | `GMAIL_APP_PASSWORD` | For follow-ups | Gmail App Password ([generate here](https://myaccount.google.com/apppasswords)) |
   | `TEAMS_WEBHOOK_URL` | For follow-ups | Teams Incoming Webhook URL (see [Teams setup](#teams-webhook-setup)) |
   | `FOLLOWUP_TRACKER_PATH` | No | Path to tracking JSON (default: `~/pandadoc_tracking.json`) |
   | `FOLLOWUP_TIME` | No | Daily follow-up time in HH:MM (default: `09:00`) |

4. **Run the application**
   ```bash
   streamlit run pandadoc_ui.py
   ```

## Usage

### Main Workflow (Streamlit UI)

1. Enter the document name
2. Upload a PDF containing approver/signer information in a table
3. Click **"Process Document"** - the 6-agent workflow will:
   - Extract all approver details from the PDF table using AI
   - Validate the extracted information
   - Analyze layout and add signature fields to the PDF
   - Upload to PandaDoc
   - Assign fields to recipients
   - Send the document to all recipients
4. Review the results and status of each agent

### Follow-up Workflow

Run manually:
```bash
python followup_workflow.py
```

Run on a daily schedule:
```bash
python followup_scheduler.py
```

The scheduler runs the follow-up workflow at the configured time (default: 09:00 daily) and also runs once immediately on startup.

The follow-up workflow picks up **all** pending documents with unsigned recipients whenever it runs. You control the scheduling.

## Files

| File | Description |
|------|-------------|
| `pandadoc_ui.py` | Main Streamlit application (primary entry point) |
| `workflow.py` | Multi-agent workflow orchestration (core business logic) |
| `followup_workflow.py` | Follow-up multi-agent workflow for unsigned documents |
| `followup_tracker.py` | Document tracking system (JSON-based persistence) |
| `followup_scheduler.py` | Daily scheduler for the follow-up workflow |
| `email_sender.py` | Gmail SMTP email utility with retry logic |
| `teams_sender.py` | Microsoft Teams webhook notification utility |
| `pandadocupl.py` | Legacy CLI script (prototype) |
| `.env` | Environment variables (not tracked in git) |
| `requirements.txt` | Python dependencies |

## Document Tracking

When a document is sent via the main workflow, it is automatically added to the tracking JSON file (`~/pandadoc_tracking.json` by default). The follow-up workflow reads this file to determine which documents need follow-up emails.

Tracked data per document:
- Document ID and name
- Sent date and recipients
- Last follow-up date and count
- Status (`pending` or `completed`)

## Teams Webhook Setup

1. In your Teams channel, click the **"..."** menu next to the channel name
2. Select **"Connectors"** (or **"Manage channel"** → **"Connectors"**)
3. Find **"Incoming Webhook"** and click **"Configure"**
4. Give it a name (e.g., "PandaDoc Reminders") and optionally upload an icon
5. Click **"Create"** and copy the webhook URL
6. Add the URL to your `.env` file:
   ```
   TEAMS_WEBHOOK_URL=https://your-org.webhook.office.com/webhookb2/...
   ```

You can test it with:
```bash
python teams_sender.py
```

## Security

- **Never commit the `.env` file** - it contains API keys and credentials
- The `.gitignore` file is configured to exclude `.env` automatically
- Gmail requires an **App Password** (not your regular password) - enable 2-Step Verification first
