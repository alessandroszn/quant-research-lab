"""Italian forms of library messages (design 8.7), and the guard that keeps them complete."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from qrlab.experiments import run_experiment
from qrlab.experiments.kinds import KINDS
from qrlab.lookthrough import NOT_LOOKED_THROUGH, UNEXPLAINED, UNKNOWN, Dimension
from qrlab.reporting import Language
from qrlab.reporting.messages import DETAIL_KEYS, detail_key, detail_value, is_known, translate

ROOT = Path(__file__).parents[3]
SOURCE = ROOT / "src" / "qrlab"
NOTE_FILES = {"portfolio/broker_import.py", "data/user_csv.py", "instruments/io.py"}


@pytest.mark.parametrize(
    ("english", "italian"),
    [
        ("no benchmark given", "nessun benchmark indicato"),
        (
            "3 common returns, fewer than the window of 36",
            "3 rendimenti comuni, meno della finestra di 36",
        ),
        (
            "4 observations leave a tail of 0.2 at confidence 0.95; need >= 1",
            "4 osservazioni lasciano una coda di 0,2 al livello di confidenza 0,95; "
            "ne serve almeno 1",
        ),
        ("no issuer known through holdings", "emittente: nessun valore noto dalle holdings"),
        (
            "down_capture: the benchmark has no down periods",
            "down_capture: il benchmark non ha periodi negativi",
        ),
        ("skewness: zero variance", "skewness: varianza nulla"),
        (
            "Cornish-Fisher expansion is not a quantile on the tail "
            "(skewness 0.281, excess kurtosis -0.172)",
            "l'espansione di Cornish-Fisher non è un quantile nella coda "
            "(asimmetria 0,281, curtosi in eccesso -0,172)",
        ),
        (
            "File listed newest first; rows reversed as a whole (chronological order).",
            "File ordinato dalla riga più recente; righe invertite in blocco (ordine cronologico).",
        ),
        (
            "Empty fees and taxes recorded as zero EUR.",
            "Commissioni e imposte vuote registrate come zero EUR.",
        ),
        ("Ignored columns: ['Descrizione'].", "Colonne ignorate: ['Descrizione']."),
        (
            "security, not issuer (no issuer map)",
            "titolo, non emittente (nessuna mappa degli emittenti)",
        ),
    ],
)
def test_messages_in_italian(english: str, italian: str) -> None:
    assert translate(english, Language.IT) == italian
    assert translate(english, Language.EN) == english
    assert is_known(english)


def test_text_outside_the_catalog_is_left_alone() -> None:
    for text in (
        "Synthetic example",
        "no benchmark given, really",
        "Example World Equity UCITS ETF",
    ):
        assert translate(text, Language.IT) == text
        assert not is_known(text)


@pytest.mark.parametrize(
    ("value", "italian"),
    [
        ("0.001744", "0,001744"),
        ("+0.425581", "+0,425581"),
        ("0.100000 / 0.250000", "0,100000 / 0,250000"),
        ("12", "12"),
        ("cash", "liquidità"),
        (
            "security, not issuer (no issuer map)",
            "titolo, non emittente (nessuna mappa degli emittenti)",
        ),
        ("IE0000000012:fund_size", "IE0000000012:fund_size"),
        ("2026-01-02 - 2026-03-31", "2026-01-02 - 2026-03-31"),
    ],
)
def test_detail_values(value: str, italian: str) -> None:
    assert detail_value(value, Language.IT) == italian
    assert detail_value(value, Language.EN) == value


def test_detail_keys() -> None:
    assert detail_key("effective_positions", Language.IT) == "posizioni effettive"
    assert detail_key("effective_positions", Language.EN) == "effective_positions"
    assert detail_key("something_new", Language.IT) == "something_new"


# --------------------------------------------------------------------------- the guard
def _template(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = [
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "1"
            for v in node.values
        ]
        return "".join(parts)
    return None


def _library_messages() -> list[tuple[str, str]]:
    """Every literal message template the library can show in a report, with its location."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        rel = path.relative_to(SOURCE).as_posix()
        if rel.startswith("reporting/"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            note = (
                rel in NOTE_FILES
                and name == "append"
                and getattr(getattr(node.func, "value", None), "id", "") == "notes"
            )
            if name in {"NotApplicable", "UndefinedMetricError"} or note:
                text = _template(node.args[0])
                if text is not None:
                    found.append((f"{rel}:{node.lineno}", text))
    return found


def test_every_library_message_has_an_italian_form() -> None:
    messages = _library_messages()
    assert len(messages) > 50  # the scan really finds the messages
    missing = [f"{where}: {text!r}" for where, text in messages if not is_known(text)]
    assert not missing, "add these to qrlab.reporting.messages:\n" + "\n".join(missing)


def _keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _detail_keys() -> set[str]:
    """Literal keys of measurement details in the checks."""
    keys: set[str] = set()
    for path in sorted((SOURCE / "checks").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "Measurement"
                and len(node.args) >= 3
                and isinstance(node.args[2], ast.Dict)
            ):
                keys |= _keys(node.args[2])
            elif (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Dict)
                and any(getattr(t, "id", None) == "details" for t in node.targets)
            ):
                keys |= _keys(node.value)
            elif (
                isinstance(node, ast.Subscript)
                and getattr(node.value, "id", None) == "details"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value)
    return keys


def test_every_detail_key_has_an_italian_name() -> None:
    keys = (
        _detail_keys() | {d.value for d in Dimension} | {UNKNOWN, UNEXPLAINED, NOT_LOOKED_THROUGH}
    )
    assert len(keys) > 20
    assert sorted(keys - set(DETAIL_KEYS)) == []


# --------------------------------------------------------------------------- end to end
ENGLISH_MARKERS = re.compile(
    r"\b(needs|given|known|fewer than|listed newest|Ignored|observations leave|"
    r"unexplained|not looked through|no benchmark|no issuer map|recorded as zero)\b"
)


def test_the_full_example_in_italian_has_no_library_english(tmp_path: Path) -> None:
    text = (ROOT / "configs/experiments/example_portfolio_report_full.toml").read_text(
        encoding="utf-8"
    )
    text = text.replace('"../../', f'"{ROOT.as_posix()}/').replace(
        '"../', f'"{(ROOT / "configs").as_posix()}/'
    )
    start = text.index('directory = "')
    end = text.index('"', start + len('directory = "'))
    text = text[:start] + f'directory = "{(tmp_path / "out").as_posix()}"' + text[end + 1 :]
    config = tmp_path / "full.toml"
    config.write_text(text, encoding="utf-8")
    result = run_experiment(config, kinds=KINDS, overwrite=False)
    assert result.succeeded, result.record["error"]
    html = (result.output_dir / "report.html").read_text(encoding="utf-8")
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    visible = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    # Provenance terms are recorded data, quoted as written; leave them out of the check.
    visible = visible.replace("user-supplied file; stays in the git-ignored data folder", "")
    assert ENGLISH_MARKERS.findall(visible) == []
