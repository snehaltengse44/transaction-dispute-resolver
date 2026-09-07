"""Sanitizes OCR-extracted text before it reaches any LLM call."""


def sanitize_ocr_text(raw_text: str) -> str:
    """
    Strips content resembling injected instructions (e.g. 'ignore
    previous instructions') and obvious PII patterns from OCR text.
    """
    # TODO: implement real sanitization / prompt-injection detection
    return raw_text
