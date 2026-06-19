from __future__ import annotations

from pyaireader.processors.number_extractor import extract_numbers


def test_extract_numbers_ignores_digits_inside_urls() -> None:
    paragraphs = [
        "GLM 5.2 is close to Opus 4.8 and GPT 5.5. https://t.co/OYDQx76Lcf",
        "The contract value is 12.5亿元, see www.example.com/report2026?id=88",
    ]

    numbers = extract_numbers(paragraphs)

    values = [item.value_raw for item in numbers]
    assert values == ["5.2", "4.8", "5.5", "12.5亿元"]
