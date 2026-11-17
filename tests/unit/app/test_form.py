"""The form's Qt-free model (design 12.1b): values by path, showability, round trip, checks."""

from __future__ import annotations

import math
import tomllib
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import tomli_w

from qrlab.experiments.kinds import KINDS
from qrlab.experiments.schema import Field, FieldKind, Help, KindSchema, check_parameters
from qrlab.experiments.workspace import config_template
from qrlab_app.form import (
    FormModel,
    combo_options,
    config_fields,
    error_target,
    help_text,
    label_text,
    parse_scalar,
    path_text,
    relative_path,
    scalar_text,
)
from qrlab_app.viewmodels import (
    AppError,
    ExperimentViewModel,
    WorkspaceViewModel,
    has_comments,
)

ROOT = Path(__file__).parents[3]
EXAMPLES = sorted(
    [*(ROOT / "configs/experiments").glob("*.toml"), *(ROOT / "configs/studies").glob("*.toml")]
)
H = Help("h", "h")


def _spec(kind: FieldKind, **options: object) -> Field:
    return Field("x", kind, H, **options)  # type: ignore[arg-type]


def _text(**parameters: str) -> str:
    """Return a backtest config with ``parameters`` written as TOML values."""
    lines = "\n".join(f"{k} = {v}" for k, v in parameters.items())
    return (
        '[experiment]\nname = "n"\nkind = "backtest"\nhypothesis = "h"\n\n'
        '[inputs]\nreturns = "r.csv"\n\n'
        f"[parameters]\n{lines}\n\n"
        '[output]\ndirectory = "out"\n'
    )


# ------------------------------------------------------------------------------ scalars
def test_scalar_text() -> None:
    assert scalar_text(None) == ""
    assert scalar_text(True) == "true"
    assert scalar_text(False) == "false"
    assert scalar_text(12) == "12"
    assert scalar_text(0.26) == "0.26"
    assert scalar_text(1.0) == "1.0"
    assert scalar_text(1e-05) == "1e-05"
    assert scalar_text(math.inf) == "inf"
    assert scalar_text(date(2026, 1, 2)) == "2026-01-02"
    assert scalar_text(datetime(2026, 1, 2, 9, 30, tzinfo=UTC)) == "2026-01-02T09:30:00+00:00"
    assert scalar_text("EUR") == "EUR"


def test_parse_scalar_reads_each_kind_and_keeps_other_text() -> None:
    integer, number = _spec(FieldKind.INTEGER), _spec(FieldKind.NUMBER)
    assert parse_scalar(integer, " 12 ") == 12
    assert parse_scalar(integer, "12.0") == "12.0"  # not an integer: kept as typed
    assert parse_scalar(integer, "abc") == "abc"
    assert type(parse_scalar(number, "12")) is int  # as TOML: 12 is an integer
    assert parse_scalar(number, "12.0") == 12.0
    assert type(parse_scalar(number, "12.0")) is float
    assert parse_scalar(number, "-3") == -3
    assert parse_scalar(number, "1e-05") == 1e-05
    assert parse_scalar(number, "inf") == math.inf
    assert parse_scalar(number, "ter") == "ter"
    assert parse_scalar(_spec(FieldKind.NUMBER, also=("ter",)), " ter ") == "ter"
    assert parse_scalar(_spec(FieldKind.DATE), "2026-01-02") == date(2026, 1, 2)
    assert parse_scalar(_spec(FieldKind.DATE), "2 Jan") == "2 Jan"
    assert parse_scalar(_spec(FieldKind.DATETIME), "2026-01-02T09:30:00+01:00") == datetime(
        2026, 1, 2, 8, 30, tzinfo=UTC
    )
    assert parse_scalar(_spec(FieldKind.BOOLEAN), "true") is True
    assert parse_scalar(_spec(FieldKind.BOOLEAN), "false") is False
    assert parse_scalar(_spec(FieldKind.BOOLEAN), "yes") == "yes"
    assert parse_scalar(_spec(FieldKind.TEXT), " a b ") == " a b "  # text as typed


def test_combo_options() -> None:
    assert combo_options(_spec(FieldKind.CHOICE, choices=("a", "b"))) == ("", "a", "b")
    assert combo_options(_spec(FieldKind.BOOLEAN)) == ("", "true", "false")
    assert combo_options(_spec(FieldKind.TEXT)) is None


# ------------------------------------------------------------------------------ paths
def test_path_text_is_the_checks_own() -> None:
    assert path_text(("parameters",)) == "[parameters]"
    assert path_text(("parameters", "risk", "window")) == "[parameters.risk.window]"
    assert path_text(("parameters", "percentiles", 2)) == "[parameters.percentiles][2]"
    assert path_text(("parameters", "flows", 0, "amount")) == "[parameters.flows][0].amount"
    assert path_text(("parameters", "taxes", "2026")) == "[parameters.taxes.2026]"
    # The check writes the same paths.
    flows = Field("flows", FieldKind.RECORDS, H, fields=(Field("amount", FieldKind.NUMBER, H),))
    schema = KindSchema((), (flows,))
    with pytest.raises(ValueError, match=r"^\[parameters\.flows\]\[0\]\.amount: a number"):
        check_parameters(schema, {"flows": [{"amount": "x"}]})


def test_error_target() -> None:
    risk, window = ("parameters", "risk"), ("parameters", "risk", "window")
    paths = [("parameters",), risk, window]
    assert error_target("[parameters.risk.window]: an integer is required", paths) == window
    assert error_target("[parameters.risk]: missing keys ['window', 'x']", paths) == window
    assert error_target("[parameters.risk]: missing keys ['other']", paths) == risk
    assert error_target("[parameters.risk] must be a table", paths) == risk
    assert error_target("[parameters.riskier]: x", paths) is None
    assert error_target("[parameters]: unknown keys ['z']", paths) == ("parameters",)
    proxies = ("parameters", "proxies")
    assert error_target("[parameters.proxies] key: 'X' is not a valid isin", [proxies]) == proxies


def test_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "configs" / "a.toml"
    assert relative_path(tmp_path / "data" / "r.csv", config) == "../data/r.csv"
    assert relative_path(tmp_path / "configs" / "r.csv", config) == "r.csv"

    def other_drive(path: object, start: object) -> str:
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr("qrlab_app.form.os.path.relpath", other_drive)
    assert relative_path(tmp_path / "r.csv", config) == (tmp_path / "r.csv").as_posix()


def test_labels_and_help() -> None:
    window = Field(
        "window", FieldKind.INTEGER, Help("Days used.", "Giorni usati."), unit="days", minimum=2
    )
    assert label_text(window, "en") == "window (days)"
    assert label_text(window, "it") == "window (giorni)"
    assert label_text(_spec(FieldKind.TEXT), "en") == "x"
    assert help_text(window, "en") == "Days used.\nRequired.\nRange: ≥ 2."
    assert help_text(window, "it") == "Giorni usati.\nObbligatorio.\nIntervallo: ≥ 2."
    rate = Field(
        "rate",
        FieldKind.NUMBER,
        H,
        required=False,
        minimum=0,
        maximum=1,
        open_minimum=True,
        open_maximum=True,
        also=("ter",),
    )
    assert help_text(rate, "en").splitlines()[1:] == [
        "Optional: leave it blank (or unticked) to switch it off.",
        "Range: > 0, < 1.",
        "Also accepted: ter.",
    ]


def test_has_comments() -> None:
    assert has_comments("a = 1  # note")
    assert has_comments("# a header\na = 1")
    assert not has_comments("a = 1\nb = [1, 2]\n")
    assert not has_comments('a = "#1"')
    assert not has_comments("a = '#1'")
    assert not has_comments('a = "quote \\" # still text"')
    assert not has_comments('a = """\nline # text\n"""')
    assert not has_comments("a = '''# text'''")
    assert has_comments('a = """x""""  # after a string ending in a quote')
    assert not has_comments('"key#1" = 2')
    assert not has_comments('a = "unterminated')


# ------------------------------------------------------------------------------ the fields
def test_config_fields() -> None:
    backtest = config_fields(KINDS["backtest"])
    assert [f.key for f in backtest] == ["experiment", "inputs", "parameters", "output"]
    experiment = {f.key: f for f in backtest[0].fields}
    assert set(experiment) == {"name", "hypothesis", "seed"}
    assert not experiment["seed"].required
    assert {f.key: f for f in config_fields(KINDS["projection"])[0].fields}["seed"].required
    assert [f.key for f in config_fields(KINDS["projection"])] == [
        "experiment",
        "parameters",
        "output",
    ]
    inputs = {f.key: f for f in config_fields(KINDS["portfolio_report"])[1].fields}
    assert inputs["holdings"].kind is FieldKind.MAP
    assert inputs["fx"].kind is FieldKind.TEXT
    assert not inputs["fx"].required
    with pytest.raises(AppError, match="has no schema"):
        config_fields(replace(KINDS["backtest"], schema=None))


# ------------------------------------------------------------------------------ reading
@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_every_example_shows_and_round_trips(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    form = FormModel.from_text(text, KINDS)
    assert tomllib.loads(form.to_text()) == tomllib.loads(text)
    assert form.check() is None


@pytest.mark.parametrize("name", sorted(KINDS))
def test_every_template_shows(name: str) -> None:
    text = config_template(KINDS[name])
    form = FormModel.from_text(text, KINDS)
    assert tomllib.loads(form.to_text()) == tomllib.loads(text)
    assert (form.check() or "").startswith("[parameters]: missing keys")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("a = ", "needs valid TOML"),
        ("[output]\ndirectory = 'x'\n", "known \\[experiment\\] kind, not None"),
        ('[experiment]\nkind = "nope"\n', "not 'nope'"),
        ('experiment = "x"\n', "not None"),
        (_text() + "[extra]\na = 1\n", r"\[extra\]: unknown section"),
        (_text(window="1"), r"\[parameters\]: unknown keys \['window'\]"),
        (_text(currency="1"), r"\[parameters.currency\]: 1 cannot be shown"),
        (_text(returns_price_type='"nope"'), r"returns_price_type\]: 'nope' cannot be shown"),
        (_text(strategy='{ name = "nope" }'), r"strategy\]: name = 'nope' is not an option"),
        (_text(strategy="{ lookback = 3 }"), r"strategy\]: name = None is not an option"),
        (_text(strategy='{ name = "trend", x = 1 }'), r"strategy\]: unknown keys \['x'\]"),
        (_text(costs="1"), r"\[parameters.costs\]: a table is required"),
        (_text(losses="{ fund_assets = 1 }"), r"losses.fund_assets\]: a list is required"),
    ],
)
def test_configs_the_form_cannot_show_exactly_are_refused(text: str, message: str) -> None:
    with pytest.raises(AppError, match=message):
        FormModel.from_text(text, KINDS)


def _projection(**changes: object) -> str:
    """Return the example projection with ``changes`` to its parameters, as TOML."""
    raw = tomllib.loads(
        (ROOT / "configs/experiments/example_projection.toml").read_text(encoding="utf-8")
    )
    raw["parameters"].update(changes)
    return tomli_w.dumps(raw)


def test_projection_inputs_records_and_matrices() -> None:
    assert FormModel.from_text(_projection(), KINDS).value(("inputs",)) == {}  # kept as is
    with pytest.raises(AppError, match=r"\[inputs\]: unknown section"):
        FormModel.from_text(_projection().replace("[inputs]", '[inputs]\nx = "a.csv"'), KINDS)
    with pytest.raises(AppError, match=r"\[parameters.flows\]\[0\]: a table is required"):
        FormModel.from_text(_projection(flows=[1]), KINDS)
    with pytest.raises(AppError, match=r"\[parameters.flows\]: a list is required"):
        FormModel.from_text(_projection(flows={"a": 1}), KINDS)
    with pytest.raises(AppError, match=r"correlation\]: a square list of rows"):
        FormModel.from_text(_projection(correlation=[[1.0], [1.0]]), KINDS)
    with pytest.raises(AppError, match=r"correlation\]: a cell cannot be shown"):
        FormModel.from_text(_projection(correlation=[[True]]), KINDS)
    shown = FormModel.from_text(_projection(correlation=[[1.0, "x"], ["", 1]]), KINDS)
    assert shown.check() == "[parameters.correlation]: row 0 must hold numbers"


def test_a_list_of_tables_is_refused() -> None:
    table = Field("t", FieldKind.TABLE, H, fields=(Field("a", FieldKind.TEXT, H),))
    odd = Field("odd", FieldKind.LIST, H, item=table)
    kind = replace(KINDS["backtest"], schema=KindSchema((), (odd,)))
    text = _text(odd='[{ a = "x" }]').replace('[inputs]\nreturns = "r.csv"', "[inputs]")
    with pytest.raises(AppError, match=r"\[parameters.odd\]: a list of tables cannot be shown"):
        FormModel.from_text(text, {"backtest": kind})


# ------------------------------------------------------------------------------ changing
def _backtest() -> FormModel:
    return FormModel.from_text(
        (ROOT / "configs/experiments/example_backtest.toml").read_text(encoding="utf-8"), KINDS
    )


def _field(path: tuple[str, ...]) -> Field:
    fields = config_fields(KINDS["backtest"])
    spec: Field | None = None
    for step in path:
        spec = next(f for f in fields if f.key == step)
        fields = spec.fields
    assert spec is not None
    return spec


def test_values_and_text() -> None:
    form = _backtest()
    lag = ("parameters", "execution_lag")
    assert form.value(lag) == 1
    assert form.value(("parameters", "nope", "x")) is None
    assert form.value(("parameters", "execution_lag", "x")) is None
    assert form.present(lag)
    spec = _field(lag)
    form.set_text(lag, spec, "2")
    assert form.value(lag) == 2
    form.set_text(lag, spec, "two")
    assert form.value(lag) == "two"
    assert form.check() == "[parameters.execution_lag]: an integer is required"
    form.set_text(lag, spec, "  ")  # blank: the key is absent
    assert not form.present(lag)
    assert form.check() == "[parameters]: missing keys ['execution_lag']"
    form.set_text(("parameters", "costs", "fixed"), _field(("parameters", "costs")).fields[1], "")
    assert form.value(("parameters", "costs")) == {"proportional": 0.001}
    first = _field(("experiment", "name"))
    form.set_text(("experiment", "name"), first, "renamed")
    assert form.to_config()["experiment"] == {
        "name": "renamed",
        "kind": "backtest",
        "hypothesis": (
            "Walk-forward minimum variance has lower volatility than buy-and-hold after costs"
        ),
    }


def test_text_creates_the_tables_on_the_way() -> None:
    form = FormModel.from_text(config_template(KINDS["backtest"]), KINDS)
    spec = _field(("parameters", "costs")).fields[0]
    form.set_text(("parameters", "costs", "proportional"), spec, "0.001")
    assert form.value(("parameters",)) == {"costs": {"proportional": 0.001}}


def test_include_and_choose() -> None:
    form = _backtest()
    losses = _field(("parameters", "losses"))
    assert not form.present(("parameters", "losses"))
    form.include(("parameters", "losses"), losses, True)
    assert form.value(("parameters", "losses")) == {}
    form.set_text(("parameters", "losses", "carry_years"), losses.fields[0], "4")
    form.include(("parameters", "losses"), losses, True)  # already on: kept
    assert form.value(("parameters", "losses")) == {"carry_years": 4}
    form.include(("parameters", "losses"), losses, False)
    assert not form.present(("parameters", "losses"))

    strategy = _field(("parameters", "strategy"))
    where = ("parameters", "strategy")
    form.choose(where, strategy, "walk_forward")  # the same option: all its fields are kept
    assert form.value(where) == {
        "name": "walk_forward",
        "method": "minimum_variance",
        "min_train": 36,
        "step": 12,
        "max_weight": 0.6,
    }
    form.choose(where, strategy, "trend")  # it shares no field with walk_forward
    assert form.value(where) == {"name": "trend"}
    lookback = next(f for f in strategy.variants["trend"] if f.key == "lookback")
    form.set_text((*where, "lookback"), lookback, "12")
    form.set_text((*where, "cash"), lookback, "cash")
    form.choose(where, strategy, "momentum")  # lookback is described the same way: kept
    assert form.value(where) == {"name": "momentum", "lookback": 12}
    form.choose(where, strategy, "")
    assert form.value(where) == {}
    form.remove(where)
    form.choose(where, strategy, "buy_and_hold")
    assert form.value(where) == {"name": "buy_and_hold"}


def test_lists_records_and_maps() -> None:
    form = FormModel.from_text(config_template(KINDS["projection"]), KINDS)
    fields = {f.key: f for f in KINDS["projection"].schema.parameters}  # type: ignore[union-attr]
    percentiles = ("parameters", "percentiles")
    form.add_item(percentiles, fields["percentiles"])  # creates the list
    form.add_item(percentiles, fields["percentiles"])
    assert form.value(percentiles) == ["", ""]
    item = fields["percentiles"].item
    assert item is not None
    form.set_text((*percentiles, 1), item, "0.5")
    form.set_text((*percentiles, 0), item, " ", entry=True)  # a blank item stays
    assert form.value(percentiles) == [" ", 0.5]
    form.remove((*percentiles, 0))
    assert form.value(percentiles) == [0.5]
    form.remove((*percentiles, 5))  # nothing there
    form.remove(("parameters", "nope", "x"))  # nothing there
    assert form.value(percentiles) == [0.5]

    flows = ("parameters", "flows")
    form.add_item(flows, fields["flows"])
    assert form.value(flows) == [{}]

    assets = ("parameters", "assets")
    spec = fields["assets"]
    with pytest.raises(AppError, match="Type the new key first"):
        form.add_entry(assets, spec, "  ")
    form.add_entry(assets, spec, " equity ")  # an asset is a table
    with pytest.raises(AppError, match="The key equity is already there"):
        form.add_entry(assets, spec, "equity")
    assert form.value(assets) == {"equity": {}}


def test_map_entries_of_scalars_keep_blank_text() -> None:
    form = _backtest()
    weights = ("parameters", "initial_weights")
    spec = _field(weights)
    assert spec.item is not None
    form.add_entry(weights, spec, "gold")
    assert form.value((*weights, "gold")) == ""
    form.set_text((*weights, "gold"), spec.item, "", entry=True)
    assert form.value((*weights, "gold")) == ""
    form.set_text((*weights, "cash"), spec.item, "0.5", entry=True)
    assert form.value((*weights, "cash")) == 0.5


def test_matrices() -> None:
    form = FormModel.from_text(config_template(KINDS["projection"]), KINDS)
    where = ("parameters", "correlation")
    form.resize(where, 2)
    assert form.value(where) == [["", ""], ["", ""]]
    form.set_cell(where, 0, 0, "1")
    form.set_cell(where, 0, 1, "0.3")
    form.set_cell(where, 1, 0, "x")
    form.set_cell(where, 1, 1, " ")
    assert form.value(where) == [[1, 0.3], ["x", ""]]
    form.resize(where, 3)
    assert form.value(where) == [[1, 0.3, ""], ["x", "", ""], ["", "", ""]]
    form.resize(where, 1)
    assert form.value(where) == [[1]]
    form.resize(where, -1)
    assert form.value(where) == []


def test_text_out_has_the_usual_order_and_no_comments() -> None:
    text = _text(execution_lag="1").replace("[experiment]", "[output]\ndirectory = 'o'\n\n[x]")
    with pytest.raises(AppError):
        FormModel.from_text(text, KINDS)
    form = FormModel.from_text(
        '[output]\ndirectory = "o"\n\n[parameters]\n\n[experiment]\nname = "n"\n'
        'kind = "backtest"\nhypothesis = "h"\n\n[inputs]\n',
        KINDS,
    )
    assert list(form.to_config()) == ["experiment", "inputs", "parameters", "output"]
    assert not has_comments(form.to_text())


# ------------------------------------------------------------------------------ the screen's model
def _flags(model: ExperimentViewModel) -> tuple[bool, bool]:
    """Return ``form_wrote`` and ``loses_comments``, read afresh."""
    return model.form_wrote, model.loses_comments


def test_the_experiment_model_knows_when_comments_would_be_lost(tmp_path: Path) -> None:
    workspace = WorkspaceViewModel()
    workspace.create(tmp_path / "ws")
    model = ExperimentViewModel(workspace, kinds=KINDS, kind_names=["backtest"])
    path = tmp_path / "ws" / "configs" / "b.toml"
    text = (ROOT / "configs/experiments/example_backtest.toml").read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    model.select(path)
    assert _flags(model)[1] is False
    model.set_text(text + "\n")  # typed in the TOML tab: comments are the user's own
    assert _flags(model)[1] is False
    form = FormModel.from_text(model.text, KINDS)
    model.set_form_text(form.to_text())
    assert _flags(model)[0] is True
    assert _flags(model)[1] is True
    model.revert()
    assert _flags(model)[0] is False
    model.set_form_text(form.to_text())
    model.save()
    assert _flags(model)[1] is False  # the saved file has no comments any more
    model.set_form_text(form.to_text() + "\n")
    assert _flags(model)[1] is False
    model.select(path)
    assert _flags(model)[0] is False
    model.set_form_text("x")
    model.clear()
    assert _flags(model)[0] is False


def test_an_empty_variant_is_shown_without_an_option() -> None:
    form = FormModel.from_text(_text(strategy="{}"), KINDS)
    assert form.value(("parameters", "strategy")) == {}
    assert (form.check() or "").startswith("[parameters]: missing keys")
