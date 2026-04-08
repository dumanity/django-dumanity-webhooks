"""Verificaciones de sistema para django-dumanity-webhooks.

Se registran con el framework de checks de Django y se ejecutan al inicio
para detectar configuraciones incorrectas antes de producción.

Checks registrados
-------------------
``webhooks.W001`` timeout de un perfil no es un número positivo.
``webhooks.W002`` limit o window dentro de rate_limit no son enteros positivos.
``webhooks.E001`` WEBHOOK_PROFILES no es un diccionario.
``webhooks.E002`` Un perfil individual no es un diccionario.
``webhooks.E003`` rate_limit dentro de un perfil no es un diccionario.
``webhooks.I001`` Información: no se configuró WEBHOOK_PROFILES.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Info, Warning, register


@register("webhooks")
def check_webhook_profiles(app_configs, **kwargs) -> list:
    """Valida el formato de ``settings.WEBHOOK_PROFILES``."""
    messages: list = []
    profiles = getattr(settings, "WEBHOOK_PROFILES", None)

    if profiles is None:
        messages.append(
            Info(
                "WEBHOOK_PROFILES no está configurado en settings. "
                "Se usarán los valores por defecto (timeout=10 s, 100 req/min, sin firma).",
                hint=(
                    "Agrega WEBHOOK_PROFILES a tu settings.py para personalizar el comportamiento."
                ),
                id="webhooks.I001",
            )
        )
        return messages

    if not isinstance(profiles, dict):
        messages.append(
            Error(
                "WEBHOOK_PROFILES debe ser un diccionario de perfiles.",
                hint="Ejemplo: WEBHOOK_PROFILES = {'default': {'timeout': 10, ...}}",
                id="webhooks.E001",
            )
        )
        return messages

    for name, config in profiles.items():
        if not isinstance(config, dict):
            messages.append(
                Error(
                    f"WEBHOOK_PROFILES['{name}'] debe ser un diccionario.",
                    id="webhooks.E002",
                )
            )
            continue

        timeout = config.get("timeout")
        if timeout is not None and (
            not isinstance(timeout, (int, float)) or timeout <= 0
        ):
            messages.append(
                Warning(
                    f"WEBHOOK_PROFILES['{name}']['timeout'] debe ser un número positivo.",
                    hint="Valor por defecto cuando se omite: 10 segundos.",
                    id="webhooks.W001",
                )
            )

        rate_limit = config.get("rate_limit")
        if rate_limit is not None:
            if not isinstance(rate_limit, dict):
                messages.append(
                    Error(
                        f"WEBHOOK_PROFILES['{name}']['rate_limit'] debe ser un diccionario.",
                        hint="Ejemplo: {'limit': 100, 'window': 60}",
                        id="webhooks.E003",
                    )
                )
            else:
                for field in ("limit", "window"):
                    value = rate_limit.get(field)
                    if value is not None and (
                        not isinstance(value, int) or value <= 0
                    ):
                        messages.append(
                            Warning(
                                f"WEBHOOK_PROFILES['{name}']['rate_limit']['{field}'] "
                                "debe ser un entero positivo.",
                                hint="Valores por defecto: limit=100, window=60.",
                                id="webhooks.W002",
                            )
                        )

    return messages
