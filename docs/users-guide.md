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
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0"
```

Alternativa declarativa en `pyproject.toml`:

```toml
[project]
dependencies = [
    "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0",
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
    secret="whsec_example_123",
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
        api_key="<your_receiver_api_key>",  # opcional si el receiver la exige
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
    --secret whsec_example_123 \
    --api-key <your_receiver_api_key> \
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
    secret="whsec_example_123",
    is_active=True,
    expires_at=now() + timedelta(days=30),
)
```

### 5.1 Ejemplo completo: dos proyectos Django (A ↔ B), ambos receiver + producer

Objetivo: que **Proyecto A** y **Proyecto B** se envíen eventos en ambos sentidos usando el mismo framework.

#### Paso 1: instalar en ambos proyectos

En A y en B:

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0"
```

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

#### Paso 2: exponer endpoint receiver en ambos

En `urls.py` de A y de B:

```python
from django.urls import path
from webhooks.receiver.api import WebhookView

urlpatterns = [
    path("webhooks/", WebhookView.as_view()),
]
```

#### Paso 3: crear credenciales cruzadas (A acepta a B, B acepta a A)

En **Proyecto A** (para aceptar eventos enviados por B):

```python
from datetime import timedelta
from django.utils.timezone import now
from rest_framework_api_key.models import APIKey
from webhooks.receiver.models import Integration, Secret

api_key_b_to_a, plaintext_b_to_a = APIKey.objects.create_key(name="project-b")
integration_b_to_a = Integration.objects.create(name="project-b", api_key=api_key_b_to_a)
Secret.objects.create(
    integration=integration_b_to_a,
    secret="whsec_b_to_a_example",
    is_active=True,
    expires_at=now() + timedelta(days=30),
)
```

En **Proyecto B** (para aceptar eventos enviados por A):

```python
from datetime import timedelta
from django.utils.timezone import now
from rest_framework_api_key.models import APIKey
from webhooks.receiver.models import Integration, Secret

api_key_a_to_b, plaintext_a_to_b = APIKey.objects.create_key(name="project-a")
integration_a_to_b = Integration.objects.create(name="project-a", api_key=api_key_a_to_b)
Secret.objects.create(
    integration=integration_a_to_b,
    secret="whsec_a_to_b_example",
    is_active=True,
    expires_at=now() + timedelta(days=30),
)
```

> Guarda `plaintext_b_to_a` y `plaintext_a_to_b`: se usan como API key de autorización en el sentido contrario.

#### Paso 4: crear endpoints producer cruzados

En **Proyecto A** (A envía a B):

```python
from webhooks.producer.models import WebhookEndpoint

endpoint_a_to_b = WebhookEndpoint.objects.create(
    name="project-b",
    url="https://project-b.example.com/webhooks/",
    secret="whsec_a_to_b_example",
    is_active=True,
)
```

En **Proyecto B** (B envía a A):

```python
from webhooks.producer.models import WebhookEndpoint

endpoint_b_to_a = WebhookEndpoint.objects.create(
    name="project-a",
    url="https://project-a.example.com/webhooks/",
    secret="whsec_b_to_a_example",
    is_active=True,
)
```

#### Paso 5: publicar eventos en ambos sentidos

En A (hacia B):

```python
from webhooks.producer.services import publish_event

publish_event(endpoint_a_to_b, {
    "id": "11111111-1111-4111-8111-111111111111",
    "type": "order.created.v1",
    "data": {"order_id": "A-1001"},
})
```

En B (hacia A):

```python
from webhooks.producer.services import publish_event

publish_event(endpoint_b_to_a, {
    "id": "22222222-2222-4222-8222-222222222222",
    "type": "payment.confirmed.v1",
    "data": {"payment_id": "B-9001"},
})
```

#### Paso 6: operación mínima en ambos

- Ejecutar worker en A: `python manage.py runworker`
- Ejecutar worker en B: `python manage.py runworker`
- Verificar logs/estado de `OutgoingEvent`, `EventLog` y `DeadLetter` en ambos proyectos.

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
- Listar fallos operativos:
  - `python manage.py webhooks_list_failures`
- Replay seguro de DLQ:
  - `python manage.py webhooks_replay --dead-letter-id <id> --endpoint-id <uuid> --reason "<motivo>" --dry-run`

Notas de métricas (modo lean):

- Las métricas son in-memory por proceso (costo cero de infraestructura adicional).
- En despliegues con múltiples instancias, cada instancia expone sus propios contadores.
- Si más adelante necesitas agregación global, puedes sumar Prometheus + Redis/OTel.

## 8. Rotacion de secretos

1. Crear secreto nuevo con expiracion futura.
2. Mantener secreto anterior temporalmente activo.
3. Cambiar producer al nuevo secreto.
4. Expirar/desactivar secreto anterior.

## 9. Eventos por dominio (recomendado)

Cuando un equipo necesita eventos propios por dominio, la forma más mantenible es crear una app `<dominio>_events` y separar responsabilidades por archivo:

- `events.py`: define tipos de evento versionados (`*.v1`, `*.v2`).
- `registry.py`: registra contratos/schemas de esos tipos.
- `handlers.py`: implementa lógica de consumo post-validación.
- `signals.py`: emisión opcional desde señales de dominio (si aporta valor).
- `apps.py`: bootstrap central en `AppConfig.ready()`.

Punto de partida rápido:

```bash
python manage.py start_webhook_domain orders
```

Flujo recomendado de implementación:

1. Definir el evento versionado en `events.py`.
2. Registrar su contrato en `registry.py`.
3. Registrar el handler en `handlers.py`.
4. Cargar registros en `apps.py` dentro de `ready()`.
5. Usar `signals.py` solo cuando necesites emitir desde eventos internos de Django.
6. Validar contratos registrados: `python manage.py webhooks_validate_contracts`.

Responsabilidades esperadas:

- **Negocio**: en la app de dominio (no en `core` del framework).
- **Contrato**: en `events.py` + `registry.py`.
- **Ejecución**: en `handlers.py` una vez validado firma/schema/idempotencia.
- **Signals**: mecanismo opcional de emisión; no reemplaza contrato ni versionado.

Versionado y compatibilidad:

- No rompas `v1` cambiando payload de forma incompatible.
- Crea `v2` para cambios rompientes.
- Mantén convivencia temporal (`v1` + `v2`) hasta migrar consumidores.

Checklist operativo corto para integradores:

- [ ] Crear/actualizar `events.py`, `registry.py`, `handlers.py`, `apps.py` (y `signals.py` si aplica).
- [ ] Verificar que los contratos de evento estén registrados.
- [ ] Verificar que los handlers estén registrados y sean idempotentes.
- [ ] Confirmar que cambios rompientes salgan en nueva versión (`v2`).
- [ ] Probar flujo completo antes de producción (firma, schema, dispatch, deduplicación).

## 10. Problemas frecuentes

- `Invalid signature`: secreto incorrecto, expirado o replay fuera de tolerancia.
- `duplicate`: mismo `X-Event-ID` ya procesado.
- `429 rate limited`: exceso de requests por integracion en una ventana.
- `failed` en outbox: endpoint caido o respuestas no-2xx.
- Timeouts frecuentes: subir `request_timeout_seconds` o reducir carga en el receiver.

## 10.1 Regla de oro operativa

- Nunca permitas que dos apps sean source-of-truth de la misma entidad.
- Webhook = "informo estado".
- REST = "solicito acción".

## 10.2 Auditoria liviana del intercambio (recomendado)

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

## 11. Producción (modo lean + Sentry Free)

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

## 12. Docker Compose / Coolify con repositorio privado

Si tu proyecto consumidor usa Docker Compose o Coolify y este paquete se instala desde GitHub privado, considera lo siguiente:

### Reglas clave

- Instala dependencias privadas en build-time, no en runtime.
- Usa tag fijo (`@v1.1.0`) para builds reproducibles.
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
