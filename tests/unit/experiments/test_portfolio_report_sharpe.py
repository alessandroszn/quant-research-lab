"""€STR and the Sharpe ratio in the ``portfolio_report`` kind (design 8.5), with hand values.

The portfolio is 100 units of one fund bought on 30/01/2026 with all the cash, so the monthly
TWR returns are the fund's price returns: (1, 2, 0, 3) %.

- **€STR at 0.** The excess returns are the TWR returns: a mean of 1.5 % and a standard
  deviation of 1.29099 %, a monthly Sharpe ratio of 1.161895, annualised x sqrt(12) = 4.02492.
- **€STR at 3.6 %.** The first period, Friday 30 January to Friday 27 February 2026, has four
  Fridays whose fixing covers 3 days (30/1, 6/2, 13/2, 20/2) and 16 one-day fixings:
  (1 + 0.036 x 3/360)^4 x (1 + 0.036/360)^16 - 1.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import target2_calendar
from qrlab.core.errors import ValidationError
from qrlab.experiments import run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.metrics.performance import SharpeSE, sharpe_ratio

ROOT = Path(__file__).parents[3]
DAYS = ("30/01/2026", "27/02/2026", "31/03/2026", "30/04/2026", "29/05/2026")
TWR = (0.01, 0.02, 0.0, 0.03)
HEADER = "KEY,FREQ,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MEASURE,UNIT,UNIT_MULT,UNIT_INDEX_BASE\n"


def _estr(path: Path, percent: float, *, skip: str | None = None) -> Path:
    days = target2_calendar(range(2025, 2028)).business_days(date(2026, 1, 2), date(2026, 6, 30))
    rows = "".join(
        f"EST.B.EU000A2X2A25.WT,B,{d.date()},{percent},A,PC,,0,\n"
        for d in days
        if str(d.date()) != skip
    )
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def _setup(tmp: Path, *, estr: Path | None, frequency: str = "monthly") -> Path:
    tmp.mkdir(parents=True, exist_ok=True)
    prices = [100.0]
    for r in TWR:
        prices.append(prices[-1] * (1 + r))
    (tmp / "export.csv").write_text(
        "Riferimento;Data;Operazione;ISIN;Quantita;Prezzo;Divisa;Importo;Commissioni;Imposte;"
        "Controvalore;Divisa controvalore;Descrizione\n"
        "t2;30/01/2026;Acquisto;IE0000000012;100;100,00;EUR;;;;;;\n"
        "t1;30/01/2026;Bonifico in entrata;;;;EUR;10.000,00;;;;;\n",
        encoding="utf-8",
    )
    (tmp / "prices.csv").write_text(
        "Data;IE0000000012\n"
        + "".join(
            f"{d};{p:.10f}".replace(".", ",") + "\n" for d, p in zip(DAYS, prices, strict=True)
        ),
        encoding="utf-8",
    )
    data = ROOT / "examples" / "data"
    extra = "" if estr is None else f'estr = "{estr.as_posix()}"\n'
    config = tmp / "report.toml"
    config.write_text(
        '[experiment]\nname = "sharpe-report"\nkind = "portfolio_report"\n'
        'hypothesis = "descriptive"\n\n[inputs]\n'
        f'transactions = "{(tmp / "export.csv").as_posix()}"\n'
        f'transactions_mapping = "{(ROOT / "configs/csv_mappings/example_broker.toml").as_posix()}"\n'  # noqa: E501
        f'prices = "{(tmp / "prices.csv").as_posix()}"\n'
        f'prices_mapping = "{(data / "prices_mapping.toml").as_posix()}"\n'
        f'instruments = "{(data / "instruments.toml").as_posix()}"\n'
        f'checks = "{(ROOT / "configs/checks/example.toml").as_posix()}"\n'
        + extra
        + '\n[parameters]\ntitle = "Sharpe test"\nbase_currency = "EUR"\nlanguage = "en"\n'
        f'flow_timing = "start"\nmax_price_age_days = 0\nreturn_frequency = "{frequency}"\n'
        "generated_at = 2026-06-01T09:00:00Z\ntarget_weights = {}\n"
        f'\n[output]\ndirectory = "{(tmp / "out").as_posix()}"\n',
        encoding="utf-8",
    )
    return config


def _run(config: Path) -> tuple[dict[str, object], Path]:
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    return dict(result.record), result.output_dir


def _scalar(record: dict[str, object], name: str) -> float:
    return float(record["scalars"][name]["value"])  # type: ignore[index]


def test_sharpe_with_estr_at_zero_by_hand(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, estr=_estr(tmp_path / "estr.csv", 0.0)))
    assert record["status"] == "success", record["error"]
    assert _scalar(record, "risk_free_total") == 0.0
    assert _scalar(record, "sharpe_ratio") == pytest.approx(4.0249223595, abs=1e-8)
    table = pd.read_csv(out / "risk_free.csv", index_col=0)
    assert table["twr"].tolist() == pytest.approx(list(TWR), abs=1e-10)
    excess = pd.Series(table["excess"].to_numpy(), index=pd.DatetimeIndex(table.index))
    expected = sharpe_ratio(excess, periods_per_year=12, se_method=SharpeSE.IID_NON_NORMAL)
    assert _scalar(record, "sharpe_ratio_se") == pytest.approx(expected.standard_error)
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "Sharpe ratio (TWR in excess of the risk-free rate, annualised)" in html
    assert "4.02 ± " in html
    assert "(n = 4)" in html
    assert record["outputs"]["risk_free.csv"]["tag"] == "descriptive"  # type: ignore[index]


def test_risk_free_accrual_of_the_first_period_by_hand(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, estr=_estr(tmp_path / "estr.csv", 3.6)))
    assert record["status"] == "success", record["error"]
    table = pd.read_csv(out / "risk_free.csv", index_col=0)
    first = (1 + 0.036 * 3 / 360) ** 4 * (1 + 0.036 / 360) ** 16 - 1
    assert table["risk_free"].iloc[0] == pytest.approx(first, abs=1e-15)
    assert table["excess"].iloc[0] == pytest.approx(0.01 - first, abs=1e-12)
    total = float(np.prod(1 + table["risk_free"].to_numpy()) - 1)
    assert _scalar(record, "risk_free_total") == pytest.approx(total)
    # About 3.6 % x 119 days / 360 over the four months.
    assert total == pytest.approx(math.expm1(0.036 * 119 / 360), abs=2e-5)


def test_a_missing_fixing_fails_the_run(tmp_path: Path) -> None:
    estr = _estr(tmp_path / "estr.csv", 2.0, skip="2026-03-10")
    record, _ = _run(_setup(tmp_path, estr=estr))
    assert record["status"] == "failure"
    assert "2026-03-10" in str(record["error"])


def test_estr_needs_monthly_returns(tmp_path: Path) -> None:
    config = _setup(tmp_path, estr=_estr(tmp_path / "estr.csv", 2.0), frequency="none")
    with pytest.raises(ValidationError, match="monthly"):
        validate_experiment(config, kinds=KINDS)


def test_too_few_returns_shows_why(tmp_path: Path) -> None:
    """Three monthly returns are too few for the Mertens standard error (it needs 4)."""
    config = _setup(tmp_path, estr=_estr(tmp_path / "estr.csv", 0.0))
    prices = (tmp_path / "prices.csv").read_text(encoding="utf-8").splitlines()
    (tmp_path / "prices.csv").write_text("\n".join(prices[:-1]) + "\n", encoding="utf-8")
    record, out = _run(config)
    assert record["status"] == "success", record["error"]
    assert "sharpe_ratio" not in record["scalars"]  # type: ignore[operator]
    html = (out / "report.html").read_text(encoding="utf-8")
    assert "The Sharpe ratio is not shown:" in html


def test_without_estr_nothing_changes(tmp_path: Path) -> None:
    record, out = _run(_setup(tmp_path, estr=None))
    assert record["status"] == "success", record["error"]
    assert not (out / "risk_free.csv").exists()
    assert "Sharpe ratio" not in (out / "report.html").read_text(encoding="utf-8")
