# Release Guide

Guia operativa para distribuir `django-dumanity-webhooks` de forma privada primero.

## Changelog v0.3.0 (Initial Stable Lean Release)

### New Features
- Soporte real para múltiples apps (A, B, C) como producers+receivers sin colisión de event_id.
- Idempotencia garantizada por integración (permite reutilizar UUIDs entre productores).
- Rate limit determinístico y aislado por integración.
- Outbox transaccional y políticas por endpoint (`max_retries`, `request_timeout_seconds`).
- Endpoint `/metrics`, script de carga y runbook operativo lean.
- Prueba de conexión de endpoint (`probe_connection`, CLI y UI mínima en admin).

### Migrations Required
- `webhooks/producer/migrations/0001_initial.py`: modelos OutgoingEvent y WebhookEndpoint.
- `webhooks/receiver/migrations/0001_initial.py`: modelos con EventLog scoped.

### Testing Added
- `tests.py`: suite completa con tests de fail-closed, idempotencia scoped, rate limit per-integration, y multi-app integration.

### Documentation Updated
- `docs/developers-guide.md`: detalles de garantías v3.1, testing recomendado, roadmap.
- `docs/users-guide.md`: referencia multi-app, configuración de múltiples integraciones.
- `README.md`: actualizado con características de seguridad multi-app.
- Docstrings: documentación exhaustiva de todas las clases y funciones principales.

## 1. Pre-release checklist

- Tests y validaciones en verde.
- Version en `pyproject.toml` actualizada a 0.1.x.
- `README.md`, `developers-guide.md`, `users-guide.md` sincronizadas.
- Migraciones generadas y validadas con Django.

## 2. Build local

Desde `django-dumanity-webhooks/`:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

## 3. Distribucion privada manual

```bash
cp -R dist/ /ruta/interna/artefactos/
```

## 3.1 Consumo desde proyectos con uv

Agregar dependencia privada por tag:

```bash
uv add "django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.3.0"
```

o declararla en `pyproject.toml` del consumidor:

```toml
[project]
dependencies = [
	"django-dumanity-webhooks @ git+https://github.com/dumanity/django-dumanity-webhooks.git@v0.3.0",
]
```

Para CI con repo privado, configurar PAT o deploy key.

## 4. Distribucion automatica interna (GitHub Actions)

Hay un workflow para construir y adjuntar artefactos al crear un release/tag.

- El workflow construye el paquete desde `django-dumanity-webhooks/`.
- Los artefactos se adjuntan a la ejecucion de GitHub Actions para consumo interno.

## 5. Versionado recomendado

SemVer:

- MAJOR: cambios incompatibles de API/contratos.
- MINOR: nuevas capacidades compatibles.
- PATCH: fixes sin cambios de API.

Ejemplo:
- 0.1.x → 0.1.1 (hotfix)
- 0.1.x → 0.3.0 (nuevas features compatibles)
- 0.x → 1.0.0 (API/operación estable de largo plazo)

## 6. Post-release

- Verificar instalacion desde el artefacto privado en entorno limpio.
- Validar quickstart del README.
- Ejecutar tests con nuevos datos (migraciones).
- Crear issue con feedback de integracion temprana.

