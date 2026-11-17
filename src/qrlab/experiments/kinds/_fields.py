"""Short constructors for the kinds' schemas, and the fields several kinds share (12.1).

Each constructor takes the key, then the English and Italian help, then the field's own
options. ``required`` is keyword-only and defaults to ``True``.
"""

from __future__ import annotations

from collections.abc import Mapping

from qrlab.experiments.schema import Field, FieldKind, Help, InputSpec

__all__ = [
    "COVARIANCE",
    "PERIODS_PER_YEAR",
    "RETURNS_FORMAT",
    "RETURNS_PRICE_TYPE",
    "boolean",
    "choice",
    "currency",
    "day",
    "file",
    "group",
    "integer",
    "listing",
    "mapping",
    "matrix",
    "moment",
    "number",
    "records",
    "table",
    "text",
    "variant",
]

K = FieldKind


def text(key: str, en: str, it: str, *, required: bool = True) -> Field:
    """Describe non-empty text."""
    return Field(key, K.TEXT, Help(en, it), required=required)


def integer(
    key: str, en: str, it: str, *, minimum: float | None = None, maximum: float | None = None,
    unit: str | None = None, required: bool = True,
) -> Field:  # fmt: skip
    """Describe an integer, optionally bounded (bounds included)."""
    return Field(
        key, K.INTEGER, Help(en, it), required=required, unit=unit, minimum=minimum,
        maximum=maximum,
    )  # fmt: skip


def number(
    key: str, en: str, it: str, *, minimum: float | None = None, maximum: float | None = None,
    open_minimum: bool = False, open_maximum: bool = False, unit: str | None = None,
    required: bool = True, also: tuple[str, ...] = (), allow_inf: bool = False,
) -> Field:  # fmt: skip
    """Describe a number, optionally bounded.

    ``also`` lists texts accepted too; ``allow_inf`` lets the number be +inf.
    """
    return Field(
        key, K.NUMBER, Help(en, it), required=required, unit=unit, minimum=minimum,
        maximum=maximum, open_minimum=open_minimum, open_maximum=open_maximum, also=also,
        allow_inf=allow_inf,
    )  # fmt: skip


def boolean(key: str, en: str, it: str, *, required: bool = True) -> Field:
    """Describe true or false."""
    return Field(key, K.BOOLEAN, Help(en, it), required=required)


def day(key: str, en: str, it: str, *, required: bool = True) -> Field:
    """Describe a date (YYYY-MM-DD)."""
    return Field(key, K.DATE, Help(en, it), required=required)


def moment(key: str, en: str, it: str, *, required: bool = True) -> Field:
    """Describe a date-time with a time zone."""
    return Field(key, K.DATETIME, Help(en, it), required=required)


def choice(key: str, en: str, it: str, options: tuple[str, ...], *, required: bool = True) -> Field:
    """Describe one of ``options``."""
    return Field(key, K.CHOICE, Help(en, it), required=required, choices=options)


def currency(key: str, en: str, it: str, *, required: bool = True) -> Field:
    """Describe an ISO 4217 code."""
    return Field(key, K.CURRENCY, Help(en, it), required=required)


def listing(
    key: str, en: str, it: str, item: Field, *, allow_empty: bool = False, required: bool = True
) -> Field:
    """Describe a list of ``item`` values."""
    return Field(key, K.LIST, Help(en, it), required=required, item=item, allow_empty=allow_empty)


def matrix(key: str, en: str, it: str, *, required: bool = True) -> Field:
    """Describe a square list of lists of numbers."""
    return Field(key, K.MATRIX, Help(en, it), required=required)


def table(
    key: str, en: str, it: str, fields: tuple[Field, ...], *, allow_empty: bool = False,
    required: bool = True,
) -> Field:  # fmt: skip
    """Describe a table with fixed ``fields``."""
    return Field(
        key, K.TABLE, Help(en, it), required=required, fields=fields, allow_empty=allow_empty
    )


def mapping(
    key: str, en: str, it: str, key_kind: FieldKind, item: Field, *, allow_empty: bool = False,
    required: bool = True,
) -> Field:  # fmt: skip
    """Describe a table of free keys of ``key_kind``, each an ``item`` value."""
    return Field(
        key, K.MAP, Help(en, it), required=required, key_kind=key_kind, item=item,
        allow_empty=allow_empty,
    )  # fmt: skip


def records(
    key: str, en: str, it: str, fields: tuple[Field, ...], *, allow_empty: bool = False,
    required: bool = True,
) -> Field:  # fmt: skip
    """Describe a list of tables with fixed ``fields``."""
    return Field(
        key, K.RECORDS, Help(en, it), required=required, fields=fields, allow_empty=allow_empty
    )


def variant(
    key: str, en: str, it: str, selector: str, options: Mapping[str, tuple[Field, ...]], *,
    required: bool = True,
) -> Field:  # fmt: skip
    """Describe a table whose ``selector`` key picks the fields of the rest."""
    return Field(
        key, K.VARIANT, Help(en, it), required=required, selector=selector, variants=options
    )


def file(name: str, en: str, it: str, *, required: bool = True) -> InputSpec:
    """Describe one input file."""
    return InputSpec(name, Help(en, it), required=required)


def group(name: str, en: str, it: str) -> InputSpec:
    """Describe a table of input files, one per free key (always optional)."""
    return InputSpec(name, Help(en, it), required=False, group=True)


# --------------------------------------------------------------------------- shared fields
RETURNS_FORMAT = table(
    "returns_format",
    "How the returns CSV is written: its date column and format, delimiter and decimal separator.",
    "Come è scritto il CSV dei rendimenti: colonna e formato delle date, separatore di campo e "
    "separatore decimale.",
    (
        text("date_column", "Name of the date column.", "Nome della colonna delle date."),
        text(
            "date_format",
            "Date format, e.g. %Y-%m-%d.",
            "Formato delle date, ad esempio %Y-%m-%d.",
        ),
        text(
            "delimiter",
            "Field delimiter, e.g. a comma.",
            "Separatore di campo, ad esempio la virgola.",
        ),
        text(
            "decimal_separator",
            "Decimal separator, a point or a comma.",
            "Separatore decimale, punto o virgola.",
        ),
    ),
)
RETURNS_PRICE_TYPE = choice(
    "returns_price_type",
    "Whether the returns include dividends: total_return, or price (dividends excluded).",
    "Se i rendimenti includono i dividendi: total_return, oppure price (dividendi esclusi).",
    ("total_return", "price"),
)
PERIODS_PER_YEAR = integer(
    "periods_per_year",
    "Return periods in a year, matching the dates (12 for monthly returns).",
    "Periodi di rendimento in un anno, coerenti con le date (12 per rendimenti mensili).",
    minimum=1,
    unit="periods",
)
COVARIANCE = variant(
    "covariance",
    "How the covariance of returns is estimated.",
    "Come si stima la covarianza dei rendimenti.",
    "estimator",
    {
        "sample": (),
        "ledoit_wolf": (),
        "ewma": (
            number(
                "decay",
                "Weight of each older return, between 0 and 1 (e.g. 0.94).",
                "Peso di ogni rendimento più vecchio, tra 0 e 1 (ad esempio 0,94).",
                minimum=0.0,
                maximum=1.0,
                open_minimum=True,
                open_maximum=True,
            ),
            boolean(
                "demean",
                "Whether returns are demeaned first.",
                "Se ai rendimenti si toglie prima la media.",
            ),
        ),
    },
)
