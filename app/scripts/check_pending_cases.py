"""
Checks a paused case's response deadline and only resumes it if that
deadline has genuinely passed. Once an interrupt() is resumed with any
value it unblocks unconditionally — it will NOT re-pause itself even
if called too early — so the "has enough real time passed?" check
must happen here, before deciding to resume at all, not inside the
node.

In production, schedule this to run periodically (e.g. daily via
Windows Task Scheduler / cron) over your list of open case IDs. For
testing, run it manually anytime.

Run with: python -m app.scripts.check_pending_cases <thread_id>
"""

import sys
from datetime import datetime
from langgraph.types import Command
from app.agents.graph import dispute_graph


def resume_case(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = dispute_graph.get_state(config)

    pending_interrupt = None
    for task in snapshot.tasks:
        if task.interrupts:
            pending_interrupt = task.interrupts[0].value
            break

    if pending_interrupt is None:
        print(f"Case {thread_id}: no pending interrupt (already resolved, or not paused).")
        return None

    deadline = datetime.fromisoformat(pending_interrupt["response_deadline"])
    now = datetime.utcnow()

    if now < deadline:
        print(f"Case {thread_id}: still within window until {deadline.isoformat()} — not resuming.")
        return None

    print(f"Case {thread_id}: window elapsed ({deadline.isoformat()}) — resuming.")
    result = dispute_graph.invoke(Command(resume="deadline_check"), config=config)

    if "__interrupt__" in result:
        print(f"Case {thread_id} still paused: {result['__interrupt__'][0].value}")
    else:
        print(f"Case {thread_id} resolved. case_status={result.get('case_status')}")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m app.scripts.check_pending_cases <thread_id>")
        sys.exit(1)
    resume_case(sys.argv[1])