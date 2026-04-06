# Quickstart (10 minutos)

Objetivo: enviar y recibir tu primer webhook en pocos pasos con defaults seguros.

## 1) Instalar

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0"
```

## 2) Configuración mínima

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

## 3) Bootstrap automático (rápido)

```bash
python manage.py webhooks_bootstrap \
  --integration-name producer-a \
  --endpoint-name receiver-a \
  --endpoint-url https://receiver.example.com/webhooks/
```

Guarda en vault los secretos/keys mostrados por el comando.

Notas rápidas:

- Si repites bootstrap para la misma integración, se reutiliza la integración y se crea un secreto nuevo para rotación segura.
- Si ya existe endpoint y quieres actualizar URL/secret, agrega `--update-endpoint`.

## 4) Crear un contrato de evento y validarlo

Si ya tienes un dominio scaffold:

```bash
python manage.py start_webhook_domain orders
python manage.py webhooks_validate_contracts
```

## 5) Probar conexión endpoint

```bash
webhooks-info test-endpoint \
  --url https://receiver.example.com/webhooks/ \
  --secret whsec_example_123 \
  --api-key <your_receiver_api_key> \
  --timeout 5
```

## 6) Enviar primer evento

```python
from webhooks.producer.models import WebhookEndpoint
from webhooks.producer.services import publish_event

endpoint = WebhookEndpoint.objects.get(name="receiver-a")
publish_event(endpoint, {
    "id": "11111111-1111-4111-8111-111111111111",
    "type": "orders.created.v1",
    "data": {"order_id": "A-1001"},
})
```

## 7) Verificar éxito

- Receiver devuelve `status=ok`, `duplicate` o `connection_ok`.
- `EventLog` en receiver contiene el `event_id`.
- `OutgoingEvent` en producer avanza a `delivered`.

Chequeo operativo mínimo:

```bash
python manage.py webhooks_list_failures
```

Debería mostrar sin fallos o con lista accionable para resolver.

## Troubleshooting rápido

- `Invalid signature`: secreto incorrecto/expirado o timestamp fuera de tolerancia.  
  **Acción:** rotar/alinear secret y reintentar.
- `integration not found` (403): API key inválida o no asociada a Integration.  
  **Acción:** recrear con `webhooks_bootstrap --receiver-only`.
- `duplicate`: mismo `X-Event-ID` ya procesado.  
  **Acción:** para replay seguro usa `python manage.py webhooks_replay --new-event-id ...`.
- `rate limited` (429): exceso de requests por integración.  
  **Acción:** reduce burst o ajusta ventana/límite operativos.
- Outbox `failed` / DLQ crece: endpoint/handler inestable.  
  **Acción:** `python manage.py webhooks_list_failures` y luego replay controlado con `--dry-run`.
- `Replay blocked: already replayed`: ese DLQ ya fue replayado antes.  
  **Acción:** crea un nuevo `event_id` (`--new-event-id`) o usa `--allow-previously-replayed` solo si controlaste efectos duplicados downstream.
- `Contract validation failed`: contrato inválido o sin versionado adecuado.  
  **Acción:** ejecuta `python manage.py webhooks_validate_contracts` y corrige `type` + `payload_schema` según el mensaje.
