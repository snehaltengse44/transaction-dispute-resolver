"""
SQLAlchemy models + connection layer for PostgreSQL.

Reads DATABASE_URL from .env. Works against any SQLAlchemy-supported
dialect — during local development you can point this at SQLite
(sqlite:///./app/db/dev.db) with zero code changes, then switch
DATABASE_URL to a real Postgres connection string for production.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app/db/dev.db")

# check_same_thread only applies to SQLite; harmless to pass for Postgres
# since it's filtered out by the dialect, but safer to conditionally set it.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    customer_name = Column(String, primary_key=True)
    bank_account_number = Column(String, nullable=False)
    mobile_no = Column(String)
    email = Column(String)
    address = Column(String)
    amount = Column(Float, nullable=False)


class ExistingCustomer(Base):
    """Blocked/seized accounts — mirrors Customer plus an audit trail."""
    __tablename__ = "existing_customer"

    customer_name = Column(String, primary_key=True)
    bank_account_number = Column(String, nullable=False)
    mobile_no = Column(String)
    email = Column(String)
    address = Column(String)
    amount = Column(Float, nullable=False)
    blocked_reason = Column(String)
    blocked_date = Column(DateTime, default=datetime.utcnow)
    case_id = Column(String)


class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(String, primary_key=True)
    amount = Column(Float, nullable=False)
    date_time = Column(String, nullable=False)
    receiver_name = Column(String, nullable=False)
    sender_name = Column(String, nullable=False)
    refund_received = Column(Float, default=0)  # 0/1 flag, kept as Float for SQLite/PG parity


def get_session():
    """Yields a session; caller is responsible for closing it."""
    return SessionLocal()


def init_db():
    """Creates all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)
