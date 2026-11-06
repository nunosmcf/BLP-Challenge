"""Extract plain text from PDF bytes using pdfplumber."""
import io

import pdfplumber


def extract_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages).strip()
    except Exception as exc:
        return f"[PDF extraction error: {exc}]"
