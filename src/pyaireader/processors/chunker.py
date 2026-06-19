from __future__ import annotations


def split_paragraphs(text: str) -> list[str]:
    paragraphs = []
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < 8:
            continue
        paragraphs.append(line)
    return paragraphs
