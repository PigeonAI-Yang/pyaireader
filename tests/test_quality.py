from __future__ import annotations

from pyaireader.quality import score_quality


def test_quality_flags_empty_content() -> None:
    quality = score_quality("", "", None, 0)

    assert quality.level == "failed"
    assert "empty_content" in quality.flags


def test_quality_scores_useful_content() -> None:
    text = "\n".join(
        [
            "测试公司公告称，公司获得数据中心电力设备订单，金额为12.5亿元。",
            "公司预计上半年净利润同比增长45%至60%，主要受益于订单交付和产能释放。",
            "该项目涉及变压器、UPS和配电设备，交付周期预计持续到2027年。",
        ]
        * 5
    )

    quality = score_quality("<html></html>", text, "测试公司公告", 6)

    assert quality.score >= 0.6
    assert quality.level in {"usable", "strong"}
