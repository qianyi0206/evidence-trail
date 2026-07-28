from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_ANNOTATION_KEYS = {
    "$schema",
    "$id",
    "title",
    "description",
    "$defs",
    "default",
    "examples",
}
_SUPPORTED_ASSERTIONS = {
    "$ref",
    "type",
    "required",
    "properties",
    "additionalProperties",
    "minProperties",
    "minLength",
    "pattern",
    "enum",
    "const",
    "items",
    "minItems",
    "uniqueItems",
    "minimum",
}


def load_schema(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON Schema root must be an object: {path}")
    return payload


def _resolve_ref(root: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise RuntimeError(f"Only local JSON Schema references are supported: {ref}")
    value: Any = root
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            raise RuntimeError(f"Unresolvable JSON Schema reference: {ref}")
        value = value[token]
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON Schema reference does not target an object: {ref}")
    return value


def _matches_type(instance: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, dict)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "null":
        return instance is None
    raise RuntimeError(f"Unsupported JSON Schema type: {expected}")


def validate_instance(
    instance: Any,
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
    path: str = "$",
) -> list[str]:
    unknown = set(schema) - _ANNOTATION_KEYS - _SUPPORTED_ASSERTIONS
    if unknown:
        raise RuntimeError(
            f"Unsupported JSON Schema keyword(s) at {path}: {sorted(unknown)}"
        )
    if "$ref" in schema:
        return validate_instance(
            instance,
            _resolve_ref(root, str(schema["$ref"])),
            root=root,
            path=path,
        )
    errors: list[str] = []
    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_matches_type(instance, item) for item in expected_types):
            return [
                f"{path}: expected type {expected_types}, got {type(instance).__name__}"
            ]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} is not in enum")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        minimum = schema.get("minProperties")
        if minimum is not None and len(instance) < int(minimum):
            errors.append(f"{path}: has fewer than {minimum} properties")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                errors.extend(
                    validate_instance(
                        value,
                        child_schema,
                        root=root,
                        path=f"{path}.{key}",
                    )
                )
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key!r} is not allowed")

    if isinstance(instance, list):
        minimum = schema.get("minItems")
        if minimum is not None and len(instance) < int(minimum):
            errors.append(f"{path}: has fewer than {minimum} items")
        if schema.get("uniqueItems"):
            serialized = [
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in instance
            ]
            if len(serialized) != len(set(serialized)):
                errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                errors.extend(
                    validate_instance(
                        value,
                        item_schema,
                        root=root,
                        path=f"{path}[{index}]",
                    )
                )

    if isinstance(instance, str):
        minimum = schema.get("minLength")
        if minimum is not None and len(instance) < int(minimum):
            errors.append(f"{path}: string is shorter than {minimum}")
        pattern = schema.get("pattern")
        if pattern is not None and re.search(str(pattern), instance) is None:
            errors.append(f"{path}: string does not match pattern {pattern!r}")

    if (
        "minimum" in schema
        and isinstance(instance, (int, float))
        and not isinstance(instance, bool)
        and instance < schema["minimum"]
    ):
        errors.append(f"{path}: value is smaller than {schema['minimum']}")
    return errors


def validate_definition(
    records: list[dict[str, Any]],
    *,
    schema: dict[str, Any],
    definition: str,
    label: str,
) -> list[str]:
    definitions = schema.get("$defs", {})
    if definition not in definitions:
        raise RuntimeError(f"Schema lacks $defs/{definition}")
    errors: list[str] = []
    for index, record in enumerate(records, 1):
        errors.extend(
            f"{label} row {index} {message}"
            for message in validate_instance(
                record,
                definitions[definition],
                root=schema,
            )
        )
    return errors
