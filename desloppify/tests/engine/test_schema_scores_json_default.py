"""Tests for json_default serializer fallback.

The dataclass handler was added after @0-CYBERDYNE-SYSTEMS-0 reported in PR #486
that EcosystemFrameworkDetection instances crash serialization when they leak into
review_cache via shared dict references.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path, PurePosixPath

import pytest

from desloppify.engine._state.schema_scores import json_default


@dataclasses.dataclass
class _SampleDataclass:
    name: str
    path: Path
    count: int = 0


def test_json_default_handles_dataclass_with_path():
    """Dataclass containing a Path field serializes cleanly."""
    obj = _SampleDataclass(name="test", path=Path("/tmp/foo"), count=3)
    result = json.loads(json.dumps(obj, default=json_default))
    assert result == {"name": "test", "path": "/tmp/foo", "count": 3}


def test_json_default_handles_nested_dataclass():
    """Nested dataclass with Path fields serializes recursively."""

    @dataclasses.dataclass
    class _Inner:
        value: Path

    @dataclasses.dataclass
    class _Outer:
        inner: _Inner
        label: str

    obj = _Outer(inner=_Inner(value=Path("/a/b")), label="x")
    result = json.loads(json.dumps(obj, default=json_default))
    assert result == {"inner": {"value": "/a/b"}, "label": "x"}


def test_json_default_still_raises_on_unknown_types():
    """Types we don't handle should still raise TypeError."""
    with pytest.raises(TypeError, match="not JSON serializable"):
        json_default(object())


def test_json_default_handles_set():
    result = json_default({3, 1, 2})
    assert result == [1, 2, 3]


def test_json_default_handles_path():
    result = json_default(Path("/foo/bar"))
    assert result == "/foo/bar"
