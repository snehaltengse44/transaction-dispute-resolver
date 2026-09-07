"""
3. Data Verification

Cross-checks OCR-extracted transaction fields against the bank's own
records (Postgres) via the bank_db_tools. If anything mismatches, the
case is flagged so the graph can route straight to a rejection/notify
step instead of continuing.
"""

import logging

from app.agents.state import DisputeCaseState
from app.tools.bank_db_tools import get_transaction, verify_account

logger = logging.getLogger(__name__)


def verification_agent(state: DisputeCaseState) -> dict:
    """
    LangGraph node. Verifies transaction_id, amount, date, and both
    accounts against the database of record.
    """
    errors: list[str] = []
    transaction_id = state.get("transaction_id")

    if not transaction_id:
        return {
            "verified": False,
            "verification_errors": ["missing_transaction_id"],
        }

    db_txn = get_transaction(transaction_id)
    if db_txn is None:
        return {
            "verified": False,
            "verification_errors": ["transaction_not_found_in_db"],
        }

    # Amount check (allow tiny float rounding tolerance)
    ocr_amount = state.get("transaction_amount")
    if ocr_amount is None or abs(ocr_amount - db_txn["amount"]) > 0.01:
        errors.append("amount_mismatch")

    # Date check. OCR gives a full timestamp; the DB record here is
    # date-only, so compare on the date portion rather than the full
    # ISO string.
    ocr_date = state.get("transaction_date")
    ocr_date_only = ocr_date.split("T")[0] if ocr_date else None
    if ocr_date_only != db_txn["date"]:
        errors.append("date_mismatch")

    # Sender account check: OCR reliably extracts the debited-from
    # account, so we can validate and cross-check it directly.
    sender_ok = verify_account(state.get("sender_account"), role="sender")
    if not sender_ok:
        errors.append("sender_account_invalid")
    if db_txn.get("sender_account") != state.get("sender_account"):
        errors.append("sender_account_mismatch")

    # Receiver check: UPI receipts generally do NOT expose the
    # receiver's own bank account number (only their name/phone/UPI
    # handle), so we verify by name instead of account number here.
    # If a receiver_account IS present (e.g. a different receipt
    # format that shows it), cross-check it too.
    ocr_receiver_name = (state.get("receiver_name") or "").strip().lower()
    db_receiver_name = (db_txn.get("receiver_name") or "").strip().lower()
    if not ocr_receiver_name or ocr_receiver_name not in db_receiver_name:
        errors.append("receiver_name_mismatch")

    if state.get("receiver_account") and db_txn.get("receiver_account") != state.get("receiver_account"):
        errors.append("receiver_account_mismatch")

    verified = len(errors) == 0

    logger.info(
        "Verification for case %s: verified=%s errors=%s",
        state.get("case_id"),
        verified,
        errors,
    )

    return {
        "verified": verified,
        "verification_errors": errors,
    }
