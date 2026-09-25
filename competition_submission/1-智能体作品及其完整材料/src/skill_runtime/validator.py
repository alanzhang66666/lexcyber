from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import ValidationError as JsonSchemaValidationError

from skill_runtime.errors import SkillOutputInvalidError, SkillValidationError


def _normalize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    if not schema:
        return {"type": "object"}
    normalized = dict(schema)
    normalized.setdefault("type", "object")
    return normalized


def _format_error(exc: JsonSchemaValidationError) -> str:
    path = ".".join(str(part) for part in exc.absolute_path) or "<root>"
    return f"{path}: {exc.message}"


def validate_payload(schema: dict[str, Any] | None, payload: Any, *, output: bool = False) -> None:
    validator = Draft202012Validator(_normalize_schema(schema))
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if not errors:
        return
    details = "; ".join(_format_error(error) for error in errors[:8])
    if output:
        raise SkillOutputInvalidError(f"skill output failed schema validation: {details}")
    raise SkillValidationError(f"skill input failed schema validation: {details}")
