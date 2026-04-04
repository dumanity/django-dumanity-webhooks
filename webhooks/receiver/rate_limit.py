"""
Rate limiting simple por buckets temporales usando cache Django.

Implementa rate limiting por bucket temporal (ventana deslizante).
Es rápido y suficiente para uso single-server. Para distribuido, mirar Redis.
"""

from django.core.cache import cache
import time


def is_rate_limited(integration_id, limit=100, window=60):
    """
    Valida si una integración ha excedido el límite de requests.
    
    Usa cache Django para mantener contadores por bucket temporal.
    Cada bucket cubre `window` segundos. Es una implementación simple
    y rápida, adecuada para operación local/single-instance.
    
    Args:
        integration_id: UUID de la Integration (no nombre, para determinismo).
        limit: Máximo de requests permitidos en la ventana (default: 100).
        window: Duración de la ventana en segundos (default: 60).
    
    Returns:
        bool: True si el límite fue excedido, False si está dentro de límite.
    
    Algorithm:
        1. Calcula bucket = "{integration_id}:{current_second // window}"
        2. Obtiene contador actual del bucket desde cache
        3. Si contador >= limit, retorna True (limitado)
        4. Incrementa contador, lo guarda con TTL=window
        5. Retorna False (no limitado)
    
    Example:
        >>> from webhooks.receiver.models import Integration
        >>> integration = Integration.objects.first()
        >>> if is_rate_limited(integration.id, limit=100, window=60):
        ...     return Response({"detail": "rate limited"}, status=429)
    
    Limitations:
        - No es distribuido: cada instancia tiene su propio cache
        - Para multi-worker, usar Redis o servicio externo
    """
    now = int(time.time())
    bucket = f"{integration_id}:{now // window}"

    count = cache.get(bucket, 0)

    if count >= limit:
        return True

    cache.set(bucket, count + 1, timeout=window)
    return False
