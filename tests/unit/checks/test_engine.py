"""Health-check framework, configuration and engine."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from qrlab.checks.engine import ALL_CHECKS, CheckConfig, load_check_config, run_checks
from qrlab.checks.framework import Direction, Measurement, Severity, Thresholds, classify
from qrlab.core.errors import ValidationError
from support.checks import A, B, C, weighted_context

EXAMPLE = Path(__file__).parents[3] / "configs" / "checks" / "example.toml"


def _config(**overrides: Thresholds) -> CheckConfig:
    base = dict(load_check_config(EXAMPLE).checks)
    base.update(overrides)
    return CheckConfig(base)


# --------------------------------------------------------------------------- classification
@pytest.mark.parametrize(
    ("observed", "direction", "expected"),
    [
        (0.20, Direction.ABOVE, None),  # exactly at the warning level: strict, no finding
        (0.2001, Direction.ABOVE, Severity.WARNING),
        (0.35, Direction.ABOVE, Severity.WARNING),  # exactly at critical: still only warning
        (0.36, Direction.ABOVE, Severity.CRITICAL),
        (0.19, Direction.ABOVE, None),
    ],
)
def test_classify_above(observed: float, direction: Direction, expected: Severity | None) -> None:
    verdict = classify(observed, Thresholds(True, 0.20, 0.35), direction)
    assert (verdict[0] if verdict else None) is expected


def test_classify_below_and_without_critical() -> None:
    thresholds = Thresholds(True, -0.10, -0.25)
    assert classify(-0.10, thresholds, Direction.BELOW) is None
    assert classify(-0.11, thresholds, Direction.BELOW) == (Severity.WARNING, -0.10)
    assert classify(-0.30, thresholds, Direction.BELOW) == (Severity.CRITICAL, -0.25)
    assert classify(5.0, Thresholds(True, 0.0, None), Direction.ABOVE) == (Severity.WARNING, 0.0)


def test_measurements_must_be_finite() -> None:
    with pytest.raises(ValidationError, match="finite"):
        Measurement("portfolio", float("nan"))


# --------------------------------------------------------------------------- config
def test_example_config_covers_every_check() -> None:
    config = load_check_config(EXAMPLE)
    assert set(config.checks) == {spec.id for spec in ALL_CHECKS}


def test_check_ids_are_unique_and_prefixed() -> None:
    ids = [spec.id for spec in ALL_CHECKS]
    assert len(ids) == len(set(ids))
    assert all(spec.id.startswith(spec.category.value + ".") for spec in ALL_CHECKS)


def test_config_validation() -> None:
    checks = dict(load_check_config(EXAMPLE).checks)
    with pytest.raises(ValidationError, match="unknown"):
        CheckConfig({**checks, "risk.made_up": Thresholds(True, 0.0, None)})
    missing = dict(checks)
    missing.pop("concentration.top5")
    with pytest.raises(ValidationError, match="missing"):
        CheckConfig(missing)
    with pytest.raises(ValidationError, match="less severe"):
        _config(**{"concentration.top5": Thresholds(True, 0.7, 0.5)})
    with pytest.raises(ValidationError, match="parameters"):
        _config(**{"data_quality.stale_master": Thresholds(True, 0, None, {})})


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("warning = 0.20\ncritical = 0.35", "warning = 0.20", "critical"),
        ("critical = 0.35", 'critical = "high"', "critical"),
        ("warning = 0.20\n", 'warning = "0.20"\n', "warning"),
        ("enabled = true\nwarning = 0.20", 'enabled = "yes"\nwarning = 0.20', "enabled"),
        (
            "[concentration.largest_position]",
            "[concentration]\nlargest_position = 1\n[concentration.x]",
            "table",
        ),
    ],
)
def test_config_file_strictness(tmp_path: Path, old: str, new: str, match: str) -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "checks.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        load_check_config(path)


# --------------------------------------------------------------------------- engine
def test_engine_sorts_results() -> None:
    ctx = weighted_context({A: "0.5", B: "0.3", C: "0.2"})
    result = run_checks(ctx, load_check_config(EXAMPLE))
    ids = {f.check_id for f in result.findings}
    assert "concentration.largest_position" in ids
    assert "concentration.top5" in result.passed or "concentration.top5" in ids
    assert set(result.passed) | ids | {c for c, _ in result.not_applicable} | set(
        result.disabled
    ) == {spec.id for spec in ALL_CHECKS}


def test_disabled_checks_do_not_run() -> None:
    ctx = weighted_context({A: "0.5", B: "0.5"})
    off = replace(
        load_check_config(EXAMPLE).checks["concentration.largest_position"], enabled=False
    )
    result = run_checks(ctx, _config(**{"concentration.largest_position": off}))
    assert "concentration.largest_position" in result.disabled
    assert all(f.check_id != "concentration.largest_position" for f in result.findings)


def test_finding_carries_numbers() -> None:
    ctx = weighted_context({A: "0.5", B: "0.3", C: "0.2"})
    result = run_checks(ctx, load_check_config(EXAMPLE))
    (finding,) = [f for f in result.findings if f.check_id == "concentration.largest_position"]
    assert finding.severity is Severity.CRITICAL
    assert finding.observed == pytest.approx(0.5)
    assert finding.threshold == pytest.approx(0.35)
    assert finding.details == {"isin": A.code}


def test_top_level_value_must_be_a_table(tmp_path: Path) -> None:
    path = tmp_path / "checks.toml"
    path.write_text("stray = 1\n" + EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValidationError, match="table of checks"):
        load_check_config(path)


def test_spec_id_must_match_category() -> None:
    from qrlab.checks.framework import Category, CheckSpec, MeasureUnit, NotApplicable

    with pytest.raises(ValidationError, match="must start with"):
        CheckSpec(
            "costs.x", Category.RISK, Direction.ABOVE, MeasureUnit.RATIO, frozenset(),
            lambda ctx, params: NotApplicable("x"),
        )  # fmt: skip
