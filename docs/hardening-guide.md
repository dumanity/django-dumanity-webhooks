# Hardening Guide (Producción)

Checklist práctico alineado al comportamiento real del paquete.

## 1) Rotación de secretos

- Usa secretos por integración.
- Mantén coexistencia temporal (nuevo + viejo).
- Expira/desactiva el secreto anterior.

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
- Hacer replay seguro con:
  - `python manage.py webhooks_replay --dead-letter-id <id> --endpoint-id <uuid> --reason "<motivo>" --dry-run`
  - ejecutar sin `--dry-run` solo tras corregir causa raíz.
