"""The structural check of a config against its kind's schema (design note 12.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments.schema import (
    Field,
    FieldKind,
    Help,
    InputSpec,
    KindSchema,
    check_parameters,
)

K = FieldKind
H = Help("help", "aiuto")
ISIN = "IE0000000012"


def _f(key: str, kind: FieldKind, **extra: object) -> Field:
    return Field(key, kind, H, **extra)  # type: ignore[arg-type]


RECORD = (_f("amount", K.NUMBER, minimum=0.0), _f("note", K.TEXT, required=False))
SCHEMA = KindSchema(
    inputs=(InputSpec("returns", H),),
    parameters=(
        _f("title", K.TEXT),
        _f("window", K.INTEGER, minimum=2),
        _f("rate", K.NUMBER, minimum=0.0, maximum=1.0, open_maximum=True, unit="fraction"),
        _f("flag", K.BOOLEAN, required=False),
        _f("start", K.DATE, required=False),
        _f("stamp", K.DATETIME, required=False),
        _f("language", K.CHOICE, choices=("it", "en"), required=False),
        _f("currency", K.CURRENCY, required=False),
        _f("fund", K.ISIN, required=False),
        _f("levels", K.LIST, item=_f("", K.NUMBER), required=False),
        _f("tags", K.LIST, item=_f("", K.TEXT), allow_empty=True, required=False),
        _f("correlation", K.MATRIX, required=False),
        _f("risk", K.TABLE, fields=(_f("window", K.INTEGER, minimum=2),), required=False),
        _f("weights", K.MAP, key_kind=K.ISIN, item=_f("", K.NUMBER), required=False),
        _f("net", K.MAP, key_kind=K.INTEGER, item=_f("", K.NUMBER), required=False),
        _f("flows", K.RECORDS, fields=RECORD, required=False),
        _f(
            "engine",
            K.VARIANT,
            selector="name",
            variants={
                "normal": (),
                "student_t": (_f("dof", K.NUMBER, minimum=2.0, open_minimum=True),),
            },
            required=False,
        ),
    ),
)
BASE: dict[str, object] = {"title": "t", "window": 4, "rate": 0.26}


def _check(**extra: object) -> None:
    check_parameters(SCHEMA, BASE | extra)


def test_a_complete_config_passes() -> None:
    _check(
        flag=True,
        start=date(2026, 1, 2),
        stamp=datetime(2026, 1, 2, 9, tzinfo=UTC),
        language="it",
        currency="EUR",
        fund=ISIN,
        levels=[5, 50.0, 95],
        tags=[],
        correlation=[[1.0, 0.2], [0.2, 1]],
        risk={"window": 36},
        weights={ISIN: 1.0},
        net={"2025": 50000},
        flows=[{"amount": 100}, {"amount": 0.0, "note": "x"}],
        engine={"name": "student_t", "dof": 5},
    )
    _check(engine={"name": "normal"})


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"surprise": 1}, r"\[parameters\]: unknown keys \['surprise'\]"),
        ({"title": ""}, r"\[parameters.title\]: non-empty text"),
        ({"window": 1}, r"\[parameters.window\]: a value >= 2 is required, got 1"),
        ({"window": 4.0}, r"\[parameters.window\]: an integer"),
        ({"window": True}, r"\[parameters.window\]: an integer"),
        ({"rate": 1.0}, r"\[parameters.rate\]: a value >= 0 and < 1 is required"),
        ({"rate": "x"}, r"\[parameters.rate\]: a number"),
        ({"rate": float("nan")}, r"\[parameters.rate\]: a finite number"),
        ({"flag": 1}, r"\[parameters.flag\]: true or false"),
        ({"start": datetime(2026, 1, 2)}, r"\[parameters.start\]: a date"),
        ({"stamp": datetime(2026, 1, 2)}, r"\[parameters.stamp\]: a date-time with a time zone"),
        ({"language": "fr"}, r"\[parameters.language\]: one of \['it', 'en'\]"),
        ({"currency": "EURO"}, r"\[parameters.currency\]: 'EURO' is not a valid currency"),
        ({"currency": 3}, r"\[parameters.currency\]: currency text"),
        ({"fund": "IE0000000013"}, r"\[parameters.fund\]: 'IE0000000013' is not a valid isin"),
        ({"levels": 5}, r"\[parameters.levels\]: a list"),
        ({"levels": []}, r"\[parameters.levels\]: the list must not be empty"),
        ({"levels": [5, "x"]}, r"\[parameters.levels\]\[1\]: a number"),
        ({"correlation": []}, r"\[parameters.correlation\]: a non-empty list"),
        ({"correlation": [[1.0], [0.2, 1.0]]}, r"row 0 must be a list of 2 numbers"),
        ({"correlation": [[1.0, "x"], [0.2, 1.0]]}, r"row 0 must hold numbers"),
        ({"risk": 3}, r"\[parameters.risk\] must be a table"),
        ({"risk": {}}, r"\[parameters.risk\] must not be empty"),
        ({"risk": {"window": 1}}, r"\[parameters.risk.window\]: a value >= 2"),
        ({"risk": {"size": 1}}, r"\[parameters.risk\]: unknown keys \['size'\]"),
        ({"weights": {}}, r"\[parameters.weights\] must not be empty"),
        ({"weights": []}, r"\[parameters.weights\] must be a table"),
        ({"weights": {"XX": 1.0}}, r"\[parameters.weights\] key: 'XX' is not a valid isin"),
        ({"weights": {ISIN: "a"}}, rf"\[parameters.weights.{ISIN}\]: a number"),
        ({"net": {"year": 1}}, r"\[parameters.net\] key: 'year' is not a valid integer"),
        ({"flows": {}}, r"\[parameters.flows\]: a list of tables"),
        ({"flows": []}, r"\[parameters.flows\]: the list must not be empty"),
        ({"flows": [{"note": "x"}]}, r"\[parameters.flows\]\[0\]: missing keys \['amount'\]"),
        ({"flows": [{"amount": -1}]}, r"\[parameters.flows\]\[0\].amount: a value >= 0"),
        ({"flows": [1]}, r"\[parameters.flows\]\[0\] must be a table"),
        ({"engine": 1}, r"\[parameters.engine\] must be a table"),
        ({"engine": {"name": "garch"}}, r"\[parameters.engine\]: name must be one of"),
        ({"engine": {"name": "student_t"}}, r"\[parameters.engine\]: missing keys \['dof'\]"),
        ({"engine": {"name": "student_t", "dof": 2}}, r"\[parameters.engine.dof\]: a value > 2"),
        ({"engine": {"name": "normal", "dof": 5}}, r"\[parameters.engine\]: unknown keys"),
    ],
)
def test_every_refusal_names_the_path(extra: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _check(**extra)


def test_missing_required_keys() -> None:
    with pytest.raises(ValidationError, match=r"\[parameters\]: missing keys \['window'\]"):
        check_parameters(SCHEMA, {"title": "t", "rate": 0.1})
    with pytest.raises(ValidationError, match=r"\[parameters\] must be a table"):
        check_parameters(SCHEMA, [])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: _f("c", K.CHOICE), "a choice needs choices"),
        (lambda: _f("l", K.LIST), "a list needs an item"),
        (lambda: _f("m", K.MAP, item=_f("", K.NUMBER)), "a map needs key_kind"),
        (lambda: _f("t", K.TABLE), "a table needs fields"),
        (lambda: _f("r", K.RECORDS), "a records needs fields"),
        (lambda: _f("v", K.VARIANT, selector="name"), "a variant needs"),
        (lambda: _f("t", K.TABLE, fields=(_f("a", K.TEXT), _f("a", K.TEXT))), "duplicate fields"),
        (lambda: Help("x", " "), "both English and Italian"),
        (
            lambda: KindSchema((InputSpec("a", H), InputSpec("a", H)), ()),
            "duplicate inputs or parameters",
        ),
    ],
)
def test_incomplete_descriptions_are_refused(build: object, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        build()  # type: ignore[operator]


def test_a_number_may_also_accept_listed_texts() -> None:
    cost = KindSchema((), (_f("annual_cost", K.NUMBER, minimum=0.0, also=("ter",)),))
    check_parameters(cost, {"annual_cost": "ter"})
    check_parameters(cost, {"annual_cost": 0.002})
    with pytest.raises(ValidationError, match=r"\[parameters.annual_cost\]: a number"):
        check_parameters(cost, {"annual_cost": "fee"})


def test_a_number_may_allow_infinity() -> None:
    caps = KindSchema((), (_f("cap", K.NUMBER, minimum=0.0, open_minimum=True, allow_inf=True),))
    check_parameters(caps, {"cap": float("inf")})
    check_parameters(caps, {"cap": 1.5})
    for bad in (float("-inf"), float("nan")):
        with pytest.raises(ValidationError, match="a finite number"):
            check_parameters(caps, {"cap": bad})


def test_an_upper_bound_alone_and_blank_text_keys() -> None:
    capped = KindSchema((), (_f("share", K.NUMBER, maximum=1.0),))
    with pytest.raises(ValidationError, match=r"a value <= 1 is required, got 2"):
        check_parameters(capped, {"share": 2.0})
    accounts = KindSchema((), (_f("custody", K.MAP, key_kind=K.TEXT, item=_f("", K.NUMBER)),))
    check_parameters(accounts, {"custody": {"Bank": 1.0}})
    with pytest.raises(
        ValidationError, match=r"\[parameters.custody\] key: ' ' is not a valid text"
    ):
        check_parameters(accounts, {"custody": {" ": 1.0}})
