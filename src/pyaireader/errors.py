from __future__ import annotations


class ReaderError(Exception):
    """Base error for pyaireader."""


class UnsafeUrlError(ReaderError):
    """URL is not safe to fetch from an agent tool."""


class FetchError(ReaderError):
    """URL fetch failed."""


class ExtractionError(ReaderError):
    """Content extraction failed."""
