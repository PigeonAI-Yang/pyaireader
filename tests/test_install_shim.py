from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_global_shim_script_wraps_uv_directory_cli() -> None:
    script = ROOT / "scripts" / "install-global-shim.ps1"
    text = script.read_text(encoding="utf-8")

    assert "pyaireader.cmd" in text
    assert "--directory" in text
    assert "run pyaireader %*" in text
    assert ".local\\bin" in text
    assert "PATH" in text
