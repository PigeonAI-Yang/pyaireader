from __future__ import annotations

import importlib.util

from pyaireader.errors import ExtractionError


class PdfExtractor:
    name = "pdf"

    def available(self) -> bool:
        return importlib.util.find_spec("fitz") is not None

    def extract_bytes(self, content: bytes) -> str:
        if not self.available():
            raise ExtractionError("not_implemented: pymupdf is not installed")
        import fitz  # type: ignore

        text_parts: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as document:
            for page in document:
                text_parts.append(page.get_text("text"))
        return "\n".join(text_parts).strip()
