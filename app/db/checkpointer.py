"""
Builds the LangGraph checkpointer used to persist case state across
process restarts — required for genuine multi-day waits (e.g. giving
Person B 2 days to voluntarily return funds) since a case may be
paused now and only resumed after the app has been restarted several
times.

Uses Postgres (same DATABASE_URL as the rest of the app) when
available, falling back to a local SQLite file for development
without a live Postgres connection.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app/db/dev.db")


def build_checkpointer():
    if DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres"):
        from psycopg import Connection
        from langgraph.checkpoint.postgres import PostgresSaver

        # psycopg (v3) accepts the same DSN format used elsewhere.
        conn = Connection.connect(DATABASE_URL, autocommit=True, prepare_threshold=0)
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
        return checkpointer

    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path = Path(__file__).parent / "checkpoints.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return checkpointer