import json
import uuid

from jsonschema import validate
from django.db.models import Q
from django.utils.timezone import now

from webhooks.core.metrics import inc
from webhooks.core.verification import verify
from webhooks.core.registry import get_event
from webhooks.core.handlers import get_handler

from .models import AuditLog, DeadLetter, EventLog, Integration, Secret


def _extract_trace_context(headers, payload=None):
    """Obtiene correlation_id/request_id desde headers o meta del payload."""
    meta = (payload or {}).get("meta") or {}
    return {
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
            str: "ok" si procesado exitosamente, "duplicate" si es reintento.
        
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
            raise Exception("Invalid event id")

        if not integration:
            inc("webhook.failed")
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
            request_headers=dict(headers),
        )

        if not verify(secrets, sig, body):
            inc("webhook.failed")
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
                type=payload["type"],
                payload=payload,
                status="processed",
            )
            return "connection_ok"

        event = get_event(payload["type"])
        if not event:
            inc("webhook.failed")
            raise Exception("Unknown event type")

        validate(instance=payload["data"], schema=event["payload_schema"])

        log = EventLog.objects.create(
            integration=integration,
            event_id=event_id,
            correlation_id=trace_context["correlation_id"],
            request_id=trace_context["request_id"],
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
            DeadLetter.objects.create(
                payload=payload,
                reason=str(e),
                retries=1,
                correlation_id=trace_context["correlation_id"],
                request_id=trace_context["request_id"],
            )

        log.save()
        return "ok"