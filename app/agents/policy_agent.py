"""
4. Policy & Rule Check

Runs a RAG query against the ingested refund-policy documents to
determine eligibility, checks the time window (with the three real
buckets your policy doc defines, not just a binary in/out), and
applies simple fraud heuristics. Every eligibility claim carries a
citation back to the source policy chunk.
"""

import os
import logging
from datetime import datetime

from app.agents.state import DisputeCaseState
from app.tools.policy_tools import search_policy

logger = logging.getLogger(__name__)

REFUND_WINDOW_DAYS = int(os.getenv("REFUND_WINDOW_DAYS", "15"))
MANUAL_REVIEW_WINDOW_DAYS = int(os.getenv("MANUAL_REVIEW_WINDOW_DAYS", "30"))


def _classify_time_window(transaction_date: str) -> str:
    """
    Returns one of: 'within_window', 'manual_review_window', 'expired'.
    Matches Section 5 of the policy doc:
      - within REFUND_WINDOW_DAYS: standard refund workflow
      - between REFUND_WINDOW_DAYS and MANUAL_REVIEW_WINDOW_DAYS:
        requires manual officer approval regardless of other checks
      - beyond MANUAL_REVIEW_WINDOW_DAYS: not eligible
    """
    try:
        txn_dt = datetime.fromisoformat(transaction_date)
    except (TypeError, ValueError):
        return "expired"

    days_elapsed = (datetime.utcnow() - txn_dt).days

    if days_elapsed <= REFUND_WINDOW_DAYS:
        return "within_window"
    if days_elapsed <= MANUAL_REVIEW_WINDOW_DAYS:
        return "manual_review_window"
    return "expired"


def _check_fraud_indicators(state: DisputeCaseState) -> bool:
    amount = state.get("transaction_amount") or 0
    threshold = float(os.getenv("FRAUD_AMOUNT_THRESHOLD", "100000"))
    return amount > threshold


def policy_agent(state: DisputeCaseState) -> dict:
    transaction_date = state.get("transaction_date")
    window_status = _classify_time_window(transaction_date) if transaction_date else "expired"
    fraud_flag = _check_fraud_indicators(state)

    query = (
        f"refund eligibility for mistaken transfer, amount="
        f"{state.get('transaction_amount')}, window_status={window_status}"
    )
    policy_hits = search_policy(query, top_k=3)
    citations = [hit["source"] for hit in policy_hits]

    within_time_window = window_status == "within_window"
    refund_eligible = bool(
        state.get("verified")
        and within_time_window
        and not fraud_flag
        and len(policy_hits) > 0
    )

    logger.info(
        "Policy check for case %s: window_status=%s eligible=%s fraud_flag=%s",
        state.get("case_id"), window_status, refund_eligible, fraud_flag,
    )

    return {
        "within_time_window": within_time_window,
        "time_window_status": window_status,
        "refund_eligible": refund_eligible,
        "fraud_flag": fraud_flag,
        "policy_citations": citations,
    }