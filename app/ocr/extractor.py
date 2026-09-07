"""Wraps Tesseract OCR to pull raw text out of a receipt image."""

import os
import pytesseract
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Point pytesseract directly at the binary instead of relying on PATH —
# avoids the common Windows issue where the installer doesn't add
# Tesseract to PATH automatically.
_tesseract_cmd = os.getenv("TESSERACT_CMD")
if _tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd


def extract_text_from_image(image_path: str) -> str:
    image = Image.open(image_path)
    return pytesseract.image_to_string(image)
