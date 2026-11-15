"""Qt-free state of the Portfolio screen (phase 8.8b): tables of text, checked by the library.

A portfolio is a folder ``portfolios/<name>/`` of the workspace. Reading, checking and writing
it are :mod:`qrlab.experiments.portfolios`; this module keeps the rows being edited and turns
the library's problems into messages. Nothing here computes a number.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from qrlab.experiments.portfolios import (
    INSTRUMENT_FIELDS,
    INSTRUMENTS_FILE,
    NATIVE_COLUMNS,
    TRANSACTIONS_FILE,
    PortfolioProblem,
    check_portfolio,
    kind_columns,
    read_portfolio,
    write_portfolio,
)
from qrlab.experiments.registry import ExperimentKind
from qrlab.experiments.workspace import config_template
from qrlab_app.viewmodels import AppError, WorkspaceViewModel, check_file_name

__all__ = ["INSTRUMENTS_FILE", "TRANSACTIONS_FILE", "PortfolioViewModel", "Problem"]

_UNKNOWN_DEFAULTS = {
    "domicile": "unknown",
    "replication": "unknown",
    "distribution": "unknown",
    "ter": "unknown",
    "benchmark": "unknown",
    "hedged_to": "none",
    "inception": "unknown",
    "fund_size": "unknown",
}
_REASON_KEYS = {
    "invalid": ("portfolio.library", "error"),
    "duplicate_isin": ("portfolio.duplicate_isin", "isin"),
    "unknown_isin": ("portfolio.unknown_isin", "isin"),
    "no_transactions": ("portfolio.no_transactions", ""),
}

Row = dict[str, str]


@dataclass(frozen=True)
class Problem:
    """Why a portfolio cannot be saved: the table, the row (0-based) and the message key."""

    table: str  # "transactions" or "instruments"
    row: int | None
    key: str
    values: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def of(cls, problem: PortfolioProblem) -> Problem:
        """Turn the library's problem into a message key and its values."""
        key, value = _REASON_KEYS[problem.reason]
        return cls(problem.table, problem.row, key, {value: problem.detail} if value else {})


class PortfolioViewModel:
    """The portfolios of the workspace and the tables of the selected one."""

    def __init__(
        self,
        workspace: WorkspaceViewModel,
        *,
        kinds: Mapping[str, ExperimentKind],
        now: Callable[[], datetime],
    ) -> None:
        """Bind to the workspace; ``kinds`` gives the report template, ``now`` the clock."""
        self.workspace = workspace
        self.report_kind = kinds["portfolio_report"]
        self.now = now
        self.names: list[str] = []
        self.selected: str | None = None
        self.transactions: list[Row] = []
        self.instruments: list[Row] = []
        self._saved: tuple[list[Row], list[Row]] = ([], [])

    # ----------------------------------------------------------------------- portfolios
    def folder(self) -> Path:
        """Return the workspace's ``portfolios/`` folder (created when missing)."""
        folder = self.workspace.require() / "portfolios"
        folder.mkdir(exist_ok=True)
        return folder

    def refresh(self) -> list[str]:
        """List the portfolio folders, sorted by name."""
        self.names = sorted(p.name for p in self.folder().iterdir() if p.is_dir())
        return self.names

    def create(self, name: str) -> str:
        """Create an empty portfolio folder and select it; an existing name is refused."""
        clean = check_file_name(name)
        path = self.folder() / clean
        if path.exists():
            raise AppError("error.exists", name=clean)
        path.mkdir()
        self.refresh()
        self.select(clean)
        return clean

    def select(self, name: str) -> None:
        """Load a portfolio's files as rows of text (an unreadable file raises AppError)."""
        try:
            transactions, instruments = read_portfolio(self.folder() / name)
        except Exception as exc:  # read_portfolio raises QrlabError, OSError or ValueError
            raise AppError("portfolio.bad_file", name=name, error=str(exc)) from exc
        self.selected = name
        self.transactions, self.instruments = transactions, instruments
        self._saved = ([dict(r) for r in transactions], [dict(r) for r in instruments])

    def clear(self) -> None:
        """Forget the selection (another workspace was opened)."""
        self.names = []
        self.selected = None
        self.transactions, self.instruments = [], []
        self._saved = ([], [])

    @property
    def dirty(self) -> bool:
        """Whether the tables differ from the files last loaded or saved."""
        return self.selected is not None and (self.transactions, self.instruments) != self._saved

    def revert(self) -> None:
        """Drop unsaved edits."""
        self.transactions = [dict(r) for r in self._saved[0]]
        self.instruments = [dict(r) for r in self._saved[1]]

    # -------------------------------------------------------------------------- editing
    def add_transaction(self, kind: str) -> int:
        """Append a transaction of ``kind`` with a new id; return its row."""
        self._require()
        currency = self.instruments[0]["currency"] if self.instruments else ""
        row = dict.fromkeys(NATIVE_COLUMNS, "")
        row |= {"id": self._next_id(), "kind": kind, "account": "main"}
        row |= {"fees": "0", "fees_currency": currency, "taxes": "0", "taxes_currency": currency}
        self.transactions.append(row)
        return len(self.transactions) - 1

    def editable(self, row: int, column: str) -> bool:
        """Whether a cell can be edited: only the columns its kind uses."""
        return column in kind_columns(self.transactions[row]["kind"])

    def set_transaction(self, row: int, column: str, text: str) -> None:
        """Set a cell; a new kind empties the cells it does not use.

        A cost typed without its currency takes the price currency, the only one the library
        accepts for it.
        """
        cells = self.transactions[row]
        cells[column] = text.strip()
        if column == "cost" and cells["cost"] and not cells["cost_currency"]:
            cells["cost_currency"] = cells["price_currency"]
        if column == "kind":
            for name in NATIVE_COLUMNS:
                if not self.editable(row, name):
                    cells[name] = ""

    def remove_transaction(self, row: int) -> None:
        """Delete a transaction row."""
        del self.transactions[row]

    def add_instrument(self) -> int:
        """Append an instrument row ("unknown" where the file allows it); return its row."""
        self._require()
        self.instruments.append(dict.fromkeys(INSTRUMENT_FIELDS, "") | _UNKNOWN_DEFAULTS)
        return len(self.instruments) - 1

    def set_instrument(self, row: int, name: str, text: str) -> None:
        """Set an instrument field."""
        self.instruments[row][name] = text.strip()

    def remove_instrument(self, row: int) -> None:
        """Delete an instrument row."""
        del self.instruments[row]

    def add_starting_position(self, day: str) -> None:
        """Add a deposit and one transfer in per instrument on ``day``, to be filled in.

        Units, the market price on that day, the original cost per unit and the cash are left
        empty: they are the user's to state.
        """
        self._require()
        start = day.strip()
        try:
            date.fromisoformat(start)
        except ValueError:
            raise AppError("portfolio.bad_date", text=day) from None
        if not self.instruments:
            raise AppError("portfolio.no_instruments")
        row = self.add_transaction("deposit")
        self.transactions[row] |= {
            "trade_date": start,
            "amount_currency": self.instruments[0]["currency"],
        }
        for instrument in self.instruments:
            row = self.add_transaction("transfer_in")
            currency = instrument["currency"]
            self.transactions[row] |= {
                "trade_date": start,
                "isin": instrument["isin"],
                "price_currency": currency,
                "cost_currency": currency,
            }

    # ---------------------------------------------------------------------- validation
    def check(self) -> Problem | None:
        """Check both tables with the library; ``None`` when the portfolio can be saved."""
        problem = check_portfolio(self.transactions, self.instruments, now=self.now)
        return None if problem is None else Problem.of(problem)

    def save(self) -> Problem | None:
        """Check, then write both files through the library and reload them (rows sorted).

        Nothing is written when there is a problem; the edits stay in the tables.
        """
        name = self._require()
        problem = self.check()
        if problem is not None:
            return problem
        write_portfolio(self.folder() / name, self.transactions, self.instruments, now=self.now)
        self.select(name)
        return None

    def create_report(self, file_name: str) -> Path:
        """Write ``configs/<file_name>.toml``, a report config with this portfolio's files.

        The portfolio must be saved and valid. The price file, its mapping, the checks and the
        parameters stay to be filled in, as in any new config.
        """
        name = self._require()
        if self.dirty or self.check() is not None:
            raise AppError("portfolio.save_first")
        path = self.workspace.require() / "configs" / f"{check_file_name(file_name)}.toml"
        if path.exists():
            raise AppError("error.exists", name=path.name)
        text = config_template(
            self.report_kind,
            inputs={
                "transactions": f"../portfolios/{name}/{TRANSACTIONS_FILE}",
                "instruments": f"../portfolios/{name}/{INSTRUMENTS_FILE}",
            },
            parameters={"transactions_format": '"native"'},
        )
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    # ------------------------------------------------------------------------- helpers
    def _require(self) -> str:
        if self.selected is None:
            raise AppError("portfolio.no_selection")
        return self.selected

    def _next_id(self) -> str:
        used = {r["id"] for r in self.transactions}
        number = len(self.transactions) + 1
        while f"t{number}" in used:
            number += 1
        return f"t{number}"
