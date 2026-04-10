"""django-dumanity-webhooks — Infraestructura de webhooks segura por diseño para Django.

Versión 2.1.0:
- Trazabilidad end-to-end consistente: X-Trace-Id leído en receiver y propagado a
  EventLog, AuditLog, DeadLetter y la señal webhook_received.
- Señales lifecycle verificadas: webhook_received incluye trace_id en kwargs.
- Transporte HTTP vía httpx (reemplaza requests, desde v2.0.0).
- Señales de ciclo de vida (webhook_received, webhook_dispatched, webhook_failed, webhook_replayed).
- Despachador sincrónico con perfiles, rate limiting y firma HMAC opcionales.
- Inyección automática de X-Trace-Id vía OpenTelemetry (dependencia opcional).
- Helper Pydantic CanonicalEventEnvelope (dependencia opcional).
- Verificaciones de sistema para WEBHOOK_PROFILES.
"""

__version__ = "2.1.0"
