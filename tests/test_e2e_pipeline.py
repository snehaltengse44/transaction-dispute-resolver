"""
End-to-end pipeline test: runs the real receipt images through OCR ->
verification -> policy check -> decision -> notify/escalate, using the
locally-seeded SQLite DB and the actual policy .docx.

This exercises every node in app/agents/graph.py with real (not
mocked) logic — only external paid services (email/SMS/LLM API calls)
are stubbed to print instead of calling out.

Run with: python -m tests.test_e2e_pipeline
"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.types import Command
from app.agents.graph import dispute_graph
from app.db.seed_postgres import seed

RECEIPTS = [
    ("data/sample_receipts/receipt_pranay.png", "Snehal"),   # amount 300 -> should be refund-eligible
    ("data/sample_receipts/receipt_sonali.png", "Snehal"),   # amount 40  -> should be refund-eligible
]


def run_case(receipt_path: str, customer_name: str):
    case_id = str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": case_id}}

    initial_state = {
        "case_id": case_id,
        "receipt_image_path": receipt_path,
        "customer_id": customer_name.lower(),
        "customer_name": customer_name,
        "errors": [],
    }

    print(f"\n{'=' * 70}")
    print(f"CASE {case_id}  ({receipt_path})")
    print("=" * 70)

    result = dispute_graph.invoke(initial_state, config=config)

    # If the graph paused at human_review, LangGraph surfaces it via
    # __interrupt__ in the result rather than raising.
    if "__interrupt__" in result:
        interrupt_payload = result["__interrupt__"][0].value
        print(f"\n[PAUSED] Human review requested: {interrupt_payload}")
        print("[TEST MODE] Auto-approving as officer to continue the run...")
        result = dispute_graph.invoke(Command(resume="approved"), config=config)

    print("\n--- Final state ---")
    for key in [
        "transaction_id", "transaction_amount", "verified",
        "verification_errors", "within_time_window", "refund_eligible",
        "fraud_flag", "policy_citations", "decision", "decision_reason",
        "receiver_notified", "case_status",
    ]:
        print(f"  {key}: {result.get(key)}")

    return result


if __name__ == "__main__":
    print("Seeding local SQLite DB from sample_dataset CSVs...")
    seed()

    for receipt, customer_name in RECEIPTS:
        run_case(receipt, customer_name)
