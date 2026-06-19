from __future__ import annotations

from pyaireader.models import EvidenceSnippet
from pyaireader.reader.traces import sha256_text


SIGNAL_KEYWORDS = {
    "company": ["公司", "集团", "股份", "公告", "董事会", "交易所"],
    "finance": ["营收", "收入", "利润", "净利润", "毛利率", "订单", "合同", "中标"],
    "market": ["同比", "环比", "增长", "下降", "涨价", "降价", "需求", "供给"],
    "policy": ["政策", "监管", "审批", "发改委", "工信部", "证监会", "财政部"],
    "time": ["今日", "昨日", "年", "月", "日", "季度", "上半年", "下半年"],
}


def pick_evidence(
    paragraphs: list[str],
    max_items: int = 12,
    *,
    source_url: str = "",
    preferred_text: str | None = None,
    preferred_reason: str | None = None,
) -> list[EvidenceSnippet]:
    snippets = []
    seen_texts = set()
    if preferred_text and preferred_text.strip() and max_items > 0:
        preferred_text = preferred_text.strip()
        signals = _signals_for(preferred_text)
        if any(ch.isdigit() for ch in preferred_text):
            signals.append("number")
        snippets.append(
            EvidenceSnippet(
                id="ev_001",
                text=preferred_text,
                source_url=source_url,
                paragraph_index=0,
                signals=sorted(set(signals + ([preferred_reason] if preferred_reason else []))),
                importance=1.0,
                quote_hash=sha256_text(preferred_text),
                reason=preferred_reason or "primary_text",
            )
        )
        seen_texts.add(preferred_text)

    scored = []
    for index, paragraph in enumerate(paragraphs):
        if paragraph in seen_texts or any(paragraph in seen_text for seen_text in seen_texts):
            continue
        signals = _signals_for(paragraph)
        score = len(signals) * 0.2
        if any(ch.isdigit() for ch in paragraph):
            signals.append("number")
            score += 0.25
        score += min(len(paragraph) / 500, 0.25)
        if score <= 0.2:
            continue
        scored.append((score, index, paragraph, signals))

    scored.sort(key=lambda item: item[0], reverse=True)
    next_id = len(snippets) + 1
    remaining = max(max_items - len(snippets), 0)
    for item_id, (score, index, paragraph, signals) in enumerate(
        scored[:remaining], start=next_id
    ):
        snippets.append(
            EvidenceSnippet(
                id=f"ev_{item_id:03d}",
                text=paragraph,
                source_url=source_url,
                paragraph_index=index,
                signals=sorted(set(signals)),
                importance=round(min(score, 1.0), 3),
                quote_hash=sha256_text(paragraph),
                reason=", ".join(sorted(set(signals))) or None,
            )
        )
    return snippets


def _signals_for(text: str) -> list[str]:
    signals = []
    for signal, keywords in SIGNAL_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            signals.append(signal)
    return signals
