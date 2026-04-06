# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] – 2026-04-06

### Security

- **Replay seguro con trazabilidad** – Nuevo comando `webhooks_replay` con
  validaciones fail-safe: requiere `--reason`, soporta `--dry-run`, detecta
  colisiones de replay en outbox y registra metadatos de replay en `DeadLetter`
  (`replayed_at`, `replay_reason`, `replay_event_id`).

- **Contract-first validable** – Nuevo comando `webhooks_validate_contracts`
  para detectar contratos inválidos (tipo de evento, estructura de schema y
  consistencia básica de versionado) con mensajes accionables.

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
