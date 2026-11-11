"""The health-check section of the portfolio report (synthetic results, toy portfolio)."""

from __future__ import annotations

import html
import re

import pytest

from qrlab.checks import (
    ALL_CHECKS,
    Category,
    CheckResult,
    Direction,
    Finding,
    MeasureUnit,
    Severity,
)
from qrlab.core.errors import ValidationError
from qrlab.reporting.check_labels import CHECK_LABELS, check_label
from qrlab.reporting.formatting import Language
from qrlab.reporting.html import Report, render_html
from support.portfolio import D2, D3
from support.report import toy_report


def _report(language: Language = Language.EN, **changes: object) -> Report:
    return toy_report(language, **changes)


def _finding(
    check_id: str,
    severity: Severity,
    observed: float,
    threshold: float,
    unit: MeasureUnit,
    direction: Direction = Direction.ABOVE,
    subject: str = "portfolio",
    details: dict[str, str] | None = None,
) -> Finding:
    return Finding(
        check_id=check_id,
        category=Category(check_id.split(".")[0]),
        severity=severity,
        subject=subject,
        observed=observed,
        threshold=threshold,
        unit=unit,
        direction=direction,
        details=details or {},
    )


RESULT = CheckResult(
    as_of=D3,
    findings=(
        _finding(
            "concentration.largest_position", Severity.WARNING, 0.42, 0.25, MeasureUnit.FRACTION,
        ),
        _finding(
            "etf_quality.fund_size", Severity.CRITICAL, 40e6, 50e6, MeasureUnit.MONEY,
            Direction.BELOW, subject="IE0000000012",
        ),
        _finding(
            "etf_quality.fund_age", Severity.INFO, 2.04, 3.0, MeasureUnit.YEARS, Direction.BELOW,
        ),
        _finding(
            "data_quality.missing_master", Severity.WARNING, 2, 0, MeasureUnit.COUNT,
            details={"missing": "IE0000000012:inception", "empty": ""},
        ),
        _finding(
            "diversification.ratio", Severity.WARNING, 1.0512, 1.10, MeasureUnit.RATIO,
            Direction.BELOW,
        ),
    ),
    passed=("costs.weighted_ter",),
    not_applicable=(("risk.beta", "no benchmark given"),),
    disabled=("drift.total",),
)  # fmt: skip


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def test_labels_cover_exactly_the_registered_checks() -> None:
    ids = {spec.id for spec in ALL_CHECKS}
    for language in Language:
        assert set(CHECK_LABELS[language]) == ids
        assert all(name.strip() and text.strip() for name, text in CHECK_LABELS[language].values())
    assert check_label("risk.beta", Language.IT) == CHECK_LABELS[Language.IT]["risk.beta"]


def test_section_without_checks_says_they_were_not_run() -> None:
    text = _text(render_html(_report(Language.EN)))
    assert "Health checks were not run for this report." in text


def test_findings_are_ranked_formatted_and_explained() -> None:
    report = _report(Language.EN, checks=RESULT)
    text = _text(render_html(report))
    assert (
        "1 critical, 3 warning and 1 information findings; 1 checks passed, "
        "1 not applicable, 1 disabled." in text
    )
    assert "not a recommendation to trade" in text
    assert "Disabled checks: Total drift." in text
    critical = text.index("Critical Fund size IE0000000012 EUR 40,000,000.00 < EUR 50,000,000.00")
    warning = text.index("Warning Largest position Portfolio 42.00% > 25.00%")
    assert critical < warning
    assert "Information Fund age Portfolio 2.0 < 3.0" in text
    assert "Warning Missing master data Portfolio 2 > 0 missing: IE0000000012:inception " in text
    assert "empty:" not in text  # empty details are left out
    assert "Diversification ratio Portfolio 1.05 < 1.10" in text
    assert "Beta no benchmark given" in text
    assert "Reasons are given in English" in text
    explained = text[text.index("What the checks measure") :]
    order = [explained.index(check_label(c, Language.EN)[0]) for c in (
        "concentration.largest_position", "diversification.ratio", "risk.beta",
        "costs.weighted_ter", "etf_quality.fund_size", "data_quality.missing_master",
    )]  # fmt: skip
    assert order == sorted(order)  # registry order
    assert "Total drift" not in explained  # disabled checks are not explained
    assert report.warnings == ("1 critical health-check findings: see Health checks.",)


def test_section_in_italian() -> None:
    text = _text(render_html(_report(Language.IT, checks=RESULT)))
    assert "Controlli di salute" in text
    assert "Critica Dimensione del fondo IE0000000012 40.000.000,00 EUR < 50.000.000,00 EUR" in text
    assert "I motivi sono in inglese" in text


def test_clean_result_has_no_findings_table_or_warning() -> None:
    clean = CheckResult(
        as_of=D3, findings=(), passed=("costs.weighted_ter",), not_applicable=(), disabled=()
    )
    report = _report(Language.EN, checks=clean)
    text = _text(render_html(report))
    assert "Findings" not in text
    assert "Checks not applicable" not in text
    assert "Weighted TER" in text
    assert report.warnings == ()
    nothing = CheckResult(
        as_of=D3,
        findings=(),
        passed=(),
        not_applicable=(),
        disabled=tuple(s.id for s in ALL_CHECKS),
    )
    assert "What the checks measure" not in _text(render_html(_report(checks=nothing)))


def test_checks_for_another_date_raise() -> None:
    stale = CheckResult(as_of=D2, findings=(), passed=(), not_applicable=(), disabled=())
    with pytest.raises(ValidationError, match="health checks are as of"):
        _report(checks=stale)
