# Hardening Guide (Producción)

Checklist práctico alineado al comportamiento real del paquete.

## 1) Rotación de secretos

Modelo operativo recomendado — elige la vía que se adapte a tu flujo:

### Opción A — Django Admin (sin terminal)

1. Admin → **Integraciones** → fila de la integración → botón **"Rotar secreto"**.
2. Se crea un secreto nuevo activo (`is_active=True`) con expiración en 30 días.
3. ⚠️ El nuevo secreto se muestra en el mensaje de confirmación — cópialo a vault ahora.
4. Informa al producer del nuevo secreto y espera a que lo despliegue.
5. Admin → **Secretos** → selecciona el secreto anterior → acción **"Desactivar secretos seleccionados"**.

### Opción B — CLI / management command

```bash
# 1. Crear secreto nuevo (el anterior permanece activo — ventana de transición)
python manage.py webhooks_bootstrap \
  --receiver-only \
  --integration-name producer-a \
  --secret whsec_nuevo_secreto \
  --expires-days 30

# 2. Informar al producer del nuevo secreto y esperar despliegue

# 3. Desactivar el secreto anterior desde Django shell
python manage.py shell -c "
from webhooks.receiver.models import Secret
Secret.objects.filter(integration__name='producer-a', secret='whsec_secreto_anterior').update(is_active=False)
"
```

### Reglas para ambas opciones

- Mantén coexistencia temporal (nuevo + viejo activos) mientras el producer despliega.
- El receiver valida contra **todos** los secretos activos y no expirados — no hay downtime.
- Nunca elimines el secreto anterior antes de confirmar que el producer usa el nuevo.
- Expira/desactiva el secreto anterior; no lo reutilices.

## 2) `/metrics` seguro

- Por defecto deshabilitado (`WEBHOOK_METRICS_ENABLED=False`).
- En producción, habilitar solo en red controlada.
- Configura `WEBHOOK_METRICS_TOKEN` para requerir Bearer token.

## 3) Idempotencia

- Mantener `X-Event-ID` único por evento.
- El receiver deduplica por `(integration, event_id)`.
- Para replay, prefiere `--new-event-id` cuando requieras reproceso explícito.

## 4) Rate limiting

- Mantener límites por integración para aislar abuso.
- Monitorear respuestas 429 y ajustar límites por patrón real.

## 5) Auditoría y redacción de sensibles

- `AuditLog` registra request headers con redacción automática:
  `Authorization`, `Webhook-Signature`, `X-Api-Key`, `Cookie`, `Set-Cookie`.
- Nunca registrar secretos en logs de aplicación ni en tickets.

## 6) Retención de datos

- Logs técnicos detallados: 14 días.
- Resumen de auditoría: 90 días.
- Métricas agregadas: 6-12 meses.

## 7) Despliegue recomendado

- API receiver + worker async separados.
- Monitorear `OutgoingEvent(status=failed)` y `DeadLetter`.
- Replay seguro — elige la vía:

  **Admin (sin terminal):**
  Admin → **Dead Letters** → fila del evento → botón **"Replay"** → selecciona endpoint, escribe motivo, activa "Generar nuevo event ID" → confirmar.

  **CLI:**
  ```bash
  python manage.py webhooks_replay \
    --dead-letter-id <id> \
    --endpoint-id <uuid> \
    --reason "<motivo>" \
    --dry-run    # validar primero; quitar --dry-run para ejecutar
  ```

- Ejecutar replay solo tras corregir la causa raíz del fallo.
