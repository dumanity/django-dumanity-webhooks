"""django-dumanity-webhooks — Infraestructura de webhooks segura por diseño para Django.

Versión 2.0.0:
- Transporte HTTP vía httpx (reemplaza requests).
- Señales de ciclo de vida (webhook_received, webhook_dispatched, webhook_failed, webhook_replayed).
- Despachador sincrónico con perfiles, rate limiting y firma HMAC opcionales.
- Inyección automática de X-Trace-Id vía OpenTelemetry (dependencia opcional).
- Helper Pydantic CanonicalEventEnvelope (dependencia opcional).
- Verificaciones de sistema para WEBHOOK_PROFILES.
"""

__version__ = "2.0.0"
