# django-dumanity-webhooks

Framework Django para webhooks seguros, desacoplados y listos para produccion.

## Objetivo

Resolver de forma reusable el envio y recepcion de webhooks entre aplicaciones sin dispersar logica de seguridad, validacion y resiliencia.

## Modulos

- `webhooks.core`
  - registry de eventos
  - registry de handlers
  - firma HMAC y verificacion multi-secret
  - metricas basicas
- `webhooks.producer`
  - outbox (`OutgoingEvent`)
  - sender HTTP
  - procesamiento async con retries no bloqueantes
- `webhooks.receiver`
  - endpoint DRF protegido por API Key
  - verificacion de firma (`Webhook-Signature`)
  - idempotencia, schema validation y dispatch
  - rate limiting, DLQ y auditoria

## Instalacion

Desde proyectos con `uv`, recomendado fijar por tag de Git:

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.1.0"
```

Instalación equivalente con `pip`:

```bash
pip install "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.1.0"
```

También puedes declararlo manualmente en `pyproject.toml` del consumidor:

```toml
[project]
dependencies = [
  "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.1.0",
]
```

Notas sobre repositorio privado:

- En local, usa `gh auth login`, token o SSH key con acceso al repo.
- En CI, configura credenciales de GitHub (PAT/deploy key) para poder resolver la dependencia.
- Mantén siempre la dependencia fijada por tag (`@v0.1.0`) para builds reproducibles.

Si el paquete vive en un subdirectorio de un monorepo, usa `#subdirectory=`:

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.1.0#subdirectory=django-dumanity-webhooks"
```

## Configuracion minima

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
  --secret whsec_prod_123 \
  --api-key <receiver_api_key> \
  --timeout 5
```

## Flujo Receiver

1. API Key gate.
2. Rate limit por integracion.
3. Verificacion de firma HMAC con anti-replay.
4. Idempotencia por `X-Event-ID`.
5. Validacion JSON Schema del tipo de evento.
6. Dispatch a handler registrado.
7. Auditoria (`AuditLog`) y trazabilidad (`EventLog`, `DeadLetter`).

## Seguridad por diseño

- Defaults seguros
- Cambios incrementales
- Sin dependencias innecesarias
- Sin complejidad operativa evitable

## Operacion

- Worker async: `python manage.py runworker`
- Revisar periodicamente `OutgoingEvent` con status `failed`
- Monitorear `DeadLetter` y `AuditLog`
- Rotar secretos periodicamente

## Para desarrolladores

Scaffold rapido de dominio webhook:

```bash
python manage.py start_webhook_domain socios
```

Si hay colision de nombre (por ejemplo ya existe una app `socios`), el comando resuelve automaticamente usando sufijos (`socios_events_2`, etc.).

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
python manage.py start_webhook_domain socios
python manage.py start_webhook_domain comercios --output-dir ./domains
python manage.py start_webhook_domain socios --dry-run
```

Con esto, incluso si ya existe una app `socios`, el scaffold evita colision con sufijos (`socios_events_2`, `socios_events_3`, ...).

Referencia tecnica ampliada en:

- `webhooks/README.md`
- `docs/developers-guide.md`
- `docs/auditing-guide.md`
- `docs/incident-playbook.md`
- `docs/examples/audit-record-template.json`
- `docs/release.md`
