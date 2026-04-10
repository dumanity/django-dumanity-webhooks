import json
import secrets
import uuid
from datetime import timedelta

from jsonschema import validate
from django.db.models import Q
from django.utils.timezone import now

from webhooks.core.metrics import inc
from webhooks.core.security import redact_headers
from webhooks.core.verification import verify
from webhooks.core.registry import get_event
from webhooks.core.handlers import get_handler
from webhooks.signals import webhook_failed, webhook_received

from .models import AuditLog, DeadLetter, EventLog, Integration, Secret


def _extract_trace_context(headers, payload=None):
    """Obtiene correlation_id/request_id/trace_id desde headers o meta del payload.

    Prioridades:
    - ``trace_id``:      ``X-Trace-Id`` (header estándar del paquete).
    - ``correlation_id``: ``X-Correlation-ID`` > ``payload.meta.correlation_id``.
    - ``request_id``:    ``X-Request-ID`` > ``payload.meta.request_id``.
    """
    meta = (payload or {}).get("meta") or {}
    return {
        "trace_id": headers.get("X-Trace-Id"),
        "correlation_id": headers.get("X-Correlation-ID") or meta.get("correlation_id"),
        "request_id": headers.get("X-Request-ID") or meta.get("request_id"),
    }

class WebhookService:
    """
    Pipeline de procesamiento de eventos entrantes (receiver).
    
    Implementa el flujo completo de recepción y validación de webhooks:
    1) Métricas de entrada -> incrementa contador
    2) Parseo de event_id -> valida UUID
    3) Resolución de integración -> busca por API Key (fallo cerrado)
    4) Auditoria -> crea AuditLog con headers
    5) Verificación de firma -> valida HMAC multi-secret con anti-replay
    6) Deduplicación -> rechaza duplicados por (integration_id, event_id)
    7) Schema validation -> jsonschema contra event registry
    8) Dispatch -> ejecuta handler registrado
    9) Trazabilidad -> EventLog + DeadLetter en caso de error
    
    Garantías:
    - Fail-closed: sin integración válida → excepción (no procesa)
    - Idempotencia: misma (integration, event_id) → "duplicate" sin retrabajar
    - Signature: valida contra todos los secretos activos no expirados
    - Anti-replay: timestamp debe estar ±300s respecto a now()
    
    Ejemplo llamada:
        from rest_framework.request import Request
        req = Request(request)
        result = WebhookService.process(req, integration=integration_obj)
        # Retorna: "ok", "duplicate"
        # Exceptions: "Invalid event id", "Integration not found", 
        #            "Invalid signature", "Unknown event type", handler exceptions
    """

    @classmethod
    def process(cls, request, integration=None):
        """
        Procesa un webhook entrante.
        
        Args:
            request: Request objeto DRF con headers y body del webhook.
            integration: Instancia Integration obtenida desde API Key.
                         Si None, lanza excepción (fallo cerrado).
        
        Returns:
            str: "ok" si procesado exitosamente, "duplicate" si es reintento,
                 "connection_ok" si es un evento de prueba de conexión
                 (`webhook.connection_test.v1`).
        
        Raises:
            Exception: con mensajes de error specificos para cada validación fallida.
        """
        body = request.body
        headers = request.headers
        inc("webhook.received")

        sig = headers.get("Webhook-Signature")
        event_id_raw = headers.get("X-Event-ID")
        trace_context = _extract_trace_context(headers)

        try:
            event_id = uuid.UUID(event_id_raw)
        except (ValueError, TypeError):
            inc("webhook.failed")
            webhook_failed.send(
                sender=WebhookService,
                event_id=str(event_id_raw),
                event_type=None,
                target_url=None,
                profile=None,
                error="Invalid event id",
            )
            raise Exception("Invalid event id")

        if not integration:
            inc("webhook.failed")
            webhook_failed.send(
                sender=WebhookService,
                event_id=str(event_id_raw),
                event_type=None,
                target_url=None,
                profile=None,
                error="Integration not found",
            )
            raise Exception("Integration not found")

        secrets = list(
            Secret.objects.filter(integration=integration, is_active=True).filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now())
            )
            .values_list("secret", flat=True)
        )

        AuditLog.objects.create(
            event_id=event_id,
            integration=integration.name if integration else "unknown",
            correlation_id=trace_context["correlation_id"],
            request_id=trace_context["request_id"],
            trace_id=trace_context["trace_id"],
            request_headers=redact_headers(dict(headers)),
        )

        if not verify(secrets, sig, body):
            inc("webhook.failed")
            webhook_failed.send(
                sender=WebhookService,
                event_id=str(event_id),
                event_type=None,
                target_url=None,
                profile=None,
                error="Invalid signature",
            )
            raise Exception("Invalid signature")

        if EventLog.objects.filter(integration=integration, event_id=event_id).exists():
            return "duplicate"

        payload = json.loads(body)

        if payload.get("type") == "webhook.connection_test.v1":
            EventLog.objects.create(
                integration=integration,
                event_id=event_id,
                correlation_id=trace_context["correlation_id"],
                request_id=trace_context["request_id"],
                trace_id=trace_context["trace_id"],
                type=payload["type"],
                payload=payload,
                status="processed",
            )
            return "connection_ok"

        event = get_event(payload["type"])
        if not event:
            inc("webhook.failed")
            webhook_failed.send(
                sender=WebhookService,
                event_id=str(event_id),
                event_type=payload.get("type"),
                target_url=None,
                profile=None,
                error="Unknown event type",
            )
            raise Exception("Unknown event type")

        validate(instance=payload["data"], schema=event["payload_schema"])

        log = EventLog.objects.create(
            integration=integration,
            event_id=event_id,
            correlation_id=trace_context["correlation_id"],
            request_id=trace_context["request_id"],
            trace_id=trace_context["trace_id"],
            type=payload["type"],
            payload=payload,
            status="received"
        )

        handler = get_handler(payload["type"])

        try:
            if handler:
                handler(payload["data"])
            log.status = "processed"
        except Exception as e:
            log.status = "failed"
            inc("webhook.failed")
            webhook_failed.send(
                sender=WebhookService,
                event_id=str(event_id),
                event_type=payload.get("type"),
                target_url=None,
                profile=None,
                error=str(e),
            )
            DeadLetter.objects.create(
                payload=payload,
                reason=str(e),
                retries=1,
                correlation_id=trace_context["correlation_id"],
                request_id=trace_context["request_id"],
                trace_id=trace_context["trace_id"],
            )

        log.save()

        if log.status == "processed":
            webhook_received.send(
                sender=WebhookService,
                event_id=str(event_id),
                event_type=payload.get("type"),
                integration_name=integration.name,
                trace_id=trace_context["trace_id"],
            )

        return "ok"


def bootstrap_receiver(integration_name: str, shared_secret: str | None = None, expires_days: int = 30) -> dict:
    """
    Crea o reutiliza una Integration con su API Key y un Secret inicial.

    Pensado para ser invocado tanto desde el management command ``webhooks_bootstrap``
    como desde el Django Admin, evitando duplicar lógica.

    Args:
        integration_name: Nombre descriptivo de la integración (ej: "producer-a").
        shared_secret: Secreto HMAC compartido. Si es None se genera automáticamente.
        expires_days: Días hasta que expira el secreto (mínimo 1).

    Returns:
        dict con las claves:
            - ``integration``: instancia de Integration creada o reutilizada.
            - ``api_key_plaintext``: str con la API key en claro, o None si
              la integración ya existía (la clave no puede recuperarse).
            - ``secret``: str con el secreto HMAC compartido.
            - ``integration_reused``: bool, True si la Integration ya existía.

    Example::

        result = bootstrap_receiver("producer-a", expires_days=30)
        # Guardar en vault:
        # result["api_key_plaintext"]  → Authorization: Api-Key <value>
        # result["secret"]             → compartir con el producer
    """
    from rest_framework_api_key.models import APIKey
    from .models import Integration, Secret

    if expires_days < 1:
        raise ValueError("expires_days must be >= 1")

    resolved_secret = shared_secret or f"whsec_{secrets.token_urlsafe(24)}"
    expires_at = now() + timedelta(days=expires_days)

    existing = Integration.objects.filter(name=integration_name).first()
    if existing:
        integration = existing
        api_key_plaintext = None
        integration_reused = True
    else:
        api_key_obj, api_key_plaintext = APIKey.objects.create_key(name=integration_name)
        integration = Integration.objects.create(name=integration_name, api_key=api_key_obj)
        integration_reused = False

    Secret.objects.create(
        integration=integration,
        secret=resolved_secret,
        is_active=True,
        expires_at=expires_at,
    )

    return {
        "integration": integration,
        "api_key_plaintext": api_key_plaintext,
        "secret": resolved_secret,
        "integration_reused": integration_reused,
    }