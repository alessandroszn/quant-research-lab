"""Every user-visible string, by language (English now; Italian in phase 6.1c)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

__all__ = ["LANGUAGES", "STRINGS", "tr"]

LANGUAGES = ("en",)

STRINGS: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "en": MappingProxyType(
            {
                "app.title": "Quant Research Lab",
                "app.disclaimer": (
                    "Research analytics, not investment advice. Every number comes from the "
                    "qrlab library through the same runner as the command line."
                ),
                "nav.home": "Home",
                "nav.portfolio": "Portfolio",
                "nav.projections": "Projections",
                "nav.backtests": "Backtests & studies",
                "nav.data": "Data",
                "nav.history": "History",
                "home.open": "Open workspace…",
                "home.create": "Create workspace…",
                "home.none": "No workspace open.",
                "home.current": "Workspace: {path}",
                "screen.configs": "Configs",
                "screen.new": "New from template",
                "screen.duplicate": "Duplicate",
                "screen.refresh": "Refresh",
                "screen.save": "Save",
                "screen.validate": "Validate",
                "screen.run": "Run",
                "screen.open_report": "Open report",
                "screen.open_folder": "Open folder",
                "screen.no_workspace": "Open a workspace first (Home).",
                "screen.new_name": "File name for the new config (without .toml):",
                "screen.kind": "Kind of the new config:",
                "screen.overwrite": "{name} already has outputs from an earlier run. Replace them?",
                "screen.running": "Running… {seconds} s",
                "screen.done": "Finished: {status}.",
                "screen.failed": "Failed: {error}",
                "screen.valid": "Valid: {name} ({kind}).",
                "screen.invalid": "Not valid: {error}",
                "screen.busy": "Another run is in progress.",
                "results.scalars": "Scalars",
                "results.figures": "Figures",
                "data.columns": "Source|Dataset|Retrieved|Age (days)|Latest|Bytes|SHA-256|Terms",
                "history.columns": "Finished|Name|Kind|Status|Configurations|Folder|Error",
                "history.open": "Open folder",
            }
        )
    }
)


def tr(key: str, language: str, **values: object) -> str:
    """Return the string ``key`` in ``language`` with ``{placeholders}`` filled in."""
    if language not in STRINGS:
        raise KeyError(f"unsupported language {language!r}; supported: {list(STRINGS)}")
    return STRINGS[language][key].format(**values)
