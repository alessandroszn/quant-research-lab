"""Italian and English strings, display formatting, settings and unsaved edits (no Qt)."""

from __future__ import annotations

import json
import math
import string
from pathlib import Path

import numpy as np
import pytest

from qrlab.experiments.kinds import KINDS
from qrlab_app.display import MISSING, cell_text, date_text, timestamp_text
from qrlab_app.runs import RunQueue
from qrlab_app.strings import LANGUAGES, STRINGS, tr, tr_value
from qrlab_app.viewmodels import (
    MAX_RECENT,
    AppError,
    ExperimentViewModel,
    SettingsViewModel,
    WorkspaceViewModel,
    load_result,
)

ROOT = Path(__file__).parents[3]


class MemoryStore:
    """Settings kept in a dict."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.entries = dict(values or {})

    def get(self, key: str) -> str | None:
        return self.entries.get(key)

    def set(self, key: str, value: str) -> None:
        self.entries[key] = value


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# ------------------------------------------------------------------------------- strings
def test_both_languages_have_the_same_keys_and_placeholders() -> None:
    assert LANGUAGES == ("en", "it")
    assert tuple(STRINGS) == LANGUAGES
    english, italian = STRINGS["en"], STRINGS["it"]
    assert set(english) == set(italian)
    for key in english:
        assert english[key].strip(), key
        assert italian[key].strip(), key
        assert _placeholders(english[key]) == _placeholders(italian[key]), key
        # Regression: a {language} placeholder clashes with tr()'s own parameter.
        assert "language" not in _placeholders(english[key]), key
        assert english[key].count("|") == italian[key].count("|"), key  # table headers


def test_tr_and_tr_value() -> None:
    assert tr("nav.settings", "it") == "Impostazioni"
    assert tr("screen.done", "it", status="riuscita") == "Esecuzione terminata: riuscita."
    with pytest.raises(KeyError, match="unsupported language"):
        tr("app.title", "fr")
    assert tr_value("tag", "out_of_sample", "it") == "fuori campione"
    assert tr_value("tag", "in_sample", "en") == "in-sample"
    assert tr_value("status", "failure", "it") == "non riuscita"
    assert tr_value("status", "something_new", "it") == "something_new"  # shown as recorded


def test_every_app_error_is_translated(tmp_path: Path) -> None:
    """Trigger each view-model error and read it in both languages."""
    ws = WorkspaceViewModel()
    errors: list[AppError] = []

    def catch(action: object) -> None:
        with pytest.raises(AppError) as info:
            action()  # type: ignore[operator]
        errors.append(info.value)

    catch(ws.require)
    catch(lambda: ws.open(tmp_path / "missing"))
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    catch(lambda: ws.create(tmp_path / "file.txt"))
    catch(lambda: load_result(tmp_path))
    catch(lambda: ExperimentViewModel(ws, kinds=KINDS, kind_names=["nope"]))
    ws.create(tmp_path / "ws")
    screen = ExperimentViewModel(ws, kinds=KINDS, kind_names=["projection"])
    catch(screen.save)
    catch(lambda: screen.new_from_template("backtest", "x"))
    catch(lambda: screen.new_from_template("projection", "a/b"))
    screen.new_from_template("projection", "mine")
    catch(lambda: screen.new_from_template("projection", "mine"))
    catch(screen.prepare_run)  # the template is not valid until filled in
    queue = RunQueue(lambda config: None)  # type: ignore[arg-type, return-value]
    catch(lambda: queue.add(tmp_path / "absent.toml"))
    template = tmp_path / "ws" / "configs" / "mine.toml"
    template.write_text(
        '[experiment]\nname = "m"\nkind = "projection"\nhypothesis = "h"\n[inputs]\n'
        '[parameters]\n[output]\ndirectory = "../results/m"\n',
        encoding="utf-8",
    )
    queue.add(template)
    catch(lambda: queue.add(template))
    catch(lambda: SettingsViewModel(MemoryStore(), system_language="en").set_language("fr"))

    keys = [e.key for e in errors]
    assert keys == [
        "screen.no_workspace",
        "error.not_folder",
        "error.workspace",
        "error.no_record",
        "error.unknown_kinds",
        "error.no_selection",
        "error.not_on_screen",
        "error.bad_name",
        "error.exists",
        "screen.invalid",
        "queue.unreadable",
        "queue.same_output",
        "error.language",
    ]
    for error in errors:
        assert str(error) == error.text("en")
        assert error.text("it") != error.text("en") or error.key == "error.unknown_kinds"
    assert errors[8].text("it") == "mine.toml esiste già."
    assert errors[7].text("en") == "'a/b' is not a valid file name."


# ------------------------------------------------------------------------------- display
@pytest.mark.parametrize(
    ("value", "en", "it"),
    [
        (0.0317, "0.0317", "0,0317"),
        (np.float64(1234567.891), "1,234,570", "1.234.570"),
        (-22500.0, "-22,500", "-22.500"),
        (math.nan, MISSING, MISSING),
        (np.float64("nan"), MISSING, MISSING),
        (math.inf, "∞", "∞"),
        (-math.inf, "-∞", "-∞"),
        (2024, "2024", "2024"),  # integers are not grouped
        (np.int64(1914), "1914", "1914"),
        (True, "True", "True"),
        (np.bool_(False), "False", "False"),
        ("2026-03-31", "2026-03-31", "2026-03-31"),  # text is shown as recorded
        ("hrp", "hrp", "hrp"),
        (None, "", ""),
    ],
)
def test_cell_text(value: object, en: str, it: str) -> None:
    assert cell_text(value, "en") == en
    assert cell_text(value, "it") == it


def test_dates_and_timestamps() -> None:
    from datetime import date

    assert date_text(date(2026, 11, 12), "it") == "12/11/2026"
    assert date_text(date(2026, 11, 12), "en") == "2026-11-12"
    assert timestamp_text("2026-11-12T14:03:59.5+00:00", "it") == "12/11/2026 14:03 UTC"
    assert timestamp_text("2026-11-12T15:03:00+01:00", "en") == "2026-11-12 14:03 UTC"
    assert timestamp_text("2026-11-12T14:03:00", "en") == "2026-11-12T14:03:00"  # no zone
    assert timestamp_text("not a date", "it") == "not a date"


# ------------------------------------------------------------------------------ settings
def test_language_default_choice_and_fallback() -> None:
    assert SettingsViewModel(MemoryStore(), system_language="it_IT").language == "it"
    assert SettingsViewModel(MemoryStore(), system_language="IT").language == "it"
    assert SettingsViewModel(MemoryStore(), system_language="en_GB").language == "en"
    assert SettingsViewModel(MemoryStore(), system_language="").language == "en"
    store = MemoryStore({"language": "fr"})  # not supported: the default applies
    settings = SettingsViewModel(store, system_language="it_IT")
    assert settings.language == "it"
    settings.set_language("en")
    assert settings.language == "en"
    assert store.entries["language"] == "en"


def test_recent_workspaces(tmp_path: Path) -> None:
    store = MemoryStore()
    settings = SettingsViewModel(store, system_language="en")
    assert settings.recent() == []
    folders = [tmp_path / f"ws{i}" for i in range(MAX_RECENT + 2)]
    for folder in folders:
        folder.mkdir()
        settings.remember(folder)
    recent = settings.recent()
    assert len(recent) == MAX_RECENT
    assert [r.path for r in recent] == [f.resolve() for f in reversed(folders)][:MAX_RECENT]
    # Opening one again moves it first, without a duplicate (paths are compared resolved).
    settings.remember(folders[5] / ".." / "ws5")
    assert [r.path for r in settings.recent()][:2] == [folders[5].resolve(), folders[9].resolve()]
    assert len(settings.recent()) == MAX_RECENT
    # A folder that disappears is kept but marked.
    folders[9].rmdir()
    marked = {r.path: r.exists for r in settings.recent()}
    assert marked[folders[9].resolve()] is False
    assert marked[folders[5].resolve()] is True
    settings.forget(folders[9])
    assert folders[9].resolve() not in {r.path for r in settings.recent()}
    settings.clear_recent()
    assert settings.recent() == []


@pytest.mark.parametrize("raw", ["not json", '{"a": 1}', "[1, 2]", ""])
def test_unreadable_recent_list_is_ignored(raw: str) -> None:
    settings = SettingsViewModel(MemoryStore({"recent_workspaces": raw}), system_language="en")
    assert settings.recent() == []


def test_geometry_round_trip() -> None:
    settings = SettingsViewModel(MemoryStore(), system_language="en")
    assert settings.geometry is None
    settings.set_geometry("01d9d0cb")
    assert settings.geometry == "01d9d0cb"


# ---------------------------------------------------------------------------- dirty state
def _dirty(screen: ExperimentViewModel) -> bool:
    """Read the property through a call, so the type checker does not narrow it."""
    return screen.dirty


def test_unsaved_edits_are_tracked(tmp_path: Path) -> None:
    ws = WorkspaceViewModel()
    ws.create(tmp_path / "ws")
    screen = ExperimentViewModel(ws, kinds=KINDS, kind_names=["projection"])
    assert not _dirty(screen)  # nothing selected
    path = screen.new_from_template("projection", "mine")
    assert not _dirty(screen)
    original = screen.text
    screen.set_text(original + "\n# note")
    assert _dirty(screen)
    screen.set_text(original)  # back to the saved text
    assert not _dirty(screen)
    screen.set_text(original + "\n# note")
    assert screen.revert() == original
    assert not _dirty(screen)
    screen.set_text(original + "\n# kept")
    screen.save()
    assert not _dirty(screen)
    assert path.read_text(encoding="utf-8").endswith("# kept")
    screen.set_text("x")
    screen.select(path)  # loading a file discards the editor text
    assert not _dirty(screen)
    screen.clear()
    assert (screen.selected, screen.text, screen.result, screen.status) == (None, "", None, "idle")
    assert not _dirty(screen)


def test_scalars_keep_their_recorded_values(tmp_path: Path) -> None:
    record = {
        "status": "success",
        "error": None,
        "outputs": {},
        "scalars": {
            "method": {"value": "hrp", "tag": "in_sample"},
            "p": {"value": 0.25, "tag": "descriptive"},
        },
    }
    (tmp_path / "record.json").write_text(json.dumps(record), encoding="utf-8")
    assert load_result(tmp_path).scalars == (
        ("method", "hrp", "in_sample"),
        ("p", 0.25, "descriptive"),
    )
