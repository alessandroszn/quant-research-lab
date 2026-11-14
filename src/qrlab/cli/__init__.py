"""Command line: ``qrlab run``, ``qrlab validate`` and ``qrlab kinds``.

Exit codes: 0 success; 2 config or input error (nothing run); 1 run failure (the record is
still written). The CLI only parses arguments and calls :mod:`qrlab.experiments`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from qrlab.core.errors import QrlabError
from qrlab.experiments import ExperimentKind, run_experiment, validate_experiment
from qrlab.experiments.kinds import KINDS

__all__ = ["main", "main_entry"]

OK, RUN_FAILED, CONFIG_ERROR = 0, 1, 2


def main(
    argv: Sequence[str] | None = None, *, kinds: Mapping[str, ExperimentKind] | None = None
) -> int:
    """Run the command line; return the exit code."""
    registry = KINDS if kinds is None else kinds
    parser = argparse.ArgumentParser(prog="qrlab", description="Quant Research Lab experiments")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run an experiment config")
    run.add_argument("config", type=Path)
    run.add_argument("--overwrite", action="store_true", help="replace an existing output folder")
    check = commands.add_parser("validate", help="check a config and its inputs without running")
    check.add_argument("config", type=Path)
    commands.add_parser("kinds", help="list the experiment kinds")
    args = parser.parse_args(argv)

    if args.command == "kinds":
        for kind in sorted(registry.values(), key=lambda k: k.name):
            print(f"{kind.name}: {kind.description}")
            print(f"  inputs: {', '.join(kind.inputs) or 'none'}")
            if kind.optional_inputs:
                print(f"  optional inputs: {', '.join(kind.optional_inputs)}")
            print(f"  parameters: {', '.join(kind.parameters)}")
            print(f"  seed: {'required' if kind.needs_seed else 'not used'}")
        return OK
    try:
        if args.command == "validate":
            config, kind, _ = validate_experiment(args.config, kinds=registry)
            print(f"valid: {config.name} ({kind.name}), config sha256 {config.hash}")
            return OK
        result = run_experiment(args.config, kinds=registry, overwrite=args.overwrite)
    except QrlabError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return CONFIG_ERROR
    record = result.record
    print(f"output: {result.output_dir}")
    print(f"status: {record['status']}; configurations tried: {record['configurations_tried']}")
    if record.get("notice"):
        print(f"notice: {record['notice']}")
    if not result.succeeded:
        print(f"error: {record['error']}", file=sys.stderr)
        return RUN_FAILED
    return OK


def main_entry() -> None:  # pragma: no cover - exercised by the installed-script test
    """Console-script entry point: exit with :func:`main`'s code."""
    raise SystemExit(main())
