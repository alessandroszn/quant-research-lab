"""What each experiment kind accepts, described as data (design note 12.1).

A :class:`KindSchema` lists a kind's input files (:class:`InputSpec`) and its ``[parameters]``
(:class:`Field`). The description serves three readers:

- :func:`check_parameters`, the structural check of a config: unknown and missing keys at every
  level, types, choices and ranges, the selector of a variant, free keys of the right kind. Each
  error names the full path of the key. The kind's own ``parse`` keeps the rules that tie keys
  together (pairs given together, weights summing to 1, names that must exist in a file);
- the generated guide ``docs/guides/kinds.md``;
- the app's form (phase 12.1b).

A schema states no defaults: an optional key that is absent switches its feature off, and its
help says so. Help texts are in English and Italian, the app's languages.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency
from qrlab.instruments.identifiers import Isin

__all__ = [
    "Field",
    "FieldKind",
    "Help",
    "InputSpec",
    "KindSchema",
    "check_parameters",
]


class FieldKind(Enum):
    """What a key holds."""

    TEXT = "text"
    INTEGER = "integer"
    NUMBER = "number"  # an int or a float, finite
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"  # with a time zone
    CHOICE = "choice"  # one of ``choices``
    CURRENCY = "currency"  # an ISO 4217 code
    ISIN = "isin"
    LIST = "list"  # a list of ``item`` values
    MATRIX = "matrix"  # a square list of lists of numbers
    TABLE = "table"  # the fixed ``fields``
    MAP = "map"  # free keys of ``key_kind``, each an ``item`` value
    RECORDS = "records"  # a list of tables with the fixed ``fields``
    VARIANT = "variant"  # a table whose ``selector`` key picks the rest of its fields


@dataclass(frozen=True)
class Help:
    """A short explanation, in English and Italian."""

    en: str
    it: str

    def __post_init__(self) -> None:
        """Both texts are required."""
        if not self.en.strip() or not self.it.strip():
            raise ValidationError("a help text needs both English and Italian")


@dataclass(frozen=True)
class Field:
    """One key of ``[parameters]`` (or the shape of a value, for ``item``).

    ``minimum`` and ``maximum`` bound numbers (``open_minimum`` / ``open_maximum`` exclude the
    bound itself). ``allow_empty`` lets a table, map, list or records be empty. A ``MAP``'s
    keys are ``key_kind`` (``TEXT``, ``ISIN``, ``CURRENCY`` or ``INTEGER`` for years written as
    text). A ``VARIANT``'s ``selector`` key chooses one of ``variants``, the fields of each
    option. ``also`` lists literal texts accepted besides the field's own kind (e.g. a cost
    that is a number or ``"ter"``).
    """

    key: str
    kind: FieldKind
    help: Help
    required: bool = True
    unit: str | None = None
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    open_minimum: bool = False
    open_maximum: bool = False
    item: Field | None = None
    fields: tuple[Field, ...] = ()
    key_kind: FieldKind | None = None
    selector: str | None = None
    variants: Mapping[str, tuple[Field, ...]] = field(default_factory=dict)
    allow_empty: bool = False
    also: tuple[str, ...] = ()
    allow_inf: bool = False  # a NUMBER may be +inf (e.g. "no cap"); NaN and -inf never

    def __post_init__(self) -> None:
        """Check that the description is complete for its kind."""
        kind = self.kind
        if kind is FieldKind.CHOICE and not self.choices:
            raise ValidationError(f"{self.key}: a choice needs choices")
        if kind in (FieldKind.LIST, FieldKind.MAP) and self.item is None:
            raise ValidationError(f"{self.key}: a {kind.value} needs an item")
        if kind in (FieldKind.TABLE, FieldKind.RECORDS) and not self.fields:
            raise ValidationError(f"{self.key}: a {kind.value} needs fields")
        if kind is FieldKind.MAP and self.key_kind not in _KEY_KINDS:
            raise ValidationError(f"{self.key}: a map needs key_kind, one of {_KEY_NAMES}")
        if kind is FieldKind.VARIANT and (not self.selector or not self.variants):
            raise ValidationError(f"{self.key}: a variant needs a selector and variants")
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValidationError(f"{self.key}: duplicate fields")


@dataclass(frozen=True)
class InputSpec:
    """One input file, or one group of files (one per free key, e.g. a fund's ISIN)."""

    name: str
    help: Help
    required: bool = True
    group: bool = False


@dataclass(frozen=True)
class KindSchema:
    """A kind's inputs and the fields of its ``[parameters]``."""

    inputs: tuple[InputSpec, ...]
    parameters: tuple[Field, ...]

    def __post_init__(self) -> None:
        """Names are unique."""
        names = [i.name for i in self.inputs]
        keys = [f.key for f in self.parameters]
        if len(names) != len(set(names)) or len(keys) != len(set(keys)):
            raise ValidationError("a kind schema has duplicate inputs or parameters")


_KEY_KINDS = (FieldKind.TEXT, FieldKind.ISIN, FieldKind.CURRENCY, FieldKind.INTEGER)
_KEY_NAMES = sorted(k.value for k in _KEY_KINDS)


def check_parameters(schema: KindSchema, parameters: Mapping[str, object]) -> None:
    """Check ``parameters`` against ``schema``; raise naming the first wrong key's full path.

    Raises
    ------
    ValidationError
        For an unknown or missing key, a value of the wrong type, outside its choices or
        range, an unknown variant, or a free key of the wrong kind.
    """
    _check_table(schema.parameters, parameters, "[parameters]", allow_empty=True)


# --------------------------------------------------------------------------- the checks
def _check_table(fields: Sequence[Field], value: object, path: str, *, allow_empty: bool) -> None:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{path} must be a table")
    if not value and not allow_empty:
        raise ValidationError(f"{path} must not be empty")
    known = {f.key: f for f in fields}
    unknown = sorted(str(k) for k in value if k not in known)
    if unknown:
        raise ValidationError(f"{path}: unknown keys {unknown}")
    missing = sorted(f.key for f in fields if f.required and f.key not in value)
    if missing:
        raise ValidationError(f"{path}: missing keys {missing}")
    for key, spec in known.items():
        if key in value:
            _check_value(spec, value[key], _join(path, key))


def _join(path: str, key: str) -> str:
    """Return the path of ``key`` inside ``path``.

    ``[parameters.risk]`` + ``window`` gives ``[parameters.risk.window]``; after a record's
    index, ``[parameters.flows][0]`` + ``amount`` gives ``[parameters.flows][0].amount``.
    """
    if path.endswith("]") and not path[path.rindex("[") + 1 : -1].isdigit():
        return f"{path[:-1]}.{key}]"
    return f"{path}.{key}"


def _check_value(spec: Field, value: object, path: str) -> None:
    kind = spec.kind
    if spec.also and isinstance(value, str) and value in spec.also:
        return
    if kind is FieldKind.TEXT:
        if not isinstance(value, str) or not value:
            raise ValidationError(f"{path}: non-empty text is required")
    elif kind is FieldKind.INTEGER:
        if type(value) is not int:
            raise ValidationError(f"{path}: an integer is required")
        _check_range(spec, float(value), path)
    elif kind is FieldKind.NUMBER:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValidationError(f"{path}: a number is required")
        if not math.isfinite(float(value)) and not (spec.allow_inf and value == math.inf):
            raise ValidationError(f"{path}: a finite number is required")
        _check_range(spec, float(value), path)
    elif kind is FieldKind.BOOLEAN:
        if not isinstance(value, bool):
            raise ValidationError(f"{path}: true or false is required")
    elif kind is FieldKind.DATE:
        if isinstance(value, datetime) or not isinstance(value, date):
            raise ValidationError(f"{path}: a date (YYYY-MM-DD) is required")
    elif kind is FieldKind.DATETIME:
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValidationError(f"{path}: a date-time with a time zone is required")
    elif kind is FieldKind.CHOICE:
        if value not in spec.choices:
            raise ValidationError(f"{path}: one of {list(spec.choices)} is required")
    elif kind is FieldKind.CURRENCY:
        _check_key_kind(FieldKind.CURRENCY, value, path)
    elif kind is FieldKind.ISIN:
        _check_key_kind(FieldKind.ISIN, value, path)
    elif kind is FieldKind.LIST:
        _check_list(spec, value, path)
    elif kind is FieldKind.MATRIX:
        _check_matrix(value, path)
    elif kind is FieldKind.TABLE:
        _check_table(spec.fields, value, path, allow_empty=spec.allow_empty)
    elif kind is FieldKind.MAP:
        _check_map(spec, value, path)
    elif kind is FieldKind.RECORDS:
        _check_records(spec, value, path)
    else:
        _check_variant(spec, value, path)


def _check_range(spec: Field, value: float, path: str) -> None:
    low, high = spec.minimum, spec.maximum
    below = low is not None and (value <= low if spec.open_minimum else value < low)
    above = high is not None and (value >= high if spec.open_maximum else value > high)
    if below or above:
        raise ValidationError(f"{path}: {_range_text(spec)} is required, got {value:g}")


def _range_text(spec: Field) -> str:
    parts = []
    if spec.minimum is not None:
        parts.append(f"{'>' if spec.open_minimum else '>='} {spec.minimum:g}")
    if spec.maximum is not None:
        parts.append(f"{'<' if spec.open_maximum else '<='} {spec.maximum:g}")
    return "a value " + " and ".join(parts)


def _check_key_kind(kind: FieldKind, value: object, path: str) -> None:
    if not isinstance(value, str):
        raise ValidationError(f"{path}: {kind.value} text is required")
    try:
        if kind is FieldKind.CURRENCY:
            Currency(value)
        elif kind is FieldKind.ISIN:
            Isin(value)
        elif kind is FieldKind.INTEGER:
            int(value)
        elif not value.strip():
            raise ValidationError("empty")
    except (ValidationError, ValueError) as error:
        raise ValidationError(f"{path}: {value!r} is not a valid {kind.value}") from error


def _check_list(spec: Field, value: object, path: str) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{path}: a list is required")
    if not value and not spec.allow_empty:
        raise ValidationError(f"{path}: the list must not be empty")
    assert spec.item is not None  # checked when the field was built
    for index, item in enumerate(value):
        _check_value(spec.item, item, f"{path}[{index}]")


def _check_matrix(value: object, path: str) -> None:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{path}: a non-empty list of rows is required")
    size = len(value)
    for index, row in enumerate(value):
        if not isinstance(row, list) or len(row) != size:
            raise ValidationError(f"{path}: row {index} must be a list of {size} numbers")
        for cell in row:
            if isinstance(cell, bool) or not isinstance(cell, int | float):
                raise ValidationError(f"{path}: row {index} must hold numbers")


def _check_map(spec: Field, value: object, path: str) -> None:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{path} must be a table")
    if not value and not spec.allow_empty:
        raise ValidationError(f"{path} must not be empty")
    assert spec.key_kind is not None  # checked when the field was built
    assert spec.item is not None
    for key, item in value.items():
        _check_key_kind(spec.key_kind, key, f"{path} key")
        _check_value(spec.item, item, _join(path, str(key)))


def _check_records(spec: Field, value: object, path: str) -> None:
    if not isinstance(value, list):
        raise ValidationError(f"{path}: a list of tables is required")
    if not value and not spec.allow_empty:
        raise ValidationError(f"{path}: the list must not be empty")
    for index, record in enumerate(value):
        _check_table(spec.fields, record, f"{path}[{index}]", allow_empty=False)


def _check_variant(spec: Field, value: object, path: str) -> None:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{path} must be a table")
    selector = spec.selector
    assert selector is not None  # checked when the field was built
    option = value.get(selector)
    if option not in spec.variants:
        raise ValidationError(f"{path}: {selector} must be one of {sorted(spec.variants)}")
    rest = {k: v for k, v in value.items() if k != selector}
    _check_table(spec.variants[str(option)], rest, path, allow_empty=True)
