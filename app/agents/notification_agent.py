"""
6B / 7A / 7B / 8. Notify Receiver, Monitor Response, Escalation & Bank Action

Three node functions live here because they form one tight loop in the
diagram: notify -> wait/monitor -> either resolved or escalated.
"""

import os
import logging
from datetime import datetime, timedelta

from langgraph.types import interrupt

from app.agents.state import DisputeCaseState
from app.notifications.email_client import send_email
from app.notifications.sms_client import send_sms

logger = logging.getLogger(__name__)

RECEIVER_RESPONSE_WINDOW_DAYS = float(os.getenv("RECEIVER_RESPONSE_WINDOW_DAYS", "2"))


def notify_receiver_node(state: DisputeCaseState) -> dict:
    """6B. Notify Person B by email/SMS to voluntarily return the funds."""
    receiver_name = state.get("receiver_name")
    amount = state.get("transaction_amount")
    case_id = state.get("case_id")

    message = (
        f"A refund request has been raised for a mistaken transfer of "
        f"{amount} associated with transaction linked to your account. "
        f"Please return the amount within {RECEIVER_RESPONSE_WINDOW_DAYS} days. "
        f"Case ref: {case_id}."
    )

    sent_email = send_email(to=receiver_name, subject="Refund Request", body=message)
    sent_sms = send_sms(to=receiver_name, body=message)

    logger.info(
        "Notified receiver for case %s (email=%s, sms=%s)",
        case_id,
        sent_email,
        sent_sms,
    )

    return {
        "receiver_notified": bool(sent_email or sent_sms),
        "receiver_notified_at": datetime.utcnow().isoformat(),
    }


def monitor_response_node(state: DisputeCaseState) -> dict:
    """
    7B. Checks whether Person B has returned the funds. If the
    response window hasn't elapsed yet, this node genuinely pauses the
    graph via interrupt() — same pause/resume mechanism as human
    review, but time-gated rather than officer-gated. Requires a
    persistent checkpointer (app/db/checkpointer.py) since the pause
    can span real days across app restarts.

    Resuming re-runs this node from the top: it re-checks the DB and
    the real elapsed time on every resume, so it will keep pausing
    until either the receiver actually pays or the window has genuinely
    elapsed — nothing here fast-forwards time artificially.
    """
    from app.tools.bank_db_tools import get_transaction

    case_id = state.get("case_id")
    txn = get_transaction(state.get("transaction_id"))
    refunded = bool(txn and txn.get("refund_received"))

    if refunded:
        logger.info("Receiver refunded for case %s", case_id)
        return {"receiver_refunded": True, "case_status": "resolved"}

    notified_at_str = state.get("receiver_notified_at")
    notified_at = datetime.fromisoformat(notified_at_str) if notified_at_str else datetime.utcnow()
    deadline = notified_at + timedelta(days=RECEIVER_RESPONSE_WINDOW_DAYS)
    now = datetime.utcnow()

    if now < deadline:
        logger.info(
            "Case %s still within response window (deadline %s) — pausing",
            case_id, deadline.isoformat(),
        )
        # Pauses here. Resume by re-invoking the graph with the same
        # thread_id once the window should have elapsed — e.g. via a
        # scheduled check (see app/scripts/check_pending_cases.py).
        interrupt({
            "reason": "awaiting_receiver_response",
            "case_id": case_id,
            "receiver_notified_at": notified_at.isoformat(),
            "response_deadline": deadline.isoformat(),
        })
        # Unreachable until resumed; on resume the node re-runs from
        # the top and re-evaluates the real elapsed time above.

    logger.info("Response window elapsed with no refund for case %s", case_id)
    return {"receiver_refunded": False}


def escalation_node(state: DisputeCaseState) -> dict:
    """
    8. Escalation & Bank Action (part 1) — sends the final notice to
    Person B warning of account action. The actual account
    seizure/fund transfer happens in the next node, seizure_node
    (agents/seizure_agent.py), so it can be audited and tested as its
    own discrete step.
    """
    from app.tools.bank_db_tools import freeze_account

    case_id = state.get("case_id")
    receiver_name = state.get("receiver_name")
    amount = state.get("transaction_amount")

    send_email(
        to=receiver_name,
        subject="Final Notice: Account Action Pending",
        body=(
            f"You have not returned the mistaken transfer of {amount}. "
            "Your account may be frozen and the amount deducted per bank policy."
        ),
    )

    freeze_account(state.get("receiver_account") or receiver_name)

    logger.info("Final notice sent for case %s", case_id)

    return {
        "case_status": "escalated",
        "decision_reason": state.get("decision_reason", "") + " | final_notice_sent",
    }