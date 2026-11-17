"""The form of an analysis config: Qt-free state built from the kind's schema (design 12.1b).

The form edits the same config as the TOML editor. :class:`FormModel` holds the parsed config
and changes it by *path*, a tuple of keys and list indices such as
``("parameters", "risk", "window")``. Widgets only show its values and forward what the user
types.

Rules that keep the form honest:

- **Nothing is filled silently.** Every scalar is typed as text and can be left blank; a blank
  key of a table is absent from the config. A new list item, map entry or matrix cell is the
  empty text until it is filled, and the check names it.
- **Nothing is dropped silently.** A config the form cannot show exactly (an unknown key, or a
  value whose text would not read back as the same value) is refused with the key's path; the
  screen keeps it in the TOML tab.
- **What is typed is kept.** Text that does not read as the field's type (``"abc"`` for a
  window) is stored as text, so the schema check names the key instead of the form guessing.

The checks are the library's: :func:`qrlab.experiments.schema.check_parameters` after each
change, and the runner's validation on *Validate*.
"""

from __future__ import annotations

import ast
import copy
import os
import re
import tomllib
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import tomli_w

from qrlab.experiments.registry import ExperimentKind
from qrlab.experiments.schema import Field, FieldKind, Help, InputSpec, check_parameters
from qrlab_app.strings import tr, tr_value
from qrlab_app.viewmodels import AppError

__all__ = [
    "SCALARS",
    "FieldPath",
    "FormModel",
    "combo_options",
    "config_fields",
    "error_target",
    "help_text",
    "label_text",
    "parse_scalar",
    "path_text",
    "relative_path",
    "scalar_text",
]

FieldPath = tuple[str | int, ...]
"""Where a value is: section, keys and list indices, e.g. ``("parameters", "flows", 0)``."""

SCALARS = frozenset(
    {
        FieldKind.TEXT,
        FieldKind.INTEGER,
        FieldKind.NUMBER,
        FieldKind.BOOLEAN,
        FieldKind.DATE,
        FieldKind.DATETIME,
        FieldKind.CHOICE,
        FieldKind.CURRENCY,
        FieldKind.ISIN,
    }
)
"""Field kinds edited as one text (a line edit, or a combo box for choices and booleans)."""

_SECTIONS = ("experiment", "inputs", "parameters", "output")
_INTEGER_TEXT = re.compile(r"[+-]?\d+")
_NOT_SHOWN = "cannot be shown in the form exactly"
_EMPTY: dict[FieldKind, object] = {
    FieldKind.TABLE: {},
    FieldKind.MAP: {},
    FieldKind.VARIANT: {},
    FieldKind.LIST: [],
    FieldKind.RECORDS: [],
    FieldKind.MATRIX: [],
}


def _help(key: str) -> Help:
    return Help(en=tr(key, "en"), it=tr(key, "it"))


_CELL = Field("cell", FieldKind.NUMBER, _help("form.help.cell"))


# ------------------------------------------------------------------------------ the fields
def config_fields(kind: ExperimentKind) -> tuple[Field, ...]:
    """Return the form's sections for ``kind``: experiment, inputs, parameters and output.

    ``[experiment] kind`` is not a field: it is shown, never edited. A kind without inputs has
    no inputs section.

    Raises
    ------
    AppError
        When the kind has no schema.
    """
    schema = kind.schema
    if schema is None:
        raise AppError("form.no_schema", kind=kind.name)
    experiment = Field(
        "experiment",
        FieldKind.TABLE,
        _help("form.help.experiment"),
        fields=(
            Field("name", FieldKind.TEXT, _help("form.help.name")),
            Field("hypothesis", FieldKind.TEXT, _help("form.help.hypothesis")),
            Field(
                "seed",
                FieldKind.INTEGER,
                _help("form.help.seed"),
                required=kind.needs_seed,
                minimum=0,
            ),
        ),
    )
    sections = [experiment]
    if schema.inputs:
        sections.append(
            Field(
                "inputs",
                FieldKind.TABLE,
                _help("form.help.inputs"),
                fields=tuple(_input_field(spec) for spec in schema.inputs),
                allow_empty=True,
            )
        )
    sections.append(
        Field(
            "parameters",
            FieldKind.TABLE,
            _help("form.help.parameters"),
            fields=schema.parameters,
            allow_empty=True,
        )
    )
    sections.append(
        Field(
            "output",
            FieldKind.TABLE,
            _help("form.help.output"),
            fields=(Field("directory", FieldKind.TEXT, _help("form.help.directory")),),
        )
    )
    return tuple(sections)


def _input_field(spec: InputSpec) -> Field:
    if spec.group:
        path = Field("path", FieldKind.TEXT, spec.help)
        return Field(
            spec.name, FieldKind.MAP, spec.help, required=False, key_kind=FieldKind.TEXT, item=path
        )
    return Field(spec.name, FieldKind.TEXT, spec.help, required=spec.required)


# ------------------------------------------------------------------------------ scalars
def scalar_text(value: object) -> str:
    """Return the text a scalar value is shown as; ``None`` (absent) is the empty text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, date):  # also a datetime
        return value.isoformat()
    return str(value)


def parse_scalar(spec: Field, text: str) -> object:
    """Read ``text`` as a value of ``spec``; text that does not read as its type stays text.

    Numbers keep their written type: ``12`` is an integer and ``12.0`` a float, as in TOML.
    """
    stripped = text.strip()
    kind = spec.kind
    if spec.also and stripped in spec.also:
        return stripped
    try:
        if kind is FieldKind.INTEGER:
            return int(stripped)
        if kind is FieldKind.NUMBER:
            return int(stripped) if _INTEGER_TEXT.fullmatch(stripped) else float(stripped)
        if kind is FieldKind.DATE:
            return date.fromisoformat(stripped)
        if kind is FieldKind.DATETIME:
            return datetime.fromisoformat(stripped)
    except ValueError:
        return text
    if kind is FieldKind.BOOLEAN and stripped in ("true", "false"):
        return stripped == "true"
    return text


def combo_options(spec: Field) -> tuple[str, ...] | None:
    """Return the texts of a combo box for ``spec`` (the first, empty, means not set), or None."""
    if spec.kind is FieldKind.CHOICE:
        return ("", *spec.choices)
    if spec.kind is FieldKind.BOOLEAN:
        return ("", "true", "false")
    return None


def _shows(spec: Field, value: object) -> bool:
    """Whether the form shows ``value`` exactly: its text reads back as the same value."""
    text = scalar_text(value)
    options = combo_options(spec)
    if options is not None and text not in options:
        return False
    back = parse_scalar(spec, text)
    return type(back) is type(value) and back == value


# ------------------------------------------------------------------------------ paths
def path_text(path: FieldPath) -> str:
    """Return a path as the schema check writes it, e.g. ``[parameters.flows][0].amount``."""
    text = f"[{path[0]}]"
    for step in path[1:]:
        if isinstance(step, int):
            text += f"[{step}]"
        elif not text[text.rindex("[") + 1 : -1].isdigit():
            text = f"{text[:-1]}.{step}]"
        else:
            text += f".{step}"
    return text


def error_target(message: str, paths: Iterable[FieldPath]) -> FieldPath | None:
    """Return the path (of ``paths``) that the check's ``message`` is about, or None.

    That is the path with the longest text the message starts with, followed by ``:`` or a
    space. When the message names missing keys, the first missing key's path is returned if it
    is among ``paths``.
    """
    texts = {path_text(p): p for p in paths}
    found = [t for t in texts if message.startswith(t) and message[len(t) : len(t) + 1] in ": "]
    if not found:
        return None
    target = texts[max(found, key=len)]
    rest = message[len(path_text(target)) :]
    if rest.startswith(": missing keys ["):
        child = (*target, ast.literal_eval(rest[len(": missing keys ") :])[0])
        if path_text(child) in texts:
            return child
    return target


def relative_path(chosen: Path, config: Path) -> str:
    """Return ``chosen`` relative to the config's folder (as the config writes inputs).

    A file on another drive keeps its absolute path. Separators are forward slashes.
    """
    try:
        return Path(os.path.relpath(chosen, Path(config).parent)).as_posix()
    except ValueError:  # another drive on Windows
        return Path(chosen).as_posix()


# ------------------------------------------------------------------------------ texts
def label_text(spec: Field, language: str) -> str:
    """Return a field's label: its key, with its unit in ``language`` when it has one."""
    if spec.unit:
        return f"{spec.key} ({tr_value('unit', spec.unit, language)})"
    return spec.key


def help_text(spec: Field, language: str) -> str:
    """Return a field's tooltip: its help in ``language``, whether it is required, its range."""
    lines = [spec.help.it if language == "it" else spec.help.en]
    lines.append(tr("form.required" if spec.required else "form.optional", language))
    bounds = []
    if spec.minimum is not None:
        bounds.append(f"{'>' if spec.open_minimum else '≥'} {spec.minimum:g}")
    if spec.maximum is not None:
        bounds.append(f"{'<' if spec.open_maximum else '≤'} {spec.maximum:g}")
    if bounds:
        lines.append(tr("form.range", language, range=", ".join(bounds)))
    if spec.also:
        lines.append(tr("form.also", language, texts=", ".join(spec.also)))
    return "\n".join(lines)


# ------------------------------------------------------------------------------ the model
class FormModel:
    """The values of one config, changed by path; build it with :meth:`from_text`."""

    def __init__(self, kind: ExperimentKind, config: dict[str, object]) -> None:
        """Hold ``config`` (a parsed config the form can show) for ``kind``."""
        self.kind = kind
        self.fields = config_fields(kind)
        self._config = config

    @classmethod
    def from_text(cls, text: str, kinds: Mapping[str, ExperimentKind]) -> FormModel:
        """Parse a config's TOML text for the form.

        Raises
        ------
        AppError
            When the text is not valid TOML, its kind is unknown or has no schema, or the form
            cannot show it exactly (the message names the key).
        """
        try:
            config = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise AppError("form.bad_toml", error=str(exc)) from exc
        experiment = config.get("experiment")
        name = experiment.get("kind") if isinstance(experiment, dict) else None
        if not isinstance(name, str) or name not in kinds:
            raise AppError("form.unknown_kind", kind=name)
        kind = kinds[name]
        problem = _unshown_config(config_fields(kind), config)
        if problem is not None:
            raise AppError("form.unreadable", problem=problem)
        return cls(kind, config)

    # ----------------------------------------------------------------------- reading
    def value(self, path: FieldPath) -> object | None:
        """Return the value at ``path``, or ``None`` when it is absent."""
        node: object = self._config
        for step in path:
            if isinstance(node, dict):
                node = node.get(step)
            elif isinstance(node, list) and isinstance(step, int) and step < len(node):
                node = node[step]
            else:
                return None
        return node

    def present(self, path: FieldPath) -> bool:
        """Whether ``path`` is in the config."""
        return self.value(path) is not None

    def to_config(self) -> dict[str, object]:
        """Return a copy of the config, its sections in the usual order."""
        ordered = {k: self._config[k] for k in _SECTIONS if k in self._config}
        ordered.update({k: v for k, v in self._config.items() if k not in ordered})
        return copy.deepcopy(ordered)

    def to_text(self) -> str:
        """Return the config as TOML (without comments)."""
        return tomli_w.dumps(self.to_config())

    def check(self) -> str | None:
        """Check the parameters against the kind's schema; return the message or None."""
        schema = self.kind.schema
        assert schema is not None  # config_fields refused a kind without one
        parameters = self._config.get("parameters", {})
        assert isinstance(parameters, dict)  # from_text refused anything else
        try:
            check_parameters(schema, parameters)
        except ValueError as exc:  # ValidationError
            return str(exc)
        return None

    # ----------------------------------------------------------------------- changing
    def set_text(self, path: FieldPath, spec: Field, text: str, *, entry: bool = False) -> None:
        """Set a scalar from its text.

        Blank text removes a table's key. A list item or a map ``entry`` keeps it as the empty
        text, so the item stays and the check names it.
        """
        if not text.strip() and not entry and isinstance(path[-1], str):
            self.remove(path)
            return
        self._set(path, parse_scalar(spec, text))

    def include(self, path: FieldPath, spec: Field, on: bool) -> None:
        """Switch an optional table, list, map, records, matrix or variant on (empty) or off."""
        if on:
            if not self.present(path):
                self._set(path, copy.deepcopy(_EMPTY[spec.kind]))
        else:
            self.remove(path)

    def choose(self, path: FieldPath, spec: Field, option: str) -> None:
        """Choose a variant's option; the fields the new option shares are kept.

        A field is shared when the old and the new option describe it the same way. The empty
        option leaves the variant empty.
        """
        assert spec.selector is not None  # a variant has one
        current = self.value(path)
        old = current if isinstance(current, dict) else {}
        if not option:
            self._set(path, {})
            return
        before = {f.key: f for f in spec.variants.get(str(old.get(spec.selector)), ())}
        after = {f.key: f for f in spec.variants[option]}
        kept = {k: v for k, v in old.items() if k in after and before.get(k) == after[k]}
        self._set(path, {spec.selector: option, **kept})

    def add_item(self, path: FieldPath, spec: Field) -> None:
        """Append an empty item (the empty text) to a list, or an empty record."""
        items = self.value(path)
        if not isinstance(items, list):
            items = []
            self._set(path, items)
        items.append({} if spec.kind is FieldKind.RECORDS else "")

    def add_entry(self, path: FieldPath, spec: Field, key: str) -> None:
        """Add the entry ``key`` to a map: the empty text, or an empty table, list or map.

        Raises
        ------
        AppError
            When the key is blank or already in the map.
        """
        name = key.strip()
        if not name:
            raise AppError("form.empty_key")
        entries = self.value(path)
        if not isinstance(entries, dict):
            entries = {}
            self._set(path, entries)
        if name in entries:
            raise AppError("form.duplicate_key", name=name)
        assert spec.item is not None  # a map has one
        entries[name] = copy.deepcopy(_EMPTY.get(spec.item.kind, ""))

    def remove(self, path: FieldPath) -> None:
        """Remove a key of a table or map, or an item of a list or records."""
        parent = self.value(path[:-1])
        last = path[-1]
        if isinstance(parent, dict):
            parent.pop(last, None)
        elif isinstance(parent, list) and isinstance(last, int) and last < len(parent):
            del parent[last]

    def resize(self, path: FieldPath, size: int) -> None:
        """Make a matrix ``size`` by ``size``, keeping the cells that fit; new cells are empty."""
        old = self.value(path)
        rows = old if isinstance(old, list) else []
        size = max(size, 0)
        self._set(
            path,
            [
                [rows[r][c] if r < len(rows) and c < len(rows[r]) else "" for c in range(size)]
                for r in range(size)
            ],
        )

    def set_cell(self, path: FieldPath, row: int, column: int, text: str) -> None:
        """Set a matrix cell from its text (blank stays the empty text)."""
        matrix = self.value(path)
        assert isinstance(matrix, list)  # the form shows only existing cells
        matrix[row][column] = parse_scalar(_CELL, text) if text.strip() else ""

    def _set(self, path: FieldPath, value: object) -> None:
        """Set ``path`` to ``value``, creating the tables on the way."""
        node: Any = self._config
        for step in path[:-1]:
            node = node.setdefault(step, {}) if isinstance(node, dict) else node[step]
        node[path[-1]] = value


# ------------------------------------------------------------------------------ showability
def _unshown_config(sections: tuple[Field, ...], config: Mapping[str, object]) -> str | None:
    """Return why the form cannot show ``config`` exactly, or None."""
    known = {f.key: f for f in sections}
    for name, value in config.items():
        path: FieldPath = (name,)
        if name == "inputs" and name not in known and value == {}:
            continue  # a kind without inputs keeps its empty [inputs]
        if name not in known:
            return f"{path_text(path)}: unknown section"
        if name == "experiment" and isinstance(value, dict):
            value = {k: v for k, v in value.items() if k != "kind"}
        problem = _unshown(known[name], value, path)
        if problem is not None:
            return problem
    return None


def _unshown(spec: Field, value: object, path: FieldPath) -> str | None:
    """Return why ``value`` of ``spec`` at ``path`` cannot be shown exactly, or None."""
    kind = spec.kind
    where = path_text(path)
    if kind in SCALARS:
        return None if _shows(spec, value) else f"{where}: {value!r} {_NOT_SHOWN}"
    if kind in (FieldKind.TABLE, FieldKind.VARIANT, FieldKind.MAP):
        if not isinstance(value, dict):
            return f"{where}: a table is required"
        if kind is FieldKind.MAP:
            assert spec.item is not None  # a map has one
            return _first(_unshown(spec.item, v, (*path, k)) for k, v in value.items())
        fields = spec.fields
        if kind is FieldKind.VARIANT:
            assert spec.selector is not None  # a variant has one
            option = value.get(spec.selector)
            if not value:
                return None
            if option not in spec.variants:
                return f"{where}: {spec.selector} = {option!r} is not an option"
            value = {k: v for k, v in value.items() if k != spec.selector}
            fields = spec.variants[str(option)]
        return _unshown_table(fields, value, path)
    if not isinstance(value, list):
        return f"{where}: a list is required"
    if kind is FieldKind.LIST:
        assert spec.item is not None  # a list has one
        item = spec.item
        if item.kind not in SCALARS:
            return f"{where}: a list of tables {_NOT_SHOWN}"
        return _first(_unshown(item, v, (*path, i)) for i, v in enumerate(value))
    if kind is FieldKind.RECORDS:
        return _first(
            _unshown_table(spec.fields, v, (*path, i))
            if isinstance(v, dict)
            else f"{path_text((*path, i))}: a table is required"
            for i, v in enumerate(value)
        )
    size = len(value)  # a matrix: square, every cell a number or text
    if any(not isinstance(row, list) or len(row) != size for row in value):
        return f"{where}: a square list of rows is required"
    cells = (cell for row in value for cell in row)
    return None if all(_shows(_CELL, c) for c in cells) else f"{where}: a cell {_NOT_SHOWN}"


def _unshown_table(
    fields: tuple[Field, ...], value: Mapping[str, object], path: FieldPath
) -> str | None:
    known = {f.key: f for f in fields}
    unknown = sorted(k for k in value if k not in known)
    if unknown:
        return f"{path_text(path)}: unknown keys {unknown}"
    return _first(_unshown(known[k], v, (*path, k)) for k, v in value.items())


def _first(problems: Iterable[str | None]) -> str | None:
    return next((p for p in problems if p is not None), None)
