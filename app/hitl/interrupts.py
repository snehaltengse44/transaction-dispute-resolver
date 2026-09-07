"""
Human-in-the-loop interrupt node. Pauses the graph so a bank officer
can approve/reject/request-info via approval_routes.py, then resumes
using the LangGraph checkpointer.
"""

import logging
from langgraph.types import interrupt

from app.agents.state import DisputeCaseState

logger = logging.getLogger(__name__)


def human_review_node(state: DisputeCaseState) -> dict:
    """
    Surfaces the case summary to a human reviewer and blocks until
    approval_routes.py resumes the graph with the officer's decision.
    """
    case_summary = {
        "case_id": state.get("case_id"),
        "transaction_id": state.get("transaction_id"),
        "amount": state.get("transaction_amount"),
        "fraud_flag": state.get("fraud_flag"),
        "decision_reason": state.get("decision_reason"),
    }

    # Pauses execution here; resumed via graph.invoke(Command(resume=...))
    # from approval_routes.py once the officer acts.
    officer_decision = interrupt(case_summary)

    logger.info(
        "Officer decision received for case %s: %s",
        state.get("case_id"),
        officer_decision,
    )

    status_map = {
        "approved": "resolved",
        "rejected": "rejected",
        "more_info": "open",
    }

    return {
        "officer_decision": officer_decision,
        "case_status": status_map.get(officer_decision, "open"),
    }
