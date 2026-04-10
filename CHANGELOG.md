# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] – 2026-04-10

### Added

- **`X-Trace-Id` en receiver** – `_extract_trace_context()` ahora lee el header
  `X-Trace-Id` del webhook entrante y lo propaga a `EventLog`, `AuditLog` y
  `DeadLetter` como campo `trace_id`.  Permite correlación E2E completa entre
  el sistema emisor (que inyecta el trace via OTel) y el registro de auditoría
  del receptor.

- **`trace_id` en señal `webhook_received`** – La señal `webhook_received` ahora
  incluye el kwarg `trace_id` (str | None), disponible para que las host apps
  logueen el trace sin acceder a los internos del paquete.

- **Campos `trace_id` en modelos** – Nuevas columnas opcionales `trace_id`
  (`CharField(max_length=128, null=True)`) en `EventLog`, `AuditLog` y
  `DeadLetter`.  Requiere ejecutar `python manage.py migrate` después de
  actualizar.

### Migration guide `2.0.0 → 2.1.0`

1. Actualiza la dependencia a `@v2.1.0`.
2. Ejecuta migraciones: `python manage.py migrate`.
3. No hay cambios breaking: nuevos campos son `null=True`, el comportamiento
   existente es idéntico si no se envía `X-Trace-Id`.
4. Opcional: conecta el nuevo kwarg `trace_id` en tu receiver de
   `webhook_received` para enriquecer tus logs de dominio.

```python
@receiver(webhook_received)
def on_received(sender, *, event_id, event_type, integration_name, trace_id, **kwargs):
    logger.info("webhook received", extra={"trace_id": trace_id, "event_type": event_type})
```

## [1.2.0] – 2026-04-08

### Added

- **Django Admin completo para el Receiver** – Nuevas clases `IntegrationAdmin`,
  `SecretAdmin`, `EventLogAdmin`, `DeadLetterAdmin` y `AuditLogAdmin` en
  `webhooks/receiver/admin.py`. Gestión completa de integraciones, secretos,
  dead letters y audit logs sin necesidad de CLI ni acceso a la consola Django.

- **Bootstrap desde Admin** – Botón "Bootstrap nueva integración" en el
  changelist de Integraciones lanza un formulario seguro que llama internamente
  a `bootstrap_receiver()`. La API Key se muestra una sola vez en el mensaje
  de confirmación.

- **Replay desde Admin** – `DeadLetterAdmin` incluye botón "Replay" por fila
  con formulario de endpoint + motivo + checkbox "Nuevo event ID", y una acción
  bulk "Replay seleccionados". Ambas rutas aplican las mismas guardas que el
  comando CLI (anti-doble-replay, bloqueo de colisión de outbox).

- **Rotación de secreto desde Admin** – Botón "Rotar secreto" por fila en
  `IntegrationAdmin`. Crea un secreto nuevo activo con expiración de 30 días;
  el anterior permanece activo para ventana de transición.

- **`bootstrap_receiver()` como API pública** – Nueva función en
  `webhooks.receiver.services` que encapsula la creación de Integration +
  APIKey + Secret en una sola llamada reutilizable. Usada por el management
  command `webhooks_bootstrap --receiver-only` y por el Admin.

- **Templates Django Admin** – Tres templates en
  `webhooks/receiver/templates/admin/dumanity_webhooks_receiver/`:
  `integration/change_list.html`, `integration/bootstrap.html`,
  `deadletter/replay.html`.

### Security

- **Redacción en Admin** – `SecretAdmin` nunca expone el valor completo de un
  secreto: muestra solo los primeros 8 caracteres seguidos de `[REDACTED]`.
  `EventLogAdmin` y `AuditLogAdmin` son solo-lectura sin permisos de add,
  change ni delete.

### Changed

- **`webhooks_bootstrap` refactorizado** – El management command
  `webhooks_bootstrap --receiver-only` delega ahora a `bootstrap_receiver()`
  en lugar de duplicar la lógica, garantizando paridad de comportamiento entre
  CLI y Admin.

- **Quickstart reescrito** – `docs/quickstart.md` reestructurado con roles
  explícitos 📥 Receiver / 📤 Producer, diagrama ASCII, Admin como opción
  primaria en cada paso, y tabla de troubleshooting.

- **Documentación actualizada** – `docs/hardening-guide.md`,
  `docs/developers-guide.md`, `docs/incident-playbook.md`,
  `docs/users-guide.md`, `README.md` y `webhooks/README.md` actualizados
  con flujos Admin, API de `bootstrap_receiver()`, e instrucciones de replay
  desde Admin.

### Tests

- 24 nuevos tests de unit/integración cubriendo:
  `BootstrapReceiverServiceTest`, `ReceiverIntegrationAdminTest`,
  `ReceiverSecretAdminTest`, `ReceiverDeadLetterAdminTest`,
  `ReceiverAdminReadonlyModelsTest`.
- 6 nuevos tests E2E con Django `TestClient` (superuser autenticado) que
  verifican el ciclo completo Admin → DB para bootstrap, replay y rotación
  de secretos.

## [1.1.0] – 2026-04-06

### Security

- **Replay seguro con trazabilidad** – Nuevo comando `webhooks_replay` con
  validaciones fail-safe: requiere `--reason`, soporta `--dry-run`, detecta
  colisiones de replay en outbox y registra metadatos de replay en `DeadLetter`
  (`replayed_at`, `replay_reason`, `replay_event_id`).

- **Contract-first validable** – Nuevo comando `webhooks_validate_contracts`
  para detectar contratos inválidos (tipo de evento, estructura de schema y
  consistencia básica de versionado) con mensajes accionables.

- **Replay aún más seguro** – `webhooks_replay` bloquea por defecto
  re-ejecuciones sobre `DeadLetter` ya replayado (requiere
  `--allow-previously-replayed` para override explícito) y evita colisiones de
  `event_id` contra cualquier estado existente en outbox.

### Added

- **Bootstrap automático** – Nuevo comando `webhooks_bootstrap` para setup
  inicial de receiver/producer con defaults seguros y salida orientada a vault.

- **Operación CLI/management** – Nuevo comando `webhooks_list_failures` para
  listar fallos operativos (`OutgoingEvent.failed`, `DeadLetter`) y guiar
  resolución/replay seguro.

- **Quickstart 10 minutos** – Nuevo `docs/quickstart.md` con flujo copy/paste
  end-to-end y troubleshooting accionable.

- **Hardening guide** – Nuevo `docs/hardening-guide.md` con checklist de
  producción alineado al comportamiento real del código.

### Changed

- **Scaffold de dominio mejorado** – `start_webhook_domain` ahora incluye
  mensajes de next steps más guiados y referencia directa a
  `webhooks_validate_contracts`.

- **DX de test-endpoint** – `webhooks-info test-endpoint` ahora imprime
  resumen didáctico (resultado, estado HTTP, latencia, y pasos de resolución).

- **Bootstrap idempotente para onboarding** – `webhooks_bootstrap` ahora puede
  reutilizar integraciones existentes sin fallar y actualizar endpoints
  existentes de forma explícita mediante `--update-endpoint`.

- **Compatibilidad de contratos reforzada** – `webhooks_validate_contracts`
  ahora advierte gaps de versionado y posibles breaking changes por remoción de
  campos `required` entre versiones.

- **Flujo DX local rápido** – Nuevo script `scripts/dev_check.sh` para ejecutar
  check de migraciones, validación de contratos y tests en un solo comando.

- **Versionado a v1.1.0** – Actualizado `pyproject.toml`, `webhooks.__version__`
  y referencias de documentación de instalación por tag.

## [1.0.1] – doc-code alignment

### Documentation

- **Version tags updated** – All installation examples in `README.md`,
  `docs/users-guide.md`, `docs/developers-guide.md`, and `docs/release.md`
  updated from `@v0.3.0` to `@v1.0.0` to match the current stable release.

- **`docs/release.md` overhauled** – Added v1.0.0 changelog section; removed
  outdated `0.1.x` version placeholder from pre-release checklist; kept v0.3.0
  history for reference.

- **`docs/developers-guide.md` – internal version references removed** –
  "Garantías implementadas (v3.1+)" and roadmap items "hecho en v3.1" now
  reference the public semver `v1.0.0`.

- **`TESTING.md` rewritten** – Corrected test runner from `python manage.py test`
  to `python -m pytest tests.py`; updated version label; added all 12 test
  classes (including `HeaderRedactionTest`, `MetricsSecurityTest`,
  `ProducerAdminActionTest`, `ProducerOutboxTransactionalTest`,
  `MetricsExportTest`, `E2EExampleAppsTest`, `DomainScaffoldCommandTest`);
  updated CI/CD YAML example.

- **`README.md` – Flujo Receiver step order corrected** – `AuditLog` is now
  listed at step 3 (before signature verification), matching the actual
  execution order in `WebhookService.process()`.

### Code (docstrings)

- **`WebhookService.process()` return value documented** – Added `"connection_ok"`
  as a valid return string for `webhook.connection_test.v1` events.

- **`WebhookView.post()` response codes updated** – Added `connection_ok` to
  the documented 200 response statuses.

## [1.0.0] – 2026-04-06

### Security

- **Header redaction in AuditLog**: Sensitive request headers (`Authorization`,
  `Webhook-Signature`, `X-Api-Key`, `Cookie`, `Set-Cookie`) are now redacted to
  `[REDACTED]` before being persisted in `AuditLog.request_headers`.  The
  redaction utility lives in `webhooks.core.security.redact_headers` and is
  applied deterministically on every incoming webhook request.

- **Hardened `/metrics` endpoint** – The endpoint is now **disabled by default**
  (`WEBHOOK_METRICS_ENABLED` defaults to `False`).  To enable it, set
  `WEBHOOK_METRICS_ENABLED = True` in Django settings.  An optional
  `WEBHOOK_METRICS_TOKEN` setting enforces bearer-token authentication
  (`Authorization: Bearer <token>`); requests without a valid token receive
  a `403` response.  See the README for the full configuration table.

- **Safe example placeholders** – All documentation, docstrings, and test
  fixtures that previously used prod-sounding secrets (`whsec_prod_123`,
  `test-secret-key`, `<receiver_api_key>`) have been replaced with clearly
  fictitious values (`whsec_example_123`, `example-test-secret-key`,
  `<your_receiver_api_key>`).  A "Safe Examples Policy" note was added to the
  README.

- **CodeQL SAST** – Added `.github/workflows/codeql.yml` to run GitHub CodeQL
  static analysis for Python on every push, pull request, and weekly schedule.

- **Dependabot** – Added `.github/dependabot.yml` to keep `pip` dependencies
  and GitHub Actions up to date automatically (weekly cadence).

### Changed

- `webhooks.receiver.api.MetricsView` now checks `WEBHOOK_METRICS_ENABLED` and
  `WEBHOOK_METRICS_TOKEN` settings before returning metrics data.  **Breaking
  for any deployment that relied on the unauthenticated open metrics endpoint**:
  set `WEBHOOK_METRICS_ENABLED = True` (and optionally `WEBHOOK_METRICS_TOKEN`)
  in your settings to restore access.

### Added

- `webhooks.core.security` module with `redact_headers()` utility function.
- 11 new security-focused tests in `tests.py` covering header redaction and
  metrics endpoint access control.

## [0.3.0] and earlier

See repository history.
