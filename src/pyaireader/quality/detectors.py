from __future__ import annotations


def detect_problem_flags(html: str, clean_text: str) -> dict[str, bool]:
    lowered = (html or "").lower()
    text_lowered = (clean_text or "").lower()
    replacement_ratio = clean_text.count("\ufffd") / max(len(clean_text), 1)
    return {
        "empty_content": not clean_text.strip(),
        "content_too_short": len(clean_text.strip()) < 200,
        "garbled_text": replacement_ratio > 0.02,
        "js_shell": _looks_like_js_shell(lowered, clean_text),
        "captcha": any(token in lowered or token in text_lowered for token in ["captcha", "验证码", "人机验证"]),
        "login_required": any(
            token in lowered or token in text_lowered
            for token in ["login", "log in", "sign in", "登录", "登录后", "请登录"]
        ),
        "paywall_likely": any(token in text_lowered for token in ["subscribe", "付费阅读", "订阅后"]),
    }


def _looks_like_js_shell(html: str, clean_text: str) -> bool:
    if len(clean_text.strip()) >= 500:
        return False
    shell_markers = ["__next_data__", "window.__initial_state__", "id=\"root\"", "id=\"app\""]
    return any(marker in html for marker in shell_markers)
