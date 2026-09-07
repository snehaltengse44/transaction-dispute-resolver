"""
4. Policy & Rule Check

Runs a RAG query against the ingested refund-policy documents to
determine eligibility, checks the time window, and applies simple
fraud heuristics. Every eligibility claim carries a citation back to
the source policy chunk so the decision agent (and a human reviewer)
can audit *why* the system decided what it decided.
"""

import logging
from datetime import datetime, timedelta

from app.agents.state import DisputeCaseState
from app.tools.policy_tools import search_policy

logger = logging.getLogger(__name__)

REFUND_WINDOW_DAYS = 15


def _within_time_window(transaction_date: str) -> bool:
    try:
        txn_dt = datetime.fromisoformat(transaction_date)
    except (TypeError, ValueError):
        return False
    return datetime.utcnow() - txn_dt <= timedelta(days=REFUND_WINDOW_DAYS)


def _check_fraud_indicators(state: DisputeCaseState) -> bool:
    """Lightweight heuristic checks; extend with a real fraud model later."""
    amount = state.get("transaction_amount") or 0
    # Flag unusually large mistaken-transfer claims for extra scrutiny.
    return amount > 100_000


def policy_agent(state: DisputeCaseState) -> dict:
    """
    LangGraph node. Determines refund eligibility against bank policy.
    """
    transaction_date = state.get("transaction_date")
    within_window = _within_time_window(transaction_date) if transaction_date else False
    fraud_flag = _check_fraud_indicators(state)

    query = (
        f"refund eligibility for mistaken transfer, amount="
        f"{state.get('transaction_amount')}, within_window={within_window}"
    )
    policy_hits = search_policy(query, top_k=3)
    citations = [hit["source"] for hit in policy_hits]

    # Eligibility requires: verified transaction, within time window,
    # not flagged for fraud, and policy retrieval finding supporting rules.
    refund_eligible = bool(
        state.get("verified")
        and within_window
        and not fraud_flag
        and len(policy_hits) > 0
    )

    logger.info(
        "Policy check for case %s: eligible=%s within_window=%s fraud_flag=%s",
        state.get("case_id"),
        refund_eligible,
        within_window,
        fraud_flag,
    )

    return {
        "within_time_window": within_window,
        "refund_eligible": refund_eligible,
        "fraud_flag": fraud_flag,
        "policy_citations": citations,
    }
