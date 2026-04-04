from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_api_key.permissions import HasAPIKey
from rest_framework_api_key.models import APIKey
from django.http import HttpResponse

from webhooks.core.metrics import inc, export_prometheus_text
from .models import Integration
from .rate_limit import is_rate_limited
from .services import WebhookService


def _resolve_integration(request):
    """
    Resuelve la integración desde el header Authorization.
    
    Busca la API Key en el header 'Authorization: Api-Key <key>' y la mapea
    a una integración registrada. Si no encuentra API key válida, retorna None
    (fallo cerrado, sin fallback a primer registro).
    
    Args:
        request: Request object con headers.
    
    Returns:
        Integration: instancia de la app productora registrada, o None si no encontrada.
    
    Security:
        - Sin API Key → None (NO fallback implícito)
        - API Key inválida → None
        - Integración no existe para la API Key → None
        El VIEW debe rechazar con 403 si es None
    """
    authorization = request.headers.get("Authorization", "")
    prefix = "Api-Key "

    if authorization.startswith(prefix):
        raw_key = authorization[len(prefix):].strip()
        try:
            api_key = APIKey.objects.get_from_key(raw_key)
            integration = Integration.objects.filter(api_key=api_key).first()
            if integration:
                return integration
        except Exception:
            pass

    return None

class WebhookView(APIView):
    """
    Endpoint principal de recepción de webhooks (POST).
    
    Implementa seguridad en capas:
    1) HasAPIKey permission: valida header Authorization
    2) Resolución: mapea API Key a Integration (fail-closed sin fallback)
    3) Rate limit: por integration_id no por nombre
    4) Dispatch: pasa a WebhookService para validación y procesamiento completo
    
    Headers esperados:
        - Authorization: Api-Key <key>  (obligatorio, validado por permission)
        - Webhook-Signature: t=<ts>,v1=<hmac>  (obligatorio, validado en process)
        - X-Event-ID: <uuid>  (obligatorio, validado en process)
    
    Respuestas:
        - 400: X-Event-ID inválido, payload malformado
        - 403: API Key no encontrada, integración no existe
        - 429: Rate limit excedido para esta integración
        - 200: Procesado (ok) o duplicado (duplicate)
        - 500: Error interno en handler o validación
    """
    permission_classes = [HasAPIKey]

    def post(self, request):
        """
        Procesa un webhook entrante.
        
        Args:
            request: HTTP request con headers de firma y body JSON.
        
        Returns:
            Response con {"status": "ok"} o {"status": "duplicate"}
                       o error 403, 429 si fallan controles de entrada.
        """
        integration = _resolve_integration(request)

        if not integration:
            inc("webhook.rejected.integration_not_found")
            return Response({"detail": "integration not found"}, status=403)

        if is_rate_limited(integration.id):
            inc("webhook.rejected.rate_limited")
            return Response({"detail": "rate limited"}, status=429)

        return Response({"status": WebhookService.process(request, integration=integration)})


class MetricsView(APIView):
    """Endpoint de métricas en formato texto Prometheus."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return HttpResponse(
            export_prometheus_text(),
            content_type="text/plain; version=0.0.4; charset=utf-8",
        )