"""Every kind's schema agrees with the registry and with what the kind accepts (design 12.1).

1. The schema's inputs and top-level parameters are exactly the registry's.
2. Every example config passes the schema check. (Every config of the kinds' own tests passes
   it too: ``validate_experiment`` runs the check after ``parse``.)
3. Removing any required key of an example config, at any level, fails the check and names
   the key.
"""

from __future__ import annotations

import copy
import tomllib
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from qrlab.core.errors import ValidationError
from qrlab.experiments.kinds import KINDS
from qrlab.experiments.registry import ExperimentKind
from qrlab.experiments.schema import Field, FieldKind, KindSchema, check_parameters

ROOT = Path(__file__).parents[3]
EXAMPLES = sorted([*(ROOT / "configs/experiments").glob("*.toml"),
                   *(ROOT / "configs/studies").glob("*.toml")])  # fmt: skip


def _with_schema() -> list[ExperimentKind]:
    return [kind for kind in KINDS.values() if kind.schema is not None]


def test_every_kind_has_a_schema() -> None:
    assert sorted(k.name for k in KINDS.values() if k.schema is None) == []


@pytest.mark.parametrize("kind", _with_schema(), ids=lambda k: k.name)
def test_the_schema_lists_the_registrys_keys(kind: ExperimentKind) -> None:
    schema = kind.schema
    assert schema is not None
    required = {i.name for i in schema.inputs if i.required}
    optional = {i.name for i in schema.inputs if not i.required and not i.group}
    groups = {i.name for i in schema.inputs if i.group}
    assert required == set(kind.inputs)
    assert optional == set(kind.optional_inputs)
    assert groups == set(kind.input_groups)
    assert {f.key for f in schema.parameters if f.required} == set(kind.parameters)
    assert {f.key for f in schema.parameters if not f.required} == set(kind.optional_parameters)


def _examples() -> Iterator[tuple[str, KindSchema, dict[str, object]]]:
    for path in EXAMPLES:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        kind = KINDS[raw["experiment"]["kind"]]
        if kind.schema is not None:
            yield path.name, kind.schema, raw.get("parameters", {})


EXAMPLE_CASES = list(_examples())


@pytest.mark.parametrize(("name", "schema", "parameters"), EXAMPLE_CASES, ids=lambda x: str(x)[:40])
def test_every_example_passes(name: str, schema: KindSchema, parameters: dict[str, object]) -> None:
    check_parameters(schema, parameters)


def _required_paths(
    fields: tuple[Field, ...], value: Mapping[str, object], path: tuple[object, ...]
) -> Iterator[tuple[object, ...]]:
    """Yield the path of every required key present in ``value``, at every level."""
    for spec in fields:
        if spec.key not in value:
            continue
        here = (*path, spec.key)
        if spec.required:
            yield here
        yield from _inner_paths(spec, value[spec.key], here)


def _inner_paths(
    spec: Field, value: object, path: tuple[object, ...]
) -> Iterator[tuple[object, ...]]:
    if spec.kind is FieldKind.TABLE and isinstance(value, Mapping):
        yield from _required_paths(spec.fields, value, path)
    elif spec.kind is FieldKind.RECORDS and isinstance(value, list):
        for index, record in enumerate(value):
            yield from _required_paths(spec.fields, record, (*path, index))
    elif spec.kind is FieldKind.MAP and isinstance(value, Mapping):
        assert spec.item is not None
        for key, item in value.items():
            yield from _inner_paths(spec.item, item, (*path, key))
    elif spec.kind is FieldKind.VARIANT and isinstance(value, Mapping):
        assert spec.selector is not None
        yield (*path, spec.selector)
        yield from _required_paths(spec.variants[str(value[spec.selector])], value, path)


def _without(parameters: dict[str, object], path: tuple[object, ...]) -> dict[str, object]:
    copied = copy.deepcopy(parameters)
    node: object = copied
    for step in path[:-1]:
        node = node[step]  # type: ignore[index]
    del node[path[-1]]  # type: ignore[attr-defined]
    return copied


@pytest.mark.parametrize(("name", "schema", "parameters"), EXAMPLE_CASES, ids=lambda x: str(x)[:40])
def test_removing_a_required_key_fails(
    name: str, schema: KindSchema, parameters: dict[str, object]
) -> None:
    paths = list(_required_paths(schema.parameters, parameters, ()))
    assert paths
    for path in paths:
        with pytest.raises(ValidationError, match=str(path[-1])):
            check_parameters(schema, _without(parameters, path))
