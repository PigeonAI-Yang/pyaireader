from __future__ import annotations

from pyaireader.models import ReaderQuality
from pyaireader.quality.detectors import detect_problem_flags


SERIOUS_FLAGS = {"empty_content", "garbled_text", "captcha", "login_required", "js_shell", "unsafe"}


def score_quality(
    html: str,
    clean_text: str,
    title: str | None,
    evidence_count: int,
    *,
    extractor: str | None = None,
) -> ReaderQuality:
    detected = detect_problem_flags(html, clean_text)
    social_primary_success = extractor == "x_status" and len(clean_text.strip()) >= 40
    if social_primary_success and detected.get("login_required"):
        detected["login_required"] = False
        detected["page_has_login_chrome"] = True
    flags = [name for name, value in detected.items() if value]
    text_length = len(clean_text.strip())
    paragraph_count = len([line for line in clean_text.splitlines() if len(line.strip()) >= 8])

    length_score = _length_score(text_length)
    paragraph_score = min(paragraph_count / 12, 1.0)
    title_score = 1.0 if title else 0.0
    evidence_score = min(evidence_count / 6, 1.0)
    cleanliness_score = 0.0 if any(flag in SERIOUS_FLAGS for flag in flags) else 1.0

    score = (
        length_score * 0.4
        + paragraph_score * 0.15
        + title_score * 0.15
        + evidence_score * 0.2
        + cleanliness_score * 0.1
    )
    if any(flag in {"garbled_text", "captcha", "login_required", "js_shell"} for flag in flags):
        score *= 0.35
    score = round(max(0.0, min(score, 1.0)), 3)

    if any(flag in {"empty_content", "garbled_text", "captcha", "login_required", "js_shell"} for flag in flags):
        level = "failed"
    elif score >= 0.8:
        level = "strong"
    elif score >= 0.6:
        level = "usable"
    elif score >= 0.35:
        level = "weak"
    else:
        level = "failed"
    if social_primary_success and evidence_count > 0 and level in {"weak", "failed"}:
        level = "usable"
        score = max(score, 0.6)

    reasons = _reasons_for(flags, text_length)
    return ReaderQuality(
        score=score,
        level=level,
        reasons=reasons,
        flags=flags,
        subscores={
            "length": length_score,
            "paragraphs": round(paragraph_score, 3),
            "title": title_score,
            "evidence": round(evidence_score, 3),
            "cleanliness": cleanliness_score,
        },
        metrics={
            "text_length": text_length,
            "paragraph_count": paragraph_count,
            "evidence_count": evidence_count,
            "problem_flags": detected,
        },
    )


def _length_score(text_length: int) -> float:
    if text_length >= 2000:
        return 1.0
    if text_length >= 1000:
        return 0.8
    if text_length >= 500:
        return 0.6
    if text_length >= 100:
        return 0.3
    return 0.1


def _reasons_for(flags: list[str], text_length: int) -> list[str]:
    reasons = list(flags)
    if text_length < 100:
        reasons.append("clean_text_lt_100")
    elif text_length < 500:
        reasons.append("clean_text_lt_500")
    return reasons
