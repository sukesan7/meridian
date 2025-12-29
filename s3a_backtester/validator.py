"""
Configuration Validator
-----------------------
Provides utilities for strict schema validation of configuration dictionaries against
defined Dataclasses.

This module is critical for 'Fail-Fast' safety: it ensures that the application
crashes immediately upon startup if the user provides a configuration key that
does not exist in the code, preventing silent errors where parameters are ignored.
"""

from dataclasses import fields, is_dataclass
from typing import Dict, Type, Any, Set, cast


def validate_keys(
    raw_config: Dict[str, Any], data_class: Type[Any], path: str = ""
) -> None:
    """
    Recursively validates that all keys in a raw configuration dictionary exist
    as fields in the target Dataclass schema.

    This function performs a depth-first traversal of the configuration dictionary.
    If it encounters a key in the dictionary that is not defined in the corresponding
    Dataclass, it raises a ValueError immediately.

    Args:
        raw_config (Dict[str, Any]): The raw configuration dictionary (usually loaded from YAML).
        data_class (Type[Any]): The Dataclass type definition to validate against.
        path (str, optional): The dot-notation path to the current section (used for error messaging).
                              Defaults to "".

    Raises:
        ValueError: If 'raw_config' contains keys that are not present in 'data_class'.
    """
    allowed_fields: Set[str] = {f.name for f in fields(data_class)}

    unknown_keys = set(raw_config.keys()) - allowed_fields

    if unknown_keys:
        error_path = path if path else "root"
        raise ValueError(
            f"Config Error: Unknown keys detected at '{error_path}': {sorted(unknown_keys)}. "
            f"Allowed keys: {sorted(allowed_fields)}"
        )

    for field in fields(data_class):
        value = raw_config.get(field.name)

        if is_dataclass(field.type) and isinstance(value, dict):
            new_path = f"{path}.{field.name}" if path else field.name
            validate_keys(value, cast(Type[Any], field.type), path=new_path)
