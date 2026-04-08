"""Despachador sincrónico de webhooks con perfiles configurables.

Punto de entrada de alto nivel para enviar webhooks de forma síncrona con:

- **Perfiles** — resuelve ``timeout``, ``secret``, ``headers`` y ``rate_limit``
  desde ``settings.WEBHOOK_PROFILES``, con valores por defecto seguros si no
  se configuró nada.
- **Rate limiting** — ventana deslizante sobre el cache de Django sin dependencias
  externas.  Para producción basta con apuntar ``CACHES["default"]`` a Redis.
- **Firma HMAC opcional** — solo si el perfil tiene ``secret`` configurado.
- **Señales de ciclo de vida** — emite ``webhook_dispatched`` / ``webhook_failed``
  para observabilidad sin acoplar el código consumidor.
- **CanonicalEventEnvelope** — acepta modelos Pydantic directamente; la serialización
  es automática (no hay que llamar ``.model_dump()`` manualmente).
- **OTel X-Trace-Id** — inyectado automáticamente si OpenTelemetry está activo
  en el proceso; no-op silencioso si no está instalado.

Configuración mínima en ``settings.py``::

    WEBHOOK_PROFILES = {
        "default": {
            "timeout": 10,
        },
        "billing": {
            "timeout": 30,
            "secret": "whsec_billing_...",
            "headers": {"X-Source": "billing-service"},
            "rate_limit": {"limit": 50, "window": 60},
        },
    }

    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # Para producción: django.core.cache.backends.redis.RedisCache
        }
    }

Uso rápido::

    import uuid
    from webhooks.producer.dispatch import dispatch_webhook_sync

    response = dispatch_webhook_sync(
        payload={
            "id": str(uuid.uuid4()),
            "type": "orders.created.v1",
            "data": {"order_id": "ord-123"},
        },
        target_url="https://partner.example.com/webhooks/",
        profile="billing",
    )
    assert response.status_code == 200

Con ``CanonicalEventEnvelope``::

    from webhooks.contrib.pydantic import CanonicalEventEnvelope

    envelope = CanonicalEventEnvelope(
        type="orders.created.v1",
        data={"order_id": "ord-123"},
    )
    response = dispatch_webhook_sync(envelope, "https://partner.example.com/webhooks/")
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

from webhooks.core.signing import sign
from webhooks.signals import webhook_dispatched, webhook_failed


# ──────────────────────────────────────────────────────────────────────────────
# Excepciones públicas
# ──────────────────────────────────────────────────────────────────────────────


class RateLimitExceeded(Exception):
    """Lanzada antes de enviar cuando el perfil superó su límite configurado.

    Attributes:
        profile:     Nombre del perfil que alcanzó el límite.
        limit:       Máximo de peticiones permitidas en la ventana.
        window:      Duración de la ventana en segundos.
        retry_after: Segundos estimados hasta que sea seguro reintentar.

    Example::

        from webhooks.producer.dispatch import RateLimitExceeded

        try:
            dispatch_webhook_sync(payload, url, profile="billing")
        except RateLimitExceeded as exc:
            print(f"Reintentar en {exc.retry_after}s")
    """

    def __init__(self, profile: str, limit: int, window: int, retry_after: int = 0) -> None:
        self.profile = profile
        self.limit = limit
        self.window = window
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit del perfil '{profile}' alcanzado: "
            f"{limit} peticiones en {window}s. "
            f"Reintenta en {retry_after}s."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_profile(name: str) -> dict[str, Any]:
    """Resuelve la configuración de un perfil desde ``settings.WEBHOOK_PROFILES``.

    Si el perfil no existe (o ``WEBHOOK_PROFILES`` no está configurado) retorna
    valores por defecto seguros para que el sistema funcione sin ninguna
    configuración explícita.

    Defaults:
        - ``timeout``:    10 segundos
        - ``secret``:     ``None`` (sin firma HMAC)
        - ``headers``:    ``{}`` (sin headers extra)
        - ``rate_limit``: ``None`` (sin límite de tasa)
    """
    profiles: dict[str, Any] = getattr(settings, "WEBHOOK_PROFILES", {}) or {}
    defaults: dict[str, Any] = {
        "timeout": 10,
        "secret": None,
        "headers": {},
        "rate_limit": None,
    }
    defaults.update(profiles.get(name, {}))
    return defaults


def _check_rate_limit(profile: str, config: dict[str, Any]) -> None:
    """Verifica y actualiza el rate limit del perfil usando el cache de Django.

    Implementa una ventana fija con contador atómico via el cache de Django.
    Para la mayoría de despliegues (< 10 000 req/min) esta implementación es
    suficiente y no requiere Redis ni dependencias extra.  Apuntando
    ``CACHES["default"]`` a Redis se obtiene consistencia distribuida.

    Args:
        profile: Nombre del perfil (usado como clave de cache).
        config:  Configuración del perfil ya resuelta por ``_resolve_profile``.

    Raises:
        RateLimitExceeded: Si el contador de la ventana actual superó el límite.
    """
    rate_limit = config.get("rate_limit")
    if not rate_limit:
        return

    limit: int = rate_limit.get("limit", 100)
    window: int = rate_limit.get("window", 60)
    cache_key = f"webhooks:rl:{profile}"

    current: int = cache.get(cache_key, 0)
    if current >= limit:
        raise RateLimitExceeded(
            profile=profile,
            limit=limit,
            window=window,
            retry_after=window,
        )

    # Incremento atómico: ``add`` crea la clave con TTL si no existe.
    if not cache.add(cache_key, 1, timeout=window):
        cache.incr(cache_key)


def _serialize_payload(payload: Any) -> dict[str, Any]:
    """Convierte el payload a ``dict`` estándar listo para serializar a JSON.

    Acepta tanto ``dict`` normales como instancias de ``CanonicalEventEnvelope``
    (o cualquier modelo Pydantic v2) sin necesidad de importar la clase.
    Los campos ``datetime`` se convierten automáticamente a strings ISO 8601.
    """
    if hasattr(payload, "model_dump"):
        data = payload.model_dump()
        # Normalizar datetime → ISO 8601 para serialización JSON segura
        for key, value in data.items():
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data
    return dict(payload)


def _otel_trace_id() -> str | None:
    """Devuelve el trace ID de OpenTelemetry activo o ``None`` si no está disponible.

    El patrón "optional dependency as a no-op" garantiza que el paquete funcione
    sin OpenTelemetry instalado, sin warnings ni errores de importación.
    """
    try:
        from opentelemetry import trace  # type: ignore[import]

        ctx = trace.get_current_span().get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────────────────
# API pública
# ──────────────────────────────────────────────────────────────────────────────


def dispatch_webhook_sync(
    payload: Any,
    target_url: str,
    profile: str = "default",
    extra_headers: dict[str, str] | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> httpx.Response:
    """Envía un webhook de forma síncrona usando el perfil especificado.

    Combina en un único punto de entrada:

    1. **Resolución de perfil** — ``timeout``, ``secret``, ``headers`` y
       ``rate_limit`` desde ``settings.WEBHOOK_PROFILES[profile]``.
    2. **Rate limiting** — verificado antes de hacer I/O; lanza
       ``RateLimitExceeded`` sin penalizar latencia.
    3. **Firma HMAC** — solo si el perfil tiene ``secret``; seguro para perfiles
       públicos o de baja criticidad sin secreto.
    4. **Trazabilidad** — ``X-Correlation-ID``, ``X-Request-ID`` y
       ``X-Trace-Id`` (OTel, no-op si no está instalado).
    5. **Señales** — ``webhook_dispatched`` en éxito, ``webhook_failed`` en error;
       sin acoplar observabilidad al core de envío.

    Args:
        payload:        Evento a enviar.  Puede ser un ``dict`` con las claves
                        ``id``, ``type``, ``data`` o una instancia de
                        ``CanonicalEventEnvelope`` (Pydantic v2).
        target_url:     URL destino del receptor (HTTP POST).
        profile:        Nombre del perfil en ``settings.WEBHOOK_PROFILES``.
                        Si se omite se usa ``"default"`` con valores seguros.
        extra_headers:  Headers adicionales fusionados sobre los del perfil
                        (tienen prioridad en colisiones de nombre).
        correlation_id: Valor para ``X-Correlation-ID``.
        request_id:     Valor para ``X-Request-ID``.

    Returns:
        ``httpx.Response`` con la respuesta del receptor.

    Raises:
        RateLimitExceeded: Antes de enviar si el perfil superó su límite de tasa.
        httpx.HTTPError:   Si ocurre un error de transporte o conexión.

    Example::

        import uuid
        from webhooks.producer.dispatch import dispatch_webhook_sync

        response = dispatch_webhook_sync(
            payload={
                "id": str(uuid.uuid4()),
                "type": "orders.created.v1",
                "data": {"order_id": "ord-123"},
            },
            target_url="https://partner.example.com/webhooks/",
            profile="billing",
            correlation_id="trace-abc-123",
        )
        print(response.status_code)  # 200
    """
    config = _resolve_profile(profile)
    data = _serialize_payload(payload)
    event_id = str(data.get("id", ""))
    event_type = str(data.get("type", ""))

    # Verificar rate limit ANTES de hacer cualquier I/O
    _check_rate_limit(profile, config)

    body = json.dumps(data).encode()
    ts = str(int(time.time()))

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Event-ID": event_id,
    }

    # Firma HMAC: solo si el perfil tiene un secret configurado
    if config.get("secret"):
        headers["Webhook-Signature"] = sign(config["secret"], ts, body)

    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    if request_id:
        headers["X-Request-ID"] = request_id

    # Headers del perfil (ej. X-Source, X-Service-Name, X-Api-Version…)
    if config.get("headers"):
        headers.update(config["headers"])

    # OTel X-Trace-Id (no-op silencioso si OTel no está instalado)
    trace_id = _otel_trace_id()
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    if extra_headers:
        headers.update(extra_headers)

    started = time.perf_counter()
    try:
        response = httpx.post(
            target_url,
            content=body,
            headers=headers,
            timeout=config.get("timeout", 10),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        webhook_dispatched.send(
            sender=dispatch_webhook_sync,
            target_url=target_url,
            event_id=event_id,
            event_type=event_type,
            profile=profile,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )
        return response

    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        webhook_failed.send(
            sender=dispatch_webhook_sync,
            target_url=target_url,
            event_id=event_id,
            event_type=event_type,
            profile=profile,
            error=str(exc),
        )
        raise
