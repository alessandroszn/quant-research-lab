"""The app's icon is the one the script draws (design note 12.4)."""

from __future__ import annotations

from pathlib import Path

import make_icon
import pytest
from PIL import Image

ROOT = Path(__file__).parents[3]


def test_the_committed_icons_are_the_drawn_ones() -> None:
    drawn = make_icon.draw(256).tobytes()
    with Image.open(make_icon.PNG) as png:
        assert png.size == (256, 256)
        assert png.convert("RGBA").tobytes() == drawn
    with Image.open(make_icon.ICO) as ico:
        assert sorted(ico.info["sizes"]) == [(s, s) for s in make_icon.ICO_SIZES]
        assert ico.convert("RGBA").tobytes() == drawn  # the largest frame


def test_the_command_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(make_icon, "ROOT", tmp_path)
    monkeypatch.setattr(make_icon, "PNG", tmp_path / "res" / "qrlab.png")
    monkeypatch.setattr(make_icon, "ICO", tmp_path / "qrlab.ico")
    assert make_icon.main([]) == 0
    with Image.open(tmp_path / "res" / "qrlab.png") as png:
        assert png.size == (256, 256)
    assert (tmp_path / "qrlab.ico").read_bytes()[:4] == b"\x00\x00\x01\x00"  # an ICO header
    assert "wrote" in capsys.readouterr().out
    assert make_icon.main(["extra"]) == 2


def test_the_build_and_the_installer_use_the_icon() -> None:
    spec = (ROOT / "packaging" / "qrlab.spec").read_text(encoding="utf-8")
    assert spec.count("icon=ICON") == 2  # both programs
    assert '"qrlab_app/resources"' in spec  # the window's PNG travels with the app
    assert "backend_qtagg" not in spec  # the charts' backend is bundled (12.3b)
    installer = (ROOT / "packaging" / "installer.iss").read_text(encoding="utf-8")
    assert "SetupIconFile=qrlab.ico" in installer
