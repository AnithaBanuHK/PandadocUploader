import streamlit as st
import os
from dotenv import load_dotenv
from workflow import run_workflow

# Load environment variables from .env file
load_dotenv()

# Validate API configuration
API_KEY = os.getenv("PANDADOC_API_KEY")
API_URL = os.getenv("PANDADOC_API_URL")

if not API_KEY or not API_URL:
    st.error("⚠️ Missing API configuration! Please check your .env file.")
    st.stop()

# Page configuration
st.set_page_config(page_title="PandaDoc Multi-Agent Upload", page_icon="📄", layout="wide")

# --- PandaDoc Theme CSS ---
st.markdown("""
<style>
    /* === PandaDoc Brand Colors === */
    :root {
        --pd-green: #00B800;
        --pd-green-dark: #009A00;
        --pd-green-light: #E6F9E6;
        --pd-dark: #1B2A4A;
        --pd-gray: #6B7B8D;
        --pd-light-bg: #F7FAF7;
        --pd-white: #FFFFFF;
        --pd-border: #E0E8E0;
    }

    /* Main background */
    .stApp {
        background-color: var(--pd-light-bg);
    }

    /* Header styling */
    .stApp header {
        background-color: var(--pd-dark) !important;
    }

    /* Primary button - PandaDoc green */
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background-color: var(--pd-green) !important;
        border-color: var(--pd-green) !important;
        color: white !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 2rem !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[data-testid="stBaseButton-primary"]:hover {
        background-color: var(--pd-green-dark) !important;
        border-color: var(--pd-green-dark) !important;
        box-shadow: 0 4px 12px rgba(0, 184, 0, 0.3) !important;
    }

    /* Secondary buttons */
    .stButton > button {
        border-radius: 8px !important;
        border-color: var(--pd-border) !important;
        font-weight: 500 !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: var(--pd-dark) !important;
    }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li,
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label {
        color: #E0E8EF !important;
    }
    section[data-testid="stSidebar"] .stMarkdown strong {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: rgba(255, 255, 255, 0.15) !important;
    }

    /* File uploader */
    .stFileUploader section {
        border: 2px dashed var(--pd-green) !important;
        border-radius: 12px !important;
        background-color: var(--pd-green-light) !important;
    }

    /* Text inputs */
    .stTextInput input {
        border-radius: 8px !important;
        border-color: var(--pd-border) !important;
    }
    .stTextInput input:focus {
        border-color: var(--pd-green) !important;
        box-shadow: 0 0 0 2px rgba(0, 184, 0, 0.15) !important;
    }

    /* Info/success/warning/error alerts */
    .stAlert [data-testid="stNotification"] {
        border-radius: 8px !important;
    }

    /* Success alerts - PandaDoc green */
    div[data-testid="stNotification"][data-type="success"] {
        background-color: var(--pd-green-light) !important;
        border-left-color: var(--pd-green) !important;
    }

    /* Expander */
    .streamlit-expanderHeader {
        border-radius: 8px !important;
        font-weight: 600 !important;
        color: var(--pd-dark) !important;
    }

    /* Dataframe */
    .stDataFrame {
        border-radius: 8px !important;
        overflow: hidden !important;
    }

    /* Spinner */
    .stSpinner > div {
        border-top-color: var(--pd-green) !important;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background-color: var(--pd-white);
        border: 1px solid var(--pd-border);
        border-radius: 10px;
        padding: 1rem;
    }

    /* Custom title bar */
    .pd-header {
        background: linear-gradient(135deg, var(--pd-dark) 0%, #2A3F6A 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .pd-header h1 {
        margin: 0;
        font-size: 1.8rem;
        font-weight: 700;
        color: white !important;
    }
    .pd-header p {
        margin: 0.3rem 0 0 0;
        color: #B0BEC5;
        font-size: 1rem;
    }
    .pd-header .pd-logo-accent {
        color: var(--pd-green);
        font-weight: 800;
    }

    /* Agent status columns */
    .stColumn > div {
        border-radius: 8px;
    }

    /* Progress pipeline styling */
    .pd-pipeline {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: white;
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid var(--pd-border);
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# Custom branded header
st.markdown("""
<div class="pd-header">
    <h1><span class="pd-logo-accent">Panda</span>Doc Multi-Agent Uploader</h1>
    <p>Upload your PDF and let our AI agents handle the rest</p>
</div>
""", unsafe_allow_html=True)

# Add info about the multi-agent workflow
with st.expander("About the Multi-Agent Workflow", expanded=False):
    st.markdown("""
    This application uses a **6-agent workflow** powered by LangGraph and Vertex AI Gemini:

    1. **🔍 Extraction Agent**: Analyzes the PDF and extracts ALL approver information from tables (email, name)
    2. **✅ Validation Agent**: Validates the extracted data for correctness and completeness
    3. **📝 Form Fields Agent**: Uses AI to detect signature positions and adds PDF form widgets
    4. **📤 Upload Agent**: Uploads the PDF to PandaDoc (PandaDoc recognizes the form fields)
    5. **📋 Field Assignment Agent**: Assigns the detected fields to specific recipients via API
    6. **📧 Send Agent**: Sends the document to all recipients for signature

    **How it works:** The AI detects where signatures should go, adds PDF form widgets, uploads to PandaDoc, then uses the API to assign each field to the correct recipient!

    Each agent is powered by Google's Gemini AI for intelligent document processing.
    """)

# Document name input
document_name = st.text_input("Document Name", placeholder="Enter document name", help="Name for the document in PandaDoc")

# File upload
uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'], help="Upload a PDF containing signer information")

# Upload button
st.markdown("<br>", unsafe_allow_html=True)
if st.button("Process Document", type="primary", disabled=not uploaded_file or not document_name):
    if uploaded_file and document_name:
        # Create columns for agent status
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown("**1. Extraction**")
            extraction_status = st.empty()
        with col2:
            st.markdown("**2. Validation**")
            validation_status = st.empty()
        with col3:
            st.markdown("**3. Upload**")
            upload_status = st.empty()
        with col4:
            st.markdown("**4. Send**")
            send_status = st.empty()

        # Show initial status
        extraction_status.text("⏳ Waiting...")
        validation_status.text("⏳ Waiting...")
        upload_status.text("⏳ Waiting...")
        send_status.text("⏳ Waiting...")
        
        # Read PDF file
        pdf_bytes = uploaded_file.getvalue()
        
        # Run the multi-agent workflow
        with st.spinner("🤖 Running multi-agent workflow..."):
            try:
                # Update extraction status
                extraction_status.text("🔄 Processing...")
                
                # Run workflow
                final_state = run_workflow(pdf_bytes, document_name)
                
                # Update extraction status
                if final_state.get("extracted_data"):
                    extraction_status.text("✅ Complete")
                else:
                    extraction_status.text("❌ Failed")
                
                # Show extracted data
                st.subheader("Extraction Results")
                extracted_data = final_state.get("extracted_data", [])

                if extracted_data and len(extracted_data) > 0:
                    st.write(f"**Found {len(extracted_data)} recipient(s):**")

                    # Display extracted recipients in a table
                    import pandas as pd
                    df = pd.DataFrame(extracted_data)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.error("Failed to extract any recipient information from the PDF.")
                
                # Update validation status
                validation_result = final_state.get("validation_status", {})
                if validation_result.get("is_valid"):
                    validation_status.text("✅ Valid")
                    st.success("✅ Validation passed!")
                else:
                    validation_status.text("❌ Invalid")
                    st.error(f"❌ Validation failed: {', '.join(validation_result.get('errors', []))}")

                # Update upload status
                upload_result = final_state.get("upload_status", {})
                if upload_result.get("success"):
                    upload_status.text("✅ Uploaded")
                elif upload_result.get("error"):
                    upload_status.text("❌ Failed")
                    error_msg = upload_result.get("error", "Unknown error")
                    st.error(f"❌ Upload failed: {error_msg}")
                else:
                    # Upload was skipped due to validation failure
                    upload_status.text("⏭️ Skipped")
                    st.warning("⚠️ Upload was skipped because validation failed.")

                # Update send status
                send_result = final_state.get("send_status", {})
                if send_result.get("success"):
                    send_status.text("✅ Sent")
                    st.success("🎉 Document successfully sent to all recipients!")
                    st.info(f"💡 All {len(extracted_data)} recipient(s) have been notified via email.")

                    # Show document details
                    with st.expander("📋 Document Details"):
                        st.json(upload_result.get("response", {}))
                elif send_result.get("error"):
                    send_status.text("❌ Failed")
                    error_msg = send_result.get("error", "Unknown error")
                    st.warning(f"⚠️ Document uploaded but send failed: {error_msg}")
                    st.info("The document is in PandaDoc but recipients were not notified. You can send it manually from PandaDoc.")
                else:
                    send_status.text("⏭️ Skipped")
                
                # Show any general errors
                if final_state.get("error"):
                    st.error(f"❌ Workflow error: {final_state['error']}")
                
            except Exception as e:
                st.error(f"❌ An error occurred: {str(e)}")
                extraction_status.text("❌ Error")
                validation_status.text("❌ Error")
                upload_status.text("❌ Error")

# Add sidebar with instructions
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 0.5rem 0 1rem 0;">
        <span style="font-size: 1.4rem; font-weight: 700; color: #00B800;">Panda</span><span style="font-size: 1.4rem; font-weight: 700; color: #FFFFFF;">Doc</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### How to use")
    st.markdown("""
    1. **Enter document name** — This will be the name in PandaDoc

    2. **Upload PDF** — Select a PDF with approver info (email, name)
       - Form fields are added automatically by AI

    3. **Click "Process Document"** — The workflow will:
       - Extract approver details from the PDF
       - Validate the extracted information
       - Add signature fields to the PDF
       - Upload to PandaDoc
       - Send to all recipients

    4. **Review results** — Check extracted data and send status
    """)

