# Developers Guide

Guia para mantenedores y contribuidores de `django-dumanity-webhooks`.

## 1. Filosofia

- Seguridad por diseño como default.
- Simplicidad operativa: cambios incrementales, sin sobreingenieria.
- Desacople de dominio: eventos y handlers viven en plugins.

## 2. Componentes internos

### `core`

- `registry.py`: contratos de evento. Mapeo centralizado de tipos y schemas.
- `handlers.py`: dispatch desacoplado. Handlers registrados por tipo de evento.
- `signing.py`: HMAC SHA256 con timestamp. Firma determinística con anti-replay.
- `verification.py`: parse header, tolerancia temporal, multi-secret. Validación con múltiples secretos activos.
- `metrics.py`: contadores in-memory. Métricas locales por evento.

### `producer`

- `OutgoingEvent` usa outbox pattern. Garantiza entrega eventual sin bloqueos de red.
- `process_outgoing` evita bloqueos y usa `next_retry_at`. Task async con backoff exponencial.
- Backoff exponencial: `2 ** attempts` hasta MAX_ATTEMPTS (5 por defecto).
- `WebhookEndpoint`: destino externo con URL, secret HMAC y flag activo.

### `receiver`

- API protegida con `HasAPIKey`. Autenticación por API Key en header `Authorization: Api-Key ...`.
- **Resolución fail-closed**: sin API key válida retorna 403 (no fallback implícito).
- **Rate limit por integration_id**: clave segura y determinística, no por nombre.
- **Idempotencia scoped por integración**: `unique((integration, event_id))` evita colisiones entre productores.
- Filtro de secretos activos/no expirados. Validación multi-secret con ventana temporal.
- EventLog (scoped) + DeadLetter + AuditLog. Trazabilidad completa.

## 3. Cambios de esquema actuales

- `producer.OutgoingEvent.next_retry_at`
- `receiver.Secret.expires_at`
- `receiver.DeadLetter.retries`
- `receiver.AuditLog`

Tras cambios de modelos, correr:

```bash
python manage.py makemigrations
python manage.py migrate
```

## 4. Contrato de seguridad

### Headers y firma
- Header de firma del framework: `Webhook-Signature`
- Formato: `t=<timestamp>,v1=<digest>` (timestamp UNIX en segundos, HMAC SHA256 en hex)
- Header de idempotencia: `X-Event-ID` (debe ser UUID válido en v4)
- Header de autenticación: `Authorization: Api-Key <key>` (para integración entrante)

### Validación
- Si el header `Webhook-Signature` esta ausente o malformado, `verify()` retorna `False`
- Si `X-Event-ID` no es UUID válido, rechazo inmediato (400)
- Si la API Key no existe en el sistema, rechazo con 403 (fallo cerrado)
- Si el timestamp está fuera de tolerancia (±300s), rechazo por anti-replay

### Idempotencia y deduplicación
- Clave única por integración: `(integration_id, event_id)` permite reutilizar UUIDs entre productores sin colisión
- EventLog registra todos los eventos procesados o rechazados, incluidos duplicados

## 5. Extension por plugin

Un plugin debe:

1. declarar eventos versionados
2. registrar schemas
3. registrar handlers
4. bootstrapping en `AppConfig.ready()`

## 6. Testing recomendado

### Unit tests
- `test_signing`: firma HMAC determinística con timestamp.
- `test_verification`: válida multi-secret, timestamp anti-replay, formato header.
- `test_parser`: parse correcto de cabeceras, UUID validation en X-Event-ID.
- `test_retry_scheduler`: selector de eventos por `next_retry_at`, backoff exponencial.
- `test_fail_closed_resolution`: integración no encontrada → 403, sin fallback.
- `test_rate_limit_per_integration`: límite aislado por integration_id.

### Integration tests
- `test_complete_receiver_flow`: API key → firma → schema → dispatch → EventLog.
- `test_complete_producer_flow`: publish → outbox → send → retry → delivered.
- `test_multi_app_scenario`: dos apps A y B como producers+receivers con cruce de webhooks.

### Regression tests
- `test_idempotency_scoped`: mismo event_id en dos integraciones → ambos aceptados.
- `test_duplicate_rejection`: mismo event_id en misma integración → rechazo.
- `test_double_delivery`: reintento de webhook con mismo ID → idempotencia.

### Security tests
- `test_expired_secret_rejection`: secreto con expires_at < now() rechaza firma.
- `test_invalid_signature`: firma malformada o con secret incorrecto rechaza.
- `test_timestamp_replay_protection`: timestamp fuera de ±300s rechaza.
- `test_rate_limit_enforcement`: exceso de requests → 429.
- `test_missing_api_key`: sin API key o clave inválida → 403.

## 7. Limitaciones y garantías

### Limitaciones operativas
- **Rate limiting**: por bucket temporal en cache Django (no distribuido). Recomendado para <100 req/min por integración en producción simple.
- **Métricas**: contadores in-memory. Se pierden al reiniciar procesos; para HA usar Prometheus/OpenTelemetry.
- **Worker async**: singleton. Para multiworker distribuido considerar task queue (Celery, APScheduler).

### Garantías implementadas (v3.1+)
- **Resolución fail-closed**: ninguna integración sin API key válida.
- **Idempotencia scoped**: colisión imposible entre productores distintos (por design).
- **Rate limit determinístico**: clave por integration_id (UUID), no ambiguo.
- **Anti-replay**: validación de timestamp ±300s + header completo.
- **Multi-secret safe**: rotación sin downtime con ventana de transición.
- **Políticas por endpoint**: `max_retries` y `request_timeout_seconds` configurables por destino.

## 8. Roadmap sugerido

1. ✓ ~~Resolver integracion desde API key de forma estricta~~ (hecho en v3.1).
2. ✓ ~~Rate limit por integration_id~~ (hecho en v3.1).
3. ✓ ~~Idempotencia scoped por integración~~ (hecho en v3.1).
4. ✓ ~~Configurar max retries y timeout por endpoint~~ (hecho en v3.1).
5. ✓ ~~Exportar metricas a Prometheus/OpenTelemetry~~ (endpoint `/metrics` básico en v3.1; OTel avanzado queda en backlog).
6. Dashboard operativo para DeadLetter y AuditLog (backlog).
7. Event versioning y schema evolution helpers (backlog).

## 9. Despliegue Lean (1 operador)

Objetivo: operar con el menor costo y complejidad posible.

### Arquitectura mínima recomendada

- Django app (API receiver + lógica de dominio)
- PostgreSQL (estado principal)
- 1 worker async (`process_outgoing` periódico)
- Métricas locales vía `/metrics`
- Sentry Free para errores y alertas básicas

### Variables de entorno sugeridas

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY=<secret>`
- `DATABASE_URL=<postgres-url>`
- `WEBHOOK_RATE_LIMIT=100`
- `WEBHOOK_RATE_WINDOW=60`
- `WEBHOOK_SIGNATURE_TOLERANCE=300`
- `SENTRY_DSN=<dsn-opcional>`
- `SENTRY_TRACES_SAMPLE_RATE=0.05`

### Integración recomendada con Sentry (Free tier)

En `settings.py` del proyecto consumidor:

```python
import os

SENTRY_DSN = os.getenv("SENTRY_DSN")

if SENTRY_DSN:
	import sentry_sdk
	from sentry_sdk.integrations.django import DjangoIntegration

	sentry_sdk.init(
		dsn=SENTRY_DSN,
		integrations=[DjangoIntegration()],
		traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
		send_default_pii=False,
		environment=os.getenv("DJANGO_ENV", "production"),
	)
```

Buenas prácticas para el plan gratuito:

- Alertas solo para errores críticos (signature invalid spike, receiver 5xx).
- Sampling bajo (`0.01` a `0.05`) para no quemar cuota.
- No enviar payloads completos con PII.

## 10. Runbook operativo mínimo

### Señales de alarma

- `webhooks_webhook_failed` crece rápido.
- `OutgoingEvent` con `status=failed` aumenta por encima de umbral normal.
- `DeadLetter` crece sostenidamente.
- Sentry reporta excepciones repetidas en `WebhookService.process` o `send`.

### Acciones rápidas

1. Revisar disponibilidad del endpoint remoto afectado.
2. Verificar vigencia de secretos (`expires_at`) y firma.
3. Revisar API keys activas y headers reales en `AuditLog`.
4. Reprocesar eventos puntuales desde DLQ tras corregir causa.
5. Si hay tormenta de retries, bajar temporalmente `max_retries` por endpoint.

### Reproceso controlado (manual)

1. Seleccionar eventos de `DeadLetter` por causa/ventana.
2. Reconstruir payload original y re-publicar por `publish_event`.
3. Confirmar en `EventLog` estado `processed`.

## 11. Checklist de seguridad (baseline)

- [ ] API Key obligatoria para receiver.
- [ ] Resolución fail-closed activa.
- [ ] Secretos con rotación y expiración definidas.
- [ ] Tolerancia temporal de firma no mayor a 300s.
- [ ] `X-Event-ID` UUID validado e idempotencia por `(integration, event_id)`.
- [ ] Logging sin exponer secretos ni payload sensible.
- [ ] Sentry sin PII por defecto (`send_default_pii=False`).
- [ ] Dependencias escaneadas mensualmente (`pip-audit` o herramienta CI).

## 12. Performance y SLO (lean)

### Script de carga incluido

Se incluye `scripts/load_test_receiver.py` para pruebas de carga básicas sin tooling adicional.

Ejemplo:

```bash
python scripts/load_test_receiver.py \
	--url http://localhost:8000/webhooks/ \
	--api-key <API_KEY> \
	--secret <SHARED_SECRET> \
	--requests 500 \
	--concurrency 25 \
	--timeout 5
```

### SLO inicial recomendado (equipo 1 persona)

- Disponibilidad receiver (mensual): >= 99.5%
- Éxito de entrega inicial (2xx): >= 98%
- Latencia p95 receiver: <= 500 ms
- Error rate (5xx): < 1%
- DLQ growth: no crecimiento sostenido > 15 min

### Criterios de alerta

1. `webhooks_webhook_failed` sube > 3x baseline por 10 min.
2. `OutgoingEvent(status=failed)` supera umbral operativo (definir por dominio).
3. Sentry reporta error repetido en `WebhookService.process` o `send` > N/min.

### Cuándo considerar Redis para rate-limit

- Más de una instancia receiver activa.
- Inconsistencias de rate-limit observadas en producción.
- Tráfico sostenido > 100 req/min por integración con riesgo de abuso.

Si no se cumplen esas condiciones, mantener cache local simplifica operación y reduce costo.
