"""
Dispute Resolution — customer-facing intake
=============================================

Streamlit interface that collects a customer's dispute (name, issue,
transaction receipt) and runs it through the LangGraph agent pipeline
in app/agents/graph.py.

This screen is CUSTOMER-FACING ONLY. It never shows approve/reject
controls — those belong to a bank officer, not the person who filed
the complaint. If a case needs officer review (fraud flag, large
amount, etc.), the customer just sees a "under review" status here;
the actual approve/reject decision happens on the separate officer
dashboard (frontend/pages/officer_dashboard.py).

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
    from app.db.postgres import get_session, Case
    from datetime import datetime
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
    "Bank review (if needed)",
    "Notify / resolve",
]


def upsert_case_status(case_id: str, customer_name: str, receipt_path: str, status: str):
    """Writes/updates the lightweight case tracker so the officer
    dashboard can find cases that need review, without introspecting
    LangGraph's checkpointer internals."""
    session = get_session()
    try:
        case = session.query(Case).filter_by(case_id=case_id).first()
        if case is None:
            case = Case(
                case_id=case_id, customer_name=customer_name,
                receipt_image_path=receipt_path, status=status,
                created_at=datetime.utcnow(),
            )
            session.add(case)
        else:
            case.status = status
            case.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()


def run_pipeline(customer_name: str, issue: str, receipt_path: str, thread_id: str):
    initial_state = {
        "case_id": thread_id,
        "customer_id": customer_name.strip().lower().replace(" ", "_"),
        "customer_name": customer_name.strip(),
        "issue_description": issue.strip(),
        "receipt_image_path": receipt_path,
        "errors": [],
    }
    config = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(initial_state, config=config)


def status_for_result(result: dict) -> tuple[str, str]:
    """Returns (internal_status, customer_facing_message)."""
    if isinstance(result, dict) and result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value
        reason = payload.get("reason") if isinstance(payload, dict) else None

        if reason == "officer_review_required":
            return "pending_officer_review", (
                "Your case has been flagged for review by our fraud & compliance team. "
                "This happens for larger amounts or unusual patterns — it's a routine "
                "extra check, not a rejection. You'll be notified once it's reviewed."
            )
        if reason == "awaiting_receiver_response":
            deadline = payload.get("response_deadline", "")
            return "awaiting_receiver", (
                f"We've notified the recipient and given them until {deadline[:10]} to "
                "voluntarily return the funds. If they don't respond in time, we'll "
                "automatically escalate and recover the amount on your behalf."
            )
        return "open", "Your case is being processed."

    status = result.get("case_status", "open")
    messages = {
        "closed": "Your case has been resolved and closed.",
        "resolved": "Good news — the funds have been recovered.",
        "escalated": "Your case has been escalated for bank action.",
        "rejected": "Unfortunately, this case could not be verified against our records.",
    }
    return status, messages.get(status, f"Case status: {status}")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Dispute Resolution", page_icon="\U0001F3E6", layout="centered")

st.title("Transaction Dispute Intake")
st.caption("Submit a wrong-transfer complaint and our system takes it from there.")

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
    st.session_state.stage = "intake"  # intake -> resolved

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

            internal_status, _ = status_for_result(result)
            upsert_case_status(thread_id, customer_name, receipt_path, internal_status)

            st.session_state.result = result
            st.session_state.stage = "resolved"
            st.rerun()

# ---- Status (customer-facing — no approve/reject controls here) -----------
elif st.session_state.stage == "resolved":
    st.subheader(f"Case for {st.session_state.customer_name}")
    st.caption(f"Reference ID: {st.session_state.thread_id}")

    status, message = status_for_result(st.session_state.result)

    if status in ("closed", "resolved"):
        st.success(message)
    elif status in ("pending_officer_review", "awaiting_receiver"):
        st.info(message)
    elif status == "rejected":
        st.error(message)
    else:
        st.warning(message)

    with st.expander("Technical details (for debugging)"):
        st.json(st.session_state.result)

    if st.button("Start a new case"):
        for key in ("thread_id", "result", "stage", "customer_name", "issue"):
            st.session_state.pop(key, None)
        st.rerun()

with st.sidebar:
    st.header("How this works")
    for i, step in enumerate(PIPELINE_STEPS):
        st.write(f"{i + 1}. {step}")
    st.divider()
    st.caption("Bank staff: use the Officer Dashboard page (sidebar above) to review flagged cases.")
    if st.button("Reseed sample database"):
        seed_db()
        st.success("Database reseeded from sample_dataset CSVs.")