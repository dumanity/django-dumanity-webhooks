# Quickstart (10 minutos)

Envía y recibe tu primer webhook con seguridad por diseño en pocos pasos.

```
┌─────────────────────────────┐       ┌──────────────────────────────┐
│       Producer App          │       │        Receiver App           │
│     (el que envía)          │       │      (el que recibe)          │
│                             │       │                               │
│  WebhookEndpoint            │──────▶│  Integration + Secret         │
│  OutgoingEvent              │       │  EventLog                     │
│  publish_event()            │       │  register_handler()           │
└─────────────────────────────┘       └──────────────────────────────┘
```

> **¿Cuándo ejecutar cada paso?**  
> Los pasos marcados con **📥 Receiver** se hacen en la app que recibe.  
> Los pasos marcados con **📤 Producer** se hacen en la app que envía.  
> Los pasos sin marca se hacen en ambas (o solo en la que aplique si eres solo uno).

---

## 1) Instalar (ambas apps)

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v1.1.0"
```

## 2) Configurar `INSTALLED_APPS` + migrar (ambas apps)

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

---

## 3) 📥 Receiver — crear la integración

El Receiver crea una **Integration** (identifica al Producer remoto) + **Secret HMAC**.  
El Producer necesitará los dos valores que este paso produce:
- **RECEIVER_API_KEY** → para que el Producer la use en su cabecera `Authorization`.
- **WEBHOOK_SHARED_SECRET** → para firmar (Producer) y verificar (Receiver) payloads.

### Opción A — Django Admin ✨ (recomendado)

1. Entra al Admin → **Integraciones** → botón **"Bootstrap nueva integración"**.
2. Completa el nombre (ej: `producer-a`) y deja el secret vacío (se genera solo).
3. Haz clic en **Crear integración**.
4. ⚠️ Copia los valores mostrados en pantalla **ahora mismo** — la API Key no se vuelve a mostrar.

### Opción B — CLI

```bash
# Ejecutar en la app Receiver
python manage.py webhooks_bootstrap \
  --receiver-only \
  --integration-name producer-a \
  --secret whsec_example_123
```

Guarda en vault los valores que imprime el comando.

---

## 4) 📤 Producer — configurar el endpoint

El Producer crea un **WebhookEndpoint** apuntando a la URL del Receiver.  
Necesita el `WEBHOOK_SHARED_SECRET` del paso anterior.

### Opción A — Django Admin ✨

1. Admin → **Webhook Endpoints** → **Añadir endpoint**.
2. Rellena:
   - **Name**: nombre descriptivo (ej: `receiver-a`)
   - **URL**: URL pública del Receiver (ej: `https://receiver.example.com/webhooks/`)
   - **Secret**: el `WEBHOOK_SHARED_SECRET` del paso 3
3. Activa **Is active** y guarda.

### Opción B — CLI

```bash
# Ejecutar en la app Producer
python manage.py webhooks_bootstrap \
  --producer-only \
  --endpoint-name receiver-a \
  --endpoint-url https://receiver.example.com/webhooks/ \
  --secret whsec_example_123
```

---

## 5) 📤 Producer — probar la conexión

Antes de enviar tráfico real, verifica que Producer y Receiver se entienden.

### Opción A — Django Admin ✨

Admin → **Webhook Endpoints** → fila del endpoint → botón **"Probar"**.  
Verás `✓ conexión OK` o el error exacto con código HTTP.

### Opción B — CLI

```bash
webhooks-info test-endpoint \
  --url https://receiver.example.com/webhooks/ \
  --secret whsec_example_123 \
  --api-key <RECEIVER_API_KEY> \
  --timeout 5
```

### Opción C — Python

```python
from webhooks.producer.models import WebhookEndpoint
from webhooks.producer.services import probe_connection

endpoint = WebhookEndpoint.objects.get(name="receiver-a")
result = probe_connection(endpoint, api_key="<RECEIVER_API_KEY>", timeout_seconds=5)
# {"ok": True, "status_code": 200, "status": "connection_ok", "latency_ms": 34.2}
```

---

## 6) 📥 Receiver — registrar tu handler

El Receiver decide qué hacer cuando llega un evento.  
Usa el scaffold para crear la estructura de dominio completa de golpe:

```bash
# Ejecutar en la app Receiver
python manage.py start_webhook_domain orders
```

Eso crea `orders_events/` con `events.py`, `handlers.py`, `registry.py` y `apps.py`.  
Edita `orders_events/handlers.py`:

```python
from webhooks.core.handlers import register_handler

@register_handler("orders.created.v1")
def handle_order_created(data):
    # Tu lógica de negocio aquí
    order_id = data["order_id"]
    ...
```

Valida que el contrato esté bien formado:

```bash
python manage.py webhooks_validate_contracts
```

---

## 7) 📤 Producer — publicar el primer evento

```python
# Ejecutar en la app Producer
from webhooks.producer.models import WebhookEndpoint
from webhooks.producer.services import publish_event

endpoint = WebhookEndpoint.objects.get(name="receiver-a")
publish_event(endpoint, {
    "id": "11111111-1111-4111-8111-111111111111",
    "type": "orders.created.v1",
    "data": {"order_id": "A-1001"},
})
```

`publish_event` **no envía directamente** — guarda en el outbox (`OutgoingEvent`).  
El worker lo envía en background:

```bash
# Ejecutar en la app Producer
python manage.py runworker
```

---

## 8) Verificar éxito

| Dónde mirar | Qué buscar |
|---|---|
| 📥 Receiver — Admin → **Event Logs** | `status = processed`, `type = orders.created.v1` |
| 📥 Receiver — Admin → **Audit Logs** | Registro del request con headers redactados |
| 📤 Producer — Admin → **Outgoing Events** | `status = delivered` |
| Terminal (ambos) | `python manage.py webhooks_list_failures` → sin resultados |

El Receiver responde uno de estos valores:

| Respuesta | Significado |
|---|---|
| `status: ok` | Procesado correctamente |
| `status: duplicate` | Ya procesado antes (idempotencia) |
| `status: connection_ok` | Evento de prueba de conexión |

---

## Troubleshooting rápido

| Error | Dónde ocurre | Acción |
|---|---|---|
| `Invalid signature` | 📥 Receiver | Secreto incorrecto o timestamp fuera de ±5 min. Rotar/alinear secret. |
| `403` (integration not found) | 📥 Receiver | API key inválida. Rehacer bootstrap `--receiver-only` en Receiver. |
| `duplicate` | 📥 Receiver | Mismo `X-Event-ID` ya procesado. Normal en retries. |
| `429` rate limited | 📥 Receiver | Burst excesivo por integración. Reduce carga o ajusta límite. |
| Outbox `failed` / DLQ crece | 📤 Producer | Endpoint o handler inestable. `webhooks_list_failures` → replay controlado. |
| `Replay blocked: already replayed` | 📤 Producer | DLQ ya replayado. Usa `--new-event-id` o replay desde Admin con nuevo event ID. |
| `Contract validation failed` | Ambos | Schema inválido. Ejecuta `webhooks_validate_contracts` y corrige `type`/`payload_schema`. |

---

## Próximos pasos

- 📖 Configuración avanzada y opciones de producción → `docs/users-guide.md`
- 🔒 Checklist de hardening → `docs/hardening-guide.md`
- 🔍 Auditoría y trazabilidad → `docs/auditing-guide.md`

