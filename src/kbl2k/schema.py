"""패키지에 포함된 JSON Schema 로드 및 검증."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .issues import Issue, error

SCHEMA_NAMES = (
    "common",
    "attributes",
    "player",
    "team",
    "sources",
    "asset_mapping",
    "rating_rules",
    "league_stats",
)


@cache
def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"알 수 없는 스키마: {name}")
    text = resources.files("kbl2k.schemas").joinpath(f"{name}.schema.json").read_text("utf-8")
    return json.loads(text)


@cache
def _registry() -> Registry:
    pairs = []
    for name in SCHEMA_NAMES:
        doc = load_schema(name)
        pairs.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(pairs)


@cache
def validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())


def attribute_names() -> tuple[str, ...]:
    """스키마에 정의된 2K26 능력치 이름(정의 순서 유지)."""
    return tuple(load_schema("attributes")["$defs"]["attribute_name"]["enum"])


def json_path(parts) -> str:
    out = "$"
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def schema_issues(name: str, instance: Any, file: str) -> list[Issue]:
    errors = sorted(validator(name).iter_errors(instance), key=lambda e: list(map(str, e.path)))
    return [error(file, json_path(e.absolute_path), e.message) for e in errors]
