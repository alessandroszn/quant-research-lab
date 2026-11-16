"""The price type of returns files (design 7.3): declared, recorded in the notice, never applied."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.data import PriceType
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.kinds._frames import ADVICE, PRICE_RETURNS, price_type, returns_notice
from qrlab.experiments.workspace import config_template

ROOT = Path(__file__).parents[3]
EXAMPLES = {
    "backtest": ("example_backtest.toml", "returns_price_type"),
    "optimisation": ("example_optimisation.toml", "returns_price_type"),
    "risk_report": ("example_risk_report.toml", "returns_price_type"),
    "scenario_analysis": ("example_scenarios.toml", "position_returns_price_type"),
}


def _localise(name: str, tmp: Path, *replace: tuple[str, str]) -> Path:
    """Copy an example config into ``tmp`` with absolute paths and an output folder there."""
    text = (ROOT / "configs" / "experiments" / name).read_text(encoding="utf-8")
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + f'directory = "{(tmp / "out").as_posix()}"' + text[end + 1 :]
    for old, new in replace:
        assert old in text, old
        text = text.replace(old, new)
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / name
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------ parsing
def test_the_two_declarations_are_read() -> None:
    assert price_type({"k": "total_return"}, "k") is PriceType.TOTAL_RETURN
    assert price_type({"k": "price"}, "k") is PriceType.PRICE


def test_nav_is_refused_with_what_to_use_instead() -> None:
    with pytest.raises(ValidationError, match="k = 'nav'") as caught:
        price_type({"k": "nav"}, "k")
    message = str(caught.value)
    assert "'total_return' for an accumulating fund" in message
    assert "'price' for a distributing fund" in message


@pytest.mark.parametrize("value", ["dividends", "", 1, "TOTAL_RETURN"])
def test_unknown_declarations_are_refused(value: object) -> None:
    with pytest.raises(ValidationError, match="k"):
        price_type({"k": value}, "k")


# ------------------------------------------------------------------------------------- notice
def test_notice_sentences_and_order() -> None:
    assert returns_notice("A.", PriceType.TOTAL_RETURN) == f"A. {ADVICE}"
    assert returns_notice("A.", PriceType.PRICE) == f"A. {PRICE_RETURNS} {ADVICE}"
    assert returns_notice(None, PriceType.TOTAL_RETURN) is None
    assert returns_notice(None, PriceType.PRICE) == f"{PRICE_RETURNS} {ADVICE}"
    assert ADVICE == "Research analytics, not investment advice."
    assert PRICE_RETURNS.startswith("Returns declared as price returns (dividends excluded)")


# ------------------------------------------------------------------------------- every kind
def _outputs(folder: Path) -> tuple[dict[str, object], dict[str, object], object]:
    record = json.loads((folder / "record.json").read_text(encoding="utf-8"))
    outputs = {k: v for k, v in record["outputs"].items() if k != "NOTICE.txt"}
    return outputs, record["scalars"], record["notice"]


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_the_declaration_labels_the_data_and_changes_no_number(tmp_path: Path, kind: str) -> None:
    name, key = EXAMPLES[kind]
    total = _localise(name, tmp_path / "total")
    price = _localise(name, tmp_path / "price", (f'{key} = "total_return"', f'{key} = "price"'))
    a = run_experiment(total, kinds=KINDS, overwrite=False)
    b = run_experiment(price, kinds=KINDS, overwrite=False)
    assert a.record["status"] == b.record["status"] == "success"
    outputs_a, scalars_a, notice_a = _outputs(a.output_dir)
    outputs_b, scalars_b, notice_b = _outputs(b.output_dir)
    assert outputs_a == outputs_b  # same files, same tags, same bytes
    assert scalars_a == scalars_b
    # Every kind here has caveats (risk_report since design note 10.2), so a notice either way.
    assert isinstance(notice_a, str)
    assert PRICE_RETURNS not in notice_a
    assert notice_a.endswith(ADVICE)
    assert notice_b == notice_a.replace(ADVICE, f"{PRICE_RETURNS} {ADVICE}")


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_the_declaration_is_required(tmp_path: Path, kind: str) -> None:
    name, key = EXAMPLES[kind]
    config = _localise(name, tmp_path, (f'{key} = "total_return"\n', ""))
    with pytest.raises(ValidationError, match=key):
        validate_experiment(config, kinds=KINDS)


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_nav_is_refused_in_a_config(tmp_path: Path, kind: str) -> None:
    name, key = EXAMPLES[kind]
    config = _localise(name, tmp_path, (f'{key} = "total_return"', f'{key} = "nav"'))
    with pytest.raises(ValidationError, match="accumulating"):
        validate_experiment(config, kinds=KINDS)


@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_the_template_asks_for_it(kind: str) -> None:
    _, key = EXAMPLES[kind]
    assert f"# {key} = FILL-IN" in config_template(KINDS[kind])


def test_no_position_returns_no_price_sentence(tmp_path: Path) -> None:
    name, key = EXAMPLES["scenario_analysis"]
    config = _localise(
        name,
        tmp_path,
        (f'{key} = "total_return"', f'{key} = "price"'),
        ('position_returns = "', '# position_returns = "'),
    )
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.record["status"] == "success"
    assert PRICE_RETURNS not in str(result.record["notice"])
