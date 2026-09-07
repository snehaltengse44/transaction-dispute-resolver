"""
Queries the Pinecone policy index for the top-k most relevant policy
sections given a natural-language query. Embeds the query using
Gemini's embedding model (same model used at ingest time in ingest.py
— query/document embeddings must come from the same model to be
comparable).
"""

import os
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "disputedesk-policy")
EMBEDDING_MODEL = "gemini-embedding-001"


def query_policy_index(query: str, top_k: int = 3) -> List[Dict]:
    from google import genai
    from pinecone import Pinecone

    gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(PINECONE_INDEX_NAME)

    result = gemini_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query,
        config={"task_type": "RETRIEVAL_QUERY"},
    )
    embedding = result.embeddings[0].values

    results = index.query(vector=embedding, top_k=top_k, include_metadata=True)

    return [
        {"source": match.metadata["source"], "text": match.metadata["text"], "score": match.score}
        for match in results.matches
    ]