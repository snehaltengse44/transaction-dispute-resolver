"""
Policy retrieval helper used by policy_agent.

Production version queries Pinecone (see app/rag/retriever.py). For
local pipeline testing — without needing a live Pinecone index — this
extracts the policy .docx into sections and does simple keyword
overlap scoring, which is enough to validate the graph's control flow
end-to-end before wiring in real embeddings.
"""

import re
from pathlib import Path
from typing import List, Dict
from docx import Document

POLICY_PATH = Path(__file__).parent.parent.parent / "data" / "sample_dataset" / "fraud_and_refund_policy.docx"

_SECTION_CACHE: List[Dict] = []


def _load_sections() -> List[Dict]:
    global _SECTION_CACHE
    if _SECTION_CACHE:
        return _SECTION_CACHE

    doc = Document(POLICY_PATH)
    sections = []
    current_heading = "General"
    current_text = []

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ""
        if style_name.startswith("Heading"):
            if current_text:
                sections.append({"source": current_heading, "text": " ".join(current_text)})
            current_heading = para.text.strip()
            current_text = []
        elif para.text.strip():
            current_text.append(para.text.strip())

    if current_text:
        sections.append({"source": current_heading, "text": " ".join(current_text)})

    _SECTION_CACHE = sections
    return sections


def search_policy(query: str, top_k: int = 3) -> List[Dict]:
    """
    Returns top_k policy chunks relevant to the query, each with at
    least a 'text' and 'source' key. Uses keyword overlap scoring as a
    stand-in for real embedding similarity — swap for Pinecone in
    production (app/rag/retriever.py).
    """
    sections = _load_sections()
    query_terms = set(re.findall(r"\w+", query.lower()))

    scored = []
    for section in sections:
        section_terms = set(re.findall(r"\w+", section["text"].lower()))
        overlap = len(query_terms & section_terms)
        if overlap > 0:
            scored.append((overlap, section))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:top_k]]


def _pinecone_available() -> bool:
    import os
    return bool(os.getenv("PINECONE_API_KEY") and os.getenv("GEMINI_API_KEY"))


_search_policy_keyword = search_policy  # keep the original keyword-based version


def search_policy(query: str, top_k: int = 3) -> List[Dict]:
    """
    Real Pinecone + OpenAI embedding search when both API keys are
    configured; falls back to the local keyword-matching version
    otherwise, so the pipeline keeps running without live credentials.
    """
    if _pinecone_available():
        from app.rag.retriever import query_policy_index
        return query_policy_index(query, top_k=top_k)
    return _search_policy_keyword(query, top_k=top_k)