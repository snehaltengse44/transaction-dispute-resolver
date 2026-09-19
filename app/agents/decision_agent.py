"""
5. Decision Engine

Combines verification and policy results into a routing decision.
Rule-first and deterministic — the LLM is not involved in the
decision itself, only in earlier extraction/retrieval steps.
"""

import logging

from app.agents.state import DisputeCaseState

logger = logging.getLogger(__name__)


def decision_agent(state: DisputeCaseState) -> dict:
    verified = state.get("verified", False)
    refund_eligible = state.get("refund_eligible", False)
    fraud_flag = state.get("fraud_flag", False)
    window_status = state.get("time_window_status", "expired")

    if not verified:
        decision = "reject"
        reason = (
            "Transaction could not be verified against bank records: "
            f"{state.get('verification_errors')}"
        )

    elif fraud_flag:
        decision = "needs_human_review"
        reason = "Transaction flagged by fraud heuristics; requires officer review."

    elif window_status == "manual_review_window":
        # Policy Section 5: 15-30 days requires manual officer approval
        # regardless of other checks — this is a policy requirement,
        # not a fraud signal, so it's tagged separately for the
        # customer-facing message.
        decision = "needs_human_review"
        reason = (
            "Verified, but outside the standard refund window and within "
            "the manual-review window (15-30 days) — policy requires "
            "officer approval regardless of other checks."
        )

    elif window_status == "expired":
        decision = "reject"
        reason = (
            "Verified, but beyond the 30-day manual-review window. "
            "Not eligible for automated or manual refund under current policy."
        )

    elif refund_eligible:
        decision = "notify_receiver"
        reason = "Verified and within policy window; requesting voluntary return from receiver."

    else:
        decision = "escalate"
        reason = (
            "Verified but not eligible under current policy "
            f"(refund_eligible=False, window_status={window_status}); escalating for manual bank action."
        )

    logger.info("Decision for case %s: %s (%s)", state.get("case_id"), decision, reason)

    return {
        "decision": decision,
        "decision_reason": reason,
        "case_status": "open",
    }