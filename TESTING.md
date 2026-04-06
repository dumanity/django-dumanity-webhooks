# Testing Guide

Suite de tests para `django-dumanity-webhooks` 1.1.0.

## Quick Start

```bash
# Desde django-dumanity-webhooks/ (requiere uv)
uv run python -m pytest tests.py

# Sin uv (con dependencias ya instaladas)
python -m pytest tests.py
```

## Test Structure

Tests divididos por feature:

### `FailClosedResolutionTest`
Valida que sin API key válida, la resolución retorna `None` sin fallback implícito.

- `test_missing_api_key_header`: sin Authorization header → None
- `test_invalid_api_key`: API key inválida → None
- `test_valid_api_key`: API key válida → Integration instance

### `IdempotencyScopedTest`
Valida que idempotencia está scoped por `(integration, event_id)`.

- `test_same_event_id_different_integrations_allowed`: mismo UUID en dos apps → ambos accepted
- `test_duplicate_rejection_per_integration`: mismo UUID en misma app → IntegrityError

### `RateLimitPerIntegrationTest`
Valida que rate limit usa `integration_id` (UUID), no nombre (string).

- `test_rate_limit_by_integration_id`: clave de bucket es integration.id
- `test_rate_limit_isolated_per_integration`: límites no interfieren

### `ProducerOutboxTest`
Valida patrón Outbox en producer (publish_event → OutgoingEvent pending).

- `test_publish_event_creates_pending_outgoing_event`: crea con status=pending
- `test_multiple_endpoints_independent`: endpoints no interfieren

### `ProducerAdminActionTest`
Valida acciones de admin para gestión de endpoints del producer.

### `ProducerOutboxTransactionalTest`
Valida comportamiento transaccional del outbox (on_commit callbacks).

### `MetricsExportTest`
Valida exportación básica de métricas en formato Prometheus.

### `MultiAppScenarioTest`
Integración end-to-end: App A publica, App B recibe y procesa.

- `test_app_a_publishes_app_b_receives`: flujo completo A→B con firma y dispatch

### `E2EExampleAppsTest`
Tests de integración extremo a extremo con ejemplos de configuración.

### `DomainScaffoldCommandTest`
Valida el comando `start_webhook_domain` para scaffold de dominios.

### `BootstrapAndOpsCommandsTest`
Valida bootstrap automático, validación de contratos y operación (list/replay).

### `HeaderRedactionTest`
Valida que headers sensibles se redactan antes de persistir en AuditLog.

- `test_sensitive_headers_are_redacted`: headers sensibles → `[REDACTED]`
- `test_non_sensitive_headers_are_preserved`: headers no sensibles pasan intactos

### `MetricsSecurityTest`
Valida control de acceso al endpoint `/metrics`.

- `test_metrics_disabled_by_default`: sin config → 404
- `test_metrics_enabled_without_token`: habilitado sin token → 200 libre
- `test_metrics_enabled_with_valid_token`: habilitado con token correcto → 200
- `test_metrics_enabled_with_invalid_token`: token incorrecto → 403

## Setup

### Opción recomendada: pytest con uv

```bash
# Instalar dependencias de desarrollo
uv sync

# Ejecutar toda la suite
uv run python -m pytest tests.py

# Con verbose output
uv run python -m pytest tests.py -v

# Test específico por clase
uv run python -m pytest tests.py::FailClosedResolutionTest -v

# Test específico por nombre de método
uv run python -m pytest tests.py -k "test_rate_limit_by_integration_id"
```

### Opción alternativa: sin uv

```bash
pip install -e .
pip install pytest pytest-django
python -m pytest tests.py
```

## Running Specific Tests

```bash
# Solo tests de fail-closed
python -m pytest tests.py::FailClosedResolutionTest

# Solo tests de idempotencia
python -m pytest tests.py::IdempotencyScopedTest

# Solo tests de seguridad (headers y métricas)
python -m pytest tests.py::HeaderRedactionTest tests.py::MetricsSecurityTest

# Con verbose output
python -m pytest tests.py -v

# Con coverage
python -m pytest tests.py --cov=webhooks --cov-report=term-missing
```

## Coverage Goals

- `webhooks.receiver.api`: 100% (crítico: resolución y rate limit)
- `webhooks.receiver.models`: 100% (contratos de datos)
- `webhooks.core.security`: 100% (redacción de headers sensibles)
- `webhooks.producer.services`: 90%+
- `webhooks.producer.tasks`: 80%+ (depende de scheduler externo)

## CI/CD Integration

Para GitHub Actions:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        run: pip install uv
      - name: Install dependencies
        run: uv sync
      - name: Run tests
        run: uv run python -m pytest tests.py
```

## Known Limitations

- Tests usan SQLite in-memory (no distribuido)
- Rate limit tests no son distribuidos (redis/cluster)
- Mocking de HTTP sender (no prueba network real)

Para tests de integración real, ver `scripts/load_test_receiver.py`.

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'webhooks'"

```bash
pip install -e .
# o con uv:
uv sync
```

### Error: "OperationalError: no such table"

Migraciones no aplicadas. pytest-django las aplica automáticamente cuando
`DJANGO_SETTINGS_MODULE=tests_settings` está configurado en `pytest.ini`.

### Fixture Loading Issues

Tests crean datos en `setUp()`. Si necesitas fixtures, ver Django TestCase docs.
