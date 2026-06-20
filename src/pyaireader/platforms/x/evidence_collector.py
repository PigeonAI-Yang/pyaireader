from __future__ import annotations

from pyaireader.models import EvidenceSnippet, PlatformEvidenceItem
from pyaireader.processors import pick_evidence, split_paragraphs
from pyaireader.quality import score_quality


def build_platform_evidence_item(
    *,
    url: str,
    text: str,
    author: str | None = None,
    published_at_raw: str | None = None,
    relevance: float = 0.0,
) -> PlatformEvidenceItem:
    paragraphs = split_paragraphs(text)
    evidence = pick_evidence(
        paragraphs,
        max_items=4,
        source_url=url,
        preferred_text=text,
        preferred_reason="x_search",
    )
    quality = score_quality("", text, None, len(evidence), extractor="x_search")
    return PlatformEvidenceItem(
        url=url,
        author=author,
        published_at_raw=published_at_raw,
        text=text,
        metrics={},
        relevance=relevance,
        quality=quality,
        evidence=evidence or [_fallback_evidence(url, text)],
    )


def _fallback_evidence(url: str, text: str) -> EvidenceSnippet:
    return EvidenceSnippet(
        id="ev_001",
        text=text[:500],
        source_url=url,
        reason="x_search",
        paragraph_index=0,
        signals=["x_search"],
        importance=1.0,
    )
