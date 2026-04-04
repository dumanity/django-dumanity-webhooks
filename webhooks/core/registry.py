"""
Registro central de eventos.

Los eventos NO viven aquí.
Los registran los plugins o proyectos.
"""

_registry = {}

def register_event(event: dict):
    """
    Registra un evento con su schema.
    """
    _registry[event["type"]] = event

def get_event(event_type: str):
    return _registry.get(event_type)