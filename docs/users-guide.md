# Users Guide

Guia para integradores del paquete `django-dumanity-webhooks`.

## 1. Que resuelve

Permite emitir y recibir webhooks en Django con un stack de seguridad por diseño, evitando implementar manualmente firma, idempotencia y validaciones. Soporta múltiples aplicaciones (A, B, C, ...) actuando simultáneamente como productoras y receptoras con garantías de aislamiento.

## 2. Requisitos

- Python 3.12+
- Django 6+
- DRF y djangorestframework-api-key

## 3. Instalacion

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.1.0"
```

Alternativa declarativa en `pyproject.toml`:

```toml
[project]
dependencies = [
    "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.1.0",
]
```

Para repositorio privado en CI, configura credenciales GitHub (PAT o deploy key).

```python
INSTALLED_APPS += [
    "webhooks.core",
    "webhooks.producer",
    "webhooks.receiver",
]
```

```bash
python manage.py makemigrations
python manage.py migrate
```

## 4. Configuracion producer

```python
from webhooks.producer.models import WebhookEndpoint

WebhookEndpoint.objects.create(
    name="billing-service",
    url="https://billing.example.com/webhooks/",
    secret="whsec_prod_123",
    is_active=True,
    max_retries=5,
    request_timeout_seconds=10,
)
```

Campos recomendados por endpoint:

- `max_retries`: cantidad máxima de reintentos para ese destino.
- `request_timeout_seconds`: timeout HTTP por request para ese destino.

Publicar evento:

```python
from webhooks.producer.services import publish_event

publish_event(endpoint, {
    "id": "a0f54e4d-8f4b-4d5f-b6de-3f2f19c53026",
    "type": "user.created.v1",
    "data": {"id": "123"},
})
```

Probar conexión (antes de habilitar tráfico real):

```python
from webhooks.producer.services import probe_connection

result = probe_connection(
        endpoint=endpoint,
        api_key="<receiver_api_key>",  # opcional si el receiver la exige
        timeout_seconds=5,
)

# Ejemplo resultado:
# {
#   "ok": True,
#   "status_code": 200,
#   "status": "connection_ok",
#   "latency_ms": 34.21,
#   "body": {"status": "connection_ok"}
# }
```

También disponible por CLI:

```bash
webhooks-info test-endpoint \
    --url https://receiver.example.com/webhooks/ \
    --secret whsec_prod_123 \
    --api-key <receiver_api_key> \
    --timeout 5
```

UI mínima en Django Admin:

- En `WebhookEndpoint` está disponible la acción `Probar conexión al receiver`.
- Ejecuta la prueba para los endpoints seleccionados y muestra resultado en mensajes del admin.
- También hay botón por fila `Probar` en la columna `Conectividad` para test rápido de un endpoint.

## 5. Configuracion receiver

```python
from django.urls import path
from webhooks.receiver.api import WebhookView, MetricsView

urlpatterns = [
    path("webhooks/", WebhookView.as_view()),
    path("metrics/", MetricsView.as_view()),
]
```

Crear integracion + secreto:

```python
from datetime import timedelta
from django.utils.timezone import now
from rest_framework_api_key.models import APIKey
from webhooks.receiver.models import Integration, Secret

api_key, plaintext = APIKey.objects.create_key(name="producer-a")
integration = Integration.objects.create(name="producer-a", api_key=api_key)

Secret.objects.create(
    integration=integration,
    secret="whsec_prod_123",
    is_active=True,
    expires_at=now() + timedelta(days=30),
)
```

## 6. Firma y headers

- Header de firma: `Webhook-Signature`
- Header de idempotencia: `X-Event-ID`
- Formato firma: `t=<timestamp>,v1=<hmac_sha256>`

## 7. Operacion diaria

- Ejecutar worker async: `python manage.py runworker`
- Vigilar `OutgoingEvent` en estado `failed`
- Revisar `DeadLetter` para eventos no procesados
- Revisar `AuditLog` para trazabilidad de entrada
- Exponer `/metrics` para scraping Prometheus (formato texto)

Notas de métricas (modo lean):

- Las métricas son in-memory por proceso (costo cero de infraestructura adicional).
- En despliegues con múltiples instancias, cada instancia expone sus propios contadores.
- Si más adelante necesitas agregación global, puedes sumar Prometheus + Redis/OTel.

## 8. Rotacion de secretos

1. Crear secreto nuevo con expiracion futura.
2. Mantener secreto anterior temporalmente activo.
3. Cambiar producer al nuevo secreto.
4. Expirar/desactivar secreto anterior.

## 9. Problemas frecuentes

- `Invalid signature`: secreto incorrecto, expirado o replay fuera de tolerancia.
- `duplicate`: mismo `X-Event-ID` ya procesado.
- `429 rate limited`: exceso de requests por integracion en una ventana.
- `failed` en outbox: endpoint caido o respuestas no-2xx.
- Timeouts frecuentes: subir `request_timeout_seconds` o reducir carga en el receiver.

## 9.1 Regla de oro operativa

- Nunca permitas que dos apps sean source-of-truth de la misma entidad.
- Webhook = "informo estado".
- REST = "solicito acción".

## 9.2 Auditoria liviana del intercambio (recomendado)

Para operar con bajo costo y baja carga mental, usa la guia dedicada:

- `docs/auditing-guide.md`

Que incluye:

- modelo minimo de datos de auditoria (`correlation_id`, `request_id`, `event_id`)
- ejemplos concretos de provision de perfil y uso de beneficio
- runbook de incidente en 10 minutos
- politica de alertas anti-fatiga y retencion economica
- checklists diario/semanal/mensual

Recursos listos para usar:

- `docs/examples/audit-record-template.json`
- `docs/incident-playbook.md`

## 10. Producción (modo lean + Sentry Free)

Stack mínimo recomendado:

- 1 instancia Django
- PostgreSQL
- 1 worker async para `process_outgoing`
- `/metrics` expuesto
- Sentry Free para errores

Integración sugerida en `settings.py` del proyecto:

```python
import os

SENTRY_DSN = os.getenv("SENTRY_DSN")

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.05,
        send_default_pii=False,
    )
```

Regla práctica de operación:

- Si `DeadLetter` o `OutgoingEvent.failed` crece más de lo normal por 15 min, abrir incidente y pausar nuevas integraciones hasta estabilizar.

## 11. Docker Compose / Coolify con repositorio privado

Si tu proyecto consumidor usa Docker Compose o Coolify y este paquete se instala desde GitHub privado, considera lo siguiente:

### Reglas clave

- Instala dependencias privadas en build-time, no en runtime.
- Usa tag fijo (`@v0.1.0`) para builds reproducibles.
- No guardes tokens en `Dockerfile` o en variables que terminen dentro de la imagen.

### Dockerfile recomendado (BuildKit + SSH)

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git openssh-client ca-certificates \
        && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./

RUN --mount=type=ssh \
        mkdir -p -m 0700 /root/.ssh && \
        ssh-keyscan github.com >> /root/.ssh/known_hosts && \
        uv sync --no-dev

COPY . .
```

### docker-compose.yml

```yaml
services:
    web:
        build:
            context: .
            ssh:
                - default
```

Build:

```bash
DOCKER_BUILDKIT=1 docker compose build
docker compose up -d
```

### Coolify

- Configura el source privado de GitHub en Coolify.
- Usa deploy key SSH read-only o secret de build para autenticación.
- Verifica que el build soporte BuildKit (`--mount=type=ssh`).
- Evita instalar dependencias privadas en `entrypoint` o startup command.
