"""Italian country names from Unicode CLDR 49.0.0 (design note 11.5)."""

from __future__ import annotations

import json
from pathlib import Path

import country_names_it
import pytest

from qrlab.core.errors import ValidationError
from qrlab.instruments import (
    COUNTRIES,
    COUNTRY_ALIASES_IT,
    COUNTRY_NAMES_IT,
    country_code,
    country_code_it,
)
from qrlab.instruments.countries import normalise_name
from qrlab.instruments.io import CountryFormat, load_holdings_mapping

ROOT = Path(__file__).parents[3]
CLDR = ROOT / "tests/data/cldr/it-territories-49.0.0.json"

# The list the iShares Italian mapping carried before phase 11.5 (one fund, 8.2c).
ISHARES_BEFORE = {
    "Australia": "AU", "Austria": "AT", "Belgio": "BE", "Canada": "CA", "Danimarca": "DK",
    "Finlandia": "FI", "Francia": "FR", "Germania": "DE", "Giappone": "JP", "Hong Kong": "HK",
    "Irlanda": "IE", "Israele": "IL", "Italia": "IT", "Norvegia": "NO", "Nuova Zelanda": "NZ",
    "Paesi Bassi": "NL", "Portogallo": "PT", "Regno unito": "GB", "Singapore": "SG",
    "Spagna": "ES", "Stati Uniti": "US", "Svezia": "SE", "Svizzera": "CH",
}  # fmt: skip


def _territories() -> dict[str, str]:
    data = json.loads(CLDR.read_text(encoding="utf-8"))
    return dict(data["main"]["it"]["localeDisplayNames"]["territories"])


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Stati Uniti", "US"),
        ("Corea del Sud", "KR"),
        ("Hong Kong", "HK"),  # CLDR's short form of "RAS di Hong Kong"
        ("RAS di Hong Kong", "HK"),
        ("Paesi Bassi", "NL"),
        ("  paesi   BASSI ", "NL"),
        ("Cechia", "CZ"),
        ("Repubblica Ceca", "CZ"),  # CLDR's variant
        ("Costa d'Avorio", "CI"),  # a plain apostrophe matches CLDR's typographic one
        ("Côte d\u2019Ivoire", "CI"),  # as CLDR writes it
        ("Stati Uniti d'America", "US"),  # an alias
    ],
)
def test_italian_names(name: str, code: str) -> None:
    assert country_code_it(name) == code


def test_unknown_names_raise_and_languages_stay_apart() -> None:
    with pytest.raises(ValidationError, match="unknown Italian country name 'Narnia'"):
        country_code_it("Narnia")
    with pytest.raises(ValidationError):
        country_code_it("United States")  # an English name is not Italian
    with pytest.raises(ValidationError):
        country_code("Stati Uniti")  # nor the reverse


def test_every_code_has_an_italian_name_and_no_name_two_codes() -> None:
    assert set(COUNTRY_NAMES_IT) == set(COUNTRIES)
    owners: dict[str, str] = {}
    for code, names in COUNTRY_NAMES_IT.items():
        for name in names:
            assert owners.setdefault(normalise_name(name), code) == code, name
    for alias, code in COUNTRY_ALIASES_IT.items():
        assert owners.get(normalise_name(alias), code) == code, alias


def test_the_committed_table_is_the_generators_output() -> None:
    assert country_names_it.italian_names(_territories()) == dict(COUNTRY_NAMES_IT)


def test_the_generator_refuses_gaps_and_clashes() -> None:
    territories = _territories()
    del territories["US"]
    with pytest.raises(ValueError, match="no Italian name for"):
        country_names_it.italian_names(territories)
    clash = _territories() | {"FR-alt-short": "Italia"}
    with pytest.raises(ValueError, match="names both"):
        country_names_it.italian_names(clash)


def test_the_generator_writes_the_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "names.py"
    monkeypatch.setattr(country_names_it, "OUTPUT", out)
    monkeypatch.setattr(country_names_it, "ROOT", tmp_path)
    assert country_names_it.main([str(CLDR)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Unicode License v3" in text
    assert "'US': ('Stati Uniti', 'USA')" in text
    assert "wrote names.py" in capsys.readouterr().out
    assert country_names_it.main([]) == 2


def test_the_ishares_mapping_gives_the_same_codes_as_its_old_list() -> None:
    mapping = load_holdings_mapping(ROOT / "configs/csv_mappings/ishares_holdings_it.toml")
    assert mapping.country_format is CountryFormat.NAME_IT
    assert dict(mapping.country_values) == {"Unione Europea": None}  # "unknown": no country
    assert {name: country_code_it(name) for name in ISHARES_BEFORE} == ISHARES_BEFORE


def test_the_license_ships_with_the_table() -> None:
    notice = (ROOT / "src/qrlab/instruments/CLDR-LICENSE.txt").read_text(encoding="utf-8")
    assert "UNICODE LICENSE V3" in notice
    assert "SPDX-License-Identifier: Unicode-3.0" in notice
