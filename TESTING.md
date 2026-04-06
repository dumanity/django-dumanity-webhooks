# Testing Guide

Suite de tests para `django-dumanity-webhooks` v3.1+ (multi-app security).

## Quick Start

```bash
# Desde django-dumanity-webhooks/
python manage.py test
# O si no tienes manage.py, crear uno mínimo (ver abajo)
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

### `MultiAppScenarioTest`
Integración end-to-end: App A publica, App B recibe y procesa.

- `test_app_a_publishes_app_b_receives`: flujo completo A→B con firma y dispatch

## Setup

### Opción 1: Usar Django Project existente

Si tienes un proyecto Django que usa `django-dumanity-webhooks`:

```bash
python manage.py test webhooks
```

### Opción 2: Setup mínimo para desarrollo

Crear `manage.py` temporal en `django-dumanity-webhooks/`:

```python
#!/usr/bin/env python
import os
import sys
import django
from django.conf import settings
from django.core.management import execute_from_command_line

if not settings.configured:
    settings.configure(
        DEBUG=True,
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'rest_framework',
            'rest_framework_api_key',
            'webhooks.core',
            'webhooks.producer',
            'webhooks.receiver',
        ],
        SECRET_KEY='example-test-secret-key',
    )
    django.setup()

if __name__ == "__main__":
    execute_from_command_line(sys.argv)
```

Luego:

```bash
python manage.py test
```

## Running Specific Tests

```bash
# Solo tests de fail-closed
python manage.py test FailClosedResolutionTest

# Solo tests de idempotencia
python manage.py test IdempotencyScopedTest

# Con verbose output
python manage.py test -v 2

# Con coverage
coverage run --source='webhooks' manage.py test
coverage report
```

## Coverage Goals

- `webhooks.receiver.api`: 100% (crítico: resolución y rate limit)
- `webhooks.receiver.models`: 100% (contratos de datos)
- `webhooks.receiver.services`: 90%+ (pipeline complejo)
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
    strategy:
      matrix:
        python-version: ['3.12']
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e django-dumanity-webhooks/
      - run: pip install coverage
      - run: cd django-dumanity-webhooks && python manage.py test
      - run: coverage run --source='webhooks' manage.py test && coverage report
```

## Known Limitations

- Tests usan SQLite in-memory (no distribuido)
- Rate limit tests no son distribuidos (redis/cluster)
- Mocking de HTTP sender (no prueba network real)

Para tests de integración real, ver `example/` para manual testing entre apps.

## Troubleshooting

### Error: "ModuleNotFoundError: No module named 'webhooks'"

```bash
cd django-dumanity-webhooks
pip install -e .
```

### Error: "OperationalError: no such table"

Migraciones no aplicadas. Usar `-v 2` para debug:

```bash
python manage.py test -v 2
```

### Fixture Loading Issues

Tests crean datos en setUp(). Si necesitas fixtures, ver Django TestCase docs.
