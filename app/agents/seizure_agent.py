"""
8b. Account Seizure & Fund Transfer

Runs after escalation_node's final notice has gone out and the
receiver still hasn't returned the funds. This node performs the
actual bank action: deducts the disputed amount from Person B's
balance, credits it to Person A (the sender), and moves Person B's
full record out of the active customers table into
existing_customer.csv (i.e. blocks/seizes their account), with a
timestamped audit trail tying the action back to this case.
"""

import logging

from app.agents.state import DisputeCaseState
from app.tools.bank_db_tools import seize_and_transfer

logger = logging.getLogger(__name__)


def seizure_node(state: DisputeCaseState) -> dict:
    """
    LangGraph node. Executes the seizure + transfer and reports the
    outcome back into state. If the receiver's balance is insufficient
    or either party can't be found, the case is routed to manual
    review instead of silently failing.
    """
    receiver_name = state.get("receiver_name")
    sender_name = state.get("customer_name")
    amount = state.get("transaction_amount")
    case_id = state.get("case_id")

    if not receiver_name or not sender_name or amount is None:
        logger.warning(
            "Seizure skipped for case %s: missing receiver_name/sender_name/amount",
            case_id,
        )
        return {
            "case_status": "escalated",
            "decision_reason": state.get("decision_reason", "")
            + " | seizure_skipped: missing_required_fields",
        }

    result = seize_and_transfer(
        receiver_name=receiver_name,
        sender_name=sender_name,
        amount=amount,
        reason=f"Unreturned mistaken transfer, case {case_id}",
        case_id=case_id,
    )

    if not result.get("success"):
        logger.warning("Seizure failed for case %s: %s", case_id, result)
        return {
            "case_status": "escalated",
            "decision_reason": state.get("decision_reason", "")
            + f" | seizure_failed: {result.get('error')}",
        }

    logger.info(
        "Seizure completed for case %s: deducted %s from %s, credited to %s",
        case_id,
        result["amount_transferred"],
        receiver_name,
        sender_name,
    )

    return {
        "case_status": "closed",
        "decision_reason": state.get("decision_reason", "")
        + f" | account_seized=True, amount_transferred={result['amount_transferred']}",
    }
