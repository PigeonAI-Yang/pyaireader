from __future__ import annotations

from pyaireader.quality import score_quality


def test_login_chrome_in_html_does_not_fail_long_clean_article() -> None:
    html = "<html><body><nav><a>Login</a></nav><article>data center power</article></body></html>"
    clean_text = "\n".join(
        [
            "Data centers need reliable power systems, UPS backup, switchgear, and fast project delivery."
            for _ in range(20)
        ]
    )

    quality = score_quality(html, clean_text, "Data centers | Eaton", 6)

    assert "login_required" not in quality.flags
    assert quality.level in {"usable", "strong"}


def test_explicit_login_required_text_still_fails() -> None:
    quality = score_quality("<html></html>", "Please sign in to continue.", "Sign in", 0)

    assert "login_required" in quality.flags
    assert quality.level == "failed"
