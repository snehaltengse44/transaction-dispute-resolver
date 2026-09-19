"""
LangGraph StateGraph definition for DisputeDesk.

  complaint -> ocr -> verification -> policy -> decision
                                                    |
                    +-------------------------------+-------------------------------+
                    |                               |                               |
              needs_human_review              notify_receiver                    reject
                    |                               |                               |
              human_review (HITL)            monitor_response                    END
              /        |        \\               /            \\
         approved  rejected  more_info      resolved        escalate
             |         |         |             |                |
      notify_receiver END       END           END        escalation -> seizure -> END
"""

import logging

from langgraph.graph import StateGraph, END

from app.agents.state import DisputeCaseState
from app.agents.ocr_agent import ocr_agent
from app.agents.verification_agent import verification_agent
from app.agents.policy_agent import policy_agent
from app.agents.decision_agent import decision_agent
from app.agents.notification_agent import (
    notify_receiver_node,
    monitor_response_node,
    escalation_node,
)
from app.agents.seizure_agent import seizure_node
from app.hitl.interrupts import human_review_node

logger = logging.getLogger(__name__)


def route_after_decision(state: DisputeCaseState) -> str:
    decision = state.get("decision")
    mapping = {
        "reject": "end_rejected",
        "needs_human_review": "human_review",
        "notify_receiver": "notify_receiver",
        "escalate": "escalation",
        "approve_refund": "end_approved",
    }
    return mapping.get(decision, "end_rejected")


def route_after_human_review(state: DisputeCaseState) -> str:
    """
    Conditional edge out of human_review — this is the piece that was
    missing before: officer_decision was being recorded but never
    actually routed anywhere, so approving a case did nothing beyond
    marking a status field.

    approved   -> notify_receiver (give the receiver a chance to
                  voluntarily return the funds, same as the normal
                  eligible path)
    rejected   -> END (customer already notified inside human_review_node)
    more_info  -> END (customer already notified; re-submission isn't
                  wired yet — see Known Limitations)
    """
    officer_decision = state.get("officer_decision")
    if officer_decision == "approved":
        return "notify_receiver"
    return "end"


def route_after_monitor(state: DisputeCaseState) -> str:
    if state.get("receiver_refunded"):
        return "resolved"
    return "escalation"


def build_graph():
    graph = StateGraph(DisputeCaseState)

    graph.add_node("ocr", ocr_agent)
    graph.add_node("verification", verification_agent)
    graph.add_node("policy", policy_agent)
    graph.add_node("decision", decision_agent)
    graph.add_node("human_review", human_review_node)
    graph.add_node("notify_receiver", notify_receiver_node)
    graph.add_node("monitor_response", monitor_response_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("seizure", seizure_node)

    graph.set_entry_point("ocr")
    graph.add_edge("ocr", "verification")
    graph.add_edge("verification", "policy")
    graph.add_edge("policy", "decision")

    graph.add_conditional_edges(
        "decision",
        route_after_decision,
        {
            "end_rejected": END,
            "human_review": "human_review",
            "notify_receiver": "notify_receiver",
            "escalation": "escalation",
            "end_approved": END,
        },
    )

    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "notify_receiver": "notify_receiver",
            "end": END,
        },
    )

    graph.add_edge("notify_receiver", "monitor_response")

    graph.add_conditional_edges(
        "monitor_response",
        route_after_monitor,
        {
            "resolved": END,
            "escalation": "escalation",
        },
    )

    graph.add_edge("escalation", "seizure")
    graph.add_edge("seizure", END)

    from app.db.checkpointer import build_checkpointer
    checkpointer = build_checkpointer()

    return graph.compile(checkpointer=checkpointer)


dispute_graph = build_graph()