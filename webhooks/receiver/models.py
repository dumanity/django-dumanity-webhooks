import uuid
from django.db import models
from rest_framework_api_key.models import APIKey

class Integration(models.Model):
    """
    Representa una aplicación externa que envía webhooks.
    
    En arquitectura multi-app, cada producer remoto tiene una Integration
    para autenticar sus requests y validar sus firmas.
    
    Fields:
        name: Nombre descriptivo (ej: "app-a", "billing-service")
        api_key: OneToOne a djangorestframework_api_key.APIKey para autenticación
    
    Garantías:
        - Cada integración tiene su propio namespace de event_id (idempotencia scoped)
        - Cada integración tiene su propio rate limit bucket
        - Cada integración tiene sus propios secretos para validar firma
    
    Example:
        >>> from rest_framework_api_key.models import APIKey
        >>> api_key, plaintext = APIKey.objects.create_key(name="app-a-inbound")
        >>> integration = Integration.objects.create(
        ...     name="app-a",
        ...     api_key=api_key
        ... )
    """
    name = models.CharField(max_length=100)
    api_key = models.OneToOneField(APIKey, on_delete=models.CASCADE)

class Secret(models.Model):
    """
    Multi-secret para firma HMAC y rotación segura.
    
    Permite activar un nuevo secret antes de cambiar el producer,
    manteniendo ambos válidos durante la transición, sin downtime.
    
    Fields:
        integration: FK a Integration
        secret: Valor HMAC compartido con el producer
        is_active: Si está siendo usado para validación
        expires_at: Fecha de expiración (null = no expira)
    
    Security:
        - El receiver válida contra TODOS los secretos activos no expirados
        - El producer firma con UN secreto (el más reciente o especificado)
        - Ventana de transición: nuevo activo, viejo todavía activo, luego expira viejo
    
    Example:
        >>> from datetime import timedelta
        >>> from django.utils.timezone import now
        >>> Secret.objects.create(
        ...     integration=integration,
        ...     secret="whsec_prod_new_123",
        ...     is_active=True,
        ...     expires_at=now() + timedelta(days=30)
        ... )
    """
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE)
    secret = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

class EventLog(models.Model):
    """
    Registro de auditoría e idempotencia (scoped por integración).
    
    Cada evento recibido se registra aquí. La combinación (integration, event_id)
    es única, evitando duplicados por integración pero permitiendo reutilizar
    UUIDs entre productores distintos.
    
    Fields:
        integration: FK a Integration, scope del evento
        event_id: UUID del evento (reutilizable entre integraciones)
        type: Tipo de evento (ej: "user.created.v1")
        payload: JSON completo del evento
        status: "received", "processed", "failed"
    
    Guarantees:
        - Deduplicación: si (integration, event_id) existe → "duplicate", no procesa
        - Trazabilidad: registra todos los intentos (exitosos y fallidos)
        - Idempotencia: múltiples requests con mismo ID → procesado una sola vez
    
    Example:
        >>> event = EventLog.objects.get(
        ...     integration__name="app-a",
        ...     event_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        ... )
        >>> print(event.status)  # "processed"
    """
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE)
    event_id = models.UUIDField()
    type = models.CharField(max_length=100)
    payload = models.JSONField()
    status = models.CharField(max_length=20)

    class Meta:
        unique_together = ('integration', 'event_id')

class DeadLetter(models.Model):
    """
    Queue de eventos fallidos.
    
    Si WebhookService.process falla (error en handler, schema inválido, etc),
    el evento se guarda aquí para mantenimiento e investigación manual.
    
    Fields:
        payload: JSON del evento que falló
        reason: Mensaje de error
        retries: Contador de intentos fallidos
    
    Operación:
        - Revisar regularmente para debug
        - Implementar reintentos manuales o automáticos
        - Establecer alertas si la tabla crece muy rápido
    """
    payload = models.JSONField()
    reason = models.TextField()
    retries = models.IntegerField(default=0)


class AuditLog(models.Model):
    """
    Log de auditoría completo: todos los requests recibidos.
    
    Registra TODOS los webhooks recibidos (exitosos, duplicados, fallidos),
    incluyendo headers, para cumplimiento y debugging.
    
    Fields:
        event_id: UUID del evento
        integration: Nombre de la integración (desnormalizado para rapidez)
        request_headers: JSON con headers enviados (sin Authorization)
        created_at: Timestamp de recepción
    
    Guarantees:
        - Completo: nada se pierde
        - Rápido: sin FK costosas para auditoría
        - Inmutable: append-only
    """
    event_id = models.UUIDField()
    integration = models.CharField(max_length=100)
    request_headers = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)