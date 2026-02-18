"""
Multi-Agent Workflow for PandaDoc Document Upload
Uses LangGraph with Vertex AI Gemini for intelligent document processing
"""

import os
import json
import time
from datetime import datetime
from typing import TypedDict
import vertexai
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, END
import pdfplumber
import requests
import fitz  # PyMuPDF

# Initialize Vertex AI with project and location
vertexai.init(
    project=os.getenv("VERTEX_PROJECT", "aac-dw-dev"),
    location=os.getenv("VERTEX_LOCATION", "europe-west1")
)


class WorkflowState(TypedDict):
    """State schema for the multi-agent workflow"""
    pdf_file: bytes
    pdf_text: str
    document_name: str
    extracted_data: list  # Changed from dict to list to support multiple recipients
    validation_status: dict
    upload_status: dict
    field_placement_status: dict  # Status of placing signature fields
    send_status: dict  # Status of sending the document
    error: str | None


def extract_pdf_text(pdf_file: bytes) -> str:
    """Extract text from PDF file"""
    try:
        import io
        with pdfplumber.open(io.BytesIO(pdf_file)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
            return text
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"


def extraction_node(state: WorkflowState) -> WorkflowState:
    """
    Agent 1: Extract signer information from PDF using Gemini
    """
    print("🔍 Extraction Agent: Processing PDF...")
    
    # Extract text from PDF
    pdf_text = extract_pdf_text(state["pdf_file"])
    state["pdf_text"] = pdf_text
    
    # Initialize Vertex AI Gemini
    llm = ChatVertexAI(
        model=os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-lite"),
        temperature=0,
    )
    
    # Create extraction prompt
    extraction_prompt = f"""You are a document processing AI. Extract ALL recipients/signers/approvers from this document.

IMPORTANT INSTRUCTIONS:
1. Look specifically for an "APPROVER" or "APPROVERS" or "APPROVAL" section in the document mostly at the end of document section.
2. Check for any TABLES that contain names and email addresses of approvers/signers
3. Extract ALL people mentioned as recipients, signers, or approvers
4. For each person, extract their email, first name, and last name only from the table section.
5. Do not extract any other information from the document.
6. Do not extract any other name or email mentioned anywhere else from the document.
7. If you cannot find any recipients, return an empty array []. Return ONLY the JSON array, no additional text or explanation.
8. the firstname is usually the first word in the name.
9. the lastname is usually the last word in the name.
10. The role is always "Signer" for all recipients (PandaDoc requires unique roles, so we use Signer which allows multiples).
11. The email is usually the email address of the person from the table section.
12. Do not make any changes to the email address of the person from the table section.
13. Do not make any changes to the name of the person from the table section.
14. If the name is a single name, then the first name is the name and the last name is empty.

Document text:
{pdf_text}

Please return a JSON array containing ALL recipients found in the document. Each recipient should have:
- email: the person's email address
- first_name: the person's first name
- last_name: the person's last name
- role: always set to "Signer" (PandaDoc allows multiple signers)

If you cannot find any recipients, return an empty array []. Return ONLY the JSON array, no additional text or explanation.

Example response format:
[
  {{"email": "john@example.com", "first_name": "John", "last_name": "Doe", "role": "Signer"}},
  {{"email": "jane@example.com", "first_name": "Jane", "last_name": "Smith", "role": "Signer"}}
]
"""
    
    try:
        # Get response from Gemini
        response = llm.invoke(extraction_prompt)
        response_text = response.content.strip()

        # Try to parse JSON from response
        # Remove markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        extracted_data = json.loads(response_text)

        # Ensure it's a list
        if not isinstance(extracted_data, list):
            extracted_data = [extracted_data]

        state["extracted_data"] = extracted_data
        print(f"✅ Extracted {len(extracted_data)} recipient(s): {extracted_data}")

    except Exception as e:
        state["error"] = f"Extraction failed: {str(e)}"
        state["extracted_data"] = []
        print(f"❌ Extraction error: {str(e)}")
    
    return state


def validation_node(state: WorkflowState) -> WorkflowState:
    """
    Agent 2: Validate extracted data using simple Python validation
    """
    print("✅ Validation Agent: Checking extracted data...")

    extracted_data = state.get("extracted_data", [])
    errors = []

    # Validate each recipient using simple Python logic
    for i, recipient in enumerate(extracted_data, 1):
        # Check email format
        email = recipient.get("email", "")
        if not email or "@" not in email or "." not in email.split("@")[-1]:
            errors.append(f"Recipient {i}: Invalid email format")

        # Check first name (must not be empty)
        first_name = recipient.get("first_name", "").strip()
        if not first_name:
            errors.append(f"Recipient {i}: First name is empty")

        # Last name is optional - no validation needed
        # Role is optional - no validation needed

    # Determine if validation passed
    is_valid = len(errors) == 0

    state["validation_status"] = {
        "is_valid": is_valid,
        "errors": errors
    }

    if is_valid:
        print(f"✅ Validation passed for {len(extracted_data)} recipient(s)")
    else:
        print(f"❌ Validation failed: {errors}")

    return state


def add_form_fields_node(state: WorkflowState) -> WorkflowState:
    """
    Agent: Add PDF form fields to the document using AI-detected coordinates
    """
    print("📝 Form Fields Agent: Adding signature fields to PDF...")

    import io

    pdf_bytes = state["pdf_file"]
    pdf_text = state.get("pdf_text", "")
    extracted_data = state.get("extracted_data", [])

    if not extracted_data:
        print("⚠️ No recipients found, skipping form field addition")
        return state

    # Initialize Vertex AI Gemini for layout analysis
    llm = ChatVertexAI(
        model=os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-lite"),
        temperature=0,
    )

    # Analyze PDF to find signature column positions
    analysis_prompt = f"""You are a PDF layout analyzer. Analyze this document and find the "Signature" column in the approver table.

Document text:
{pdf_text}

Number of recipients: {len(extracted_data)}

Task: Determine the coordinates for placing signature fields in the "Signature" column.

IMPORTANT: PDF coordinate system:
- Origin (0,0) is at BOTTOM-LEFT corner
- X increases from left to right (0 to ~595 for A4)
- Y increases from BOTTOM to TOP (0 to ~842 for A4)
- So a field near the top of the page has a HIGH y value (e.g., 700)
- A field near the bottom has a LOW y value (e.g., 100)

Return a JSON object with:
- page: page number (0-indexed) where the table is
- signature_column_x: X coordinate of the signature column left edge (in points, typically 400-550)
- first_row_y: Y coordinate of the first signature row BOTTOM edge (in points, measured from bottom of page)
- row_height: spacing between rows (in points, typically 20-30)

Example response:
{{
  "page": 0,
  "signature_column_x": 450,
  "first_row_y": 400,
  "row_height": 25
}}

Return ONLY the JSON object, no explanation.
"""

    try:
        # Get layout analysis from Gemini
        print("🤖 Asking AI to analyze PDF layout...")
        response = llm.invoke(analysis_prompt)
        response_text = response.content.strip()

        print(f"\n🔍 DEBUG - AI Raw Response:\n{response_text}\n")

        # Parse JSON response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        layout_data = json.loads(response_text)
        print(f"📍 Layout detected: Page {layout_data.get('page')}, Column X:{layout_data.get('signature_column_x')}")

        # Open PDF with PyMuPDF
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        print(f"📄 Original PDF has {len(pdf_document)} page(s)")

        page_num = layout_data.get("page", 0)
        x = layout_data.get("signature_column_x", 450)
        first_y = layout_data.get("first_row_y", 400)
        row_height = layout_data.get("row_height", 25)

        page = pdf_document[page_num]

        print(f"📋 Adding {len(extracted_data)} signature field(s) to PDF...")

        # Assign roles to recipients (same logic as upload_node)
        role_sequence = ["Signer", "Approver", "CC"]

        for i, recipient in enumerate(extracted_data):
            # Assign role (same logic as upload_node)
            if i < len(role_sequence):
                role = role_sequence[i]
            else:
                role = f"CC_{i - len(role_sequence) + 2}"  # CC_2, CC_3, etc.

            # Calculate position for this signature field
            y = first_y - (i * row_height)  # Y decreases as we go down in PDF coords

            # Create PDF form widget (PandaDoc will recognize these!)
            widget_rect = fitz.Rect(x, y, x + 120, y + 20)

            widget = fitz.Widget()
            widget.field_name = f"Signature_{i+1}"  # Simple sequential names
            widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
            widget.rect = widget_rect
            widget.field_flags = fitz.PDF_FIELD_IS_READ_ONLY

            page.add_widget(widget)

            print(f"  ✅ Added form field 'Signature_{i+1}' for {recipient.get('first_name')} ({role}) at (x={x}, y={y})")

        # Add a new blank page at the end for signature placement
        print(f"\n📄 Adding new blank page for signatures...")
        new_page = pdf_document.new_page(width=612, height=792)  # Standard US Letter size
        new_page_index = len(pdf_document) - 1
        print(f"✅ Added new blank page at index {new_page_index} (total pages: {len(pdf_document)})")
        print(f"   Signature fields will be placed on page {new_page_index} (0-indexed)")

        # Save modified PDF to bytes
        modified_pdf_bytes = pdf_document.write()

        # Verify widgets were added
        print(f"\n🔍 Verifying widgets in modified PDF...")
        verify_doc = fitz.open(stream=modified_pdf_bytes, filetype="pdf")
        total_widgets = 0
        for page_num in range(len(verify_doc)):
            page_widgets = list(verify_doc[page_num].widgets())  # Convert generator to list
            if page_widgets:
                total_widgets += len(page_widgets)
                print(f"  Page {page_num}: {len(page_widgets)} widget(s)")
        verify_doc.close()
        print(f"  Total widgets in PDF: {total_widgets}\n")

        pdf_document.close()

        # Update state with modified PDF
        state["pdf_file"] = modified_pdf_bytes
        state["field_placement_status"] = {
            "success": True,
            "fields_added": len(extracted_data),
            "method": "pdf_widgets"
        }

        print(f"✅ Successfully added {len(extracted_data)} PDF form widget(s)!")

    except Exception as e:
        state["field_placement_status"] = {
            "success": False,
            "error": f"Form field addition error: {str(e)}"
        }
        print(f"❌ Form field addition error: {str(e)}")
        # Continue with original PDF if field addition fails

    return state


def field_placement_node(state: WorkflowState) -> WorkflowState:
    """
    Agent: Analyze PDF and place signature fields using AI
    """
    print("🎯 Field Placement Agent: Analyzing document layout...")

    api_key = os.getenv("PANDADOC_API_KEY")
    api_url = os.getenv("PANDADOC_API_URL")

    if not api_key:
        state["field_placement_status"] = {
            "success": False,
            "error": "Missing API key"
        }
        return state

    document_id = state.get("upload_status", {}).get("document_id")
    if not document_id:
        state["field_placement_status"] = {
            "success": False,
            "error": "No document ID from upload"
        }
        return state

    # Wait for document to be ready (PandaDoc processes documents asynchronously)
    print("⏳ Waiting for document to be ready...")
    max_retries = 30  # 30 seconds max wait
    retry_count = 0
    document_ready = False

    headers = {
        "Authorization": f"API-Key {api_key}",
        "Content-Type": "application/json"
    }

    while retry_count < max_retries and not document_ready:
        try:
            # Check document status
            status_url = f"{api_url}/{document_id}"
            status_response = requests.get(status_url, headers=headers)

            if status_response.status_code == 200:
                doc_status = status_response.json().get("status")
                print(f"  Document status: {doc_status}")

                if doc_status == "document.draft":
                    document_ready = True
                    print("✅ Document is ready for field placement!")
                elif doc_status in ["document.uploaded", "document.processing"]:
                    # Still processing, wait and retry
                    time.sleep(1)
                    retry_count += 1
                else:
                    # Unexpected status
                    state["field_placement_status"] = {
                        "success": False,
                        "error": f"Unexpected document status: {doc_status}"
                    }
                    return state
            else:
                state["field_placement_status"] = {
                    "success": False,
                    "error": f"Failed to check document status: {status_response.status_code}"
                }
                return state

        except Exception as e:
            state["field_placement_status"] = {
                "success": False,
                "error": f"Error checking document status: {str(e)}"
            }
            return state

    if not document_ready:
        state["field_placement_status"] = {
            "success": False,
            "error": "Timeout waiting for document to be ready (30 seconds)"
        }
        return state

    extracted_data = state.get("extracted_data", [])
    pdf_text = state.get("pdf_text", "")

    # Initialize Vertex AI Gemini for layout analysis
    llm = ChatVertexAI(
        model=os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-lite"),
        temperature=0,
    )

    # Analyze PDF to find signature column positions
    analysis_prompt = f"""You are a PDF layout analyzer. Analyze this document and find the "Signature" column in the approver table.

Document text:
{pdf_text}

Number of recipients: {len(extracted_data)}

Task: Determine the coordinates for placing signature fields in the "Signature" column.

Return a JSON object with:
- page: page number (0-indexed) where the table is
- signature_column_x: X coordinate of the signature column (in points, 0-792 for standard page)
- first_row_y: Y coordinate of the first signature row (in points, 0-612 for standard page)
- row_height: spacing between rows (in points, typically 20-30)

Example response:
{{
  "page": 0,
  "signature_column_x": 450,
  "first_row_y": 400,
  "row_height": 25
}}

Return ONLY the JSON object, no explanation.
"""

    try:
        # Get layout analysis from Gemini
        print("🤖 Asking AI to analyze PDF layout...")
        response = llm.invoke(analysis_prompt)
        response_text = response.content.strip()

        print(f"\n🔍 DEBUG - AI Raw Response:\n{response_text}\n")

        # Parse JSON response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        layout_data = json.loads(response_text)
        print(f"📍 Layout detected: Page {layout_data.get('page')}, Column X:{layout_data.get('signature_column_x')}")
        print(f"🔍 DEBUG - Parsed Layout Data: {json.dumps(layout_data, indent=2)}\n")

        # Prepare fields for each recipient
        fields_url = f"{api_url}/{document_id}/fields"
        fields = []

        page = layout_data.get("page", 0)
        x = layout_data.get("signature_column_x", 450)
        first_y = layout_data.get("first_row_y", 400)
        row_height = layout_data.get("row_height", 25)

        print(f"📋 Creating signature fields for {len(extracted_data)} recipient(s)...")
        print(f"🔍 DEBUG - Recipients: {json.dumps(extracted_data, indent=2)}\n")

        for i, recipient in enumerate(extracted_data):
            y = first_y + (i * row_height)

            field = {
                "name": f"signature_{i+1}",
                "title": "Signature",
                "type": "signature",
                "required": True,
                "recipient": recipient.get("email"),
                "layout": {
                    "merge_field": f"signature_{i+1}",
                    "page": page,
                    "position": {
                        "offset_x": x,
                        "offset_y": y,
                        "anchor_point": 0
                    },
                    "style": {
                        "width": 120,
                        "height": 20
                    }
                }
            }
            fields.append(field)
            print(f"  → Field {i+1}: {recipient.get('first_name')} ({recipient.get('email')}) at page={page}, x={x}, y={y}")

        # Add fields to document via PandaDoc API
        headers = {
            "Authorization": f"API-Key {api_key}",
            "Content-Type": "application/json"
        }

        payload = {"fields": fields}

        print(f"\n📤 Sending fields to PandaDoc API...")
        print(f"🔍 DEBUG - API URL: {fields_url}")
        print(f"🔍 DEBUG - Payload being sent:")
        print(json.dumps(payload, indent=2))
        print()

        field_response = requests.post(fields_url, headers=headers, json=payload)

        print(f"📥 Response Status: {field_response.status_code}")
        print(f"🔍 DEBUG - Response Body: {field_response.text}\n")

        if field_response.status_code in [200, 201]:
            state["field_placement_status"] = {
                "success": True,
                "fields_added": len(fields),
                "response": field_response.json() if field_response.text else {}
            }
            print(f"✅ Added {len(fields)} signature fields successfully!")
        else:
            state["field_placement_status"] = {
                "success": False,
                "error": f"Field placement failed: {field_response.status_code} - {field_response.text}"
            }
            print(f"❌ Field placement failed: {field_response.status_code}")

    except Exception as e:
        state["field_placement_status"] = {
            "success": False,
            "error": f"Field placement error: {str(e)}"
        }
        print(f"❌ Field placement error: {str(e)}")

    return state


def upload_node(state: WorkflowState) -> WorkflowState:
    """
    Agent 3: Upload document to PandaDoc API
    """
    print("📤 Upload Agent: Uploading to PandaDoc...")
    
    # Get API credentials from environment
    api_key = os.getenv("PANDADOC_API_KEY")
    api_url = os.getenv("PANDADOC_API_URL")
    
    if not api_key or not api_url:
        state["upload_status"] = {
            "success": False,
            "error": "Missing API configuration (PANDADOC_API_KEY or PANDADOC_API_URL)"
        }
        return state
    
    extracted_data = state.get("extracted_data", [])

    # Prepare headers
    headers = {
        "Authorization": f"API-Key {api_key}"
    }

    # Prepare recipients list from extracted data
    # PandaDoc requires UNIQUE roles for each recipient (no duplicates allowed)
    # Assign different roles to each person
    role_sequence = ["Signer", "Approver", "CC"]

    recipients = []
    for i, person in enumerate(extracted_data):
        # Cycle through available roles, or use numbered roles if we run out
        if i < len(role_sequence):
            role = role_sequence[i]
        else:
            # For additional recipients beyond the 3 standard roles, use numbered CC roles
            role = f"CC {i - len(role_sequence) + 2}"

        recipients.append({
            "email": person.get("email"),
            "first_name": person.get("first_name"),
            "last_name": person.get("last_name"),
            "role": role
        })
        print(f"  → Assigned {person.get('first_name')} ({person.get('email')}) as '{role}'")

    print(f"\n📧 Recipients being sent to PandaDoc:")
    for i, recipient in enumerate(recipients, 1):
        print(f"  {i}. {recipient.get('email')} - {recipient.get('first_name')} {recipient.get('last_name')} [{recipient.get('role')}]")
    print()

    # Prepare payload
    payload = {
        "name": state.get("document_name", "Untitled Document"),
        "recipients": recipients
        # Note: parse_form_fields removed - recipients can place signatures manually or use PandaDoc auto-placement
    }
    
    # Prepare files
    files = {
        "file": (
            f"{state.get('document_name', 'document')}.pdf",
            state["pdf_file"],
            "application/pdf"
        ),
        "data": (None, json.dumps(payload), "application/json")
    }
    
    try:
        # Step 1: Upload/Create the document
        response = requests.post(api_url, headers=headers, files=files)

        if response.status_code == 201:
            document_data = response.json()
            document_id = document_data.get("id")

            state["upload_status"] = {
                "success": True,
                "response": document_data,
                "document_id": document_id
            }
            print(f"✅ Document uploaded successfully! ID: {document_id}")
        else:
            state["upload_status"] = {
                "success": False,
                "error": f"Upload failed with status {response.status_code}: {response.text}"
            }
            state["send_status"] = {"success": False, "error": "Upload failed, send skipped"}
            print(f"❌ Upload failed: {response.status_code}")

    except Exception as e:
        state["upload_status"] = {
            "success": False,
            "error": f"Upload error: {str(e)}"
        }
        state["send_status"] = {"success": False, "error": "Upload failed, send skipped"}
        print(f"❌ Upload error: {str(e)}")

    return state


def assign_fields_node(state: WorkflowState) -> WorkflowState:
    """
    Agent: Assign detected PDF form fields to recipients
    """
    print("📋 Field Assignment Agent: Assigning fields to recipients...")

    api_key = os.getenv("PANDADOC_API_KEY")
    api_url = os.getenv("PANDADOC_API_URL")
    document_id = state.get("upload_status", {}).get("document_id")

    if not document_id:
        state["field_placement_status"] = {
            "success": False,
            "error": "No document ID available"
        }
        return state

    extracted_data = state.get("extracted_data", [])
    role_sequence = ["Signer", "Approver", "CC"]

    # Assign roles (same logic as before)
    recipient_roles = []
    for i, recipient in enumerate(extracted_data):
        if i < len(role_sequence):
            role = role_sequence[i]
        else:
            role = f"CC {i - len(role_sequence) + 2}"
        recipient_roles.append(role)

    # Wait for document to be ready (PandaDoc processes documents asynchronously)
    print("⏳ Waiting for document to be ready...")
    max_retries = 30
    retry_count = 0
    document_ready = False
    recipients_data = []  # Will be populated when document is ready

    status_headers = {"Authorization": f"API-Key {api_key}"}

    while retry_count < max_retries and not document_ready:
        try:
            # Use /details endpoint to get full document info including recipients
            status_url = f"{api_url}/{document_id}/details"
            print(f"🔍 DEBUG - Fetching: {status_url}")
            status_response = requests.get(status_url, headers=status_headers)
            print(f"🔍 DEBUG - Response status: {status_response.status_code}")

            if status_response.status_code == 200:
                doc_status = status_response.json().get("status")
                print(f"  Document status: {doc_status}")

                if doc_status == "document.draft":
                    document_ready = True
                    # Extract recipient UUIDs for field assignment
                    document_data = status_response.json()
                    recipients_data = document_data.get("recipients", [])
                    print("✅ Document is ready for field assignment!")
                    print(f"🔍 DEBUG - Document data keys: {list(document_data.keys())}")
                    print(f"🔍 DEBUG - Recipients found: {len(recipients_data)}")
                    if recipients_data:
                        print(f"🔍 DEBUG - First recipient sample: {recipients_data[0]}")
                    else:
                        print(f"⚠️ WARNING - No recipients in document response!")
                        print(f"🔍 DEBUG - Full document data: {json.dumps(document_data, indent=2)}")
                elif doc_status in ["document.uploaded", "document.processing"]:
                    time.sleep(1)
                    retry_count += 1
                else:
                    state["field_placement_status"] = {
                        "success": False,
                        "error": f"Unexpected document status: {doc_status}"
                    }
                    return state
            elif status_response.status_code == 409:
                # 409 Conflict means document is still processing asynchronously
                print("  ⏳ Document still processing (409), waiting...")
                time.sleep(1)
                retry_count += 1
            else:
                error_msg = f"Failed to check status: {status_response.status_code}"
                print(f"❌ ERROR - {error_msg}")
                print(f"🔍 DEBUG - Response body: {status_response.text}")
                state["field_placement_status"] = {
                    "success": False,
                    "error": error_msg
                }
                return state
        except Exception as e:
            error_msg = f"Status check error: {str(e)}"
            print(f"❌ EXCEPTION - {error_msg}")
            state["field_placement_status"] = {
                "success": False,
                "error": error_msg
            }
            return state

    if not document_ready:
        state["field_placement_status"] = {
            "success": False,
            "error": "Timeout waiting for document to be ready"
        }
        return state

    # Create email-to-UUID mapping for recipient assignment (case-insensitive)
    email_to_uuid = {}
    for recipient in recipients_data:
        email = recipient.get("email")
        uuid = recipient.get("id")
        if email and uuid:
            email_to_uuid[email.lower()] = uuid  # Normalize to lowercase
            print(f"  📧 Mapped {email} → {uuid}")

    if not email_to_uuid:
        state["field_placement_status"] = {
            "success": False,
            "error": "No recipient UUIDs found in document"
        }
        return state

    headers = {
        "Authorization": f"API-Key {api_key}",
        "Content-Type": "application/json"
    }

    try:
        # Place signature fields on the new blank page (last page) that was added
        pdf_file = state.get("pdf_file")
        pdf_doc = fitz.open(stream=pdf_file, filetype="pdf")

        # Get the last page number (0-indexed) - this is the new blank page we added
        last_page = len(pdf_doc) - 1
        pdf_doc.close()

        print(f"📄 Document has {last_page + 1} page(s)")
        print(f"📍 Placing signature fields on new blank page (page {last_page}, 0-indexed), centered")
        print(f"   This should be page {last_page + 1} in the PandaDoc viewer")

        # Centered coordinates for signature fields
        # Standard letter page: width=612, height=792
        # Signature field width=120, so center X = (612-120)/2 = 246
        # IMPORTANT: PandaDoc uses 1-indexed page numbers, not 0-indexed!
        page = last_page + 1  # Convert from 0-indexed to 1-indexed
        x = 246  # Centered horizontally
        first_y = 200  # Start from top of the blank page (with some margin)
        row_height = 60  # Spacing between multiple signatures

        print(f"   Using PandaDoc page number: {page} (1-indexed)")

        # Create fields with proper PandaDoc structure
        fields = []
        for i, recipient in enumerate(extracted_data):
            role = recipient_roles[i] if i < len(recipient_roles) else "CC"
            y = first_y + (i * row_height)

            # Get recipient UUID from email mapping (case-insensitive lookup)
            recipient_email = recipient.get("email")
            recipient_uuid = email_to_uuid.get(recipient_email.lower())  # Normalize to lowercase

            if not recipient_uuid:
                print(f"  ⚠️ Warning: No UUID found for {recipient_email}, skipping field creation")
                continue

            field = {
                "name": f"Signature_{i+1}",
                "title": "Signature",
                "type": "signature",
                "assigned_to": recipient_uuid,  # Use recipient UUID from PandaDoc
                "settings": {
                    "required": True
                },
                "layout": {
                    "page": page,
                    "position": {
                        "offset_x": x,
                        "offset_y": y,
                        "anchor_point": "topleft"  # Correct format!
                    },
                    "style": {
                        "width": 120,
                        "height": 20
                    }
                }
            }
            fields.append(field)
            print(f"  → Creating field 'Signature_{i+1}' for '{recipient_email}' ({role}) [UUID: {recipient_uuid[:8]}...] at ({x}, {y})")

        # POST to create fields
        fields_url = f"{api_url}/{document_id}/fields"
        payload = {"fields": fields}

        print(f"\n📤 Creating fields with assignments...")
        print(f"🔍 DEBUG - POST Request:")
        print(f"  URL: {fields_url}")
        print(f"  Payload: {json.dumps(payload, indent=2)[:800]}...")

        create_response = requests.post(fields_url, headers=headers, json=payload)

        print(f"  Response Status: {create_response.status_code}")
        print(f"  Response: {create_response.text[:500]}")

        if create_response.status_code in [200, 201]:
            state["field_placement_status"] = {
                "success": True,
                "fields_created": len(fields)
            }
            print(f"✅ Successfully created {len(fields)} field(s) with assignments!")
        else:
            state["field_placement_status"] = {
                "success": False,
                "error": f"Field creation failed: {create_response.status_code} - {create_response.text}"
            }
            print(f"❌ Field creation failed: {create_response.status_code}")

    except Exception as e:
        state["field_placement_status"] = {
            "success": False,
            "error": f"Field assignment error: {str(e)}"
        }
        print(f"❌ Field assignment error: {str(e)}")

    return state


def send_node(state: WorkflowState) -> WorkflowState:
    """
    Agent: Send document to recipients
    """
    print("📧 Send Agent: Sending document to recipients...")

    api_key = os.getenv("PANDADOC_API_KEY")
    api_url = os.getenv("PANDADOC_API_URL")
    document_id = state.get("upload_status", {}).get("document_id")

    if not document_id:
        state["send_status"] = {
            "success": False,
            "error": "No document ID available"
        }
        return state

    # Wait for document to be ready (PandaDoc processes documents asynchronously)
    print("⏳ Waiting for document to be ready before sending...")
    max_retries = 30  # 30 seconds max wait
    retry_count = 0
    document_ready = False

    # Headers for GET request (no Content-Type needed)
    status_headers = {
        "Authorization": f"API-Key {api_key}"
    }

    while retry_count < max_retries and not document_ready:
        try:
            # Check document status
            status_url = f"{api_url}/{document_id}"

            print(f"\n🔍 DEBUG - Status Check Request:")
            print(f"  URL: {status_url}")
            print(f"  Document ID: {document_id}")
            print(f"  Headers: {status_headers}")

            status_response = requests.get(status_url, headers=status_headers)

            print(f"  Response Status: {status_response.status_code}")
            print(f"  Response Body: {status_response.text}\n")

            if status_response.status_code == 200:
                doc_status = status_response.json().get("status")
                print(f"  ✅ Document status: {doc_status}")

                if doc_status == "document.draft":
                    document_ready = True
                    print("✅ Document is ready to send!")
                elif doc_status in ["document.uploaded", "document.processing"]:
                    # Still processing, wait and retry
                    time.sleep(1)
                    retry_count += 1
                else:
                    # Unexpected status
                    state["send_status"] = {
                        "success": False,
                        "error": f"Unexpected document status: {doc_status}"
                    }
                    return state
            else:
                print(f"❌ Status check failed with {status_response.status_code}")
                state["send_status"] = {
                    "success": False,
                    "error": f"Failed to check document status: {status_response.status_code} - {status_response.text}"
                }
                return state

        except Exception as e:
            state["send_status"] = {
                "success": False,
                "error": f"Error checking document status: {str(e)}"
            }
            return state

    if not document_ready:
        state["send_status"] = {
            "success": False,
            "error": "Timeout waiting for document to be ready (30 seconds)"
        }
        return state

    # Now send the document
    send_url = f"{api_url}/{document_id}/send"
    send_payload = {
        "message": "Please review and sign this document.",
        "silent": False
    }

    send_headers = {
        "Authorization": f"API-Key {api_key}",
        "Content-Type": "application/json"
    }

    print(f"\n📤 Sending document...")
    print(f"🔍 DEBUG - Send Request:")
    print(f"  URL: {send_url}")
    print(f"  Payload: {json.dumps(send_payload, indent=2)}")

    try:
        send_response = requests.post(send_url, headers=send_headers, json=send_payload)

        print(f"  Response Status: {send_response.status_code}")
        print(f"  Response Body: {send_response.text}\n")

        if send_response.status_code == 200:
            state["send_status"] = {
                "success": True,
                "response": send_response.json()
            }
            print("✅ Document sent to recipients successfully!")

            # Add to follow-up tracker
            try:
                from followup_tracker import add_document
                extracted_data = state.get("extracted_data", [])
                add_document(
                    document_id=document_id,
                    name=state.get("document_name", "Untitled Document"),
                    sent_date=datetime.now().isoformat(),
                    recipients=extracted_data
                )
            except Exception as e:
                print(f"⚠️ Could not add to follow-up tracker: {str(e)}")
        else:
            state["send_status"] = {
                "success": False,
                "error": f"Send failed with status {send_response.status_code}: {send_response.text}"
            }
            print(f"❌ Send failed: {send_response.status_code}")

    except Exception as send_error:
        state["send_status"] = {
            "success": False,
            "error": f"Send error: {str(send_error)}"
        }
        print(f"❌ Send error: {str(send_error)}")

    return state


def should_continue_to_add_fields(state: WorkflowState) -> str:
    """Conditional edge: only proceed to add fields if validation passed"""
    validation_status = state.get("validation_status", {})
    if validation_status.get("is_valid"):
        return "add_fields"
    else:
        return "end"


def should_continue_to_upload(state: WorkflowState) -> str:
    """Conditional edge: only proceed to upload if fields were added successfully"""
    field_status = state.get("field_placement_status", {})
    success = field_status.get("success", False)

    print(f"\n🔍 Conditional Check - Should continue to upload?")
    print(f"  Field status: {field_status}")
    print(f"  Success: {success}")
    print(f"  Decision: {'upload' if success else 'END (stopping workflow)'}\n")

    if success:
        return "upload"
    else:
        return "end"


def create_workflow() -> StateGraph:
    """Create the multi-agent workflow graph"""
    
    # Create the graph
    workflow = StateGraph(WorkflowState)
    
    # Add nodes
    workflow.add_node("extract", extraction_node)
    workflow.add_node("validate", validation_node)
    workflow.add_node("add_fields", add_form_fields_node)  # Adds PDF form widgets
    workflow.add_node("upload", upload_node)
    workflow.add_node("assign_fields", assign_fields_node)  # Assigns detected fields to recipients
    workflow.add_node("send", send_node)

    # Add edges
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "validate")

    # Conditional edge from validation
    workflow.add_conditional_edges(
        "validate",
        should_continue_to_add_fields,
        {
            "add_fields": "add_fields",
            "end": END
        }
    )

    # Conditional edge from field addition
    workflow.add_conditional_edges(
        "add_fields",
        should_continue_to_upload,
        {
            "upload": "upload",
            "end": END
        }
    )

    # Upload → Assign fields to recipients → Send
    workflow.add_edge("upload", "assign_fields")
    workflow.add_edge("assign_fields", "send")
    workflow.add_edge("send", END)
    
    return workflow.compile()


def run_workflow(pdf_file: bytes, document_name: str) -> dict:
    """
    Run the complete multi-agent workflow
    
    Args:
        pdf_file: Binary PDF file content
        document_name: Name of the document
        
    Returns:
        Final state dictionary with all results
    """
    # Create workflow
    app = create_workflow()
    
    # Initialize state
    initial_state = {
        "pdf_file": pdf_file,
        "pdf_text": "",
        "document_name": document_name,
        "extracted_data": [],  # Changed from {} to [] to support multiple recipients
        "validation_status": {},
        "upload_status": {},
        "field_placement_status": {},  # Track signature field placement
        "send_status": {},  # Track document send status
        "error": None
    }
    
    # Run workflow
    final_state = app.invoke(initial_state)
    
    return final_state
