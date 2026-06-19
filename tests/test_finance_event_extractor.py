from __future__ import annotations

from pyaireader.finance import extract_financial_events
from pyaireader.models import EntityMention, EvidenceSnippet


def test_extract_financial_events_from_order_evidence() -> None:
    evidence = [
        EvidenceSnippet(
            id="ev_001",
            text="测试公司公告称，公司获得数据中心电力设备订单，金额为12.5亿元。",
            source_url="https://example.com/article",
            paragraph_index=0,
            signals=["company", "finance", "number"],
            importance=0.8,
        )
    ]
    entities = [
        EntityMention(
            name="测试公司",
            entity_type="company",
            context=evidence[0].text,
            evidence_id="ev_001",
        ),
        EntityMention(
            name="数据中心",
            entity_type="industry",
            context=evidence[0].text,
            evidence_id="ev_001",
        ),
        EntityMention(
            name="电力设备",
            entity_type="industry",
            context=evidence[0].text,
            evidence_id="ev_001",
        ),
    ]

    events = extract_financial_events(evidence, entities)

    assert len(events) == 1
    assert events[0].event_type == "order"
    assert events[0].direction == "positive"
    assert events[0].evidence_ids == ["ev_001"]
    assert events[0].companies_mentioned[0].name == "测试公司"
