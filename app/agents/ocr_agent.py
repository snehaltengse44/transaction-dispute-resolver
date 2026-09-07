"""
2. OCR & Data Extraction

Reads the customer's receipt/screenshot, runs OCR, and asks the LLM to
pull out structured transaction fields from the raw text.
"""

import json
import logging

from app.agents.state import DisputeCaseState
from app.ocr.extractor import extract_text_from_image
from app.ocr.parser import parse_transaction_fields
from app.guardrails.input_guards import sanitize_ocr_text

logger = logging.getLogger(__name__)


def ocr_agent(state: DisputeCaseState) -> dict:
    """
    LangGraph node. Reads state["receipt_image_path"], returns a partial
    state update with extracted transaction fields.
    """
    image_path = state["receipt_image_path"]
    errors = list(state.get("errors", []))

    try:
        raw_text = extract_text_from_image(image_path)
    except Exception as exc:
        logger.exception("OCR extraction failed for case %s", state.get("case_id"))
        errors.append(f"ocr_extraction_failed: {exc}")
        return {"errors": errors, "ocr_raw_text": ""}

    # Strip anything that looks like an injected instruction before it
    # reaches the LLM parser.
    clean_text = sanitize_ocr_text(raw_text)

    try:
        fields = parse_transaction_fields(clean_text)
    except Exception as exc:
        logger.exception("Field parsing failed for case %s", state.get("case_id"))
        errors.append(f"field_parsing_failed: {exc}")
        return {"errors": errors, "ocr_raw_text": clean_text}

    logger.info(
        "OCR extracted transaction_id=%s amount=%s for case %s",
        fields.get("transaction_id"),
        fields.get("amount"),
        state.get("case_id"),
    )

    return {
        "ocr_raw_text": clean_text,
        "transaction_id": fields.get("transaction_id"),
        "transaction_date": fields.get("date"),
        "transaction_amount": fields.get("amount"),
        "sender_account": fields.get("sender_account"),
        "receiver_account": fields.get("receiver_account"),
        "receiver_name": fields.get("receiver_name"),
        "ocr_confidence": fields.get("confidence"),
        "errors": errors,
    }
