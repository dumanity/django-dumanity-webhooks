# Incident Playbook (Lean)

Playbook operativo corto para incidentes entre Sistema A <-> Sistema B.

Objetivo: resolver en 10-15 minutos el 80% de incidentes sin escalar complejidad.

## 1. Severidades simples

- `SEV-1`: transacciones bloqueadas para todos los tenants.
- `SEV-2`: degradacion parcial, reintentos elevados o latencia alta sostenida.
- `SEV-3`: error aislado por tenant/operacion.

## 2. Checklist de triage (3 minutos)

1. Confirmar ventana temporal del incidente (inicio aproximado).
2. Identificar `correlation_id` o `request_id` de un caso real.
3. Verificar si el fallo fue en comando REST, webhook o persistencia final.
4. Clasificar severidad.

## 3. Flujo de diagnostico rapido (10 minutos)

1. Buscar en trazas por `correlation_id`.
2. Verificar comando REST:
   - request enviado
   - response recibido
   - tiempo de respuesta
3. Verificar evento webhook:
   - `event_id` presente
   - firma valida
   - idempotencia
4. Verificar estado final de negocio:
   - perfil provisionado o no
   - beneficio consumido o no
5. Clasificar causa:
   - `command_failed`
   - `event_not_delivered`
   - `state_mismatch`

## 4. Accion inmediata por causa

### `command_failed`

- Reintentar una sola vez con el mismo `request_id`.
- Si vuelve a fallar, responder UI con mensaje transitorio.
- Abrir ticket con evidencia minima (IDs + codigo + latencia).

### `event_not_delivered`

- Reenviar evento por `event_id`.
- Confirmar llegada por `EventLog`.
- Si falla por firma, rotar/validar secreto antes de nuevo replay.

### `state_mismatch`

- Pausar reintentos automaticos para ese `correlation_id`.
- Ejecutar reconciliacion puntual.
- Ajustar estado final de forma idempotente.

## 5. Catalogo minimo de codigos operativos

- `OK`
- `NOT_ELIGIBLE`
- `EXPIRED`
- `LIMIT_REACHED`
- `ALREADY_REDEEMED`
- `UPSTREAM_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `UNKNOWN_ERROR`

## 6. Politica anti-fatiga

Alertar solo cuando hay accion concreta:

1. Error rate > 2% durante 15 min.
2. p95 > 2s en `benefit_redeem_attempt` durante 15 min.
3. 5 fallos consecutivos de webhook por integracion.
4. Duplicados idempotentes inesperados.

Todo lo demas va a dashboard, no a paging.

## 7. Evidencia minima obligatoria en ticket

1. `correlation_id`
2. `request_id`
3. `event_id` (si aplica)
4. `operation`
5. `status`
6. `code`
7. `latency_ms`
8. `tenant_id`

## 8. Postmortem corto (max 5 lineas)

1. Que paso.
2. Impacto real en usuario.
3. Causa raiz.
4. Correccion ejecutada.
5. Cambio minimo para prevenir repeticion.

## 9. Rutina operacional sugerida

- Diario (10 min): revisar 5xx, timeout, signature_failed, DLQ.
- Semanal (30 min): top rechazos + top latencias + reintentos.
- Mensual (45 min): eliminar alertas ruidosas y ajustar umbrales.

## 10. Referencias

- `docs/auditing-guide.md`
- `docs/examples/audit-record-template.json`
