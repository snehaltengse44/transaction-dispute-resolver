"""
Officer Dashboard — bank-staff-only view
==========================================

Lists cases currently paused for officer review (fraud flag, large
amount, etc.) and lets a bank officer Approve / Reject / Request Info.

Streamlit auto-detects this as a separate page since it lives in
frontend/pages/ next to the main streamlit_app.py — it gets its own
entry in the sidebar navigation, distinct from the customer intake
screen. In a real deployment this page would sit behind staff-only
authentication; that's not implemented here since it's out of scope
for the demo, but is the obvious next step before any real use.
"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.agents.graph import dispute_graph as graph
from app.db.postgres import get_session, Case
from langgraph.types import Command

st.set_page_config(page_title="Officer Dashboard", page_icon="\U0001F454", layout="wide")

st.title("Bank Officer Dashboard")
st.caption("Cases flagged for manual review — staff only.")


def get_pending_officer_cases():
    session = get_session()
    try:
        return session.query(Case).filter_by(status="pending_officer_review").all()
    finally:
        session.close()


def get_interrupt_payload(case_id: str):
    config = {"configurable": {"thread_id": case_id}}
    snapshot = graph.get_state(config)
    for task in snapshot.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def resolve_case(case_id: str, decision: str):
    config = {"configurable": {"thread_id": case_id}}
    result = graph.invoke(Command(resume=decision), config=config)

    session = get_session()
    try:
        case = session.query(Case).filter_by(case_id=case_id).first()
        if case:
            case.status = result.get("case_status", "resolved")
            session.commit()
    finally:
        session.close()
    return result


pending_cases = get_pending_officer_cases()

if not pending_cases:
    st.success("No cases currently awaiting review.")
else:
    st.write(f"**{len(pending_cases)} case(s)** awaiting your decision.")

    for case in pending_cases:
        payload = get_interrupt_payload(case.case_id)
        if payload is None:
            continue  # already resolved elsewhere since last page load

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.subheader(f"Case {case.case_id}")
                st.write(f"**Customer:** {payload.get('customer_name')}")
                st.write(f"**Transaction ID:** {payload.get('transaction_id')}")
                st.write(f"**Amount:** {payload.get('amount')}")
                st.write(f"**Receiver:** {payload.get('receiver_name')}")
                if payload.get("fraud_flag"):
                    st.warning("⚠️ Flagged by fraud heuristics")
                st.caption(payload.get("decision_reason", ""))

            with col2:
                approve = st.button("✅ Approve", key=f"approve_{case.case_id}", use_container_width=True)
                reject = st.button("❌ Reject", key=f"reject_{case.case_id}", use_container_width=True)
                more_info = st.button("ℹ️ Request info", key=f"info_{case.case_id}", use_container_width=True)

            if approve or reject or more_info:
                decision = "approved" if approve else ("rejected" if reject else "more_info")
                with st.spinner("Processing..."):
                    resolve_case(case.case_id, decision)
                st.success(f"Case {case.case_id} marked as {decision}.")
                st.rerun()

if st.button("Refresh"):
    st.rerun()