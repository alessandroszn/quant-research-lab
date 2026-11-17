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
    RECORD_FORMAT,
    STAGING_SUFFIX,
    RunResult,
    configurations_tried,
    count_trials,
    run_experiment,
    staging_dir,
    validate_experiment,
)
from qrlab.experiments.schema import (
    Field,
    FieldKind,
    Help,
    InputSpec,
    KindSchema,
    check_parameters,
)

__all__ = [
    "RECORD_FORMAT",
    "STAGING_SUFFIX",
    "TAGS",
    "ExperimentConfig",
    "ExperimentKind",
    "ExperimentOutput",
    "Field",
    "FieldKind",
    "Help",
    "InputSpec",
    "KindSchema",
    "RunContext",
    "RunResult",
    "Tagged",
    "check_parameters",
    "config_hash",
    "configurations_tried",
    "count_trials",
    "file_sha256",
    "load_config",
    "require_keys",
    "run_experiment",
    "staging_dir",
    "validate_experiment",
]
