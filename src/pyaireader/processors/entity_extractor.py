from __future__ import annotations

import re

from pyaireader.models import EntityMention, EvidenceSnippet


AGENCY_KEYWORDS = ["发改委", "工信部", "证监会", "财政部", "交易所", "监管"]
INDUSTRY_KEYWORDS = ["数据中心", "半导体", "人工智能", "新能源", "电力设备", "储能"]
PRODUCT_KEYWORDS = ["变压器", "UPS", "配电设备", "芯片", "服务器", "电池"]
COMPANY_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,}(?:公司|集团|股份|科技|控股)")


def extract_entities(
    paragraphs: list[str],
    evidence: list[EvidenceSnippet] | None = None,
    limit: int = 40,
) -> list[EntityMention]:
    mentions: list[EntityMention] = []
    seen: set[tuple[str, str]] = set()
    evidence_by_paragraph = {
        item.paragraph_index: item.id for item in evidence or [] if item.paragraph_index is not None
    }

    for index, paragraph in enumerate(paragraphs):
        for name in COMPANY_RE.findall(paragraph):
            _append(mentions, seen, name, "company", paragraph, evidence_by_paragraph.get(index), limit)
        for name in AGENCY_KEYWORDS:
            if name in paragraph:
                _append(mentions, seen, name, "agency", paragraph, evidence_by_paragraph.get(index), limit)
        for name in INDUSTRY_KEYWORDS:
            if name in paragraph:
                _append(mentions, seen, name, "industry", paragraph, evidence_by_paragraph.get(index), limit)
        for name in PRODUCT_KEYWORDS:
            if name in paragraph:
                _append(mentions, seen, name, "product", paragraph, evidence_by_paragraph.get(index), limit)
        if len(mentions) >= limit:
            return mentions
    return mentions


def _append(
    mentions: list[EntityMention],
    seen: set[tuple[str, str]],
    name: str,
    entity_type: str,
    context: str,
    evidence_id: str | None,
    limit: int,
) -> None:
    if len(mentions) >= limit:
        return
    key = (name, entity_type)
    if key in seen:
        return
    seen.add(key)
    mentions.append(
        EntityMention(
            name=name,
            entity_type=entity_type,  # type: ignore[arg-type]
            context=context,
            evidence_id=evidence_id,
        )
    )
