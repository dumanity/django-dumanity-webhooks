"""
Servicio de publicación de eventos (patrón Outbox).

Este módulo implementa la publicación desacoplada de webhooks sin bloqueos de red.
Los eventos se guardan en OutgoingEvent y se procesan de forma asíncrona por un worker.
"""

import time
import uuid

from django.utils.timezone import now
from django.db import transaction

from .sender import send


def _normalize_trace_context(payload, correlation_id=None, request_id=None):
    """Devuelve una copia del payload con meta de trazabilidad normalizada."""
    event_payload = dict(payload)
    meta = dict(event_payload.get("meta") or {})

    resolved_correlation_id = correlation_id or meta.get("correlation_id")
    resolved_request_id = request_id or meta.get("request_id")

    if resolved_correlation_id is not None or resolved_request_id is not None:
        if resolved_correlation_id is not None:
            meta["correlation_id"] = resolved_correlation_id
        if resolved_request_id is not None:
            meta["request_id"] = resolved_request_id
        event_payload["meta"] = meta

    return event_payload, resolved_correlation_id, resolved_request_id


def publish_event(endpoint, payload, on_commit_callback=None, correlation_id=None, request_id=None):
    """
    Publica un evento en el outbox para entrega asíncrona.
    
    Este método NO envía directamente el webhook. Simplemente registra el evento
    en la tabla OutgoingEvent con status='pending' y next_retry_at=now(), listo
    para ser procesado por la tarea asíncrona process_outgoing().
    
    Args:
        endpoint (WebhookEndpoint): Destino externo configurado (URL, secret).
        payload (dict): Diccionario con estructura {
            "id": "<event_id>",
            "type": "<event_type>.v<version>",
            "data": {<business_data>}
        }
    
    Args:
        on_commit_callback (callable | None): Callback opcional que se ejecuta
            solo cuando la transacción actual confirma (commit). Recibe como
            único argumento el `OutgoingEvent` creado.

    Returns:
        OutgoingEvent: Instancia creada en base de datos.
    
    Raises:
        ValidationError: Si endpoint o payload son inválidos.
    
    Example:
        >>> from webhooks.producer.models import WebhookEndpoint
        >>> endpoint = WebhookEndpoint.objects.get(name="billing-service")
        >>> publish_event(endpoint, {
        ...     "id": "550e8400-e29b-41d4-a716-446655440000",
        ...     "type": "user.created.v1",
        ...     "data": {"user_id": "123"}
        ... })
    """
    from .models import OutgoingEvent
    event_payload, resolved_correlation_id, resolved_request_id = _normalize_trace_context(
        payload,
        correlation_id=correlation_id,
        request_id=request_id,
    )

    event = OutgoingEvent.objects.create(
        endpoint=endpoint, 
        payload=event_payload,
        correlation_id=resolved_correlation_id,
        request_id=resolved_request_id,
        next_retry_at=now()
    )

    if on_commit_callback:
        # Evita side effects fuera de consistencia transaccional.
        transaction.on_commit(lambda: on_commit_callback(event))

    return event


def probe_connection(endpoint, api_key=None, timeout_seconds=None):
    """
    Ejecuta una prueba de conectividad contra un receiver.

    Envía un evento especial `webhook.connection_test.v1` firmado con el secret
    del endpoint. Si el receiver también usa este paquete, debería responder
    con `{"status": "connection_ok"}`.
    """
    payload = {
        "id": str(uuid.uuid4()),
        "type": "webhook.connection_test.v1",
        "data": {"message": "connection-test"},
    }
    headers = {}
    if api_key:
        headers["Authorization"] = f"Api-Key {api_key}"

    started = time.perf_counter()

    try:
        response = send(
            endpoint,
            payload,
            extra_headers=headers,
            timeout_override=timeout_seconds,
        )
        latency_ms = (time.perf_counter() - started) * 1000

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text[:200]}

        status = body.get("status") if isinstance(body, dict) else None
        ok = response.status_code < 500 and status in {"connection_ok", "ok", "duplicate"}

        return {
            "ok": ok,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "status": status,
            "body": body,
        }
    except Exception as exc:  # pragma: no cover
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "ok": False,
            "status_code": 0,
            "latency_ms": round(latency_ms, 2),
            "status": "transport_error",
            "error": str(exc),
        }