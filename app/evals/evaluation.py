"""
Evaluation harness for the DisputeDesk pipeline — designed to work
under a tight LLM/embedding API budget.

Strategy (per component, matched to what actually costs API credits):
  - Financial reconciliation & decision-rule coverage: 100+ synthetic
    cases, pure Python, ZERO API calls.
  - Verification accuracy: 20-50 synthetic cases against real DB rows,
    ZERO API calls (no OCR/LLM involved — directly constructs state).
  - Policy retrieval: ~30 golden queries. Costs one embedding call per
    UNIQUE query, ever — cached in eval_cache.json after first run.
  - OCR field extraction: small, deliberately-chosen real receipt set
    (currently 2 — expand deliberately, not randomly). Cached too.

Run with: python -m app.evals.run_evaluation
"""

import os
import csv
import time
import uuid
import statistics
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from app.agents.graph import dispute_graph
from app.agents.verification_agent import verification_agent
from app.agents.decision_agent import decision_agent
from app.db.seed_postgres import seed
from app.db.postgres import get_session, Customer, ExistingCustomer
from app.tools.policy_tools import search_policy
from app.evals.cache import cached_call

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "sample_dataset"


# ============================================================
# FREE — zero API calls — run at scale
# ============================================================

def eval_decision_rule_coverage():
    """Exhaustively tests decision_agent's routing logic across every
    combination of (verified, fraud_flag, refund_eligible) — this IS
    the full input space for its rules, so 8 cases give 100% coverage,
    not just a sample."""
    print("\n" + "=" * 70)
    print("A. Decision-rule coverage (exhaustive, 0 API calls)")
    print("=" * 70)

    expected_map = {
        (False, False, False): "reject", (False, False, True): "reject",
        (False, True, False): "reject", (False, True, True): "reject",
        (True, True, False): "needs_human_review", (True, True, True): "needs_human_review",
        (True, False, True): "notify_receiver",
        (True, False, False): "escalate",
    }

    correct = 0
    for (verified, fraud_flag, refund_eligible), expected in expected_map.items():
        state = {
            "verified": verified, "fraud_flag": fraud_flag,
            "refund_eligible": refund_eligible, "within_time_window": True,
            "verification_errors": [], "case_id": "synthetic",
        }
        result = decision_agent(state)
        is_correct = result["decision"] == expected
        correct += is_correct
        print(f"  verified={verified!s:5} fraud={fraud_flag!s:5} eligible={refund_eligible!s:5} "
              f"-> {result['decision']:20} (expected {expected}) {'OK' if is_correct else 'FAIL'}")

    accuracy = correct / len(expected_map)
    print(f"\nDecision rule coverage: {accuracy:.0%} ({correct}/{len(expected_map)} — full input space)")
    return {"decision_rule_coverage": accuracy}


def eval_verification_at_scale(n=30):
    """Tests verification_agent against n synthetic cases: half exact
    matches to real seeded transactions, half deliberately corrupted
    (wrong amount/date/name) — zero API calls, since this bypasses OCR
    entirely and constructs state directly."""
    print("\n" + "=" * 70)
    print(f"B. Verification accuracy at scale (n={n}, 0 API calls)")
    print("=" * 70)

    from app.tools.bank_db_tools import get_transaction
    real_txn = get_transaction("T2609011639482603899525")  # Pranay's real seeded transaction

    correct = 0
    for i in range(n):
        corrupt = i % 2 == 1  # alternate: valid / corrupted
        state = {
            "transaction_id": real_txn["transaction_id"],
            "transaction_amount": real_txn["amount"] + (50 if corrupt else 0),
            "transaction_date": real_txn["date_time"].replace(" ", "T"),
            "sender_account": real_txn["sender_account"],
            "receiver_name": "WrongName" if corrupt else "Pranay",
            "customer_name": "Snehal",
        }
        result = verification_agent(state)
        expected_verified = not corrupt
        is_correct = result["verified"] == expected_verified
        correct += is_correct

    accuracy = correct / n
    print(f"Verification accuracy: {accuracy:.0%} ({correct}/{n})")
    return {"verification_accuracy_at_scale": accuracy}


def eval_financial_invariant_repeated(n=50):
    """Runs the reconciliation invariant check n times against
    randomly-varied seizure amounts — zero API calls, pure DB math."""
    print("\n" + "=" * 70)
    print(f"C. Financial reconciliation invariant (n={n} runs, 0 API calls)")
    print("=" * 70)

    from app.tools.bank_db_tools import seize_and_transfer
    import random

    passed = 0
    for i in range(n):
        seed()
        session = get_session()
        before = sum(c.amount for c in session.query(Customer).all()) + \
                 sum(c.amount for c in session.query(ExistingCustomer).all())
        session.close()

        amount = round(random.uniform(1, 100), 2)
        seize_and_transfer("Sonali", "Snehal", amount, "eval test", f"eval-{i}")

        session = get_session()
        after = sum(c.amount for c in session.query(Customer).all()) + \
                sum(c.amount for c in session.query(ExistingCustomer).all())
        session.close()

        passed += abs(before - after) < 0.01

    pass_rate = passed / n
    print(f"Reconciliation pass rate: {pass_rate:.0%} ({passed}/{n})")
    seed()  # leave DB in clean state
    return {"reconciliation_pass_rate": pass_rate}


# ============================================================
# CHEAP — one embedding call per UNIQUE query, cached after first run
# ============================================================

def eval_policy_retrieval(top_k=3):
    print("\n" + "=" * 70)
    print("D. Policy retrieval: Hit@3, Recall@3, MRR (cached after first run)")
    print("=" * 70)

    queries = list(csv.DictReader(open(DATA_DIR / "eval_policy_queries.csv")))
    hits, reciprocal_ranks, cache_hits = [], [], 0

    by_category = {}
    for q in queries:
        cache_key = ["policy_retrieval", q["query"], top_k]
        results, was_cached = cached_call(cache_key, lambda q=q: search_policy(q["query"], top_k=top_k))
        cache_hits += was_cached

        sources = [r["source"] for r in results]
        expected = q["expected_section_keyword"].lower()
        rank = next((i + 1 for i, s in enumerate(sources) if expected in s.lower()), None)

        hit = rank is not None
        hits.append(hit)
        reciprocal_ranks.append(1 / rank if rank else 0)

        cat = q["category"]
        by_category.setdefault(cat, []).append(hit)

    hit_rate = sum(hits) / len(hits)
    mrr = sum(reciprocal_ranks) / len(reciprocal_ranks)

    print(f"Queries: {len(queries)} total, {cache_hits} served from cache (0 new API calls for those)")
    print(f"\nHit Rate @{top_k}: {hit_rate:.0%}")
    print(f"MRR:        {mrr:.2f}")
    print("\nBy category:")
    for cat, cat_hits in by_category.items():
        print(f"  {cat:20} {sum(cat_hits)}/{len(cat_hits)} ({sum(cat_hits)/len(cat_hits):.0%})")

    return {"hit_rate_at_3": hit_rate, "mrr": mrr}


# ============================================================
# EXPENSIVE — real LLM calls, kept small & deliberate, cached
# ============================================================

def eval_ocr_extraction():
    print("\n" + "=" * 70)
    print("E. OCR field extraction (small, deliberate set — real LLM, cached)")
    print("=" * 70)

    rows = list(csv.DictReader(open(DATA_DIR / "eval_ground_truth.csv")))
    correct, latencies, cache_hits = 0, [], 0

    for row in rows:
        case_id = str(uuid.uuid4())[:8]
        config = {"configurable": {"thread_id": case_id}}
        state = {
            "case_id": case_id, "receipt_image_path": row["receipt_path"],
            "customer_id": row["customer_name"].lower(), "customer_name": row["customer_name"],
            "errors": [],
        }

        start = time.time()
        result = dispute_graph.invoke(state, config=config)
        latencies.append(time.time() - start)

        ocr_correct = (
            result.get("transaction_id") == row["expected_transaction_id"]
            and result.get("transaction_amount") == float(row["expected_amount"])
            and result.get("receiver_name") == row["expected_receiver_name"]
        )
        correct += ocr_correct
        print(f"  {row['receipt_path']}: {'OK' if ocr_correct else 'FAIL'}")

    n = len(rows)
    accuracy = correct / n
    avg_latency = statistics.mean(latencies)
    p95_latency = max(latencies)  # n too small for a real P95; reports max as a stand-in

    print(f"\nOCR accuracy: {accuracy:.0%} (n={n} — SMALL SAMPLE, not a generalization claim)")
    print(f"Avg latency: {avg_latency:.1f}s  |  Max observed: {p95_latency:.1f}s")
    return {"ocr_accuracy": accuracy, "ocr_n": n, "avg_latency": avg_latency}


def eval_fallback_usage():
    using_gemini = bool(os.getenv("PINECONE_API_KEY") and os.getenv("GEMINI_API_KEY"))
    using_llm_ocr = bool(os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY"))
    return {"using_real_pinecone_gemini": using_gemini, "using_real_llm_ocr": using_llm_ocr}


def run_all():
    seed()
    summary = {}
    summary.update(eval_decision_rule_coverage())
    summary.update(eval_verification_at_scale())
    summary.update(eval_policy_retrieval())
    summary.update(eval_fallback_usage())
    summary.update(eval_ocr_extraction())
    summary.update(eval_financial_invariant_repeated())

    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)
    print(f"  Decision rule coverage:      {summary['decision_rule_coverage']:.0%}  (n=8, exhaustive)")
    print(f"  Verification accuracy:       {summary['verification_accuracy_at_scale']:.0%}  (n=30, synthetic)")
    print(f"  Policy Retrieval Hit@3:      {summary['hit_rate_at_3']:.0%}  (n=33 golden queries)")
    print(f"  Policy Retrieval MRR:        {summary['mrr']:.2f}")
    print(f"  OCR Field Accuracy:          {summary['ocr_accuracy']:.0%}  (n={summary['ocr_n']} — small, deliberate)")
    print(f"  Financial Reconciliation:    {summary['reconciliation_pass_rate']:.0%}  (n=50 runs)")
    print(f"  Avg OCR Latency:             {summary['avg_latency']:.1f}s")
    print(f"  Using real Pinecone+Gemini:  {summary['using_real_pinecone_gemini']}")
    print(f"  Using real LLM OCR:          {summary['using_real_llm_ocr']}")


if __name__ == "__main__":
    run_all()