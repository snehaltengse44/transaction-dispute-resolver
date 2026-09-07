"""
LLM-based structured extraction of transaction fields from raw OCR
text. More robust than regex against layout variation across UPI apps
(PhonePe, GPay, Paytm, etc.) since the model reads the receipt the
way a human would, rather than matching fixed patterns.
"""

import os
import json
from typing import Dict


def parse_transaction_fields_llm(raw_text: str) -> Dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("LLM_MODEL_NAME", "gpt-4o")

    prompt = f"""Extract transaction fields from this UPI/bank transfer receipt's OCR text.
Return ONLY a JSON object with these exact keys: transaction_id, date (ISO 8601,
e.g. 2026-09-01T16:39:00), amount (number), sender_account (masked account
shown as debited, e.g. XXXXXX2668), receiver_name (the "Paid to" name, cleaned
of any stray OCR glyphs). Use null for any field you cannot find. No prose,
no markdown fences — JSON only.

OCR text:
{raw_text}"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    content = response.choices[0].message.content.strip()
    # Strip accidental markdown fences if the model adds them anyway.
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    fields = json.loads(content)
    fields.setdefault("confidence", 0.95 if fields.get("transaction_id") else 0.3)
    return fields
