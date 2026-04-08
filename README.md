# django-dumanity-webhooks · v2.0.0

Framework Django para webhooks seguros, desacoplados y listos para producción.

> **⚠️ Política de ejemplos seguros**
> Todos los secretos, tokens y credenciales que aparecen en esta documentación,
> tests y ejemplos son **ficticios** (p. ej. `whsec_example_123`,
> `example-test-secret-key`).  Nunca uses credenciales reales en docs, tests
> ni capturas de pantalla.  Si un secreto real fue expuesto accidentalmente,
> **rótalo de inmediato**.

## Novedades en v2.0.0

| Característica | Descripción |
|---|---|
| **httpx** | Reemplaza `requests` como transporte HTTP. Soporte nativo para async en el futuro. |
| **Señales** | `webhook_received`, `webhook_dispatched`, `webhook_failed`, `webhook_replayed` — observabilidad sin acoplamiento. |
| **`dispatch_webhook_sync()`** | Despachador de alto nivel con perfiles, rate limiting, firma opcional y OTel. |
| **Perfiles** | `WEBHOOK_PROFILES` en `settings.py` — timeout, secret, headers y rate_limit por destino. |
| **CanonicalEventEnvelope** | Helper Pydantic v2 (opcional) para eventos de primera clase. |
| **System checks** | `manage.py check` valida `WEBHOOK_PROFILES` con IDs `webhooks.E001`–`E003`, `W001`–`W002`, `I001`. |
| **OTel X-Trace-Id** | Inyección automática del trace ID activo (no-op si OTel no está instalado). |

## Objetivo

Resolver de forma reusable el envío y recepción de webhooks entre aplicaciones sin dispersar lógica de seguridad, validación y resiliencia.

## Modulos

- `webhooks.core`
  - registry de eventos y handlers
  - firma HMAC y verificación multi-secret
  - métricas básicas + export Prometheus
  - **system checks** para `WEBHOOK_PROFILES`
- `webhooks.producer`
  - outbox (`OutgoingEvent`)
  - sender HTTP con **httpx** + OTel `X-Trace-Id`
  - **`dispatch_webhook_sync()`** con perfiles, rate limit y señales
  - procesamiento async con retries no bloqueantes
- `webhooks.receiver`
  - endpoint DRF protegido por API Key
  - verificación de firma (`Webhook-Signature`)
  - idempotencia, schema validation y dispatch
  - rate limiting, DLQ y auditoría
  - **Admin completo** (integraciones, secretos, event logs, dead letters, audit logs)
- `webhooks.signals`
  - `webhook_received`, `webhook_dispatched`, `webhook_failed`, `webhook_replayed`
- `webhooks.contrib.pydantic`
  - `CanonicalEventEnvelope` (requiere `pydantic>=2.0`)

## Instalacion

Desde proyectos con `uv`, recomendado fijar por tag de Git:

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v2.0.0"
```

Instalación equivalente con `pip`:

```bash
pip install "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v2.0.0"
```

También puedes declararlo manualmente en `pyproject.toml` del consumidor:

```toml
[project]
dependencies = [
  "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0",
]
```

Notas sobre repositorio privado:

- En local, usa `gh auth login`, token o SSH key con acceso al repo.
- En CI, configura credenciales de GitHub (PAT/deploy key) para poder resolver la dependencia.
- Mantén siempre la dependencia fijada por tag (`@v1.1.0`) para builds reproducibles.

Si el paquete vive en un subdirectorio de un monorepo, usa `#subdirectory=`:

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0#subdirectory=django-dumanity-webhooks"
```

## Configuracion minima

```python
INSTALLED_APPS += [
    "webhooks.core",
    "webhooks.producer",
    "webhooks.receiver",
]

# Opcional pero recomendado: perfiles de webhook (resueltos por dispatch_webhook_sync)
WEBHOOK_PROFILES = {
    "default": {"timeout": 10},
    "billing": {
        "timeout": 30,
        "secret": "whsec_...",              # firma HMAC para este destino
        "headers": {"X-Source": "mi-app"},  # headers extra en cada request
        "rate_limit": {"limit": 50, "window": 60},
    },
}

# Cache necesario para rate limiting (LocMemCache para desarrollo, Redis para producción)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
```

Internamente, las apps usan labels únicos para evitar colisiones con paquetes comunes como `core` en proyectos consumidores.

```bash
python manage.py migrate
python manage.py check  # verifica WEBHOOK_PROFILES automáticamente
```

## Quickstart en 10 minutos

Ver `docs/quickstart.md` — incluye:
- Diagrama Producer / Receiver con roles explícitos
- Configuración desde **Django Admin** (recomendado) y desde CLI
- Bootstrap automático, prueba de conexión, primer evento end-to-end y troubleshooting

## Documentacion principal

- Quickstart (10 minutos): `docs/quickstart.md`
- Guia de hardening: `docs/hardening-guide.md`
- Guia de usuario: `docs/users-guide.md`
- Guia de desarrollo: `docs/developers-guide.md`
- Guia de testing: `TESTING.md`

## Contrato de firma

Header usado por el paquete:

- `Webhook-Signature`

Formato:

- `t=<unix_timestamp>,v1=<hmac_sha256_hex>`

Notas:

- No existe un estandar global de nombre de header de firma.
- Se eligio `Webhook-Signature` por claridad y neutralidad de proveedor.
- GitHub usa `X-Hub-Signature-256`; Stripe usa `Stripe-Signature`.

## Rotacion de secretos (multi-secret)

Modelo operativo recomendado:

1. Crear secreto nuevo y activarlo con `expires_at` futuro.
2. Mantener secreto anterior activo durante ventana de transicion.
3. Cambiar el emisor para firmar con el secreto nuevo.
4. Expirar o desactivar secreto anterior.

El receiver valida contra todos los secretos activos y no expirados.

## Flujo Producer

1. `publish_event(endpoint, payload)` guarda en outbox.
2. task async toma eventos pendientes elegibles (`next_retry_at <= now`).
3. envia HTTP firmado.
4. exito: `delivered`.
5. fallo: incrementa `attempts` y programa siguiente retry con backoff exponencial.
6. al exceder max intentos: `failed`.

Prueba de conexión opcional antes de habilitar tráfico:

```bash
webhooks-info test-endpoint \
  --url https://receiver.example.com/webhooks/ \
  --secret whsec_example_123 \
  --api-key <your_receiver_api_key> \
  --timeout 5
```

## Flujo Receiver

1. API Key gate.
2. Rate limit por integracion.
3. Auditoria (`AuditLog`) — registra el request con headers redactados antes de continuar.
4. Verificacion de firma HMAC con anti-replay.
5. Idempotencia por `X-Event-ID`.
6. Validacion JSON Schema del tipo de evento.
7. Dispatch a handler registrado.
8. Trazabilidad (`EventLog`, `DeadLetter`).

## Seguridad por diseño

- Defaults seguros
- Cambios incrementales
- Sin dependencias innecesarias
- Sin complejidad operativa evitable
- Headers sensibles (`Authorization`, `Webhook-Signature`, `X-Api-Key`, `Cookie`, `Set-Cookie`) se redactan automáticamente antes de persistir en `AuditLog`.

## Endpoint /metrics

El endpoint de métricas está **deshabilitado por defecto**.  Actívalo explícitamente solo en entornos donde la exposición sea aceptable:

```python
# settings.py
WEBHOOK_METRICS_ENABLED = True           # False por defecto (seguro)
WEBHOOK_METRICS_TOKEN   = "your-secret-token"  # Recomendado en producción
```

Variables de entorno equivalentes (con `django-environ` o similar):

```
WEBHOOK_METRICS_ENABLED=true
WEBHOOK_METRICS_TOKEN=your-secret-token
```

Comportamiento:

| `WEBHOOK_METRICS_ENABLED` | `WEBHOOK_METRICS_TOKEN` | Resultado |
|---------------------------|-------------------------|-----------|
| `False` (por defecto)     | cualquiera              | 404 — endpoint no expuesto |
| `True`                    | no configurado          | 200 — acceso libre (menos seguro) |
| `True`                    | configurado             | 200 solo con `Authorization: Bearer <token>`; 403 si no |

## Operacion

**Desde Django Admin (Receiver):**
- **Integraciones** → bootstrap y gestión de secretos
- **Dead Letters** → replay individual o en bulk con trazabilidad
- **Event Logs / Audit Logs** → solo lectura, búsqueda por event_id / correlation_id

**Desde CLI:**
- Worker async: `python manage.py runworker`
- Revisar periodicamente `OutgoingEvent` con status `failed`
- Monitorear `DeadLetter` y `AuditLog`
- Rotar secretos periodicamente
- Listar fallos: `python manage.py webhooks_list_failures`
- Replay seguro (con trazabilidad): `python manage.py webhooks_replay --dead-letter-id <id> --endpoint-id <uuid> --reason "<motivo>" --dry-run`
- Si ya hubo replay previo del mismo DLQ, se bloquea por defecto. Usa `--allow-previously-replayed` solo de forma excepcional y documentada.

## Comandos de agilidad (v2.0.0)

- Bootstrap inicial seguro (CLI o Admin):
  - `python manage.py webhooks_bootstrap`
  - Admin → Integraciones → "Bootstrap nueva integración" (receiver)
  - Admin → Webhook Endpoints → Añadir (producer)
- Validación de contratos:
  - `python manage.py webhooks_validate_contracts`
- Operación:
  - `python manage.py webhooks_list_failures`
  - `python manage.py webhooks_replay ...`
  - Admin → Dead Letters → botón Replay (receiver)
- System checks (nuevo en v2.0.0):
  - `python manage.py check --tag webhooks`

### Despachador sincrónico (nuevo en v2.0.0)

```python
from webhooks.producer.dispatch import dispatch_webhook_sync

response = dispatch_webhook_sync(
    payload={"id": str(uuid.uuid4()), "type": "orders.created.v1", "data": {...}},
    target_url="https://partner.example.com/webhooks/",
    profile="billing",       # resuelve timeout, secret, headers, rate_limit
    correlation_id="req-01", # inyectado como X-Correlation-ID
)
```

### Señales (nuevo en v2.0.0)

```python
from django.dispatch import receiver
from webhooks.signals import webhook_dispatched, webhook_failed

@receiver(webhook_dispatched)
def on_dispatched(sender, *, target_url, event_id, status_code, latency_ms, **kwargs):
    logger.info("Webhook entregado", extra={"status": status_code, "ms": latency_ms})

@receiver(webhook_failed)
def on_failed(sender, *, event_id, error, **kwargs):
    alert_ops(f"Webhook {event_id} falló: {error}")
```

### CanonicalEventEnvelope (nuevo en v2.0.0)

```bash
pip install "django-dumanity-webhooks[pydantic]"
```

```python
from webhooks.contrib.pydantic import CanonicalEventEnvelope

envelope = CanonicalEventEnvelope(
    type="orders.created.v1",
    data={"order_id": "ord-123"},
)
dispatch_webhook_sync(envelope, "https://partner.example.com/webhooks/")
```

## Para desarrolladores

Scaffold rapido de dominio webhook:

```bash
python manage.py start_webhook_domain orders
```

Si hay colision de nombre (por ejemplo ya existe una app `orders`), el comando resuelve automaticamente usando sufijos (`orders_events_2`, etc.).

## Starter Kit Para Agentes IA (Copy/Paste)

Si quieres que agentes trabajen casi solos cuando este paquete sea dependencia, copia estos bloques en tu proyecto consumidor.

### 1) `AGENTS.md` minimo en la raiz

```md
# AGENTS

## Contexto del proyecto
- Arquitectura: Django monolito modular por dominios.
- Integracion entre apps: REST para comandos, webhooks para eventos de estado.
- Source-of-truth: una sola app por entidad.

## Reglas operativas
- No cambiar contratos de eventos sin versionado (`*.v1` -> `*.v2`).
- No mover secretos a logs ni respuestas de error.
- Si tocas receiver/producer, ejecutar pruebas y check de migraciones.

## Ubicacion de piezas clave
- Eventos por dominio: `<dominio>_events/events.py`
- Handlers por dominio: `<dominio>_events/handlers.py`
- Registry de schemas: `<dominio>_events/registry.py`

## Flujo esperado para cambios
1. Crear/actualizar evento en `events.py`.
2. Registrar schema en `registry.py`.
3. Implementar handler en `handlers.py`.
4. Agregar/actualizar tests del dominio.
5. Ejecutar `check-agent-ready` antes de PR.
```

### 2) Comando unico de validacion para agente

```bash
# Puedes usarlo directo o convertirlo en task de CI
DJANGO_SETTINGS_MODULE=tests_settings PYTHONPATH=. \
python -m django makemigrations --check --dry-run && \
python -m pytest tests.py
```

### 3) Guardrail de CI minimo (`.github/workflows/agent-guardrails.yml`)

```yaml
name: Agent Guardrails

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install
        run: |
          python -m pip install -U pip
          pip install -e .
      - name: Migrations drift check
        run: |
          DJANGO_SETTINGS_MODULE=tests_settings PYTHONPATH=. \
          python -m django makemigrations --check --dry-run
      - name: Tests
        run: |
          python -m pytest tests.py
```

### 4) Scaffold rapido por dominio

```bash
python manage.py start_webhook_domain orders
python manage.py start_webhook_domain billing --output-dir ./domains
python manage.py start_webhook_domain orders --dry-run
```

Con esto, incluso si ya existe una app `orders`, el scaffold evita colision con sufijos (`orders_events_2`, `orders_events_3`, ...).

Referencia tecnica ampliada en:

- `webhooks/README.md`
- `docs/developers-guide.md`
- `docs/auditing-guide.md`
- `docs/incident-playbook.md`
- `docs/examples/audit-record-template.json`
- `docs/release.md`
- `docs/quickstart.md`
- `docs/hardening-guide.md`
