"""Country names to ISO 3166-1 alpha-2 codes (design 8.2)."""

from __future__ import annotations

import pytest

from qrlab.core.errors import ValidationError
from qrlab.instruments import COUNTRIES
from qrlab.instruments.countries import (
    COUNTRY_ALIASES,
    COUNTRY_NAMES,
    country_code,
    normalise_name,
)


def test_one_name_for_every_code_and_nothing_else() -> None:
    assert set(COUNTRY_NAMES) == set(COUNTRIES)
    assert len(COUNTRY_NAMES) == 249
    assert all(name.strip() == name and name for name in COUNTRY_NAMES.values())


def test_every_alias_points_to_one_valid_code_without_collisions() -> None:
    assert set(COUNTRY_ALIASES.values()) <= set(COUNTRIES)
    seen: dict[str, str] = {}
    for code, name in COUNTRY_NAMES.items():
        key = normalise_name(name)
        assert key not in seen, (name, seen.get(key))
        seen[key] = code
    for alias, code in COUNTRY_ALIASES.items():
        key = normalise_name(alias)
        assert seen.get(key, code) == code, f"{alias!r} collides with {seen[key]!r}"
        seen[key] = code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("United States", "US"),
        ("United States of America", "US"),
        ("Korea (South)", "KR"),
        ("Korea, Republic of", "KR"),
        ("UNITED KINGDOM ", "GB"),
        ("  united   kingdom", "GB"),
        ("Taiwan", "TW"),
        ("Taiwan, Province of China", "TW"),
        ("Türkiye", "TR"),
        ("Turkiye", "TR"),  # accents ignored
        ("Turkey", "TR"),
        ("Côte d'Ivoire", "CI"),
        ("Cote d'Ivoire", "CI"),
        ("Curacao", "CW"),
        ("Hong Kong", "HK"),
        ("Netherlands", "NL"),
        ("Czech Republic", "CZ"),
        ("Russia", "RU"),
        ("Cayman Islands", "KY"),
    ],
)
def test_known_names(name: str, code: str) -> None:
    assert country_code(name) == code


@pytest.mark.parametrize("name", ["Atlantis", "Korea", "European Union", "", "U S"])
def test_unknown_names_raise(name: str) -> None:
    with pytest.raises(ValidationError, match="country_values"):
        country_code(name)


def test_normalise_name() -> None:
    assert normalise_name("  Åland   Islands ") == "aland islands"
    assert normalise_name("CURAÇAO") == "curacao"
