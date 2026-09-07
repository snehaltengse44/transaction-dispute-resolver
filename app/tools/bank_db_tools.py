"""
Plain function tools bound to LangGraph agents for reading/writing the
bank's database — now backed by SQLAlchemy (Postgres in production,
SQLite locally via DATABASE_URL), replacing the earlier raw-SQLite /
direct-CSV-mutation implementation.
"""

from datetime import datetime
from typing import Optional

from app.db.postgres import get_session, Customer, ExistingCustomer, Transaction


def get_transaction(transaction_id: str) -> Optional[dict]:
    """Fetch a transaction record by ID. Returns None if not found."""
    session = get_session()
    try:
        txn = session.query(Transaction).filter_by(transaction_id=transaction_id).first()
        if txn is None:
            return None

        result = {
            "transaction_id": txn.transaction_id,
            "amount": txn.amount,
            "date_time": txn.date_time,
            "receiver_name": txn.receiver_name,
            "sender_name": txn.sender_name,
            "refund_received": txn.refund_received,
            "date": txn.date_time.split(" ")[0],
        }

        sender = session.query(Customer).filter_by(customer_name=txn.sender_name).first()
        receiver = session.query(Customer).filter_by(customer_name=txn.receiver_name).first()
        result["sender_account"] = sender.bank_account_number if sender else None
        result["receiver_account"] = receiver.bank_account_number if receiver else None
        return result
    finally:
        session.close()


def verify_account(account_number: Optional[str], role: str) -> bool:
    """Checks whether an account number is known to the bank."""
    if not account_number:
        return False
    session = get_session()
    try:
        return session.query(Customer).filter_by(bank_account_number=account_number).first() is not None
    finally:
        session.close()


def freeze_account(account_number: str) -> bool:
    """Freeze an account pending dispute resolution (logged only in test mode)."""
    print(f"[TEST MODE] Would freeze account: {account_number}")
    return True


def get_customer_by_name(customer_name: str) -> Optional[dict]:
    session = get_session()
    try:
        row = session.query(Customer).filter(
            Customer.customer_name.ilike(f"%{customer_name}%")
        ).first()
        if row is None:
            return None
        return {
            "customer_name": row.customer_name,
            "bank_account_number": row.bank_account_number,
            "mobile_no": row.mobile_no,
            "email": row.email,
            "address": row.address,
            "amount": row.amount,
        }
    finally:
        session.close()


def seize_and_transfer(
    receiver_name: str,
    sender_name: str,
    amount: float,
    reason: str,
    case_id: str,
) -> dict:
    """
    Bank Action (box 8): deducts `amount` from Person B's balance and
    credits it to Person A's balance, then moves Person B's full
    record out of the customers table into existing_customer (i.e.
    blocks/seizes their account) with an audit trail.

    Uses substring matching on name since OCR often only captures a
    first name while the DB holds the full legal name.
    """
    session = get_session()
    try:
        receiver = session.query(Customer).filter(
            Customer.customer_name.ilike(f"%{receiver_name}%")
        ).first()
        sender = session.query(Customer).filter(
            Customer.customer_name.ilike(f"%{sender_name}%")
        ).first()

        if receiver is None:
            return {"success": False, "error": f"receiver_not_found: {receiver_name}"}
        if sender is None:
            return {"success": False, "error": f"sender_not_found: {sender_name}"}

        if receiver.amount < amount:
            return {
                "success": False,
                "error": "insufficient_receiver_balance",
                "receiver_balance": receiver.amount,
                "amount_requested": amount,
            }

        receiver_balance_before = receiver.amount
        new_receiver_balance = receiver_balance_before - amount
        new_sender_balance = sender.amount + amount

        sender.amount = new_sender_balance

        blocked = ExistingCustomer(
            customer_name=receiver.customer_name,
            bank_account_number=receiver.bank_account_number,
            mobile_no=receiver.mobile_no,
            email=receiver.email,
            address=receiver.address,
            amount=new_receiver_balance,
            blocked_reason=reason,
            blocked_date=datetime.utcnow(),
            case_id=case_id,
        )
        session.add(blocked)
        session.delete(receiver)
        session.commit()

        return {
            "success": True,
            "receiver_name": receiver_name,
            "sender_name": sender_name,
            "amount_transferred": amount,
            "receiver_balance_before": receiver_balance_before,
            "receiver_balance_after": new_receiver_balance,
            "sender_balance_after": new_sender_balance,
            "account_blocked": True,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
