"""
Human-in-the-loop interrupt node. Pauses the graph so a bank officer
can approve/reject/request-info via the officer dashboard, then
resumes using the LangGraph checkpointer.

Also sends two real notifications the moment a case enters this
state:
  - the CUSTOMER gets an email explaining their case needs manual
    review and why
  - the OFFICER gets an email flagging that a new case is waiting
"""

import os
import logging
from langgraph.types import interrupt

from app.agents.state import DisputeCaseState
from app.notifications.email_client import send_email

logger = logging.getLogger(__name__)

OFFICER_EMAIL = os.getenv("OFFICER_EMAIL", "fraud-review-team@bank.internal")


def _customer_facing_reason(state: DisputeCaseState) -> str:
    """Translates the internal decision_reason into something a
    customer should actually read — never expose raw internal
    policy-engine language to the customer."""
    if state.get("fraud_flag"):
        return (
            "your case involves a transaction amount or pattern that our "
            "fraud review process checks manually as a routine precaution"
        )
    if state.get("time_window_status") == "manual_review_window":
        return (
            "your complaint was filed more than 15 days after the transaction. "
            "Per policy, cases filed 15-30 days after the transaction require "
            "manual officer approval rather than automatic processing"
        )
    return "your case requires additional manual review before we can proceed"


def human_review_node(state: DisputeCaseState) -> dict:
    case_id = state.get("case_id")
    customer_name = state.get("customer_name")

    case_summary = {
        "reason": "officer_review_required",
        "case_id": case_id,
        "customer_name": customer_name,
        "transaction_id": state.get("transaction_id"),
        "amount": state.get("transaction_amount"),
        "receiver_name": state.get("receiver_name"),
        "fraud_flag": state.get("fraud_flag"),
        "time_window_status": state.get("time_window_status"),
        "decision_reason": state.get("decision_reason"),
    }

    send_email(
        to=customer_name,
        subject="Your dispute case is under review",
        body=(
            f"Hi {customer_name}, we've received your complaint (case ref: {case_id}) "
            f"regarding a transfer of {state.get('transaction_amount')}. "
            f"We wanted to let you know that {_customer_facing_reason(state)}. "
            "A member of our team will review it shortly — no action is needed from you "
            "right now, and we'll notify you as soon as a decision is made."
        ),
    )

    send_email(
        to=OFFICER_EMAIL,
        subject=f"New case requires review: {case_id}",
        body=(
            f"Case {case_id} for customer {customer_name} requires manual review.\n"
            f"Transaction: {state.get('transaction_id')}, amount {state.get('transaction_amount')}, "
            f"receiver {state.get('receiver_name')}.\n"
            f"Reason: {state.get('decision_reason')}\n"
            "Please review on the officer dashboard."
        ),
    )

    logger.info("Human review notifications sent for case %s", case_id)

    officer_decision = interrupt(case_summary)

    logger.info("Officer decision received for case %s: %s", case_id, officer_decision)

    status_map = {"approved": "open", "rejected": "rejected", "more_info": "open"}

    decision_messages = {
        "approved": (
            f"Good news — your case (ref: {case_id}) has been approved by our review team. "
            "We're now reaching out to the recipient to request the funds be returned."
        ),
        "rejected": (
            f"We've completed review of your case (ref: {case_id}). Unfortunately, we were "
            "unable to approve this refund under current policy. If you believe this is "
            "incorrect, please contact support with any additional documentation."
        ),
        "more_info": (
            f"We need a bit more information to process your case (ref: {case_id}). "
            "Our team will reach out with specific questions shortly."
        ),
    }

    send_email(
        to=customer_name,
        subject="Update on your dispute case",
        body=decision_messages.get(officer_decision, f"Your case (ref: {case_id}) status has been updated."),
    )

    return {
        "officer_decision": officer_decision,
        "case_status": status_map.get(officer_decision, "open"),
    }