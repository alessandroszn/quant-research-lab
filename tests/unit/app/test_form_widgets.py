"""Off-screen tests of the form's widgets (design 12.1b): every kind builds, every widget edits."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QWidget,
)

from qrlab.experiments.kinds import KINDS
from qrlab.experiments.workspace import config_template
from qrlab_app.form import FieldPath, FormModel
from qrlab_app.form_widgets import FormView

ROOT = Path(__file__).parents[3]
EXAMPLES = sorted(
    [*(ROOT / "configs/experiments").glob("*.toml"), *(ROOT / "configs/studies").glob("*.toml")]
)


class Recorder:
    """The form's collaborators: a file to pick and a count of changes."""

    def __init__(self) -> None:
        self.file: Path | None = None
        self.changes = 0

    def view(self, language: str = "en") -> FormView:
        return FormView(language, lambda title: self.file, self._changed)

    def _changed(self) -> None:
        self.changes += 1


def _example(name: str) -> FormModel:
    path = ROOT / "configs" / "experiments" / name
    return FormModel.from_text(path.read_text(encoding="utf-8"), KINDS)


def _button(widget: QWidget, text: str, index: int = -1) -> QPushButton:
    buttons = [b for b in widget.findChildren(QPushButton) if b.text() == text]
    return buttons[index]


def _group(view: FormView, path: FieldPath) -> QGroupBox:
    box = view.editors[path]
    assert isinstance(box, QGroupBox)
    return box


def _edit(view: FormView, path: FieldPath) -> QLineEdit:
    widget = view.editors[path]
    edit = widget if isinstance(widget, QLineEdit) else widget.findChild(QLineEdit)
    assert isinstance(edit, QLineEdit)
    return edit


def _marked(view: FormView) -> QWidget | None:
    """Return the marked widget, read afresh."""
    return view.marked


def _type(view: FormView, path: FieldPath, text: str) -> None:
    edit = _edit(view, path)
    edit.setText(text)
    edit.textEdited.emit(text)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_every_example_builds_a_form(qapp: QApplication, path: Path) -> None:
    view = Recorder().view()
    view.show_model(FormModel.from_text(path.read_text(encoding="utf-8"), KINDS), path)
    assert view.message.text() == ""
    assert _marked(view) is None
    assert ("parameters",) in view.editors
    assert view.kind_label.text().startswith("Kind: ")


@pytest.mark.parametrize("name", sorted(KINDS))
def test_every_template_builds_a_form_in_italian(qapp: QApplication, name: str) -> None:
    view = Recorder().view("it")
    view.show_model(FormModel.from_text(config_template(KINDS[name]), KINDS))
    assert view.message.text().startswith("[parameters]: missing keys")
    assert _marked(view) is not None  # the first missing key is marked
    assert view.kind_label.text() == f"Tipo: {name}"


def test_scalars_choices_and_the_error_mark(qapp: QApplication) -> None:
    user = Recorder()
    view = user.view()
    model = _example("example_backtest.toml")
    view.show_model(model)
    lag = ("parameters", "execution_lag")
    _type(view, lag, "two")
    assert model.value(lag) == "two"
    assert view.message.text() == "[parameters.execution_lag]: an integer is required"
    assert _marked(view) is view.editors[lag]
    assert view.editors[lag].property("formError") is True
    _type(view, lag, "2")
    assert view.message.text() == ""
    assert _marked(view) is None
    assert view.editors[lag].property("formError") is False
    price = view.editors[("parameters", "returns_price_type")]
    assert isinstance(price, QComboBox)
    price.setCurrentText("")
    assert not model.present(("parameters", "returns_price_type"))
    price.setCurrentIndex(1)
    assert model.present(("parameters", "returns_price_type"))
    assert user.changes == 4
    view.show_model(None)
    assert view.kind_label.text() == ""
    assert view.editors == {}


def test_optional_tables_variants_and_lists(qapp: QApplication) -> None:
    user = Recorder()
    view = user.view()
    model = _example("example_backtest.toml")
    view.show_model(model)
    losses = ("parameters", "losses")
    _group(view, losses).setChecked(True)
    assert model.value(losses) == {}
    fund_assets = (*losses, "fund_assets")
    _button(_group(view, fund_assets), "Add").click()
    _button(_group(view, fund_assets), "Add").click()
    assert model.value(fund_assets) == ["", ""]
    _type(view, (*fund_assets, 1), "equity_world")
    _button(_group(view, fund_assets), "Remove", 0).click()
    assert model.value(fund_assets) == ["equity_world"]
    _group(view, losses).setChecked(False)
    assert not model.present(losses)
    assert (*losses, "carry_years") not in view.editors

    selector = view.editors[("parameters", "strategy", "name")]
    assert isinstance(selector, QComboBox)
    selector.setCurrentText("trend")
    assert model.value(("parameters", "strategy")) == {"name": "trend"}
    assert ("parameters", "strategy", "lookback") in view.editors
    assert ("parameters", "strategy", "min_train") not in view.editors
    selector = view.editors[("parameters", "strategy", "name")]
    assert isinstance(selector, QComboBox)
    selector.setCurrentText("")
    assert model.value(("parameters", "strategy")) == {}


def test_maps_of_scalars_and_the_inputs(qapp: QApplication, tmp_path: Path) -> None:
    user = Recorder()
    view = user.view()
    model = _example("example_backtest.toml")
    config = tmp_path / "configs" / "b.toml"
    view.show_model(model, config)
    weights = ("parameters", "initial_weights")
    box = _group(view, weights)
    _button(box, "Add").click()  # no key typed
    assert view.message.text() == "Type the new key first."
    new_key = next(e for e in box.findChildren(QLineEdit) if e.placeholderText() == "New key")
    new_key.setText("gold")
    _button(box, "Add").click()
    assert model.value((*weights, "gold")) == ""
    _type(view, (*weights, "gold"), "")
    assert model.value((*weights, "gold")) == ""  # a blank entry stays, the check names it
    _button(_group(view, weights), "Remove", 0).click()
    assert "equity_world" not in model.value(weights)  # type: ignore[operator]

    returns = ("inputs", "returns")
    choose = _button(view.editors[returns], "Choose…")
    user.file = None
    choose.click()
    assert model.value(returns) == "../../examples/data/asset_returns.csv"
    user.file = tmp_path / "data" / "r.csv"
    choose.click()
    assert model.value(returns) == "../data/r.csv"
    assert _edit(view, returns).text() == "../data/r.csv"
    view.show_model(model)  # no config file: the path is written as chosen
    _button(view.editors[returns], "Choose…").click()
    assert model.value(returns) == (tmp_path / "data" / "r.csv").as_posix()


def test_records_maps_of_tables_and_matrices(qapp: QApplication) -> None:
    view = Recorder().view()
    model = _example("example_projection.toml")
    view.show_model(model)
    flows = ("parameters", "flows")
    count = len(model.value(flows))  # type: ignore[arg-type]
    _button(_group(view, flows), "Add").click()
    assert len(model.value(flows)) == count + 1  # type: ignore[arg-type]
    kind = view.editors[(*flows, count, "kind")]
    assert isinstance(kind, QComboBox)
    kind.setCurrentIndex(1)
    _button(_group(view, (*flows, count)), "Remove").click()
    assert len(model.value(flows)) == count  # type: ignore[arg-type]

    assets = ("parameters", "assets")
    box = _group(view, assets)
    new_key = [e for e in box.findChildren(QLineEdit) if e.placeholderText() == "New key"][-1]
    new_key.setText("gold")
    _button(box, "Add").click()
    assert model.value((*assets, "gold")) == {}
    _type(view, (*assets, "gold", "mean"), "0.03")
    assert model.value((*assets, "gold")) == {"mean": 0.03}
    _button(_group(view, (*assets, "gold")), "Remove").click()
    assert "gold" not in model.value(assets)  # type: ignore[operator]

    where = ("parameters", "correlation")
    size = len(model.value(where))  # type: ignore[arg-type]
    spin = _group(view, where).findChild(QSpinBox)
    assert isinstance(spin, QSpinBox)
    spin.setValue(size + 1)
    matrix = model.value(where)
    assert isinstance(matrix, list)
    assert len(matrix) == size + 1
    assert matrix[size] == [""] * (size + 1)
    grid = _group(view, where).findChild(QTableWidget)
    assert isinstance(grid, QTableWidget)
    cell = grid.item(size, size)
    assert cell is not None
    cell.setText("1")
    assert matrix[size][size] == 1
    assert view.message.text() == "[parameters.correlation]: row 0 must hold numbers"


def test_a_rebuild_keeps_the_scroll_position(qapp: QApplication) -> None:
    view = Recorder().view()
    view.resize(400, 300)
    view.show_model(_example("example_portfolio_report_full.toml"))
    view.show()
    QCoreApplication.processEvents()
    bar = view.area.verticalScrollBar()
    assert bar.maximum() > 100
    bar.setValue(100)
    view.rebuild()
    QCoreApplication.processEvents()
    assert bar.value() == 100
    view.hide()
