from __future__ import annotations

import re

from pyaireader.models import EvidenceSnippet, NumberMention


NUMBER_RE = re.compile(
    r"(?P<value>[+-]?\d+(?:\.\d+)?\s?(?P<unit>%|％|亿元|万元|元|美元|亿|万|倍|个|台|吨|GW|MW|GWh|MWh)?)"
)
URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"]+", re.IGNORECASE)


def extract_numbers(
    paragraphs: list[str],
    evidence: list[EvidenceSnippet] | None = None,
    limit: int = 30,
) -> list[NumberMention]:
    mentions: list[NumberMention] = []
    evidence_by_paragraph = {
        item.paragraph_index: item.id for item in evidence or [] if item.paragraph_index is not None
    }
    for index, paragraph in enumerate(paragraphs):
        url_spans = _url_spans(paragraph)
        for match in NUMBER_RE.finditer(paragraph):
            if _is_inside_spans(match.start(), match.end(), url_spans):
                continue
            value = match.group("value").strip()
            if not value:
                continue
            mentions.append(
                NumberMention(
                    value_raw=value,
                    value_normalized=_normalize_number(value),
                    unit=(match.group("unit") or None),
                    context=paragraph,
                    evidence_id=evidence_by_paragraph.get(index),
                    paragraph_index=index,
                )
            )
            if len(mentions) >= limit:
                return mentions
    return mentions


def _url_spans(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in URL_RE.finditer(text)]


def _is_inside_spans(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end in spans)


def _normalize_number(value: str) -> float | None:
    match = re.search(r"[+-]?\d+(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
