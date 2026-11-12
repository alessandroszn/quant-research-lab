"""Open Source Asset Pricing files: strict parsing of the returns and the signal documentation."""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.data.errors import ParseError
from qrlab.data.open_asset_pricing import (
    REVISION,
    SIGNAL_DOC_COLUMNS,
    download_osap,
    osap_url,
    parse_long_short_returns,
    parse_signal_doc,
)
from qrlab.data.provenance import Provenance, Unit
from qrlab.data.store import RawStore


def _prov(content: bytes, dataset: str) -> Provenance:
    return Provenance(
        source="osap",
        dataset=dataset,
        url=osap_url(dataset, revision=REVISION),
        retrieved_at=datetime(2026, 11, 12, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="test",
    )


def _parquet(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, index=False)
    return buffer.getvalue()


RETURNS = pd.DataFrame(
    {
        "date": pd.to_datetime(["2000-01-31", "2000-02-29", "2000-03-31"]).date,
        "AbnormalAccruals": [1.23, -0.5, np.nan],
        "Mom12m": [0.1, 0.2, 0.3],
    }
)


def _doc(**changes: Any) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "Acronym": ["AbnormalAccruals", "Mom12m", "Placebo1"],
            "Cat.Signal": ["Predictor", "Predictor", "Placebo"],
            "Predictability in OP": ["1_clear", "2_likely", "4_not"],
            "Signal Rep Quality": ["2_fair", "1_good", None],
            "Authors": ["Xie", "Jegadeesh and Titman", "Someone"],
            "Year": [2001, 1993, None],
            "Journal": ["AR", "JF", "JF"],
            "LongDescription": ["Abnormal Accruals", "Momentum (12 month)", "A placebo"],
            "Cat.Data": ["Accounting", "Price", "Price"],
            "SampleStartYear": [1971, 1965, None],
            "SampleEndYear": [1992, 1989, None],
            "Sign": [-1.0, 1.0, 1.0],
            "Detailed Definition": ["Residual, with a comma", "Return t-12 to t-2", "x"],
        }
    )
    for column, values in changes.items():
        frame[column] = values
    return frame


def _doc_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


# ---------------------------------------------------------------------------------- returns
def test_returns_by_hand() -> None:
    content = _parquet(RETURNS)
    ds = parse_long_short_returns(content, _prov(content, "long_short_returns"))
    assert ds.frequency is Frequency.MONTHLY
    assert ds.unit is Unit.RETURN
    assert list(ds.data.columns) == ["AbnormalAccruals", "Mom12m"]
    assert list(ds.data.index) == list(pd.date_range("2000-01-31", periods=3, freq="ME"))
    # 1.23 percent is 0.0123.
    assert ds.data.iloc[0, 0] == pytest.approx(0.0123)
    assert ds.data.isna().iloc[2, 0]
    assert any("signed as in the original papers" in note for note in ds.notes)


def test_first_of_month_dates_become_month_ends() -> None:
    frame = RETURNS.assign(date=pd.to_datetime(["2000-01-01", "2000-02-01", "2000-03-01"]))
    content = _parquet(frame)
    ds = parse_long_short_returns(content, _prov(content, "long_short_returns"))
    assert ds.data.index[1] == pd.Timestamp("2000-02-29")


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (RETURNS.drop(columns="date"), "'date' column"),
        (RETURNS[["date"]], "unique predictor columns"),
        (RETURNS.iloc[[1, 0, 2]], "not increasing"),
        (RETURNS.assign(date=["2000-01-31", "not a date", "2000-03-31"]), "invalid dates"),
        (RETURNS.assign(Mom12m=["a", "b", "c"]), "non-numeric"),
    ],
)
def test_returns_are_strict(frame: pd.DataFrame, message: str) -> None:
    content = _parquet(frame)
    with pytest.raises(ParseError, match=message):
        parse_long_short_returns(content, _prov(content, "long_short_returns"))


def test_corrupt_parquet_and_wrong_provenance() -> None:
    content = b"not parquet"
    with pytest.raises(ParseError, match="not a readable Parquet"):
        parse_long_short_returns(content, _prov(content, "long_short_returns"))
    good = _parquet(RETURNS)
    with pytest.raises(ParseError, match="provenance must be osap/long_short_returns"):
        parse_long_short_returns(good, _prov(good, "signal_doc"))


def test_missing_pyarrow_gives_an_install_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    content = _parquet(RETURNS)

    def no_parquet(*args: object, **kwargs: object) -> pd.DataFrame:
        raise ImportError("Unable to find a usable engine")

    monkeypatch.setattr(pd, "read_parquet", no_parquet)
    with pytest.raises(ParseError, match=r"qrlab\[parquet\]"):
        parse_long_short_returns(content, _prov(content, "long_short_returns"))


# ------------------------------------------------------------------------------- signal doc
def test_signal_doc_by_hand() -> None:
    content = _doc_bytes(_doc())
    doc = parse_signal_doc(content, _prov(content, "signal_doc"))
    assert list(doc.columns) == list(SIGNAL_DOC_COLUMNS[1:])
    assert list(doc.index) == ["AbnormalAccruals", "Mom12m", "Placebo1"]
    assert doc.loc["AbnormalAccruals", "SampleEndYear"] == 1992
    assert doc.loc["Mom12m", "Sign"] == 1.0
    assert doc["Year"].isna()["Placebo1"]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"Cat.Signal": ["Predictor", "Predictor", "Other"]}, "Cat.Signal must be one of"),
        ({"Predictability in OP": ["clear", "2_likely", "4_not"]}, "Predictability in OP"),
        ({"Acronym": ["A", "A", "B"]}, "duplicated acronyms"),
        ({"Acronym": ["A", None, "B"]}, "without an acronym"),
        ({"Sign": [1.0, 0.0, 1.0]}, "Sign must be 1 or -1"),
        ({"Year": [2001, None, None]}, "whole publication and sample years"),
        ({"SampleStartYear": [1971, 1965.5, None]}, "whole publication and sample years"),
        ({"SampleStartYear": [1995, 1965, None]}, "after its SampleEndYear"),
    ],
)
def test_signal_doc_is_strict(changes: dict[str, object], message: str) -> None:
    content = _doc_bytes(_doc(**changes))
    with pytest.raises(ParseError, match=message):
        parse_signal_doc(content, _prov(content, "signal_doc"))


def test_signal_doc_missing_column_and_bad_bytes() -> None:
    content = _doc_bytes(_doc().drop(columns="SampleEndYear"))
    with pytest.raises(ParseError, match="missing columns"):
        parse_signal_doc(content, _prov(content, "signal_doc"))
    bad = b"\xff\xfe\x00not utf8"
    with pytest.raises(ParseError, match="readable UTF-8 CSV"):
        parse_signal_doc(bad, _prov(bad, "signal_doc"))


# ----------------------------------------------------------------------------- URL and download
def test_urls_are_pinned_and_quoted() -> None:
    url = osap_url("long_short_returns", revision=REVISION)
    assert url == (
        "https://huggingface.co/datasets/OpenSourceAP/CrossSection/resolve/"
        f"{REVISION}/Portfolios/Full%20Sets%20OP/PredictorLSretWide.parquet"
    )
    with pytest.raises(ParseError, match="unknown OSAP dataset"):
        osap_url("firm_level", revision=REVISION)
    with pytest.raises(ParseError, match="40-character"):
        osap_url("signal_doc", revision="main")


def test_download_stores_the_raw_file(tmp_path: Path) -> None:
    content = _parquet(RETURNS)

    class Fake:
        def fetch(self, url: str) -> bytes:
            assert url == osap_url("long_short_returns", revision=REVISION)
            return content

    stored = download_osap(
        Fake(),
        RawStore(tmp_path),
        "long_short_returns",
        revision=REVISION,
        now=lambda: datetime(2026, 11, 12, tzinfo=UTC),
    )
    assert stored.path.suffix == ".parquet"
    assert stored.provenance.source == "osap"
    assert stored.path.read_bytes() == content


def test_placebo_and_dropped_rows_are_kept_as_published() -> None:
    # Regression (real release 2026.10): Cat.Signal also has "Drop"; placebos have predictability
    # "indirect" and dropped or placebo rows may have no sign. Only predictors are strict.
    frame = _doc(
        **{
            "Cat.Signal": ["Predictor", "Drop", "Placebo"],
            "Predictability in OP": ["1_clear", "9_drop", "indirect"],
            "Sign": [-1.0, None, None],
        }
    )
    content = _doc_bytes(frame)
    doc = parse_signal_doc(content, _prov(content, "signal_doc"))
    assert doc["Cat.Signal"].tolist() == ["Predictor", "Drop", "Placebo"]
    assert doc["Sign"].isna().tolist() == [False, True, True]
    bad = _doc_bytes(_doc(**{"Sign": [None, 1.0, 1.0]}))
    with pytest.raises(ParseError, match="Sign must be 1 or -1 for every predictor"):
        parse_signal_doc(bad, _prov(bad, "signal_doc"))
