from __future__ import annotations

from pyaireader.models import CompanyMention, EntityMention, EvidenceSnippet, FinancialEvent


EVENT_KEYWORDS = [
    ("order", ["订单", "合同", "中标", "采购"]),
    ("earnings", ["净利润", "营收", "收入", "业绩", "同比增长"]),
    ("capacity", ["扩产", "投产", "产能", "产线"]),
    ("price_change", ["涨价", "提价", "降价", "价格"]),
    ("policy", ["政策", "监管", "审批", "发改委", "工信部", "证监会"]),
    ("sanction", ["制裁", "限制", "禁令", "出口管制"]),
    ("accident", ["事故", "停产", "火灾", "爆炸"]),
]

POSITIVE_WORDS = ["增长", "获得", "中标", "受益", "上升", "提升", "扩产"]
NEGATIVE_WORDS = ["下降", "亏损", "事故", "制裁", "停产", "处罚", "限制"]


def extract_financial_events(
    evidence: list[EvidenceSnippet],
    entities: list[EntityMention],
    *,
    limit: int = 8,
) -> list[FinancialEvent]:
    events: list[FinancialEvent] = []
    for item in evidence:
        event_type = _event_type(item.text)
        if not event_type:
            continue
        event = FinancialEvent(
            event_type=event_type,
            confidence=_confidence(item),
            direction=_direction(item.text),
            affected_industries=_entities(entities, "industry", item.id),
            supply_chain_nodes=_entities(entities, "product", item.id),
            companies_mentioned=_companies(entities, item.id),
            impact_horizon=_impact_horizon(item.text),
            evidence_ids=[item.id],
        )
        events.append(event)
        if len(events) >= limit:
            return events
    return events


def _event_type(text: str) -> str | None:
    for event_type, keywords in EVENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return event_type
    return None


def _direction(text: str) -> str:
    has_positive = any(word in text for word in POSITIVE_WORDS)
    has_negative = any(word in text for word in NEGATIVE_WORDS)
    if has_positive and has_negative:
        return "mixed"
    if has_positive:
        return "positive"
    if has_negative:
        return "negative"
    return "unknown"


def _confidence(evidence: EvidenceSnippet) -> float:
    score = 0.45 + min(evidence.importance, 0.4)
    if "number" in evidence.signals:
        score += 0.1
    return round(min(score, 0.95), 3)


def _impact_horizon(text: str) -> str | None:
    if any(word in text for word in ["今日", "昨日", "短期", "本周"]):
        return "short"
    if any(word in text for word in ["上半年", "下半年", "季度", "今年"]):
        return "medium"
    if any(word in text for word in ["2027", "2028", "长期", "未来"]):
        return "long"
    return None


def _entities(entities: list[EntityMention], entity_type: str, evidence_id: str) -> list[str]:
    values = []
    for entity in entities:
        if entity.entity_type == entity_type and entity.evidence_id == evidence_id:
            values.append(entity.name)
    return values


def _companies(entities: list[EntityMention], evidence_id: str) -> list[CompanyMention]:
    companies = []
    for entity in entities:
        if entity.entity_type == "company" and entity.evidence_id == evidence_id:
            companies.append(CompanyMention(name=entity.name, evidence_ids=[evidence_id]))
    return companies
