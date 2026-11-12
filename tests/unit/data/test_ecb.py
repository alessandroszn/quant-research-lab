"""ECB parsers: euro reference FX rates, euro short-term rate (€STR) and euro-area HICP.

Fixtures are synthetic and reproduce only the *format* of the ECB files.

Hand calculations:

- FX row ``2026-11-09,1.1193,176.79,N/A`` -> 1 EUR = 1.1193 USD, 176.79 JPY, ISK missing
- USD 1119.30 at EUR/USD 1.1193 -> EUR 1000.00
- €STR 2.442 (percent per year) -> 0.02442; the rate for Friday 2026-11-06 is published on the
  next TARGET2 business day, Monday 2026-11-09
- HICP October 2026 with a 17-day publication lag -> available from 2026-11-17
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from qrlab.core.calendar import Frequency
from qrlab.core.errors import ValidationError
from qrlab.core.money import Currency, Money, convert
from qrlab.data.ecb import (
    ECB_SERIES,
    download_ecb_fx,
    download_ecb_series,
    ecb_series_url,
    fx_rate,
    parse_ecb_fx,
    parse_estr,
    parse_hicp,
    parse_yield_curve,
)
from qrlab.data.errors import DataNotFoundError, ParseError
from qrlab.data.provenance import Dataset, Provenance, Unit
from qrlab.data.store import RawStore

FX_CSV = (
    "Date,USD,JPY,ISK,CYP,\n"
    "2026-11-09,1.1193,176.79,N/A,N/A,\n"
    "2026-11-06,1.1165,176.77,N/A,N/A,\n"
    "1999-01-04,1.1789,133.73,N/A,0.58231,\n"
)

_SDMX_HEADER = (
    "KEY,FREQ,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MEASURE,UNIT,UNIT_MULT,UNIT_INDEX_BASE\n"
)
ESTR_CSV = _SDMX_HEADER + (
    "EST.B.EU000A2X2A25.WT,B,2026-11-05,2.442,A,PC,,0,\n"
    "EST.B.EU000A2X2A25.WT,B,2026-11-06,2.443,A,PC,,0,\n"
    "EST.B.EU000A2X2A25.WT,B,2026-11-09,2.442,A,PC,,0,\n"
)
HICP_CSV = _SDMX_HEADER + (
    "HICP.M.U2.N.000000.4D0.INX,M,1990-01,,Q,,IX,0,2025 = 100\n"
    "HICP.M.U2.N.000000.4D0.INX,M,2026-09,104.31,A,,IX,0,2025 = 100\n"
    "HICP.M.U2.N.000000.4D0.INX,M,2026-10,104.77,E,,IX,0,2025 = 100\n"
)


def _zip(text: str, name: str = "eurofxref-hist.csv") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, text)
    return buffer.getvalue()


def _prov(content: bytes, source: str, dataset: str, url: str) -> Provenance:
    return Provenance(
        source=source,
        dataset=dataset,
        url=url,
        retrieved_at=datetime(2026, 11, 10, tzinfo=UTC),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        terms="test",
    )


def _fx(text: str = FX_CSV) -> Dataset:
    content = _zip(text)
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
    return parse_ecb_fx(content, _prov(content, "ecb", "eurofxref-hist", url))


def _series(text: str, name: str) -> tuple[bytes, Provenance]:
    content = text.encode("utf-8")
    return content, _prov(content, "ecb", name, ecb_series_url(name))


# --------------------------------------------------------------------------- FX
def test_fx_hand_example_and_ascending_order() -> None:
    data = _fx().data
    assert list(data.columns) == ["USD", "JPY", "ISK", "CYP"]
    assert list(data.index) == list(pd.DatetimeIndex(["1999-01-04", "2026-11-06", "2026-11-09"]))
    assert data.loc["2026-11-09", "USD"] == pytest.approx(1.1193)
    assert data.isna().loc["2026-11-09", "ISK"]
    assert data.loc["1999-01-04", "CYP"] == pytest.approx(0.58231)


def test_fx_metadata_and_availability() -> None:
    ds = _fx()
    assert ds.unit is Unit.FX_RATE
    assert ds.currency == Currency("EUR")
    assert ds.return_kind is None
    assert any("per 1 EUR" in note for note in ds.notes)
    assert ds.available_from is not None
    assert (ds.available_from == ds.data.index.to_series()).all()  # same-day publication
    assert "16:00" in ds.availability


def test_fx_rate_bridge_to_core() -> None:
    rate = fx_rate(_fx(), quote=Currency("USD"), on=date(2026, 11, 9))
    assert rate.base == Currency("EUR")
    assert rate.rate == Decimal("1.1193")
    assert rate.as_of == date(2026, 11, 9)
    assert convert(Money.of("1119.30", "USD"), rate, to=Currency("EUR")) == Money.of(1000, "EUR")


def test_fx_rate_is_never_forward_filled() -> None:
    ds = _fx()
    with pytest.raises(DataNotFoundError, match="2026-11-07"):
        fx_rate(ds, quote=Currency("USD"), on=date(2026, 11, 7))  # Saturday: no fixing
    with pytest.raises(DataNotFoundError, match="missing"):
        fx_rate(ds, quote=Currency("ISK"), on=date(2026, 11, 9))


def test_fx_rate_unknown_column() -> None:
    with pytest.raises(DataNotFoundError, match="CHF"):
        fx_rate(_fx(), quote=Currency("CHF"), on=date(2026, 11, 9))


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("Day,USD,\n2026-11-09,1.1,\n", "Date"),
        ("Date,USD,\n2026-11-06,1.1,\n2026-11-09,1.2,\n", "decreasing"),
        ("Date,USD,\n2026-11-09,1.1,\n2026-11-09,1.2,\n", "decreasing"),
        ("Date,USD,\n2026-11-09,1.1,2.0,\n", "values"),
        ("Date,USD,\n2026-11-09,abc,\n", "number"),
        ("Date,USD,\n2026-11-09,-1.1,\n", "positive"),
        ("Date,USD,\n2026-11-09,,\n", "empty"),
        ("Date,usd,\n2026-11-09,1.1,\n", "code"),
        ("Date,USD,\n09/11/2026,1.1,\n", "date"),
        ("Date,\n", "currency"),
        ("Date,USD,\n", "no rows"),
    ],
)
def test_fx_strictness(text: str, match: str) -> None:
    with pytest.raises(ParseError, match=match):
        _fx(text)


def test_fx_zip_must_hold_one_file() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.csv", FX_CSV)
        archive.writestr("b.csv", FX_CSV)
    content = buffer.getvalue()
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
    with pytest.raises(ParseError, match="exactly one"):
        parse_ecb_fx(content, _prov(content, "ecb", "eurofxref-hist", url))


# --------------------------------------------------------------------------- €STR
def test_estr_hand_example() -> None:
    ds = parse_estr(*_series(ESTR_CSV, "estr"))
    assert ds.unit is Unit.RATE_PER_YEAR
    assert ds.frequency is Frequency.DAILY
    assert ds.data["ESTR"].tolist() == pytest.approx([0.02442, 0.02443, 0.02442])
    assert any("ACT/360" in note for note in ds.notes)


def test_estr_is_available_on_next_target2_business_day() -> None:
    ds = parse_estr(*_series(ESTR_CSV, "estr"))
    assert ds.available_from is not None
    assert list(ds.available_from) == list(
        pd.DatetimeIndex(["2026-11-06", "2026-11-09", "2026-11-10"])
    )


def test_estr_rejects_wrong_unit() -> None:
    with pytest.raises(ParseError, match="unit"):
        parse_estr(*_series(ESTR_CSV.replace(",PC,", ",XX,"), "estr"))


def test_estr_rejects_other_series_key() -> None:
    with pytest.raises(ParseError, match="key"):
        parse_estr(*_series(ESTR_CSV.replace("EU000A2X2A25.WT", "EU000A2X2A25.OTHER", 1), "estr"))


# --------------------------------------------------------------------------- HICP
def test_hicp_values_status_and_availability() -> None:
    ds = parse_hicp(*_series(HICP_CSV, "hicp_euro_area"), publication_lag_days=17)
    assert ds.unit is Unit.INDEX_LEVEL
    data = ds.data["HICP"]
    assert list(data.index) == list(pd.DatetimeIndex(["1990-01-31", "2026-09-30", "2026-10-31"]))
    assert np.isnan(data.iloc[0])
    assert data.iloc[-1] == pytest.approx(104.77)
    assert ds.status is not None
    assert ds.status.tolist() == ["Q", "A", "E"]
    assert ds.available_from is not None
    assert ds.available_from.iloc[-1] == pd.Timestamp("2026-11-17")
    assert any("2025 = 100" in note for note in ds.notes)
    assert any("estimate" in note for note in ds.notes)


@pytest.mark.parametrize("lag", [-1, 1.5, True])
def test_hicp_publication_lag_must_be_non_negative_int(lag: object) -> None:
    with pytest.raises(ValidationError, match="publication_lag_days"):
        parse_hicp(*_series(HICP_CSV, "hicp_euro_area"), publication_lag_days=lag)  # type: ignore[arg-type]


def test_hicp_missing_value_requires_missing_status() -> None:
    text = HICP_CSV.replace("2026-09,104.31,A", "2026-09,,A")
    with pytest.raises(ParseError, match="status"):
        parse_hicp(*_series(text, "hicp_euro_area"), publication_lag_days=17)


def test_hicp_rejects_unit_multiplier() -> None:
    text = HICP_CSV.replace(",IX,0,", ",IX,3,")
    with pytest.raises(ParseError, match="UNIT_MULT"):
        parse_hicp(*_series(text, "hicp_euro_area"), publication_lag_days=17)


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("KEY,TIME_PERIOD\nx,2026-01\n", "columns"),
        (_SDMX_HEADER, "no rows"),
        (HICP_CSV.replace("2026-10,", "2026-13,"), "date"),
        (HICP_CSV.replace("2026-10,", "2026-09,"), "increasing"),
        (HICP_CSV.replace("104.77", "1o4.77"), "number"),
    ],
)
def test_sdmx_strictness(text: str, match: str) -> None:
    with pytest.raises(ParseError, match=match):
        parse_hicp(*_series(text, "hicp_euro_area"), publication_lag_days=17)


def test_parsers_check_provenance_dataset() -> None:
    content, prov = _series(ESTR_CSV, "estr")
    with pytest.raises(ParseError, match="hicp_euro_area"):
        parse_hicp(content, prov, publication_lag_days=17)


# --------------------------------------------------------------------------- point-in-time
def test_available_from_cannot_precede_reference_date() -> None:
    ds = parse_hicp(*_series(HICP_CSV, "hicp_euro_area"), publication_lag_days=0)
    early = ds.available_from - pd.Timedelta(days=1)  # type: ignore[operator]
    with pytest.raises(ValidationError, match="before"):
        Dataset(**(ds.__dict__ | {"available_from": early}))


def test_available_from_and_status_must_align_with_data() -> None:
    ds = parse_hicp(*_series(HICP_CSV, "hicp_euro_area"), publication_lag_days=0)
    assert ds.status is not None
    with pytest.raises(ValidationError, match="index"):
        Dataset(**(ds.__dict__ | {"status": ds.status.iloc[:-1]}))


# --------------------------------------------------------------------------- downloads
def test_series_catalogue_and_urls() -> None:
    assert set(ECB_SERIES) == {"estr", "hicp_euro_area", "yc_aaa_spot_6y", "yc_aaa_spot_7y"}
    assert ecb_series_url("yc_aaa_spot_7y") == (
        "https://data-api.ecb.europa.eu/service/data/YC/"
        "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_7Y?format=csvdata"
    )
    assert ecb_series_url("hicp_euro_area") == (
        "https://data-api.ecb.europa.eu/service/data/HICP/M.U2.N.000000.4D0.INX?format=csvdata"
    )
    with pytest.raises(ParseError, match="unknown"):
        ecb_series_url("nope")


def test_downloads_store_raw_bytes(tmp_path: Path) -> None:
    class Fake:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def fetch(self, url: str) -> bytes:
            self.urls.append(url)
            return _zip(FX_CSV) if url.endswith(".zip") else ESTR_CSV.encode()

    fake, store = Fake(), RawStore(tmp_path)
    now = lambda: datetime(2026, 11, 10, tzinfo=UTC)  # noqa: E731
    fx = download_ecb_fx(fake, store, now=now)
    estr = download_ecb_series(fake, store, "estr", now=now)
    assert fake.urls == [
        "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip",
        ecb_series_url("estr"),
    ]
    assert fx.provenance.source == estr.provenance.source == "ecb"
    assert "ECB" in fx.provenance.terms
    assert parse_estr(store.read(estr), estr.provenance).data.shape == (3, 1)


def test_fx_blank_lines_are_ignored() -> None:
    assert _fx(FX_CSV + "\n\n").data.shape == (3, 4)


def test_fx_not_a_zip_raises() -> None:
    content = b"plain text"
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
    with pytest.raises(ParseError, match="zip"):
        parse_ecb_fx(content, _prov(content, "ecb", "eurofxref-hist", url))


def test_available_from_must_be_dates() -> None:
    ds = parse_hicp(*_series(HICP_CSV, "hicp_euro_area"), publication_lag_days=0)
    as_numbers = pd.Series([1.0, 2.0, 3.0], index=ds.data.index)
    with pytest.raises(ValidationError, match="dates"):
        Dataset(**(ds.__dict__ | {"available_from": as_numbers}))


YC_CSV = _SDMX_HEADER + (
    "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_7Y,B,2004-09-06,3.828505244973507,A,,PCPA,0,\n"
    "YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_7Y,B,2004-09-07,3.8392935757604096,A,,PCPA,0,\n"
)


def test_yield_curve_hand_example() -> None:
    ds = parse_yield_curve(*_series(YC_CSV, "yc_aaa_spot_7y"))
    assert ds.unit is Unit.RATE_PER_YEAR
    assert list(ds.data.columns) == ["SR_7Y"]
    assert ds.data.iloc[0, 0] == pytest.approx(0.03828505244973507)
    assert any("continuously compounded" in note.lower() for note in ds.notes)


def test_yield_curve_strictness() -> None:
    with pytest.raises(ParseError, match="not a supported yield-curve series"):
        parse_yield_curve(*_series(ESTR_CSV, "estr"))
    wrong_unit = YC_CSV.replace("PCPA", "PC")
    with pytest.raises(ParseError, match="unit"):
        parse_yield_curve(*_series(wrong_unit, "yc_aaa_spot_7y"))
    wrong_key = YC_CSV.replace("SR_7Y", "SR_6Y")
    with pytest.raises(ParseError, match="series key"):
        parse_yield_curve(*_series(wrong_key, "yc_aaa_spot_7y"))
