# Transaction Dispute Resolver

**Autonomous multi-agent AI system for resolving transaction disputes** — from a customer's mistaken-transfer complaint to verified fund recovery, with a real human in the loop where it matters.

---

## 1. Problem

When someone sends money to the wrong UPI ID or bank account by mistake, resolving it today is almost entirely manual. The customer calls their bank, explains what happened, submits proof, and waits — often weeks — while a support team manually checks the transaction, looks up policy rules, decides whether a refund is possible, and chases the recipient. There's no consistency in how fast this happens or how it's decided, and for fraud-flagged or large-amount cases, it isn't clear who's actually accountable for the decision.

## 2. Solution

This project automates that entire process from "customer reports a mistaken transfer" to "money is recovered" — while keeping a real human in the loop for the parts that genuinely need judgment (fraud flags, large amounts). The system reads a receipt, verifies it against real bank records, checks it against actual policy, and either resolves the case autonomously or routes it to a bank officer with everything they need to decide quickly.

## 3. Architecture

Built as a 9-node **LangGraph** multi-agent pipeline, where each stage — OCR extraction, verification, policy retrieval, decision-making, notification, escalation, and fund recovery — is its own node in a persisted state machine, not a single monolithic script.

```
Customer submits receipt (Streamlit)
        │
        ▼
   OCR Agent ── Tesseract + LLM structured extraction (LangChain)
        │
        ▼
Verification Agent ── cross-checks against PostgreSQL (Neon)
        │
        ▼
  Policy Agent ── RAG over policy doc (Pinecone + Gemini embeddings, via LangChain)
        │
        ▼
 Decision Agent ── rule-based routing
        │
   ┌────┼──────────────────┐
   ▼    ▼                  ▼
Reject  Human Review    Notify Receiver
       (Officer Dashboard)      │
                                 ▼
                         Monitor Response
                         (persisted 2-day wait)
                                 │
                          ┌──────┴──────┐
                          ▼             ▼
                      Resolved      Escalation
                                        │
                                        ▼
                                  Seizure Agent
                          (fund transfer + account block)
```

## 4. Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (persistent, Postgres-checkpointed state machine) |
| LLM framework | LangChain (structured output parsing, vector store integration) |
| LLM | OpenAI GPT-4o / Groq Llama (OCR field extraction) |
| Embeddings | Google Gemini (`gemini-embedding-001`) |
| Vector DB | Pinecone |
| Database | PostgreSQL (Neon), SQLAlchemy ORM |
| OCR | Tesseract |
| Frontend | Streamlit (separate customer + officer-dashboard views) |
| Deployment | Docker, Render |

## 5. Key Features

- **Multi-agent pipeline** — OCR, verification, RAG-based policy retrieval, and decision-making as discrete, testable LangGraph nodes.
- **Real human-in-the-loop** — fraud-flagged or high-value cases pause and route to a dedicated officer dashboard (not back to the customer) for Approve / Reject / Request-info.
- **Persisted, genuine waiting periods** — the receiver-response window is a real, checkpointed pause that survives app restarts, not a synchronous timeout.
- **Autonomous fund recovery** — unresolved cases automatically freeze the receiver's account, transfer funds back to the sender, and log a full audit trail.
- **Fallback-safe design** — every LLM/embedding call degrades gracefully to a regex/keyword fallback when API keys aren't configured, so the pipeline keeps running for local development without live credentials.

## 6. Evaluation Results

Tested with a tiered strategy — exhaustive/synthetic tests where possible (free, at scale), real LLM calls kept small and deliberate (cached to avoid repeat API cost):

| Metric | Result | Sample |
|---|---|---|
| Decision-rule coverage | 100% | n=8 (exhaustive — full input space) |
| Financial reconciliation (zero-sum invariant) | 100% pass | n=50 runs |
| Verification accuracy | 100% | n=30 (synthetic) |
| Policy Retrieval Hit Rate@3 | 100% | n=33 (golden query set) |
| Policy Retrieval MRR | 0.91 | n=33 |
| OCR field extraction accuracy | 100% | n=2 (real receipts — small sample, actively expanding) |
| Avg. end-to-end latency | ~12.6s | real LLM + embedding path |

Full evaluation harness: [`app/evals/run_evaluation.py`](app/evals/run_evaluation.py)

## 7. Project Structure

```
app/
├── agents/          # LangGraph nodes (OCR, verification, policy, decision, seizure...)
├── db/              # SQLAlchemy models, Postgres connection, persistent checkpointer
├── evals/           # Evaluation harness + response cache
├── hitl/            # Human-in-the-loop interrupt logic
├── notifications/   # Email/SMS (test-mode by default)
├── ocr/             # Tesseract extraction + LLM/regex field parsing
├── rag/             # Policy document ingestion + Pinecone retrieval
├── scripts/         # check_pending_cases.py — resumes paused cases
└── tools/           # Bank DB operations, policy search
frontend/
├── streamlit_app.py         # Customer-facing intake
└── pages/officer_dashboard.py  # Bank-officer review dashboard
data/sample_dataset/  # Sample customers, transactions, policy doc, eval sets
Dockerfile
requirements.txt
```

## 8. Running Locally

```bash
git clone https://github.com/snehaltengse44/transaction-dispute-resolver.git
cd transaction-dispute-resolver
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # fill in your own DB/API keys
python -m app.db.seed_postgres
streamlit run frontend/streamlit_app.py
```

Runs fully in fallback mode (no live API keys needed) for local testing see `.env.example` for what's required to enable real Postgres, Pinecone, and LLM calls.

## 9. Deployment

Containerized with Docker and deployed on Render (free tier, 512MB). See [`Dockerfile`](Dockerfile).
