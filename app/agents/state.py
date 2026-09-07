"""
Shared state object passed between all LangGraph nodes in the DisputeDesk graph.

Every agent reads from and writes to this single TypedDict. LangGraph merges
partial updates returned by each node into this state automatically.
"""

from typing import TypedDict, Optional, Literal


class DisputeCaseState(TypedDict, total=False):
    # --- Input ---
    case_id: str
    receipt_image_path: str
    customer_id: str  # Person A
    customer_name: Optional[str]
    issue_description: Optional[str]

    # --- 2. OCR & Data Extraction ---
    ocr_raw_text: str
    transaction_id: Optional[str]
    transaction_date: Optional[str]
    transaction_amount: Optional[float]
    sender_account: Optional[str]   # Person A
    receiver_account: Optional[str]  # Person B
    receiver_name: Optional[str]
    ocr_confidence: Optional[float]

    # --- 3. Data Verification ---
    verified: Optional[bool]
    verification_errors: list[str]
    actual_recipient_intended: Optional[str]  # Person C, if known

    # --- 4. Policy & Rule Check ---
    within_time_window: Optional[bool]
    refund_eligible: Optional[bool]
    fraud_flag: Optional[bool]
    policy_citations: list[str]

    # --- 5. Decision Engine ---
    decision: Optional[
        Literal[
            "approve_refund",
            "notify_receiver",
            "escalate",
            "reject",
            "needs_human_review",
        ]
    ]
    decision_reason: Optional[str]

    # --- 6/7/8. Human-in-the-loop / Notification / Escalation ---
    officer_decision: Optional[Literal["approved", "rejected", "more_info"]]
    receiver_notified: Optional[bool]
    receiver_notified_at: Optional[str]
    receiver_responded: Optional[bool]
    receiver_refunded: Optional[bool]
    case_status: Optional[
        Literal["open", "resolved", "escalated", "closed", "rejected"]
    ]

    # --- Guardrail / audit trail ---
    errors: list[str]