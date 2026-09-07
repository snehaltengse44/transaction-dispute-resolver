"""Parses structured transaction fields out of raw PhonePe/UPI OCR text.

OCR on dark-mode receipts is noisy around the ₹ currency glyph (Tesseract
commonly misreads it as '=', '%', 'z', or drops it into the adjacent
digit), so amount extraction deliberately avoids relying on the symbol
and instead pulls the trailing digit run off the known receipt lines.
"""

import re
from datetime import datetime
from typing import Dict, Optional


def _extract_amount_from_line(line: str) -> Optional[float]:
    """Grabs the trailing number off a line, ignoring any currency glyph."""
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*$", line.strip())
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_transaction_fields(raw_text: str) -> Dict:
    """
    Returns a dict with keys: transaction_id, date, amount,
    sender_account, receiver_account, receiver_name, confidence.

    Uses a real LLM call (GPT-4o) when OPENAI_API_KEY is configured —
    more robust across different UPI app layouts. Falls back to the
    regex-based parser below when no key is present, so the pipeline
    keeps running locally without live credentials.
    """
    import os
    if os.getenv("OPENAI_API_KEY"):
        try:
            from app.ocr.llm_parser import parse_transaction_fields_llm
            return parse_transaction_fields_llm(raw_text)
        except Exception:
            pass  # fall through to regex parser below on any LLM/API error

    return _parse_transaction_fields_regex(raw_text)


def _parse_transaction_fields_regex(raw_text: str) -> Dict:
    fields: Dict = {
        "transaction_id": None,
        "date": None,
        "amount": None,
        "sender_account": None,
        "receiver_account": None,
        "receiver_name": None,
        "confidence": None,
    }

    lines = [l for l in raw_text.split("\n")]

    # Transaction ID: "T" followed by 15-25 digits. No left word-boundary
    # requirement, since OCR often merges it with the preceding label
    # ("Transaction ID" + "T2609...") with no space.
    txn_match = re.search(r"T\d{15,25}", raw_text.replace("\n", ""))
    if txn_match:
        fields["transaction_id"] = txn_match.group(0)

    # Date + time: e.g. "04:39 PM on 01 Sep 2026"
    date_match = re.search(
        r"(\d{1,2}:\d{2}\s?[AP]M)\s+on\s+(\d{1,2}\s+\w{3,9}\s+\d{4})", raw_text
    )
    if date_match:
        time_str, date_str = date_match.groups()
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%d %b %Y %I:%M %p")
            fields["date"] = dt.isoformat()
        except ValueError:
            fields["date"] = f"{date_str} {time_str}"

    # "Paid to" is followed by the receiver name + amount on the next line.
    for i, line in enumerate(lines):
        if line.strip().lower() == "paid to" and i + 1 < len(lines):
            target_line = lines[i + 1]
            amount = _extract_amount_from_line(target_line)
            if amount is not None:
                fields["amount"] = amount
            # Name = everything before the trailing amount, minus stray
            # OCR noise from the avatar icon glyph. Icon-glyph noise
            # varies across OS/Tesseract versions ("y Pranay" on one
            # machine, "ye = Pranay" on another), so rather than
            # stripping a fixed number of leading tokens, keep only
            # words that look like a real name (Title Case, letters
            # only) — noise tends to be lowercase or symbols.
            name_part = re.sub(r"\d[\d,]*(?:\.\d+)?\s*$", "", target_line).strip()
            real_words = [w for w in name_part.split() if re.match(r"^[A-Z][a-zA-Z]*$", w)]
            name_part = " ".join(real_words)
            if name_part:
                fields["receiver_name"] = name_part
            break

    # Fallback: if "Paid to" block wasn't found, use the amount on the
    # "Debited from" line.
    if fields["amount"] is None:
        for i, line in enumerate(lines):
            if "debited from" in line.strip().lower() and i + 1 < len(lines):
                fields["amount"] = _extract_amount_from_line(lines[i + 1])
                break

    # Debited-from account, e.g. "XXXXXX2668"
    account_match = re.search(r"X{4,8}\d{3,6}", raw_text)
    if account_match:
        fields["sender_account"] = account_match.group(0)

    fields["confidence"] = 0.9 if fields["transaction_id"] and fields["amount"] else 0.4

    return fields