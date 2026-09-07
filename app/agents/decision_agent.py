"""
5. Decision Engine

Combines the verification and policy results into a single decision.
This node is intentionally rule-first (deterministic, auditable) with
the LLM used only to draft a human-readable rationale — the *decision*
itself should never depend on an LLM's whim in a financial workflow.
"""

import logging

from app.agents.state import DisputeCaseState

logger = logging.getLogger(__name__)


def decision_agent(state: DisputeCaseState) -> dict:
    """
    LangGraph node. Returns the routing decision consumed by the
    conditional edges in graph.py.
    """
    verified = state.get("verified", False)
    refund_eligible = state.get("refund_eligible", False)
    fraud_flag = state.get("fraud_flag", False)

    if not verified:
        decision = "reject"
        reason = (
            "Transaction could not be verified against bank records: "
            f"{state.get('verification_errors')}"
        )

    elif fraud_flag:
        decision = "needs_human_review"
        reason = "Transaction flagged by fraud heuristics; requires officer review."

    elif refund_eligible:
        # Route to the receiver first — give Person B a chance to return
        # funds voluntarily before any account action is taken.
        decision = "notify_receiver"
        reason = "Verified and within policy window; requesting voluntary return from receiver."

    else:
        decision = "escalate"
        reason = (
            "Verified but not eligible under current policy "
            f"(within_window={state.get('within_time_window')}); escalating for manual bank action."
        )

    logger.info(
        "Decision for case %s: %s (%s)", state.get("case_id"), decision, reason
    )

    return {
        "decision": decision,
        "decision_reason": reason,
        "case_status": "open",
    }
