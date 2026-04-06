"""
Registro central de eventos.

Los eventos NO viven aquí.
Los registran los plugins o proyectos.
"""

from __future__ import annotations

import re
from typing import Any

_registry = {}
_EVENT_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")


def register_event(event: dict[str, Any]):
    """
    Registra un evento con su schema.
    """
    _registry[event["type"]] = event


def get_event(event_type: str):
    return _registry.get(event_type)


def list_events() -> list[dict[str, Any]]:
    """Devuelve los contratos registrados actualmente."""
    return list(_registry.values())


def validate_event_contract(event: dict[str, Any]) -> list[str]:
    """Valida reglas mínimas de contrato para un evento."""
    errors: list[str] = []

    event_type = event.get("type")
    schema = event.get("payload_schema")

    if not event_type:
        errors.append("missing required key: type")
    elif not isinstance(event_type, str):
        errors.append("type must be a string")
    elif not _EVENT_TYPE_RE.match(event_type):
        errors.append(
            f"type '{event_type}' is invalid. Use dot notation and semantic suffix like 'orders.created.v1'"
        )

    if schema is None:
        errors.append("missing required key: payload_schema")
    elif not isinstance(schema, dict):
        errors.append("payload_schema must be an object")
    else:
        if schema.get("type") != "object":
            errors.append("payload_schema.type must be 'object'")
        required = schema.get("required")
        if required is not None and not isinstance(required, list):
            errors.append("payload_schema.required must be a list when provided")
        properties = schema.get("properties")
        if properties is not None and not isinstance(properties, dict):
            errors.append("payload_schema.properties must be an object when provided")

    return errors
