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

```bash
uv add django-dumanity-webhooks
```

Instalacion directa desde GitHub (repositorio privado de la organización Dumanity):

Si estás publicando el paquete en https://github.com/dumanity/dumanity-django-webhooks (repo dedicado):

```bash
pip install "git+https://github.com/dumanity/dumanity-django-webhooks.git@v0.1.0"
```

Si el paquete vive en un subdirectorio del repo (monorepo), usa `#subdirectory=`:

```bash
pip install "git+https://github.com/dumanity/dumanity-django-webhooks.git@v0.1.0#subdirectory=django-dumanity-webhooks"
```

Notas sobre repositorios privados:

- Para instalaciones automatizadas en CI, configura las credenciales de GitHub (PAT) en el runner o usa el token del runner.
- Alternativa: publicar artefactos como Release (workflow ya incluido) y descargar el wheel `.whl` desde la Release.

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

Referencia tecnica ampliada en:

- `webhooks/README.md`
- `docs/developers-guide.md`
- `docs/release.md`
