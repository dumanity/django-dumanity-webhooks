"""
Sistema desacoplado de handlers.
"""

_HANDLER_REGISTRY = {}

def register_handler(event_type):
    def decorator(func):
        _HANDLER_REGISTRY[event_type] = func
        return func
    return decorator

def get_handler(event_type):
    return _HANDLER_REGISTRY.get(event_type)