"""Cliente HTTP de envío de webhooks con firma HMAC y trazabilidad OpenTelemetry.

Utiliza ``httpx`` para transporte HTTP sincrónico (reemplaza ``requests`` en v2.0.0).
La inyección de ``X-Trace-Id`` vía OpenTelemetry es un no-op silencioso si la
librería no está instalada — no se requiere ninguna configuración adicional.

Upgrade desde v1.x
------------------
El módulo mantiene la misma firma pública de ``send()``, por lo que no hay
cambios necesarios en el código consumidor.  Solo hay que actualizar los
patches en tests de ``webhooks.producer.sender.requests.post``
a ``webhooks.producer.sender.httpx.post``.
"""

from __future__ import annotations

import json
import time

import httpx

from webhooks.core.signing import sign


def _otel_trace_id() -> str | None:
    """Devuelve el trace ID de OpenTelemetry activo, o ``None`` si no está disponible.

    Implementa el patrón "optional dependency as a no-op": si ``opentelemetry``
    no está instalado o no hay span activo, simplemente retorna None sin lanzar
    excepción ni registrar ningún warning.
    """
    try:
        from opentelemetry import trace  # type: ignore[import]

        ctx = trace.get_current_span().get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


def send(
    endpoint,
    payload: dict,
    extra_headers: dict | None = None,
    timeout_override: float | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
) -> httpx.Response:
    """Envía un webhook firmado con HMAC-SHA256 y trazabilidad completa.

    Firma el body con el secret del endpoint usando el esquema ``t=<ts>,v1=<digest>``
    compatible con el verificador multi-secret del receiver.  Inyecta
    automáticamente ``X-Trace-Id`` si OpenTelemetry está activo en el proceso.

    Args:
        endpoint:         Instancia de ``WebhookEndpoint`` con los campos
                          ``url``, ``secret`` y ``request_timeout_seconds``.
        payload:          Diccionario del evento.  Debe contener al menos ``"id"``.
        extra_headers:    Headers adicionales que se fusionan sobre los generados
                          (tienen prioridad en caso de colisión de nombre).
        timeout_override: Timeout en segundos.  Si se omite usa
                          ``endpoint.request_timeout_seconds``.
        correlation_id:   Valor para ``X-Correlation-ID``.  Si es ``None``,
                          intenta resolverlo desde ``payload["meta"]["correlation_id"]``.
        request_id:       Valor para ``X-Request-ID``.  Si es ``None``, intenta
                          resolverlo desde ``payload["meta"]["request_id"]``.

    Returns:
        ``httpx.Response`` de la petición POST.

    Raises:
        httpx.HTTPError: Error de transporte propagado al caller para que gestione
                         la política de reintentos (``process_outgoing``).

    Example::

        from webhooks.producer.sender import send

        response = send(endpoint, payload, correlation_id="req-001")
        assert response.status_code == 200
    """
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    signature = sign(endpoint.secret, ts, body)

    meta = payload.get("meta") or {}
    resolved_correlation_id = correlation_id or meta.get("correlation_id")
    resolved_request_id = request_id or meta.get("request_id")

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Webhook-Signature": signature,
        "X-Event-ID": str(payload["id"]),
    }

    if resolved_correlation_id:
        headers["X-Correlation-ID"] = str(resolved_correlation_id)

    if resolved_request_id:
        headers["X-Request-ID"] = str(resolved_request_id)

    # Inyección automática de X-Trace-Id vía OpenTelemetry (no-op si no está instalado)
    trace_id = _otel_trace_id()
    if trace_id:
        headers["X-Trace-Id"] = trace_id

    if extra_headers:
        headers.update(extra_headers)

    return httpx.post(
        endpoint.url,
        content=body,
        headers=headers,
        # Usamos `is not None` (no `or`) para respetar timeout_override=0 como valor
        # explícito válido (ej. en tests de integración sin timeout real).
        timeout=timeout_override if timeout_override is not None else endpoint.request_timeout_seconds,
    )