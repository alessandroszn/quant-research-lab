"""The public API is frozen in ``docs/api/public-api.txt`` (design note 6.3a)."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from types import ModuleType

import api_snapshot


def test_the_public_api_matches_the_committed_listing() -> None:
    expected = api_snapshot.SNAPSHOT.read_text(encoding="utf-8")
    actual = api_snapshot.listing()
    assert actual == expected, (
        "The public API changed. If the change is deliberate, regenerate the listing with "
        "`uv run python tests/api_snapshot.py --write` and review the diff in the PR."
    )


def test_public_modules_include_the_experiment_registry() -> None:
    names = [m.__name__ for m in api_snapshot.public_modules()]
    assert names == sorted(names)
    assert {"qrlab.core", "qrlab.experiments", "qrlab.experiments.kinds"} <= set(names)
    assert "qrlab.studies" not in names  # reproduced through its experiment kinds
    assert not any(name.split(".")[-1].startswith("_") for name in names)


def _fake_module() -> ModuleType:
    """Build a hand-made module with one object of every kind the listing knows."""
    module = ModuleType("qrlab.fake")

    class Colour(enum.Enum):
        RED = "red"
        BLUE = "blue"

    class BrokenError(Exception):
        pass

    @dataclass(frozen=True)
    class Point:
        x: float
        y: float = 0.0
        label: str = "p"

        @property
        def norm(self) -> float:
            return float((self.x**2 + self.y**2) ** 0.5)

        def scaled(self, factor: float) -> Point:
            return Point(self.x * factor, self.y * factor)

        @classmethod
        def origin(cls) -> Point:
            return cls(0.0)

        @staticmethod
        def parse(text: str) -> Point:
            return Point(float(text))

    def area(width: float, *, height: float = 1.0) -> float:
        return width * height

    for obj in (Colour, BrokenError, Point):
        obj.__module__ = "qrlab.fake"
    module.Colour = Colour  # type: ignore[attr-defined]
    module.BrokenError = BrokenError  # type: ignore[attr-defined]
    module.Point = Point  # type: ignore[attr-defined]
    module.area = area  # type: ignore[attr-defined]
    module.LIMIT = 3  # type: ignore[attr-defined]
    module.NAMES = ("a", "b")  # type: ignore[attr-defined]
    module.CHOICES = frozenset({"z", "y"})  # type: ignore[attr-defined]
    module.TABLE = {"a": 1}  # type: ignore[attr-defined]
    module.DEFAULT = Colour.RED  # type: ignore[attr-defined]
    module.json = enum  # type: ignore[attr-defined]  # a module re-exported by name
    module.__all__ = [  # type: ignore[attr-defined]
        "BrokenError",
        "CHOICES",
        "Colour",
        "DEFAULT",
        "LIMIT",
        "NAMES",
        "Point",
        "TABLE",
        "area",
        "json",
    ]
    return module


def test_listing_of_a_hand_made_module() -> None:
    assert api_snapshot.describe(_fake_module()) == [
        "qrlab.fake.BrokenError  exception(inherited)",
        "qrlab.fake.CHOICES  constant frozenset = ['y', 'z']",
        "qrlab.fake.Colour  enum",
        "qrlab.fake.Colour.RED  member = 'red'",
        "qrlab.fake.Colour.BLUE  member = 'blue'",
        "qrlab.fake.DEFAULT  constant Colour.RED",
        "qrlab.fake.LIMIT  constant int = 3",
        "qrlab.fake.NAMES  constant tuple = ['a', 'b']",
        "qrlab.fake.Point  class(x: 'float', y: 'float' = 0.0, label: 'str' = 'p') -> None",
        "qrlab.fake.Point.label  attribute str = 'p'",
        "qrlab.fake.Point.norm  property",
        "qrlab.fake.Point.origin  classmethod() -> 'Point'",
        "qrlab.fake.Point.parse  staticmethod(text: 'str') -> 'Point'",
        "qrlab.fake.Point.scaled  method(factor: 'float') -> 'Point'",
        "qrlab.fake.Point.y  attribute float = 0.0",
        "qrlab.fake.TABLE  constant dict",
        "qrlab.fake.area  function(width: 'float', *, height: 'float' = 1.0) -> 'float'",
        "qrlab.fake.json  module",
    ]


def test_a_signature_change_changes_the_listing() -> None:
    module = _fake_module()
    before = api_snapshot.listing([module])

    def area(width: float, *, height: float = 2.0) -> float:  # a new default
        return width * height

    module.area = area  # type: ignore[attr-defined]
    after = api_snapshot.listing([module])
    assert before != after
    assert after.startswith(api_snapshot.HEADER)
    assert "height: 'float' = 2.0" in after
