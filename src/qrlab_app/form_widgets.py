"""The form's widgets, one per field kind, built from a :class:`FormModel` (design 12.1b).

Scalars are line edits (combo boxes for choices and booleans), so a value can always be left
blank: a spin box or a date edit would always show a value, which would fill one in silently.
Tables, variants, lists, records and maps are group boxes (an optional one has a tick box), a
matrix is a grid. Each field's tooltip is its help in the app's language.

A change of a value runs the schema check and marks the field it names. A change of the form's
shape (a tick box, a variant's option, an item added or removed) builds the form again.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qrlab.experiments.schema import Field, FieldKind
from qrlab_app.form import (
    SCALARS,
    FieldPath,
    FormModel,
    combo_options,
    error_target,
    help_text,
    label_text,
    relative_path,
    scalar_text,
)
from qrlab_app.strings import tr
from qrlab_app.viewmodels import AppError

__all__ = ["MAX_MATRIX", "FormView"]

MAX_MATRIX = 50
"""The largest matrix the form edits (assets in a correlation matrix)."""

_PLACEHOLDERS = {
    FieldKind.DATE: "YYYY-MM-DD",
    FieldKind.DATETIME: "YYYY-MM-DDTHH:MM:SS+01:00",
}
_GRID_HEIGHT = 400  # pixels; a larger matrix scrolls
_ERROR_STYLE = '[formError="true"] { border: 1px solid #c62828; }'


class FormView(QWidget):
    """A scrollable form for one config, with the message of the last check."""

    def __init__(
        self,
        language: str,
        pick_file: Callable[[str], Path | None],
        on_change: Callable[[], None],
    ) -> None:
        """Build an empty form; ``on_change`` runs after every change the user makes."""
        super().__init__()
        self.language = language
        self.pick_file = pick_file
        self.on_change = on_change
        self.model: FormModel | None = None
        self.config_path: Path | None = None
        self.editors: dict[FieldPath, QWidget] = {}
        self.marked: QWidget | None = None
        self.kind_label = QLabel("")
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.setStyleSheet(_ERROR_STYLE)
        layout = QVBoxLayout(self)
        layout.addWidget(self.kind_label)
        layout.addWidget(self.area)
        layout.addWidget(self.message)

    # ------------------------------------------------------------------------ showing
    def show_model(self, model: FormModel | None, config_path: Path | None = None) -> None:
        """Show ``model`` (``None`` empties the form); inputs are chosen relative to the config."""
        self.model = model
        self.config_path = config_path
        self.rebuild()

    def rebuild(self) -> None:
        """Build the widgets again from the model, keeping the scroll position."""
        bar = self.area.verticalScrollBar()
        position = bar.value()
        old = self.area.takeWidget()
        if old is not None:
            old.deleteLater()  # it may be sending the signal that led here
        self.editors = {}
        self.marked = None
        inner = QWidget()
        layout = QVBoxLayout(inner)
        model = self.model
        if model is None:
            self.kind_label.setText("")
        else:
            self.kind_label.setText(tr("form.kind", self.language, kind=model.kind.name))
            for spec in model.fields:
                layout.addWidget(self._group(spec, (spec.key,)))
        layout.addStretch()
        self.area.setWidget(inner)
        QTimer.singleShot(0, lambda: bar.setValue(position))
        self.show_error(None if model is None else model.check())

    def show_error(self, message: str | None) -> None:
        """Show the check's message and mark the field it is about."""
        if self.marked is not None:
            self._mark(self.marked, on=False)
            self.marked = None
        self.message.setText(message or "")
        target = None if message is None else error_target(message, self.editors)
        if target is not None:
            self.marked = self.editors[target]
            self._mark(self.marked, on=True)

    @staticmethod
    def _mark(widget: QWidget, *, on: bool) -> None:
        widget.setProperty("formError", on)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # ------------------------------------------------------------------------ building
    def _field(self, spec: Field, path: FieldPath, form: QFormLayout) -> None:
        if spec.kind in SCALARS:
            form.addRow(self._label(spec), self._scalar(spec, path))
        else:
            form.addRow(self._group(spec, path))

    def _label(self, spec: Field) -> QLabel:
        label = QLabel(label_text(spec, self.language))
        label.setToolTip(help_text(spec, self.language))
        return label

    def _scalar(self, spec: Field, path: FieldPath, *, entry: bool = False) -> QWidget:
        """Return a line edit, or a combo box for a choice or a boolean; inputs get *Choose…*."""
        model = self._require()
        text = scalar_text(model.value(path))
        options = combo_options(spec)
        widget: QWidget
        if options is not None:
            box = QComboBox()
            box.addItems(list(options))
            box.setCurrentIndex(options.index(text))
            box.currentTextChanged.connect(lambda t: self._set_text(path, spec, t, entry))
            widget = box
        else:
            edit = QLineEdit(text)
            edit.setPlaceholderText(_PLACEHOLDERS.get(spec.kind, ""))
            edit.textEdited.connect(lambda t: self._set_text(path, spec, t, entry))
            widget = edit
            if path[0] == "inputs":
                widget = QWidget()
                row = QHBoxLayout(widget)
                row.setContentsMargins(0, 0, 0, 0)
                choose = QPushButton(tr("form.choose", self.language))
                choose.clicked.connect(lambda: self._choose_file(path, spec, edit, entry))
                row.addWidget(edit)
                row.addWidget(choose)
        widget.setToolTip(help_text(spec, self.language))
        self.editors[path] = widget
        return widget

    def _group(self, spec: Field, path: FieldPath) -> QGroupBox:
        """Return a group box for a table, variant, list, records, map or matrix."""
        box = QGroupBox(label_text(spec, self.language))
        box.setToolTip(help_text(spec, self.language))
        self.editors[path] = box
        if not spec.required:
            present = self._require().present(path)
            box.setCheckable(True)
            box.setChecked(present)
            box.toggled.connect(lambda on: self._structure(lambda m: m.include(path, spec, on)))
            if not present:
                return box
        self._inside(spec, path, box)
        return box

    def _inside(self, spec: Field, path: FieldPath, box: QGroupBox) -> QFormLayout:
        form = QFormLayout(box)
        kind = spec.kind
        if kind is FieldKind.TABLE:
            for child in spec.fields:
                self._field(child, (*path, child.key), form)
        elif kind is FieldKind.VARIANT:
            self._variant(spec, path, form)
        elif kind is FieldKind.LIST:
            self._list(spec, path, form)
        elif kind is FieldKind.RECORDS:
            self._records(spec, path, form)
        elif kind is FieldKind.MAP:
            self._map(spec, path, form)
        else:
            self._matrix(path, form)
        return form

    def _variant(self, spec: Field, path: FieldPath, form: QFormLayout) -> None:
        assert spec.selector is not None  # a variant has one
        value = self._require().value(path)
        option = str(value.get(spec.selector, "")) if isinstance(value, dict) else ""
        options = ("", *spec.variants)
        box = QComboBox()
        box.addItems(list(options))
        box.setCurrentIndex(options.index(option))
        box.currentTextChanged.connect(lambda t: self._structure(lambda m: m.choose(path, spec, t)))
        form.addRow(QLabel(spec.selector), box)
        self.editors[(*path, spec.selector)] = box
        for child in spec.variants.get(option, ()):
            self._field(child, (*path, child.key), form)

    def _list(self, spec: Field, path: FieldPath, form: QFormLayout) -> None:
        assert spec.item is not None  # a list has one
        items = self._require().value(path)
        for index in range(len(items) if isinstance(items, list) else 0):
            here = (*path, index)
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(self._scalar(spec.item, here, entry=True))
            line.addWidget(self._remove_button(here))
            form.addRow(QLabel(f"[{index}]"), row)
        form.addRow(self._add_button(lambda m: m.add_item(path, spec)))

    def _records(self, spec: Field, path: FieldPath, form: QFormLayout) -> None:
        records = self._require().value(path)
        for index in range(len(records) if isinstance(records, list) else 0):
            here = (*path, index)
            record = QGroupBox(f"{spec.key}[{index}]")
            self.editors[here] = record
            inner = QFormLayout(record)
            for child in spec.fields:
                self._field(child, (*here, child.key), inner)
            inner.addRow(self._remove_button(here))
            form.addRow(record)
        form.addRow(self._add_button(lambda m: m.add_item(path, spec)))

    def _map(self, spec: Field, path: FieldPath, form: QFormLayout) -> None:
        item = spec.item
        assert item is not None  # a map has one
        entries = self._require().value(path)
        for key in list(entries) if isinstance(entries, dict) else []:
            here = (*path, key)
            if item.kind in SCALARS:
                row = QWidget()
                line = QHBoxLayout(row)
                line.setContentsMargins(0, 0, 0, 0)
                line.addWidget(self._scalar(item, here, entry=True))
                line.addWidget(self._remove_button(here))
                form.addRow(QLabel(key), row)
            else:
                entry = QGroupBox(key)
                entry.setToolTip(help_text(item, self.language))
                self.editors[here] = entry
                self._inside(item, here, entry).addRow(self._remove_button(here))
                form.addRow(entry)
        new_key = QLineEdit()
        new_key.setPlaceholderText(tr("form.new_key", self.language))
        add = QPushButton(tr("form.add", self.language))
        add.clicked.connect(lambda: self._add_entry(path, spec, new_key.text()))
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(new_key)
        line.addWidget(add)
        form.addRow(row)

    def _matrix(self, path: FieldPath, form: QFormLayout) -> None:
        value = self._require().value(path)
        rows = value if isinstance(value, list) else []
        size = QSpinBox()
        size.setRange(0, MAX_MATRIX)
        size.setValue(len(rows))
        size.valueChanged.connect(lambda n: self._structure(lambda m: m.resize(path, n)))
        form.addRow(QLabel(tr("form.size", self.language)), size)
        grid = QTableWidget(len(rows), len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                grid.setItem(r, c, QTableWidgetItem(scalar_text(cell)))
        grid.itemChanged.connect(lambda i: self._cell(path, i.row(), i.column(), i.text()))
        height = grid.horizontalHeader().sizeHint().height() + grid.verticalHeader().length()
        grid.setMinimumHeight(min(height + 2 * grid.frameWidth(), _GRID_HEIGHT))
        form.addRow(grid)

    def _remove_button(self, path: FieldPath) -> QPushButton:
        button = QPushButton(tr("form.remove", self.language))
        button.clicked.connect(lambda: self._structure(lambda m: m.remove(path)))
        return button

    def _add_button(self, change: Callable[[FormModel], None]) -> QPushButton:
        button = QPushButton(tr("form.add", self.language))
        button.clicked.connect(lambda: self._structure(change))
        return button

    # ------------------------------------------------------------------------ changes
    def _require(self) -> FormModel:
        assert self.model is not None  # widgets exist only while a model is shown
        return self.model

    def _set_text(self, path: FieldPath, spec: Field, text: str, entry: bool) -> None:
        model = self._require()
        model.set_text(path, spec, text, entry=entry)
        self.show_error(model.check())
        self.on_change()

    def _cell(self, path: FieldPath, row: int, column: int, text: str) -> None:
        model = self._require()
        model.set_cell(path, row, column, text)
        self.show_error(model.check())
        self.on_change()

    def _choose_file(self, path: FieldPath, spec: Field, edit: QLineEdit, entry: bool) -> None:
        chosen = self.pick_file(tr("form.choose", self.language))
        if chosen is None:
            return
        text = relative_path(chosen, self.config_path) if self.config_path else chosen.as_posix()
        edit.setText(text)
        self._set_text(path, spec, text, entry)

    def _add_entry(self, path: FieldPath, spec: Field, key: str) -> None:
        try:
            self._require().add_entry(path, spec, key)
        except AppError as exc:
            self.message.setText(exc.text(self.language))
            return
        self._structure(lambda m: None)

    def _structure(self, change: Callable[[FormModel], None]) -> None:
        """Apply a change of the form's shape, build the form again and report it."""
        change(self._require())
        self.rebuild()
        self.on_change()
