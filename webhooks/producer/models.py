import uuid
from django.db import models

class WebhookEndpoint(models.Model):
    """
    Representa un consumidor externo que recibe webhooks.
    
    En arquitectura multi-app, cada app receptora tiene un WebhookEndpoint
    registrado en el producer para recibir eventos vía HTTP.
    
    Fields:
        name: Identificador descriptivo (ej: "app-b", "billing-service")
        url: URL destino (endpoint HTTP POST)
        secret: Secreto HMAC compartido para firma
        is_active: Si está habilitado para recibir eventos
        max_retries: Máximo de reintentos para eventos hacia este endpoint
        request_timeout_seconds: Timeout HTTP por endpoint
    
    Security:
        - El secret se usa para firmar todos los webhooks a este endpoint
        - DEBE ser compartido de forma segura fuera de banda
        - Los webhooks pueden reutilizar mismo secret si comparten credenciales
    
    Example:
        >>> endpoint = WebhookEndpoint.objects.create(
        ...     name="app-b",
        ...     url="https://app-b.example.com/webhooks/",
        ...     secret="whsec_example_123",
        ...     is_active=True
        ... )
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=100, help_text="Nombre lógico del endpoint")
    url = models.URLField(help_text="URL destino")
    secret = models.CharField(max_length=255, help_text="Secret HMAC")
    is_active = models.BooleanField(default=True)
    max_retries = models.PositiveIntegerField(default=5)
    request_timeout_seconds = models.PositiveIntegerField(default=10)

class OutgoingEvent(models.Model):
    """
    Cola de eventos salientes (patrón Outbox).
    
    Implementa garantía de entrega eventual sin bloqueos de red.
    Los eventos se guardan primero, luego se envían de forma asíncrona
    con reintentos automáticos.
    
    Fields:
        id: UUID único del evento
        endpoint: FK a WebhookEndpoint destino
        payload: JSON completo con estructura {"id", "type", "data"}
        correlation_id: Id transversal de la transaccion (opcional)
        request_id: Id del intento del comando (opcional)
        attempts: Contador de intentos de envío fallidos
        status: "pending", "delivered", "failed"
        next_retry_at: Timestamp del siguiente reintento programado
    
    Flujo:
        1. publish_event() crea OutgoingEvent con status="pending", next_retry_at=now()
        2. Tarea async process_outgoing() busca eventos con next_retry_at <= now()
        3. Envia HTTP POST firmado a endpoint.url
        4. Si 2xx → status="delivered", next_retry_at=NULL
        5. Si error → incrementa attempts, programa retry con 2^attempts segundos
        6. Si exceeds MAX_ATTEMPTS → status="failed"
    
    Guarantees:
        - Entrega eventual: no se pierden eventos (hasta status="failed")
        - Sin bloqueos: HTTP async, worker desacoplado
        - Backoff exponencial: reintenta con delays crecientes
    
    Example:
        >>> events = OutgoingEvent.objects.filter(
        ...     status="pending",
        ...     next_retry_at__lte=now()
        ... )
        >>> for e in events:
        ...     send(e.endpoint, e.payload)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE)
    payload = models.JSONField(help_text="Evento completo")
    correlation_id = models.CharField(max_length=100, null=True, blank=True)
    request_id = models.CharField(max_length=100, null=True, blank=True)
    attempts = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default="pending")
    next_retry_at = models.DateTimeField(null=True, blank=True)