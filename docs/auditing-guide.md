# Auditing Guide (Lean)

Guia practica para auditar intercambios SaaS <-> Socios sin aumentar demasiado costo, tiempo ni carga operativa.

## 1. Objetivo

Auditar lo minimo suficiente para responder rapidamente:

1. Que intento hacer el usuario o el sistema.
2. Que sistema tomo la decision.
3. Cual fue el resultado final observable.

Si un dato no ayuda a responder esas preguntas, no lo registres.

## 2. Regla de oro

- Una sola app como source-of-truth por entidad.
- REST = solicitud de accion (comando).
- Webhook = confirmacion de estado (evento).

## 3. Modelo minimo de auditoria

Registra un documento por operacion critica (provisionar perfil, email verificado, usar beneficio):

Plantilla reutilizable en el repo:

- `docs/examples/audit-record-template.json`

```json
{
  "timestamp_utc": "2026-04-04T18:45:27Z",
  "correlation_id": "cor_01JY2M1Q0Q4B7K8S6F1P9R3T5V",
  "request_id": "req_01JY2M1QCM5ZD54X3A2Y8NFV8E",
  "operation": "benefit_redeem_attempt",
  "actor_system": "saas",
  "subject_type": "socios_profile",
  "subject_id": "sp_01JY2M17N8K5Q3P7Y2R1T9V6W",
  "status": "approved",
  "code": "OK",
  "latency_ms": 184,
  "raw_ref": {
    "event_id": "evt_01JY2M1QW4W1A8R2D9N5K0H6M",
    "audit_log_id": 1245
  }
}
```

Campos obligatorios recomendados:

- `timestamp_utc`
- `correlation_id`
- `request_id`
- `operation`
- `actor_system`
- `subject_id`
- `status`
- `code`

Campos opcionales de bajo costo:

- `latency_ms`
- `http_status`
- `integration_id`
- `event_id`

## 4. Identificadores y correlacion

### 4.1 IDs recomendados

- `saas_customer_id`: id canonico del cliente en SaaS.
- `socios_profile_id`: id canonico del perfil en Socios (UUID o ULID opaco).
- `correlation_id`: id transversal de la transaccion (viaja en REST, webhook y logs).
- `request_id`: id unico por intento de comando (idempotencia).
- `event_id`: id unico por evento webhook.

### 4.2 Tabla de mapeo minima

Socios puede mantener:

- `(tenant_id, saas_customer_id) -> socios_profile_id`

SaaS puede mantener:

- `(tenant_id, socios_profile_id) -> saas_customer_id`

Esto reduce ambiguedades en soporte y evita buscar por email o datos sensibles.

## 5. Flujo auditado: provision de perfil

Escenario:

1. SaaS crea cliente.
2. SaaS llama REST de Socios para provisionar perfil.
3. Socios responde con `socios_profile_id`.
4. (Opcional recomendado) Socios emite webhook `socios.profile.provisioned.v1`.

### 5.1 Comando REST (SaaS -> Socios)

Request:

```json
{
  "request_id": "req_01JY2P5EJ0R9B1D7Q8W4K6M2T3",
  "correlation_id": "cor_01JY2P5E4G5A8F2D9N1R3M7V0Q",
  "tenant_id": "t_abc",
  "saas_customer_id": "cus_12345",
  "email": "user@example.com"
}
```

Response:

```json
{
  "status": "created",
  "socios_profile_id": "sp_01JY2P6A2X9W8N5M4Q7R1T3V6K",
  "tenant_id": "t_abc",
  "saas_customer_id": "cus_12345"
}
```

Registro de auditoria minimo en SaaS:

```json
{
  "operation": "socios_profile_provision",
  "request_id": "req_01JY2P5EJ0R9B1D7Q8W4K6M2T3",
  "correlation_id": "cor_01JY2P5E4G5A8F2D9N1R3M7V0Q",
  "status": "approved",
  "code": "PROFILE_CREATED",
  "subject_id": "sp_01JY2P6A2X9W8N5M4Q7R1T3V6K"
}
```

### 5.2 Evento webhook opcional (Socios -> SaaS)

Usalo cuando quieras robustez de reconciliacion y trazabilidad historica.

```json
{
  "id": "evt_01JY2P8V0H6B9C2N4Q5R7T1M3K",
  "type": "socios.profile.provisioned.v1",
  "data": {
    "tenant_id": "t_abc",
    "saas_customer_id": "cus_12345",
    "socios_profile_id": "sp_01JY2P6A2X9W8N5M4Q7R1T3V6K"
  },
  "meta": {
    "correlation_id": "cor_01JY2P5E4G5A8F2D9N1R3M7V0Q"
  }
}
```

## 6. Flujo auditado: uso de beneficio con respuesta UI inmediata

Escenario:

1. Usuario en Socios elige usar beneficio.
2. Socios solicita autorizacion a SaaS.
3. SaaS responde para que Socios cierre UX al instante.

### 6.1 Endpoint de comando

- `POST /internal/benefits/redeem-attempt`

Request:

```json
{
  "request_id": "req_01JY2R5AX6V1D7N9M4Q8T2K3P0",
  "correlation_id": "cor_01JY2R5A7E3F1H9K6N2Q4T8M0V",
  "tenant_id": "t_abc",
  "socios_profile_id": "sp_01JY2P6A2X9W8N5M4Q7R1T3V6K",
  "benefit_id": "ben_789",
  "occurred_at": "2026-04-04T19:00:10Z"
}
```

Response approved:

```json
{
  "request_id": "req_01JY2R5AX6V1D7N9M4Q8T2K3P0",
  "status": "approved",
  "code": "OK",
  "redemption_id": "red_01JY2R63N0W8A1Q4M9V2T5K7D3",
  "user_message": "Beneficio aplicado correctamente"
}
```

Response rejected:

```json
{
  "request_id": "req_01JY2R5AX6V1D7N9M4Q8T2K3P0",
  "status": "rejected",
  "code": "NOT_ELIGIBLE",
  "user_message": "Este beneficio no aplica para tu perfil"
}
```

Response transient error:

```json
{
  "request_id": "req_01JY2R5AX6V1D7N9M4Q8T2K3P0",
  "status": "error_transient",
  "code": "UPSTREAM_TIMEOUT",
  "user_message": "No pudimos confirmar el beneficio. Intenta nuevamente"
}
```

### 6.2 Catalogo de codigos para UI y soporte

Recomendado:

- `OK`
- `NOT_ELIGIBLE`
- `EXPIRED`
- `LIMIT_REACHED`
- `ALREADY_REDEEMED`
- `UPSTREAM_TIMEOUT`
- `UPSTREAM_UNAVAILABLE`
- `UNKNOWN_ERROR`

## 7. Runbook de incidente (10 minutos)

### Paso 1: buscar por correlation_id

Consultar `AuditLog`, `EventLog` y estado de negocio por `correlation_id`.

### Paso 2: validar comando

Confirma request/response del comando REST y su `request_id`.

### Paso 3: validar evento

Si existe webhook asociado, confirmar `event_id`, firma valida e idempotencia.

### Paso 4: validar estado final

Confirma que BD refleja la decision final (`approved` o `rejected`).

### Paso 5: clasificar causa

- `command_failed`
- `event_not_delivered`
- `state_mismatch`

### Paso 6: accion estandar

- `command_failed`: reintento manual con mismo `request_id`.
- `event_not_delivered`: replay webhook por `event_id`.
- `state_mismatch`: reconciliacion puntual por `correlation_id`.

## 8. Politica de alertas (anti-fatiga)

Activa solo alertas accionables:

1. Error rate > 2% por 15 minutos.
2. p95 de comando de beneficio > 2 segundos.
3. 5 o mas fallos consecutivos de webhook por integracion.
4. Duplicados de idempotencia inesperados.

Todo lo demas al dashboard sin paging.

## 9. Retencion de datos economica

- Logs tecnicos detallados: 14 dias.
- Resumen de auditoria: 90 dias.
- Metricas agregadas: 6-12 meses.

## 10. Checklist operativo minimo

### Diario (10 minutos)

- Revisar errores `5xx`, `timeout`, `signature_failed`.
- Revisar crecimiento inusual de `DeadLetter`.
- Validar estado de worker y cola de `OutgoingEvent`.

### Semanal (30 minutos)

- Top 5 codigos de rechazo.
- Top 3 integraciones con mayor latencia.
- Eventos con mas reintentos antes de entrega.

### Mensual (45 minutos)

- Eliminar alertas ruidosas sin accion.
- Ajustar umbrales con base real.
- Revisar campos de log no usados y simplificar.

## 11. Plantilla corta de postmortem

Usa esta plantilla para mantener aprendizaje sin desgaste:

1. Que paso.
2. Impacto en usuario.
3. Causa raiz.
4. Correccion aplicada.
5. Prevencion minima para no repetirlo.

Playbook corto para ejecutar este proceso bajo presion:

- `docs/incident-playbook.md`

## 12. Integracion con componentes del paquete

Relacion sugerida con modelos ya disponibles:

- `receiver.AuditLog`: almacenar resumen de request, response y resultado.
- `receiver.EventLog`: evidencia de procesamiento/idempotencia.
- `receiver.DeadLetter`: evidencia de fallos no recuperados.
- `producer.OutgoingEvent`: evidencia de entregas y reintentos.

No es obligatorio duplicar payload completo en todos lados. Prioriza referencias (`request_id`, `event_id`, `correlation_id`) para correlacion barata y diagnostico rapido.