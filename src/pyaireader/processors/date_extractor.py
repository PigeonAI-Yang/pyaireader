from __future__ import annotations

import re

from pyaireader.models import DateMention, EvidenceSnippet


DATE_RE = re.compile(
    r"(?P<value>(?:20\d{2}|19\d{2})[-/.年]\s?\d{1,2}[-/.月]\s?\d{1,2}日?|(?:\d{1,2}月\d{1,2}日))"
)


def extract_dates(
    paragraphs: list[str],
    evidence: list[EvidenceSnippet] | None = None,
    limit: int = 30,
) -> list[DateMention]:
    mentions: list[DateMention] = []
    evidence_by_paragraph = {
        item.paragraph_index: item.id for item in evidence or [] if item.paragraph_index is not None
    }
    for index, paragraph in enumerate(paragraphs):
        for match in DATE_RE.finditer(paragraph):
            raw = match.group("value").strip()
            mentions.append(
                DateMention(
                    date_raw=raw,
                    date_normalized=_normalize_date(raw),
                    context=paragraph,
                    evidence_id=evidence_by_paragraph.get(index),
                    paragraph_index=index,
                )
            )
            if len(mentions) >= limit:
                return mentions
    return mentions


def _normalize_date(raw: str) -> str | None:
    match = re.match(r"(20\d{2}|19\d{2})[-/.年]\s?(\d{1,2})[-/.月]\s?(\d{1,2})日?", raw)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
