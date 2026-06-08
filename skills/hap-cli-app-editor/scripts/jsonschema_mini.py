"""A tiny stdlib JSON-Schema (draft-07 subset) validator.

The skill is stdlib-only, so instead of depending on ``jsonschema`` we
ship a small validator covering exactly the keywords our edit-spec
schemas use: ``type``, ``properties``, ``required``,
``additionalProperties`` (bool), ``items``, ``enum``, ``const``,
``pattern``, ``minLength``, ``minItems``, ``minimum``/``maximum``,
``oneOf``, ``anyOf``, ``allOf``, and internal ``$ref`` (``#/$defs/...``).

``validate(instance, schema, base_path)`` returns a list of problem
strings, each prefixed with the JSON path where it occurred. An empty
list means the instance conforms.
"""
from __future__ import annotations

import re
from typing import Any

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    # bool is a subclass of int — exclude it from integer/number.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class _Validator:
    def __init__(self, root: dict[str, Any]):
        self.root = root

    def _resolve_ref(self, ref: str) -> dict[str, Any]:
        if not ref.startswith("#/"):
            raise ValueError(f"unsupported $ref (only internal refs): {ref!r}")
        node: Any = self.root
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            node = node[part]
        return node

    def _matches(self, instance: Any, schema: dict[str, Any]) -> bool:
        errs: list[str] = []
        self.check(instance, schema, "", errs)
        return not errs

    def check(self, instance: Any, schema: dict[str, Any], path: str,
              errors: list[str]) -> None:
        if "$ref" in schema:
            self.check(instance, self._resolve_ref(schema["$ref"]), path, errors)
            return

        t = schema.get("type")
        if t is not None:
            types = t if isinstance(t, list) else [t]
            if not any(_TYPE_CHECKS.get(tt, lambda v: True)(instance) for tt in types):
                errors.append(f"{path or '<root>'}: expected type {t}, "
                              f"got {type(instance).__name__}")
                return  # further checks assume the right type

        if "const" in schema and instance != schema["const"]:
            errors.append(f"{path or '<root>'}: must equal {schema['const']!r}")
        if "enum" in schema and instance not in schema["enum"]:
            errors.append(f"{path or '<root>'}: {instance!r} not in {schema['enum']}")

        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                errors.append(f"{path or '<root>'}: shorter than "
                              f"minLength {schema['minLength']}")
            pat = schema.get("pattern")
            if pat and not re.search(pat, instance):
                errors.append(f"{path or '<root>'}: does not match /{pat}/")

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in schema and instance < schema["minimum"]:
                errors.append(f"{path or '<root>'}: < minimum {schema['minimum']}")
            if "maximum" in schema and instance > schema["maximum"]:
                errors.append(f"{path or '<root>'}: > maximum {schema['maximum']}")

        if isinstance(instance, list):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                errors.append(f"{path or '<root>'}: fewer than "
                              f"minItems {schema['minItems']}")
            items = schema.get("items")
            if isinstance(items, dict):
                for i, item in enumerate(instance):
                    self.check(item, items, f"{path}[{i}]", errors)

        if isinstance(instance, dict):
            props = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in instance:
                    errors.append(f"{path or '<root>'}: missing required '{key}'")
            for key, val in instance.items():
                sub = f"{path}.{key}" if path else key
                if key in props:
                    self.check(val, props[key], sub, errors)
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{sub}: unexpected property "
                                  f"(additionalProperties is false)")

        for combiner in ("allOf",):
            for sub in schema.get(combiner, []):
                self.check(instance, sub, path, errors)
        if "oneOf" in schema:
            n = sum(1 for sub in schema["oneOf"] if self._matches(instance, sub))
            if n != 1:
                errors.append(f"{path or '<root>'}: matched {n} of oneOf "
                              f"branches (expected exactly 1)")
        if "anyOf" in schema:
            if not any(self._matches(instance, sub) for sub in schema["anyOf"]):
                errors.append(f"{path or '<root>'}: matched none of anyOf branches")


def validate(instance: Any, schema: dict[str, Any], base_path: str = "") -> list[str]:
    """Validate ``instance`` against ``schema``; return problem strings."""
    v = _Validator(schema)
    errors: list[str] = []
    v.check(instance, schema, base_path, errors)
    return errors


def validate_against(instance: Any, sub_schema: dict[str, Any],
                     root: dict[str, Any], base_path: str = "") -> list[str]:
    """Validate against ``sub_schema`` while resolving ``$ref`` against ``root``.

    Used to validate an op directly against the one verb branch it should
    match (precise errors) while that branch's internal ``$ref``s still
    resolve against the whole module schema.
    """
    v = _Validator(root)
    errors: list[str] = []
    v.check(instance, sub_schema, base_path, errors)
    return errors
