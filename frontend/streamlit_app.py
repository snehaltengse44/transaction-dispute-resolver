"""
Dispute Resolution — pipeline front door
=========================================

Streamlit interface that collects a customer's dispute (name, issue,
transaction receipt) and runs it through the LangGraph agent pipeline
in app/agents/graph.py.

Run from the project root:
    streamlit run frontend/streamlit_app.py
"""

import sys
import uuid
import traceback
from pathlib import Path

import streamlit as st

# Make `app.*` importable when launched from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent))

PIPELINE_AVAILABLE = True
IMPORT_ERROR = None
try:
    from app.agents.graph import dispute_graph as graph
    from app.db.seed_postgres import seed as seed_db
    from langgraph.types import Command
except Exception as exc:  # pragma: no cover
    PIPELINE_AVAILABLE = False
    IMPORT_ERROR = exc

UPLOAD_DIR = Path(__file__).parent.parent / "data" / "sample_receipts" / "uploaded"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

PIPELINE_STEPS = [
    "Complaint submitted",
    "OCR & data extraction",
    "Data verification",
    "Policy & rule check",
    "Decision engine",
    "Human review",
    "Notify / resolve / seize",
]


# ---------------------------------------------------------------------------
# INTEGRATION POINT 1 — kick off a new case
# ---------------------------------------------------------------------------
def run_pipeline(customer_name: str, issue: str, receipt_path: str, thread_id: str):
    """Invoke the graph with a fresh case. Returns the raw result dict."""
    initial_state = {
        "case_id": thread_id,
        "customer_id": customer_name.lower().replace(" ", "_"),
        "customer_name": customer_name,
        "issue_description": issue,
        "receipt_image_path": receipt_path,
        "errors": [],
    }
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(initial_state, config=config)


# ---------------------------------------------------------------------------
# INTEGRATION POINT 2 — resume after a human decision (HITL step)
# ---------------------------------------------------------------------------
def resume_pipeline(officer_decision: str, thread_id: str):
    """Resume a paused graph after the bank officer approves/rejects.

    officer_decision must be one of: "approved", "rejected", "more_info"
    (see app/hitl/interrupts.py).
    """
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(Command(resume=officer_decision), config=config)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Dispute Resolution", page_icon="\U0001F3E6", layout="centered")

st.title("Transaction Dispute Intake")
st.caption("Submit a wrong-transfer complaint and the agent pipeline takes it from there.")

if not PIPELINE_AVAILABLE:
    st.error(
        "Couldn't import the pipeline "
        f"({IMPORT_ERROR}). Run this with `streamlit run frontend/streamlit_app.py` "
        "from the project root, and make sure `pip install -r requirements.txt` has been run."
    )
    st.stop()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "result" not in st.session_state:
    st.session_state.result = None
if "stage" not in st.session_state:
    st.session_state.stage = "intake"  # intake -> pending_review -> resolved

# ---- Intake form -----------------------------------------------------------
if st.session_state.stage == "intake":
    with st.form("intake_form"):
        customer_name = st.text_input("Your name", placeholder="e.g. Snehal")
        issue = st.text_area(
            "Describe the issue",
            placeholder="e.g. I sent money to the wrong UPI ID by mistake and need it refunded.",
            height=120,
        )
        receipt_file = st.file_uploader(
            "Transaction receipt (required)", type=["png", "jpg", "jpeg"]
        )
        submitted = st.form_submit_button("Start case", use_container_width=True)

    if submitted:
        if not customer_name.strip() or not issue.strip():
            st.error("Name and issue description are required.")
        elif receipt_file is None:
            st.error("Please attach the transaction receipt — the pipeline reads it via OCR.")
        else:
            receipt_path = str(UPLOAD_DIR / f"{uuid.uuid4().hex}_{receipt_file.name}")
            with open(receipt_path, "wb") as f:
                f.write(receipt_file.getbuffer())

            thread_id = uuid.uuid4().hex
            st.session_state.thread_id = thread_id
            st.session_state.customer_name = customer_name
            st.session_state.issue = issue

            with st.spinner("Running OCR, verification, and policy checks..."):
                try:
                    result = run_pipeline(customer_name, issue, receipt_path, thread_id)
                except Exception:
                    st.error("The pipeline raised an error:")
                    st.code(traceback.format_exc())
                    st.stop()

            st.session_state.result = result
            if isinstance(result, dict) and result.get("__interrupt__"):
                st.session_state.stage = "pending_review"
            else:
                st.session_state.stage = "resolved"
            st.rerun()

# ---- Human-in-the-loop review ----------------------------------------------
elif st.session_state.stage == "pending_review":
    st.subheader(f"Case for {st.session_state.customer_name}")
    st.progress(5 / len(PIPELINE_STEPS), text="Awaiting bank officer review")

    interrupt_payload = st.session_state.result["__interrupt__"][0]
    value = getattr(interrupt_payload, "value", None) or interrupt_payload.get("value", {})

    st.json(value)

    col1, col2, col3 = st.columns(3)
    with col1:
        approve = st.button("Approve", type="primary", use_container_width=True)
    with col2:
        reject = st.button("Reject", use_container_width=True)
    with col3:
        more_info = st.button("Request info", use_container_width=True)

    if approve or reject or more_info:
        decision = "approved" if approve else ("rejected" if reject else "more_info")
        with st.spinner("Finalizing case..."):
            try:
                final = resume_pipeline(decision, st.session_state.thread_id)
            except Exception:
                st.error("Resuming the pipeline raised an error:")
                st.code(traceback.format_exc())
                st.stop()
        st.session_state.result = final
        st.session_state.stage = "resolved"
        st.rerun()

# ---- Resolution --------------------------------------------------------
elif st.session_state.stage == "resolved":
    st.subheader(f"Case for {st.session_state.customer_name}")
    st.progress(1.0, text="Case closed")

    status = st.session_state.result.get("case_status", "unknown")
    if status == "closed":
        st.success(f"Case closed. Status: {status}")
    elif status == "escalated":
        st.warning(f"Case escalated. Status: {status}")
    else:
        st.info(f"Case status: {status}")

    with st.expander("Full pipeline output", expanded=True):
        st.json(st.session_state.result)

    if st.button("Start a new case"):
        for key in ("thread_id", "result", "stage", "customer_name", "issue"):
            st.session_state.pop(key, None)
        st.rerun()

with st.sidebar:
    st.header("Pipeline stages")
    for i, step in enumerate(PIPELINE_STEPS):
        st.write(f"{i + 1}. {step}")
    st.divider()
    if st.button("Reseed sample database"):
        seed_db()
        st.success("customers.db reseeded from sample_dataset CSVs.")
