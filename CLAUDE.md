# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Streamlit-based document management system that uses a multi-agent AI workflow (LangGraph) to extract signer information from PDFs, validate the data, and upload documents to PandaDoc. The system uses Google Vertex AI Gemini 1.5 Flash for intelligent document processing.

## Development Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Then edit .env and add your PANDADOC_API_KEY

# Authenticate with Google Cloud (for Vertex AI)
gcloud auth application-default login
```

### Running the Application
```bash
# Main Streamlit UI (primary entry point)
streamlit run pandadoc_ui.py

# Legacy CLI script (prototype, hardcoded values)
python pandadocupl.py
```

### Environment Variables
- `PANDADOC_API_KEY`: Required for document uploads
- `PANDADOC_API_URL`: API endpoint (default: https://api.pandadoc.com/public/v1/documents)
- `VERTEX_PROJECT`: Google Cloud project ID (default: aac-dw-dev)
- `VERTEX_LOCATION`: Vertex AI region (default: europe-west1)
- `VERTEX_MODEL_NAME`: Gemini model to use (default: gemini-2.0-flash-lite)

## Architecture

### Multi-Agent Workflow Pattern (LangGraph)

The application implements a **sequential three-agent workflow** with conditional routing:

```
PDF Upload → Extract Agent → Validate Agent → (conditional) → Upload Agent → Response
```

**Workflow Implementation** ([workflow.py](workflow.py)):
- Built on LangGraph's `StateGraph` pattern
- State schema defined as `WorkflowState` TypedDict with fields: `pdf_file`, `pdf_text`, `document_name`, `extracted_data`, `validation_status`, `upload_status`, `error`
- Entry point: `run_workflow(pdf_file, document_name)` at [workflow.py:274](workflow.py#L274)

### Agent Nodes

**Agent 1 - Extraction** ([workflow.py:40](workflow.py#L40)):
- Extracts text from PDF using pdfplumber
- Uses Gemini to extract ALL recipients/signers/approvers from the document
- Specifically searches for:
  - Approver/Approvers sections
  - Tables containing names and email addresses
  - All people mentioned as recipients, signers, or approvers
- Extracts: email, first_name, last_name, and role for each person
- Handles markdown code blocks in LLM responses
- Returns array of recipients (supports multiple people)

**Agent 2 - Validation** ([workflow.py:122](workflow.py#L122)):
- Uses **simple Python validation** (not LLM-based) for reliability
- Validates ALL extracted recipients for completeness and format
- Checks: email contains "@" and domain, first_name is not empty
- Last name and role are optional (not validated)
- Returns `{is_valid: bool, errors: list}` (valid only if ALL recipients are valid)

**Agent 3 - Upload** ([workflow.py:161](workflow.py#L161)):
- Uploads to PandaDoc API using multipart form data
- Sends ALL validated recipients in the recipients array
- Each recipient includes their role (Signer, Approver, or CC)
- Only executes if validation passes (see conditional routing below)
- Expects 201 status code for success

### Conditional Routing

The `should_continue_to_upload()` function ([workflow.py:235](workflow.py#L235)) implements conditional flow:
- If `validation_status.is_valid == true` → routes to upload agent
- If validation fails → routes to END (skips upload)

This prevents invalid data from being uploaded to PandaDoc.

### State Management

- **Immutable state pattern**: Each agent node receives state, returns modified state
- **Error accumulation**: Errors stored in state, propagated throughout workflow
- **Single source of truth**: All results accumulated in final state dictionary

### UI Architecture ([pandadoc_ui.py](pandadoc_ui.py))

- **Real-time status updates**: Empty placeholders updated during workflow execution
- **Editable results**: Users can modify extracted data post-processing before upload
- **Three-column monitoring**: Shows status of Extraction → Validation → Upload agents
- **Environment validation**: Checks for .env file and required keys on startup (lines 17-34)

### LLM Response Handling

Both extraction and validation agents include robust JSON parsing ([workflow.py:79-83](workflow.py#L79-L83)):
```python
# Remove markdown code blocks if present
if "```json" in response_text:
    response_text = response_text.split("```json")[1].split("```")[0].strip()
elif "```" in response_text:
    response_text = response_text.split("```")[1].split("```")[0].strip()
```

This handles cases where Gemini wraps JSON in markdown code blocks.

## Key Files

- **[pandadoc_ui.py](pandadoc_ui.py)** - Main Streamlit application (primary entry point)
- **[workflow.py](workflow.py)** - Multi-agent workflow orchestration (core business logic)
- **[pandadocupl.py](pandadocupl.py)** - Legacy CLI script (prototype with hardcoded values)

## Important Notes

- **No test framework**: No pytest or unittest configured
- **Vertex AI initialization**: Explicitly initializes with project and location at module load (workflow.py lines 16-19)
- **Google Cloud authentication required**: Run `gcloud auth application-default login` for Vertex AI access
- **API security**: Never commit `.env` file (contains API keys)
- **Temperature=0**: All LLM calls use temperature=0 for deterministic output
- **Multiple recipients**: Supports extracting and uploading multiple recipients/signers/approvers per document
- **Model flexibility**: Uses `gemini-2.0-flash-lite` by default but configurable via `VERTEX_MODEL_NAME`
