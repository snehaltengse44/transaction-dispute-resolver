"""
Loads customers.csv and transactions.csv into the configured database
(Postgres in production, SQLite locally via DATABASE_URL) using the
SQLAlchemy models in app/db/postgres.py. Replaces seed_sqlite.py.

Run with: python -m app.db.seed_postgres
"""

import csv
from pathlib import Path

from app.db.postgres import init_db, get_session, Customer, Transaction, ExistingCustomer

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "sample_dataset"


def seed():
    init_db()
    session = get_session()

    # Full reset — including existing_customer, so a re-seed gives you a
    # clean slate for testing (e.g. re-running seizure on the same
    # receiver without hitting a duplicate-key error from a previous run).
    session.query(Customer).delete()
    session.query(Transaction).delete()
    session.query(ExistingCustomer).delete()

    with open(DATA_DIR / "customers.csv", newline="") as f:
        for row in csv.DictReader(f):
            session.add(Customer(
                customer_name=row["customer_name"],
                bank_account_number=row["bank_account_number"],
                mobile_no=row["mobile_no"],
                email=row["email"],
                address=row["address"],
                amount=float(row["amount"]),
            ))

    with open(DATA_DIR / "transactions.csv", newline="") as f:
        for row in csv.DictReader(f):
            session.add(Transaction(
                transaction_id=row["transaction_id"],
                amount=float(row["amount"]),
                date_time=row["date_time"],
                receiver_name=row["receiver_name"],
                sender_name=row["sender_name"],
                refund_received=0,
            ))

    session.commit()
    session.close()
    print(f"Seeded database at {__import__('os').getenv('DATABASE_URL', 'sqlite:///./app/db/dev.db')}")


if __name__ == "__main__":
    seed()