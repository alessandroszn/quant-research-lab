"""Ken French Data Library parser.

Fixtures are synthetic files that reproduce the *format* of the library (header text, monthly
and annual sections, CRLF or LF line endings, missing-value codes). They contain no real data.

Hand calculations (from the approved design note):

- ``202601,    1.23,   -0.45,    0.10,    0.33`` -> 2026-01-31: 0.0123, -0.0045, 0.0010, 0.0033
- ``-99.99`` and ``-999`` -> NaN
- annual ``2026,   10.00, ...`` -> 2026-12-31: 0.10
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.money import Currency
from qrlab.core.returns import ReturnKind
from qrlab.data.errors import ParseError
from qrlab.data.ken_french import (
    KEN_FRENCH_DATASETS,
    download_ken_french,
    ken_french_url,
    parse_ken_french,
)
from qrlab.data.provenance import Provenance, Unit
from qrlab.data.store import RawStore

MONTHLY_FF3 = """This file was created using the 202609 CRSP database.
The 1-month TBill rate data until 202405 are from Ibbotson Associates.

,Mkt-RF,SMB,HML,RF
202601,    1.23,   -0.45,    0.10,    0.33
202602,  -99.99,    0.20,   -0.30,    0.30
202603,    0.50,     -999,    0.00,    0.31

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RF
2025,   10.00,   -1.00,    2.50,    4.00
2026,    5.00,    1.00,   -2.50,    3.50

Copyright 2026 Eugene F. Fama and Kenneth R. French
"""

DAILY_FF3 = """This file was created by using the 202609 CRSP database.

,Mkt-RF,SMB,HML,RF
20260102,    0.09,   -0.23,   -0.28,    0.01
20260105,    0.45,   -0.34,   -0.03,    0.01

Copyright 2026 Eugene F. Fama and Kenneth R. French
"""

MOMENTUM = """This file was created using the 202609 CRSP database.  It
contains a momentum factor.
Missing data are indicated by -99.99 or -999.

,Mom
202601,    2.00
202602,   -1.50

Annual Factors:
January-December
,Mom
2026,    3.00

Copyright 2026 Eugene F. Fama and Kenneth R. French
"""


def _zip(text: str, *, crlf: bool = True, name: str = "file.csv") -> bytes:
    body = text.replace("\n", "\r\n") if crlf else text
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, body.encode("latin-1"))
    return buffer.getvalue()


def _prov(content: bytes, dataset: str = "F-F_Research_Data_Factors") -> Provenance:
    return Provenance(
        source="ken_french",
        dataset=dataset,
        url=ken_french_url(dataset),
        retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="test",
    )


def _parse(
    text: str,
    *,
    frequency: Frequency,
    dataset: str = "F-F_Research_Data_Factors",
    crlf: bool = True,
) -> pd.DataFrame:
    content = _zip(text, crlf=crlf)
    return parse_ken_french(content, _prov(content, dataset), frequency=frequency).data


# --------------------------------------------------------------------------- hand examples
def test_monthly_hand_example() -> None:
    data = _parse(MONTHLY_FF3, frequency=Frequency.MONTHLY)
    assert list(data.columns) == ["Mkt-RF", "SMB", "HML", "RF"]
    assert list(data.index) == list(pd.DatetimeIndex(["2026-01-31", "2026-02-28", "2026-03-31"]))
    np.testing.assert_allclose(data.iloc[0].to_numpy(), [0.0123, -0.0045, 0.0010, 0.0033])


def test_missing_value_codes_become_nan() -> None:
    data = _parse(MONTHLY_FF3, frequency=Frequency.MONTHLY)
    assert np.isnan(data.loc["2026-02-28", "Mkt-RF"])
    assert np.isnan(data.loc["2026-03-31", "SMB"])
    assert data.loc["2026-02-28", "SMB"] == pytest.approx(0.0020)


def test_annual_section_is_a_separate_dataset() -> None:
    data = _parse(MONTHLY_FF3, frequency=Frequency.ANNUAL)
    assert list(data.index) == list(pd.DatetimeIndex(["2025-12-31", "2026-12-31"]))
    assert data.loc["2025-12-31", "Mkt-RF"] == pytest.approx(0.10)


def test_daily_dates() -> None:
    data = _parse(DAILY_FF3, frequency=Frequency.DAILY, dataset="F-F_Research_Data_Factors_daily")
    assert list(data.index) == list(pd.DatetimeIndex(["2026-01-02", "2026-01-05"]))
    assert data.iloc[1, 0] == pytest.approx(0.0045)


@pytest.mark.parametrize("crlf", [True, False])
def test_momentum_with_two_line_title_and_either_line_ending(crlf: bool) -> None:
    monthly = _parse(
        MOMENTUM, frequency=Frequency.MONTHLY, dataset="F-F_Momentum_Factor", crlf=crlf
    )
    annual = _parse(MOMENTUM, frequency=Frequency.ANNUAL, dataset="F-F_Momentum_Factor", crlf=crlf)
    assert monthly["Mom"].tolist() == pytest.approx([0.02, -0.015])
    assert annual["Mom"].tolist() == pytest.approx([0.03])


def test_dataset_metadata() -> None:
    content = _zip(MONTHLY_FF3)
    ds = parse_ken_french(content, _prov(content), frequency=Frequency.MONTHLY)
    assert ds.unit is Unit.RETURN
    assert ds.return_kind is ReturnKind.SIMPLE
    assert ds.currency == Currency("USD")
    assert ds.frequency is Frequency.MONTHLY
    assert any("percent" in note for note in ds.notes)
    assert any("excess" in note for note in ds.notes)
    assert "revised" in ds.availability


# --------------------------------------------------------------------------- strictness
def test_unexpected_columns_raise() -> None:
    text = MONTHLY_FF3.replace(",Mkt-RF,SMB,HML,RF", ",Mkt-RF,SMB,HML,XYZ", 1)
    with pytest.raises(ParseError, match="columns"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_wrong_number_of_values_raises() -> None:
    text = MONTHLY_FF3.replace("202601,    1.23,   -0.45,    0.10,    0.33", "202601,    1.23")
    with pytest.raises(ParseError, match="values"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_non_numeric_value_raises() -> None:
    text = MONTHLY_FF3.replace("1.23", "1.2x")
    with pytest.raises(ParseError, match="number"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_unsorted_dates_raise() -> None:
    text = MONTHLY_FF3.replace("202601,", "202612,", 1)
    with pytest.raises(ParseError, match="increasing"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_invalid_month_raises() -> None:
    text = MONTHLY_FF3.replace("202601,", "202613,", 1)
    with pytest.raises(ParseError, match="date"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_mixed_date_lengths_in_a_section_raise() -> None:
    text = MONTHLY_FF3.replace("202602,", "20260215,", 1)
    with pytest.raises(ParseError, match="date"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_missing_requested_section_raises() -> None:
    with pytest.raises(ParseError, match="DAILY"):
        _parse(MONTHLY_FF3, frequency=Frequency.DAILY)


def test_data_row_outside_a_section_raises() -> None:
    text = MONTHLY_FF3.replace("Copyright", "202701,    1.00,    1.00,    1.00,    1.00\nCopyright")
    with pytest.raises(ParseError, match="outside"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_empty_section_raises() -> None:
    text = "header\n\n,Mkt-RF,SMB,HML,RF\n\nCopyright\n"
    with pytest.raises(ParseError, match="no rows"):
        _parse(text, frequency=Frequency.MONTHLY)


def test_zip_must_contain_exactly_one_file() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", "x")
        archive.writestr("b.csv", "y")
    content = buffer.getvalue()
    with pytest.raises(ParseError, match="exactly one"):
        parse_ken_french(content, _prov(content), frequency=Frequency.MONTHLY)


def test_not_a_zip_raises() -> None:
    content = b"not a zip"
    with pytest.raises(ParseError, match="zip"):
        parse_ken_french(content, _prov(content), frequency=Frequency.MONTHLY)


def test_unknown_dataset_raises() -> None:
    with pytest.raises(ParseError, match="unknown"):
        ken_french_url("Not_A_Dataset")


def test_provenance_must_be_ken_french() -> None:
    content = _zip(MONTHLY_FF3)
    other = Provenance(**(_prov(content).__dict__ | {"source": "ecb_exr"}))
    with pytest.raises(ParseError, match="ken_french"):
        parse_ken_french(content, other, frequency=Frequency.MONTHLY)


def test_frequency_must_match_dataset() -> None:
    content = _zip(DAILY_FF3)
    prov = _prov(content, "F-F_Research_Data_Factors_daily")
    with pytest.raises(ParseError, match="daily"):
        parse_ken_french(content, prov, frequency=Frequency.MONTHLY)


# --------------------------------------------------------------------------- catalogue and download
def test_catalogue_and_urls() -> None:
    assert set(KEN_FRENCH_DATASETS) == {
        "F-F_Research_Data_Factors",
        "F-F_Research_Data_Factors_daily",
        "F-F_Research_Data_5_Factors_2x3",
        "F-F_Research_Data_5_Factors_2x3_daily",
        "F-F_Momentum_Factor",
        "F-F_Momentum_Factor_daily",
    }
    assert ken_french_url("F-F_Momentum_Factor") == (
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"
    )


def test_download_stores_raw_zip_with_provenance(tmp_path: Path) -> None:
    content = _zip(MONTHLY_FF3)

    class Fake:
        def fetch(self, url: str) -> bytes:
            assert url == ken_french_url("F-F_Research_Data_Factors")
            return content

    stored = download_ken_french(
        Fake(),
        RawStore(tmp_path),
        "F-F_Research_Data_Factors",
        now=lambda: datetime(2026, 11, 10, tzinfo=UTC),
    )
    assert stored.path.read_bytes() == content
    assert stored.provenance.source == "ken_french"
    assert "Kenneth R. French" in stored.provenance.terms
