# webhooks - Guia Tecnica

Documentacion tecnica para desarrolladores del framework y mantenedores.

## 1. Objetivos de arquitectura

- Reusar infraestructura de webhooks entre proyectos Django.
- Consolidar seguridad y contratos en un nucleo unico.
- Mantener simplicidad operativa para equipos pequenos.

## 2. Estructura de modulos

### core

- `registry.py`: registro central de contratos de eventos (tipo + schema)
- `handlers.py`: registro desacoplado de handlers por `event_type`
- `signing.py`: firma HMAC de payload con timestamp
- `verification.py`: verificacion anti-replay y multi-secret
- `metrics.py`: contadores in-memory (`inc(name)`)

### producer

- `models.py`
	- `WebhookEndpoint`: configuracion de consumidor destino
	- `OutgoingEvent`: outbox + estado de entrega
- `services.py`
	- `publish_event`: inserta evento en outbox (no envia inline)
- `sender.py`
	- transporte HTTP firmado con timeout
- `tasks.py`
	- procesamiento async
	- retries no bloqueantes
	- backoff exponencial

### receiver

- `models.py`
	- `Integration`, `Secret`, `EventLog`, `DeadLetter`, `AuditLog`
- `api.py`
	- endpoint DRF protegido por API Key
	- rate limiting por integracion
- `services.py`
	- pipeline de verificacion, validacion, idempotencia y dispatch
- `rate_limit.py`
	- helper de rate limiting basado en cache

## 3. Contratos y convenciones

### Header de firma

- Header estandar del paquete: `Webhook-Signature`
- Formato: `t=<timestamp>,v1=<hmac_sha256>`
- Header de idempotencia: `X-Event-ID`

### Eventos versionados

Patron recomendado:

- `user.created.v1`
- `user.created.v2`

No romper contratos existentes: introducir nuevo tipo al cambiar schema.

## 4. Seguridad por diseño

Medidas obligatorias en runtime:

- API Key en endpoint receptor
- Firma HMAC con compare seguro
- Anti-replay con tolerancia temporal
- Multi-secret para rotacion
- Secretos con expiracion (`expires_at`)
- Idempotencia por `event_id`
- Rate limiting en entrada

Principio de implementacion:

- Preferir defaults seguros y simples.
- Evitar frameworks adicionales de complejidad operativa cuando no aportan valor inmediato.

## 5. Retry y resiliencia

`OutgoingEvent` gestiona:

- `status`: `pending`, `delivered`, `failed`
- `attempts`: numero de intentos
- `next_retry_at`: fecha para proximo intento

Algoritmo:

1. Seleccionar `pending` elegibles (`next_retry_at <= now` o null).
2. Enviar HTTP.
3. Si falla, `attempts += 1`.
4. Programar retry con `delay = 2 ** attempts`.
5. Si supera maximo, marcar `failed`.

Esto elimina bloqueos por `sleep` y mejora throughput de workers.

## 6. Observabilidad minima

- Metricas: `webhook.received`, `webhook.failed`
- Auditoria de entrada: `AuditLog`
- Trazabilidad de evento: `EventLog`
- Diagnostico de fallos: `DeadLetter`

## 7. Extender por plugin de dominio

### Registrar eventos

```python
from webhooks.core.registry import register_event

register_event({
		"type": "user.created.v1",
		"payload_schema": {
				"type": "object",
				"properties": {"id": {"type": "string"}},
				"required": ["id"],
		},
})
```

### Registrar handler

```python
from webhooks.core.handlers import register_handler

@register_handler("user.created.v1")
def handle_user_created(data):
		...
```

## 8. Guia de mantenimiento

- Revisar periodicamente `DeadLetter` y errores de firma.
- Rotar secretos con ventana de coexistencia corta.
- Mantener contratos de eventos versionados.
- Agregar tests de integracion para cada evento nuevo.

## 9. Notas de migracion

Cambios de esquema recientes:

- `producer.OutgoingEvent.next_retry_at`
- `receiver.Secret.expires_at`
- `receiver.DeadLetter.retries`
- nuevo `receiver.AuditLog`

Despues de actualizar codigo:

```bash
python manage.py makemigrations
python manage.py migrate
```