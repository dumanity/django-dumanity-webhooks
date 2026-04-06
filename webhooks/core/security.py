"""Security utilities for django-dumanity-webhooks."""

_SENSITIVE_HEADERS = frozenset(
    [
        "authorization",
        "webhook-signature",
        "x-api-key",
        "cookie",
        "set-cookie",
    ]
)

_REDACTED = "[REDACTED]"


def redact_headers(headers: dict) -> dict:
    """
    Retorna una copia del dict de headers con valores sensibles reemplazados.

    Redacta de forma determinista los headers que no deben persistirse en
    texto plano (credenciales, firmas, cookies).  La comparación es
    case-insensitive; los headers no sensibles se copian sin cambios.

    Headers redactados:
        - Authorization
        - Webhook-Signature
        - X-Api-Key
        - Cookie
        - Set-Cookie

    Args:
        headers: Mapping de nombre de header → valor.

    Returns:
        dict con los mismos keys pero valores sensibles reemplazados por
        la constante ``[REDACTED]``.

    Example:
        >>> redact_headers({"Authorization": "Bearer token", "Content-Type": "application/json"})
        {'Authorization': '[REDACTED]', 'Content-Type': 'application/json'}
    """
    return {
        key: _REDACTED if key.lower() in _SENSITIVE_HEADERS else value
        for key, value in headers.items()
    }
