"""Config-driven experiments: the single entry point for scripts, the CLI and the app."""

from qrlab.experiments.config import (
    ExperimentConfig,
    config_hash,
    file_sha256,
    load_config,
    require_keys,
)
from qrlab.experiments.registry import (
    TAGS,
    ExperimentKind,
    ExperimentOutput,
    RunContext,
    Tagged,
)
from qrlab.experiments.runner import (
    RunResult,
    configurations_tried,
    count_trials,
    run_experiment,
    validate_experiment,
)

__all__ = [
    "TAGS",
    "ExperimentConfig",
    "ExperimentKind",
    "ExperimentOutput",
    "RunContext",
    "RunResult",
    "Tagged",
    "config_hash",
    "configurations_tried",
    "count_trials",
    "file_sha256",
    "load_config",
    "require_keys",
    "run_experiment",
    "validate_experiment",
]
