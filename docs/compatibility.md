# Compatibility policy

From version 1.0.0, Quant Research Lab follows [Semantic Versioning](https://semver.org/):
`MAJOR.MINOR.PATCH`. This page says what that promise covers.

## What is public

The public API is exactly:

- every name listed in the `__all__` of a `qrlab` subpackage, such as `qrlab.core`,
  `qrlab.metrics` or `qrlab.experiments`;
- `qrlab.experiments.kinds` (the `KINDS` registry that `run_experiment` needs) and
  `qrlab.experiments.workspace`;
- the `qrlab` command line: its commands, options and exit codes;
- the config format of every experiment kind: its keys, their meaning and their units;
- the layout of `record.json`, versioned by its `format` field (`RECORD_FORMAT`, now 1).

The complete list of public names and signatures is in
[`docs/api/public-api.txt`](api/public-api.txt). A test compares it with the code, so any change
to the public surface is visible and deliberate in review.

## What is not public

These can change in any release:

- anything whose module or name starts with `_`;
- the study modules in `qrlab.studies`. The studies are reproduced through their experiment
  kinds and configs, which are public.
- the desktop app `qrlab_app`, the build scripts in `packaging/` and everything in
  `research/`;
- the exact text of error messages and reports. The exception classes are public; their wording
  is not.

## What each kind of release may change

| Release | May change |
|---|---|
| Patch (1.0.x) | Bug fixes and documentation. Results may change only to correct a bug, and the CHANGELOG says which results and why. |
| Minor (1.x.0) | Everything a patch may change, plus new functions, classes, parameters with defaults, experiment kinds, optional config keys and new fields in `record.json`. Nothing public is removed or changes meaning. |
| Major (x.0.0) | Removals, renames, changed signatures or meanings, and new required config keys. A new `record.json` layout raises `RECORD_FORMAT`. |

## Deprecation

A public name, parameter or config key is removed only in a major release, after at least one
minor release in which using it raises a `DeprecationWarning` that names the replacement. The
CHANGELOG lists every deprecation.

## Reproducibility across versions

Every run record stores the qrlab version, the commit and the versions of NumPy, pandas, SciPy,
statsmodels and Matplotlib. Re-running a config with the same versions gives the same outputs.
A bug fix that changes results is always listed in the CHANGELOG.
