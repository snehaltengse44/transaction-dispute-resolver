"""
Chunks fraud_and_refund_policy.docx by section, embeds each chunk
using Google's Gemini embedding model (free tier, no card required),
and upserts into a Pinecone index.

Run with: python -m app.rag.ingest
Requires PINECONE_API_KEY and GEMINI_API_KEY in .env.
"""

import os
from pathlib import Path
from docx import Document
from dotenv import load_dotenv

load_dotenv()

POLICY_PATH = Path(__file__).parent.parent.parent / "data" / "sample_dataset" / "fraud_and_refund_policy.docx"
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "disputedesk-policy")
EMBEDDING_MODEL = "gemini-embedding-001"  # Gemini's current embedding model, 3072 dimensions
EMBEDDING_DIMENSION = 3072


def extract_sections():
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

    return sections


def embed_text(client, text: str, task_type: str = "RETRIEVAL_DOCUMENT"):
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config={"task_type": task_type},
    )
    return result.embeddings[0].values


def run_ingest():
    from google import genai
    from pinecone import Pinecone, ServerlessSpec

    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

    if PINECONE_INDEX_NAME not in [idx.name for idx in pc.list_indexes()]:
        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=os.getenv("PINECONE_ENVIRONMENT", "us-east-1")),
        )

    index = pc.Index(PINECONE_INDEX_NAME)
    sections = extract_sections()

    vectors = []
    for i, section in enumerate(sections):
        embedding = embed_text(gemini_client, section["text"], task_type="RETRIEVAL_DOCUMENT")
        vectors.append({
            "id": f"section-{i}",
            "values": embedding,
            "metadata": {"source": section["source"], "text": section["text"]},
        })

    index.upsert(vectors=vectors)
    print(f"Ingested {len(vectors)} policy sections into Pinecone index '{PINECONE_INDEX_NAME}'")


if __name__ == "__main__":
    run_ingest()