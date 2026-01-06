"""
Configuration Validator
-----------------------
Provides utilities for strict schema validation of configuration dictionaries against
defined Dataclasses.
"""

from dataclasses import fields, is_dataclass
from typing import Any, Dict, Set, Type, cast, get_type_hints


def validate_keys(
    raw_config: Dict[str, Any], data_class: Type[Any], path: str = ""
) -> None:
    """
    Recursively validates keys against a Dataclass schema.
    Uses get_type_hints() to resolve string annotations (Postponed Evaluation).
    """
    try:
        type_hints = get_type_hints(data_class)
    except Exception:
        type_hints = {f.name: f.type for f in fields(data_class)}

    allowed_fields: Set[str] = {f.name for f in fields(data_class)}
    unknown_keys = set(raw_config.keys()) - allowed_fields

    if unknown_keys:
        error_path = path if path else "root"
        raise ValueError(
            f"Config Error: Unknown keys detected at '{error_path}': {sorted(unknown_keys)}. "
            f"Allowed keys: {sorted(allowed_fields)}"
        )

    for field in fields(data_class):
        name = field.name
        value = raw_config.get(name)

        resolved_type = type_hints.get(name)

        if is_dataclass(resolved_type) and isinstance(value, dict):
            new_path = f"{path}.{name}" if path else name

            validate_keys(value, cast(Type[Any], resolved_type), path=new_path)
